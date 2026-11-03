"use strict";
// The launcher of the widget on the demonstration store page: opens and closes the panel with the chat.
(function () {
  var launcher = document.getElementById("launcher");
  var panel = document.getElementById("panel");

  function toggle(open) {
    panel.hidden = !open;
    launcher.setAttribute("aria-expanded", String(open));
    launcher.setAttribute("aria-label", open ? "Fechar o chat com a Melô" : "Abrir o chat com a Melô");
  }

  launcher.addEventListener("click", function () { toggle(panel.hidden); });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !panel.hidden) { toggle(false); launcher.focus(); }
  });
})();
