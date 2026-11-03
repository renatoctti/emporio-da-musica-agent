"use strict";
// Turns the trace of one answer into card models. Pure: no page, no network, no clock, so Node can
// test it (tests/test_cards.py). The numbers are the ones the tools returned; nothing is computed here.
(function (root) {
  var CATEGORY = { complaint: "Reclamação", return_request: "Devolução", defect: "Defeito", other: "Outro" };
  var STATUS = { pending: "Aguardando pagamento", confirmed: "Confirmado", shipped: "Enviado", delivered: "Entregue", cancelled: "Cancelado" };
  var STEPS = ["Confirmado", "Enviado", "Entregue"];
  var DONE_UP_TO = { pending: -1, confirmed: 0, shipped: 1, delivered: 2 };
  var MAX_LIST = 4;

  function brl(value) {
    var parts = Math.abs(value).toFixed(2).split(".");
    return "R$ " + parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ".") + "," + parts[1];
  }

  function stockText(availability, quantity) {
    if (availability === "in_stock") return quantity === 1 ? "Última unidade" : quantity + " em estoque";
    return { out_of_stock: "Esgotado", discontinued: "Descontinuado", coming_soon: "Em breve" }[availability] || "";
  }

  function percent(promotion) {
    if (!promotion || promotion.discount_percent == null) return null;
    return String(promotion.discount_percent).replace(".", ",") + "% off";
  }

  function day(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
    return m ? m[3] + "/" + m[2] + "/" + m[1] : null;
  }

  function dueText(iso) {
    var m = /^\d{4}-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso || "");
    return m ? m[2] + "/" + m[1] + " às " + m[3] + ":" + m[4] : null;
  }

  function productCard(r) {
    var price = r.price;
    if (!r.name || !price || price.price_brl == null) return null;
    var promoted = price.promotion && price.list_price_brl > price.price_brl;
    var options = (price.installments && price.installments.options) || [];
    var best = options.filter(function (o) { return o.n === price.installments.max; })[0] || options[options.length - 1];
    var pix = null;
    if (price.pix_price_brl != null) pix = price.pix_price_brl < price.price_brl ? "No PIX: " + brl(price.pix_price_brl) : "PIX: sem desconto extra";
    return {
      type: "product", id: r.product_id, name: r.name, brand: r.brand || "", category: r.category || "",
      list_price: promoted ? brl(price.list_price_brl) : null, price: brl(price.price_brl), discount: promoted ? percent(price.promotion) : null,
      installment: best && best.n > 1 ? "até " + best.n + "x de " + brl(best.installment_brl) + " sem juros" : null,
      pix: pix, stock: stockText(r.availability, r.stock_quantity),
    };
  }

  function listCard(r) {
    var all = r.results || [];
    if (!all.length) return null;
    var items = all.slice(0, MAX_LIST).map(function (p) {
      var promoted = p.promotion && p.list_price_brl > p.price_brl;
      return {
        id: p.product_id, name: p.name, category: p.category || "", price: brl(p.price_brl),
        list_price: promoted ? brl(p.list_price_brl) : null, discount: promoted ? percent(p.promotion) : null,
        stock: stockText(p.availability, p.stock_quantity),
      };
    });
    var total = r.total_matches == null ? all.length : r.total_matches;
    return { type: "products", items: items, more: Math.max(0, total - items.length) };
  }

  function paymentText(payment) {
    if (!payment) return "";
    if (payment.method === "pix") return "PIX";
    if (payment.method === "boleto") return "Boleto";
    if (payment.method === "debit") return "Cartão de débito";
    if (payment.method === "credit") return "Cartão de crédito " + (payment.installments > 1 ? "em " + payment.installments + "x" : "à vista");
    return "";
  }

  function orderSteps(status) {
    if (status === "cancelled") return [{ label: "Cancelado", state: "current" }];
    var done = DONE_UP_TO[status];
    return STEPS.map(function (label, i) {
      var state = i < done ? "done" : i === done ? "current" : "todo";
      if (status === "delivered") state = "done";
      return { label: label, state: state };
    });
  }

  function orderCard(r) {
    if (r.order_id == null || !STATUS[r.status]) return null;
    var open = r.status === "pending" || r.status === "confirmed" || r.status === "shipped";
    return {
      type: "order", order_id: r.order_id, status: r.status, status_text: STATUS[r.status], steps: orderSteps(r.status),
      date: day(r.order_date), total: r.total_brl == null ? null : brl(r.total_brl), payment: paymentText(r.payment),
      items: (r.items || []).map(function (i) { return i.quantity + "× " + i.name; }),
      tracking_code: r.tracking_code || null, estimate: day(r.estimated_delivery), late: r.estimated_delivery_passed === true && open,
    };
  }

  function ticketCard(r) {
    if (!r.protocol) return null;
    return { type: "ticket", protocol: r.protocol, category: CATEGORY[r.category] || r.category || "", due: dueText(r.due_at), status: "Aberto", duplicate: r.duplicate === true };
  }

  var BUILDERS = { get_product: productCard, search_products: listCard, get_order_status: orderCard, open_handoff: ticketCard };

  function cardsFromTrace(trace) {
    var cards = [];
    var sources = null;
    (trace || []).forEach(function (step) {
      var r = step.result;
      if (!step.ok || step.truncated || !r || typeof r !== "object") return;
      if (step.name === "search_policies" || step.name === "get_policy_sections") {
        (r.sections || []).forEach(function (s) {
          if (!sources) { sources = { type: "sources", items: [] }; cards.push(sources); }
          if (!sources.items.some(function (i) { return i.id === s.id; })) sources.items.push({ id: s.id, title: s.title });
        });
        return;
      }
      var build = BUILDERS[step.name];
      var card = build ? build(r) : null;
      if (card) cards.push(card);
    });
    // A list whose products all have their own card is only a repeat of those cards.
    var shown = cards.filter(function (c) { return c.type === "product"; }).map(function (c) { return c.id; });
    return cards.filter(function (c) {
      return c.type !== "products" || !c.items.every(function (p) { return shown.indexOf(p.id) >= 0; });
    });
  }

  function followUps(cards) {
    var ups = [];
    cards.forEach(function (card) {
      if (card.type === "product") ups.push("Quais as formas de pagamento?", "Tem alguma opção parecida?");
      if (card.type === "products") ups.push("Quais as formas de pagamento?");
      if (card.type === "order") ups.push("Como faço para devolver?");
      if (card.type === "order" && card.late) ups.push("Quero falar com um atendente");
    });
    return ups.filter(function (text, i) { return ups.indexOf(text) === i; }).slice(0, 3);
  }

  var api = { cardsFromTrace: cardsFromTrace, followUps: followUps, brl: brl };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.EmporioCards = api;
})(typeof window !== "undefined" ? window : this);
