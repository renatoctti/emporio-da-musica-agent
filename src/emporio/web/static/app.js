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
  var GREETING = "Oi! Eu sou a Melô, assistente virtual da Empório da Música. Como posso ajudar?";
  var THEME_KEY = "emporio-theme";
  var DEV_KEY = "emporio-dev";
  var TABS = ["trace", "metrics", "tickets", "tests"];
  var THEMES = ["system", "light", "dark"];
  var THEME_ICON = { system: "#i-monitor", light: "#i-sun", dark: "#i-moon" };
  var THEME_NAME = { system: "do sistema", light: "claro", dark: "escuro" };
  var narrowQuery = window.matchMedia("(max-width: 900px)");
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var app = { info: null, turns: [], busy: false, theme: "system" };

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

  // ---- small formatters ----
  function clock(date) { return date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }); }
  function plural(n, one, many) { return n + " " + (n === 1 ? one : many); }
  function seconds(ms) { return (ms / 1000).toFixed(1).replace(".", ",") + " s"; }
  function money(usd) { return "US$ " + usd.toFixed(4).replace(".", ","); }

  function metricsText(m) {
    if (!m) return "";
    var parts = [seconds(m.latency_ms), plural(m.tool_calls, "consulta", "consultas")];
    var tokens = m.prompt_tokens + m.completion_tokens;
    if (tokens) parts.push(tokens.toLocaleString("pt-BR") + " tokens");
    if (m.cost_usd != null) parts.push(money(m.cost_usd));
    return parts.join(" · ");
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
  function avatar() { return h("div", { class: "avatar", "aria-hidden": "true", text: "M" }); }

  function userMessage(text, at) {
    var stack = h("div", { class: "stack" }, h("div", { class: "bubble", text: text }),
      at ? h("div", { class: "meta" }, h("span", { text: clock(at) })) : null);
    return h("article", { class: "msg msg-user" }, stack);
  }

  function kindsOf(trace) {
    var kinds = [];
    trace.forEach(function (item) { if (kinds.indexOf(item.kind) < 0) kinds.push(item.kind); });
    return kinds.length ? kinds : ["none"];
  }

  // The time is for everybody; the metrics line and the source tags are only for the developer mode.
  function botMessage(turn, index) {
    var meta = h("div", { class: "meta" },
      turn.at ? h("span", { text: clock(turn.at) }) : null,
      turn.metrics ? h("span", { class: "dev-line dev-only", text: metricsText(turn.metrics) }) : null);
    var tags = h("div", { class: "tags dev-only" });
    kindsOf(turn.trace).forEach(function (kind) {
      tags.append(h("button", { type: "button", class: "tag k-" + kind, title: "Ver em Decisões", onclick: function () { focusTurn(index); } }, KINDS[kind]));
    });
    var stack = h("div", { class: "stack" }, h("div", { class: "bubble" }, richText(turn.reply)), meta.childNodes.length ? meta : null, tags);
    return h("article", { class: "msg msg-bot", id: "turn-" + index }, avatar(), stack);
  }

  function greetingMessage() {
    return h("article", { class: "msg msg-bot", id: "greeting" }, avatar(),
      h("div", { class: "stack" }, h("div", { class: "bubble" }, h("div", { class: "prose" }, h("p", { text: GREETING })))));
  }

  // Quick replies under the greeting; they go away with the first customer message.
  function chipsNode() {
    var box = h("div", { class: "chips", id: "chips" });
    app.info.suggestions.forEach(function (s) {
      box.append(h("button", { type: "button", class: "chip-btn", onclick: function () { send(s.text); } }, s.label));
    });
    return box;
  }

  function typingNode() {
    return h("article", { class: "msg msg-bot", id: "typing" }, avatar(),
      h("div", { class: "stack" }, h("div", { class: "bubble", role: "status", "aria-label": "A Melô está digitando" },
        h("div", { class: "typing" }, h("span"), h("span"), h("span")))));
  }

  function scrollEnd() {
    var box = $("#scroll");
    box.scrollTo({ top: box.scrollHeight, behavior: reduceMotion ? "auto" : "smooth" });
  }

  function renderLog() {
    var log = $("#log");
    log.replaceChildren(greetingMessage());
    if (!app.turns.length && app.info) log.append(chipsNode());
    app.turns.forEach(function (turn, index) {
      log.append(userMessage(turn.user, turn.at), botMessage(turn, index));
    });
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
    var chips = $("#chips");
    if (chips) chips.remove();
    var log = $("#log");
    if (!retry) {
      log.append(userMessage(text, new Date()));
      $("#input").value = "";
      autosize();
    }
    var typing = typingNode();
    log.append(typing);
    scrollEnd();
    return api("/api/chat", { text: text }).then(function (result) {
      typing.remove();
      var turn = { user: text, reply: result.reply, trace: result.trace, metrics: result.metrics, at: new Date() };
      app.turns.push(turn);
      log.append(botMessage(turn, app.turns.length - 1));
      setVerified(result.verified);
      renderTrace();
      renderMetrics();
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

  // ---- developer panel: how the agent decided ----
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
  }

  function focusTurn(index) {
    setDev(true);
    setTab("trace");
    var node = $("#trace-" + index);
    if (!node) return;
    node.scrollIntoView({ block: "start", behavior: reduceMotion ? "auto" : "smooth" });
    node.classList.remove("flash");
    void node.offsetWidth;
    node.classList.add("flash");
  }

  // ---- developer panel: metrics ----
  function renderMetrics() {
    var rows = [];
    app.turns.forEach(function (turn, index) { if (turn.metrics) rows.push({ n: index + 1, m: turn.metrics }); });
    var summary = $("#metrics-summary");
    var list = $("#metrics-list");
    summary.replaceChildren();
    list.replaceChildren();
    $("#metrics-empty").hidden = rows.length > 0;
    if (!rows.length) return;

    var total = 0, slowest = 0, tools = 0, input = 0, output = 0, cost = 0, costKnown = true;
    rows.forEach(function (row) {
      total += row.m.latency_ms;
      slowest = Math.max(slowest, row.m.latency_ms);
      tools += row.m.tool_calls;
      input += row.m.prompt_tokens;
      output += row.m.completion_tokens;
      if (row.m.cost_usd == null) costKnown = false; else cost += row.m.cost_usd;
    });
    var facts = [
      ["Respostas medidas", String(rows.length)],
      ["Tempo médio", seconds(total / rows.length)],
      ["Mais lenta", seconds(slowest)],
      ["Consultas por resposta", (tools / rows.length).toFixed(1).replace(".", ",")],
      ["Tokens", input.toLocaleString("pt-BR") + " entrada · " + output.toLocaleString("pt-BR") + " saída"],
      ["Custo estimado", costKnown ? money(cost) : "preços não configurados (LLM_PRICE_IN_PER_M)"],
    ];
    facts.forEach(function (fact) { summary.append(h("dt", { text: fact[0] }), h("dd", { text: fact[1] })); });
    rows.forEach(function (row) {
      list.append(h("li", {}, h("strong", { text: "Resposta " + row.n }), h("span", { text: metricsText(row.m) })));
    });
  }

  function setTab(name) {
    TABS.forEach(function (tab) {
      var selected = tab === name;
      var button = $("#tab-" + tab);
      button.setAttribute("aria-selected", String(selected));
      button.tabIndex = selected ? 0 : -1;
      $("#pane-" + tab).hidden = !selected;
    });
  }

  // ---- developer panel: tickets and test data; and the store information for everybody ----
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
    });
  }

  function renderTesters(customers) {
    var list = $("#test-list");
    list.replaceChildren();
    customers.forEach(function (c) {
      list.append(h("li", { class: "tester" }, h("h3", { text: c.name }), h("p", { text: c.note }),
        h("p", {}, "Pedido ", h("code", { text: String(c.order_id) }), " · e-mail ", h("code", { text: c.email })),
        h("button", { type: "button", class: "btn", onclick: function () {
          if (narrowQuery.matches) setDev(false);
          var input = $("#input");
          input.value = "Meu pedido é o " + c.order_id + " e meu e-mail é " + c.email + ".";
          autosize();
          updateSend();
          input.focus();
        } }, "Usar na conversa")));
    });
  }

  // ---- page chrome ----
  function applyInfo(info) {
    app.info = info;
    var status = info.store.status_text;
    $("#head-status").textContent = "Loja " + status.charAt(0).toLowerCase() + status.slice(1);
    $("#day-text").textContent = info.reference.simulated ? info.reference.label + " · data simulada" : "Hoje";
    var legend = $("#legend");
    legend.replaceChildren();
    Object.keys(LEGEND).forEach(function (kind) { legend.append(h("li", { class: "k-" + kind, text: LEGEND[kind] })); });
    app.turns = info.turns;
    renderLog();
    renderTrace();
    renderMetrics();
    renderStore();
    renderTesters(info.test_customers);
    setVerified(info.verified);
    return refreshTickets();
  }

  function readSaved(key) {
    try { return localStorage.getItem(key); } catch (error) { return null; }
  }

  // Developer mode: a column next to the chat on a wide screen (the choice is remembered), a drawer
  // that always starts closed on a narrow one.
  function setDev(on, remember) {
    document.body.dataset.dev = on ? "on" : "off";
    $("#btn-dev").setAttribute("aria-pressed", String(on));
    $("#backdrop").hidden = !(on && narrowQuery.matches);
    if (remember !== false && !narrowQuery.matches) {
      try { localStorage.setItem(DEV_KEY, on ? "on" : "off"); } catch (error) { /* the choice then lasts until the page closes */ }
    }
    if (on && narrowQuery.matches) $("#tab-trace").focus();
  }

  function initDev() {
    var apply = function () { setDev(narrowQuery.matches ? false : readSaved(DEV_KEY) === "on", false); };
    apply();
    narrowQuery.addEventListener("change", apply);
  }

  function applyTheme(choice) {
    var root = document.documentElement;
    app.theme = choice;
    if (choice === "system") delete root.dataset.theme;
    else root.dataset.theme = choice;
    try {
      if (choice === "system") localStorage.removeItem(THEME_KEY);
      else localStorage.setItem(THEME_KEY, choice);
    } catch (error) { /* storage can be blocked; the choice then lasts until the page closes */ }
    $("#theme-icon").setAttribute("href", THEME_ICON[choice]);
    var label = "Tema " + THEME_NAME[choice] + ". Clique para trocar.";
    $("#btn-theme").setAttribute("aria-label", label);
    $("#btn-theme").setAttribute("title", label);
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
    $("#btn-info").addEventListener("click", function () { $("#info-dialog").showModal(); });
    $("#info-close").addEventListener("click", function () { $("#info-dialog").close(); });
    $("#btn-theme").addEventListener("click", function () { applyTheme(THEMES[(THEMES.indexOf(app.theme) + 1) % THEMES.length]); });
    $("#btn-dev").addEventListener("click", function () { setDev(document.body.dataset.dev !== "on"); });
    $("#btn-close").addEventListener("click", function () { setDev(false); $("#btn-dev").focus(); });
    $("#backdrop").addEventListener("click", function () { setDev(false); });
    document.addEventListener("keydown", function (event) { if (event.key === "Escape" && narrowQuery.matches && document.body.dataset.dev === "on") setDev(false); });
    TABS.forEach(function (tab) {
      $("#tab-" + tab).addEventListener("click", function () { setTab(tab); if (tab === "tickets") refreshTickets(); });
    });
    $(".tabs").addEventListener("keydown", function (event) {
      if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
      var current = TABS.filter(function (tab) { return $("#tab-" + tab).getAttribute("aria-selected") === "true"; })[0];
      var step = event.key === "ArrowRight" ? 1 : TABS.length - 1;
      var next = TABS[(TABS.indexOf(current) + step) % TABS.length];
      setTab(next);
      $("#tab-" + next).focus();
    });
  }

  function start() {
    var saved = readSaved(THEME_KEY);
    applyTheme(saved === "light" || saved === "dark" ? saved : "system");
    initDev();
    bind();
    updateSend();
    api("/api/state").then(applyInfo).catch(function (error) {
      $("#log").append(h("div", { class: "msg-error", role: "alert" }, h("span", { text: "Não consegui carregar a página: " + error.message })));
    });
  }

  start();
})();
