"use strict";
(function () {
  var KINDS = { data: "Dados", policy: "Manual", identity: "Identidade", rules: "Regras", handoff: "Atendimento", none: "Sem consulta" };
  var LEGEND = {
    data: "Dados · catálogo e pedidos",
    policy: "Manual · políticas da loja",
    identity: "Identidade · confirma o cliente",
    rules: "Regras · devolução e garantia",
    handoff: "Atendimento · equipe humana",
  };
  var THEME_KEY = "emporio-theme";
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var app = { info: null, turns: [], busy: false };

  function $(selector, root) { return (root || document).querySelector(selector); }

  // Builds an element. Text always goes in as text, never as markup.
  function h(tag, attrs) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (key) {
      var value = attrs[key];
      if (value === false || value == null) return;
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else if (key.indexOf("on") === 0) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value === true ? "" : value);
    });
    for (var i = 2; i < arguments.length; i++) {
      var kids = [].concat(arguments[i]);
      kids.forEach(function (kid) { if (kid != null && kid !== false) node.append(kid); });
    }
    return node;
  }

  function api(path, body) {
    var options = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
    return fetch(path, options).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok) throw new Error(data.error || "Algo deu errado. Tente de novo.");
        return data;
      });
    });
  }

  // ---- reply text: **bold**, `code`, bullet and numbered lists, paragraphs ----
  function inline(text, parent) {
    text.split(/(\*\*[^*]+\*\*|`[^`]+`)/).forEach(function (part) {
      if (!part) return;
      if (part.indexOf("**") === 0) parent.append(h("strong", { text: part.slice(2, -2) }));
      else if (part.charAt(0) === "`") parent.append(h("code", { text: part.slice(1, -1) }));
      else parent.append(part);
    });
  }

  function richText(text) {
    var box = h("div", { class: "prose" });
    var item = /^\s*([-*•]|\d+[.)])\s+/;
    var paragraph = null;
    var list = null;
    text.trim().split("\n").forEach(function (line) {
      if (!line.trim()) { paragraph = null; list = null; return; }
      if (item.test(line)) {
        var ordered = /^\s*\d+[.)]/.test(line);
        if (!list || list.ordered !== ordered) {
          list = { ordered: ordered, node: h(ordered ? "ol" : "ul") };
          box.append(list.node);
        }
        var li = h("li");
        inline(line.replace(item, ""), li);
        list.node.append(li);
        paragraph = null;
      } else {
        if (!paragraph) { paragraph = h("p"); box.append(paragraph); } else paragraph.append(h("br"));
        inline(line, paragraph);
        list = null;
      }
    });
    return box;
  }

  // ---- conversation ----
  function avatar() { return h("img", { class: "avatar", src: "/static/favicon.svg", alt: "", width: "28", height: "28" }); }

  function userMessage(text) {
    return h("article", { class: "msg msg-user" }, h("div", { class: "bubble", text: text }));
  }

  function kindsOf(trace) {
    var kinds = [];
    trace.forEach(function (item) { if (kinds.indexOf(item.kind) < 0) kinds.push(item.kind); });
    return kinds.length ? kinds : ["none"];
  }

  function botMessage(turn, index) {
    var tags = h("div", { class: "tags" });
    kindsOf(turn.trace).forEach(function (kind) {
      tags.append(h("button", { type: "button", class: "tag k-" + kind, title: "Ver no painel", onclick: function () { focusTurn(index); } }, KINDS[kind]));
    });
    return h("article", { class: "msg msg-bot", id: "turn-" + index }, avatar(), h("div", { class: "who", text: "Melô" }), richText(turn.reply), tags);
  }

  function typingNode() {
    return h("div", { class: "msg msg-bot", id: "typing" }, avatar(), h("div", { class: "who", text: "Melô" }),
      h("div", { class: "typing", role: "status", "aria-label": "A Melô está escrevendo" }, h("span"), h("span"), h("span")));
  }

  function scrollEnd() {
    var box = $("#scroll");
    box.scrollTo({ top: box.scrollHeight, behavior: reduceMotion ? "auto" : "smooth" });
  }

  function renderLog() {
    var log = $("#log");
    log.replaceChildren();
    app.turns.forEach(function (turn, index) {
      log.append(userMessage(turn.user), botMessage(turn, index));
    });
    $("#hero").hidden = app.turns.length > 0;
  }

  function showError(message, text) {
    var box = h("div", { class: "msg-error", role: "alert", id: "chat-error" }, h("span", { text: message }),
      h("button", { type: "button", class: "btn", onclick: function () { box.remove(); send(text, true); } }, "Tentar de novo"));
    $("#log").append(box);
  }

  function send(text, retry) {
    text = text.trim();
    if (app.busy || !text) return Promise.resolve();
    app.busy = true;
    updateSend();
    $("#hero").hidden = true;
    var log = $("#log");
    if (!retry) {
      log.append(userMessage(text));
      $("#input").value = "";
      autosize();
    }
    var typing = typingNode();
    log.append(typing);
    scrollEnd();
    return api("/api/chat", { text: text }).then(function (result) {
      typing.remove();
      var turn = { user: text, reply: result.reply, trace: result.trace };
      app.turns.push(turn);
      log.append(botMessage(turn, app.turns.length - 1));
      setVerified(result.verified);
      renderTrace();
      refreshTickets();
    }).catch(function (error) {
      typing.remove();
      showError(error.message, text);
    }).then(function () {
      app.busy = false;
      updateSend();
      scrollEnd();
      $("#input").focus();
    });
  }

  function updateSend() {
    $("#send").disabled = app.busy || !$("#input").value.trim();
    $("#log").setAttribute("aria-busy", String(app.busy));
  }

  function autosize() {
    var input = $("#input");
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 152) + "px";
  }

  function setVerified(verified) {
    $("#verified").hidden = !verified;
    if (verified) $("#verified-text").textContent = "Identidade confirmada: " + verified.first_name;
  }

  // ---- side panel: how the agent decided ----
  function detailText(item) {
    var text = JSON.stringify({ chamada: item.name, argumentos: item.arguments, resultado: item.result }, null, 2);
    return item.truncated ? text + "\n\n(resultado cortado)" : text;
  }

  function step(item) {
    return h("li", {}, h("details", { class: "step k-" + item.kind, "data-ok": String(item.ok) },
      h("summary", {}, h("span", { class: "step-kind", text: KINDS[item.kind] }), h("span", { class: "step-title", text: item.title }),
        h("span", { class: "step-summary", text: item.summary }), h("span", { class: "step-more", text: "Ver argumentos e resultado" })),
      h("pre", { text: detailText(item) })));
  }

  function traceTurn(turn, index) {
    var steps = h("ol", { class: "steps" });
    if (!turn.trace.length) {
      steps.append(h("li", {}, h("div", { class: "step k-none", "data-ok": "true" },
        h("p", { class: "step-note", text: "Respondeu sem consultar nada: endereço, horários e regras de conduta já fazem parte das instruções da Melô." }))));
    }
    turn.trace.forEach(function (item) { steps.append(step(item)); });
    return h("li", { class: "turn", id: "trace-" + index },
      h("span", { class: "turn-no", text: "Resposta " + (index + 1) }), h("p", { class: "turn-q", text: turn.user }), steps);
  }

  function renderTrace() {
    var list = $("#trace-list");
    list.replaceChildren();
    app.turns.forEach(function (turn, index) { list.append(traceTurn(turn, index)); });
    $("#trace-empty").hidden = app.turns.length > 0;
    var total = app.turns.reduce(function (sum, turn) { return sum + turn.trace.length; }, 0);
    $("#trace-count").hidden = total === 0;
    $("#trace-count").textContent = String(total);
  }

  function focusTurn(index) {
    openPanel(true);
    setTab("trace");
    var node = $("#trace-" + index);
    if (!node) return;
    node.scrollIntoView({ block: "start", behavior: reduceMotion ? "auto" : "smooth" });
    node.classList.remove("flash");
    void node.offsetWidth;
    node.classList.add("flash");
  }

  function setTab(name) {
    ["trace", "store"].forEach(function (tab) {
      var selected = tab === name;
      var button = $("#tab-" + tab);
      button.setAttribute("aria-selected", String(selected));
      button.tabIndex = selected ? 0 : -1;
      $("#pane-" + tab).hidden = !selected;
    });
  }

  // ---- side panel: the store ----
  function formatDue(iso) {
    var d = new Date(iso);
    var two = function (n) { return String(n).padStart(2, "0"); };
    return two(d.getDate()) + "/" + two(d.getMonth() + 1) + " às " + two(d.getHours()) + ":" + two(d.getMinutes());
  }

  function renderStore() {
    var store = app.info.store;
    var facts = h("dl", { class: "facts" });
    store.hours.forEach(function (row) { facts.append(h("dt", { text: row.label }), h("dd", { text: row.value })); });
    facts.append(h("dt", { text: "Endereço" }), h("dd", { text: store.address }), h("dt", { text: "WhatsApp" }), h("dd", { text: store.phone }), h("dt", { text: "E-mail" }), h("dd", { text: store.email }));
    var chip = h("span", { class: "chip", "data-state": store.open ? "open" : "closed" }, h("span", { class: "dot", "aria-hidden": "true" }), h("span", { text: store.status_text }));
    $("#store-card").replaceChildren(h("h2", { text: store.name }), chip, facts);
  }

  function refreshTickets() {
    return api("/api/handoffs").then(function (data) {
      var list = $("#tickets");
      list.replaceChildren();
      data.tickets.forEach(function (ticket) {
        var meta = "Resposta até " + formatDue(ticket.due_at) + (ticket.order_id ? " · pedido " + ticket.order_id : "");
        list.append(h("li", { class: "ticket" },
          h("div", { class: "ticket-top" }, h("span", { class: "ticket-protocol", text: ticket.protocol }), h("span", { class: "tag k-handoff", text: ticket.category_label })),
          h("p", { class: "ticket-summary", text: ticket.summary }), h("p", { class: "ticket-meta", text: meta })));
      });
      $("#tickets-empty").hidden = data.tickets.length > 0;
      $("#ticket-count").hidden = data.tickets.length === 0;
      $("#ticket-count").textContent = String(data.tickets.length);
    });
  }

  // ---- page chrome ----
  function applyInfo(info) {
    app.info = info;
    var chip = $("#store-chip");
    chip.dataset.state = info.store.open ? "open" : "closed";
    $("#store-text").textContent = info.store.status_text;
    $("#ref-chip").hidden = !info.reference.simulated;
    $("#ref-text").textContent = "Simulando " + info.reference.label;
    var list = $("#suggestions");
    list.replaceChildren();
    info.suggestions.forEach(function (s) {
      list.append(h("li", {}, h("button", { type: "button", class: "suggest k-" + s.kind, onclick: function () { send(s.text); } },
        h("span", { class: "suggest-topic", text: s.topic }), h("span", { class: "suggest-label", text: s.label }), h("span", { class: "suggest-text", text: s.text }))));
    });
    var legend = $("#legend");
    legend.replaceChildren();
    Object.keys(LEGEND).forEach(function (kind) { legend.append(h("li", { class: "k-" + kind, text: LEGEND[kind] })); });
    app.turns = info.turns;
    renderLog();
    renderTrace();
    renderStore();
    renderTesters(info.test_customers);
    setVerified(info.verified);
    return refreshTickets();
  }

  function renderTesters(customers) {
    var list = $("#test-list");
    list.replaceChildren();
    customers.forEach(function (c) {
      list.append(h("li", { class: "tester" }, h("h3", { text: c.name }), h("p", { text: c.note }),
        h("p", {}, "Pedido ", h("code", { text: String(c.order_id) }), " · e-mail ", h("code", { text: c.email })),
        h("button", { type: "button", class: "btn", onclick: function () {
          $("#test-dialog").close();
          var input = $("#input");
          input.value = "Meu pedido é o " + c.order_id + " e meu e-mail é " + c.email + ".";
          autosize();
          updateSend();
          input.focus();
        } }, "Usar na conversa")));
    });
  }

  function openPanel(open) {
    document.body.dataset.panel = open ? "open" : "closed";
    $("#btn-panel").setAttribute("aria-expanded", String(open));
    $("#backdrop").hidden = !open;
    if (open && window.matchMedia("(max-width: 900px)").matches) $("#tab-trace").focus();
  }

  function applyTheme(choice) {
    var root = document.documentElement;
    if (choice === "system") delete root.dataset.theme;
    else root.dataset.theme = choice;
    try {
      if (choice === "system") localStorage.removeItem(THEME_KEY);
      else localStorage.setItem(THEME_KEY, choice);
    } catch (error) { /* storage can be blocked; the choice then lasts until the page closes */ }
    document.querySelectorAll("[data-theme-choice]").forEach(function (button) {
      button.setAttribute("aria-pressed", String(button.dataset.themeChoice === choice));
    });
  }

  function newConversation() {
    if (app.busy) return Promise.resolve();
    return api("/api/reset", {}).then(function () { return api("/api/state"); }).then(applyInfo).then(function () { $("#input").focus(); });
  }

  function bind() {
    var input = $("#input");
    input.addEventListener("input", function () { autosize(); updateSend(); });
    input.addEventListener("keydown", function (event) {
      if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); $("#form").requestSubmit(); }
    });
    $("#form").addEventListener("submit", function (event) { event.preventDefault(); send(input.value); });
    $("#btn-new").addEventListener("click", newConversation);
    $("#btn-test").addEventListener("click", function () { $("#test-dialog").showModal(); });
    $("#test-close").addEventListener("click", function () { $("#test-dialog").close(); });
    $("#btn-panel").addEventListener("click", function () { openPanel(document.body.dataset.panel !== "open"); });
    $("#btn-close").addEventListener("click", function () { openPanel(false); $("#btn-panel").focus(); });
    $("#backdrop").addEventListener("click", function () { openPanel(false); });
    document.addEventListener("keydown", function (event) { if (event.key === "Escape" && document.body.dataset.panel === "open") openPanel(false); });
    $("#tab-trace").addEventListener("click", function () { setTab("trace"); });
    $("#tab-store").addEventListener("click", function () { setTab("store"); refreshTickets(); });
    $(".tabs").addEventListener("keydown", function (event) {
      if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
        var next = $("#tab-trace").getAttribute("aria-selected") === "true" ? "store" : "trace";
        setTab(next);
        $("#tab-" + next).focus();
      }
    });
    document.querySelectorAll("[data-theme-choice]").forEach(function (button) {
      button.addEventListener("click", function () { applyTheme(button.dataset.themeChoice); });
    });
  }

  function start() {
    var saved = null;
    try { saved = localStorage.getItem(THEME_KEY); } catch (error) { saved = null; }
    applyTheme(saved === "light" || saved === "dark" ? saved : "system");
    document.body.dataset.panel = "closed";
    bind();
    updateSend();
    api("/api/state").then(applyInfo).catch(function (error) {
      $("#log").append(h("div", { class: "msg-error", role: "alert" }, h("span", { text: "Não consegui carregar a página: " + error.message })));
    });
  }

  start();
})();