// Runs before the first paint so a saved theme never flashes the wrong colors. It also marks the
// chat when the store page shows it inside its widget (/?embed=1).
(function () {
  if (/[?&]embed=1(&|$)/.test(location.search)) document.documentElement.dataset.embed = "on";
  try {
    var saved = localStorage.getItem("emporio-theme");
    if (saved === "light" || saved === "dark") document.documentElement.dataset.theme = saved;
  } catch (error) {
    /* storage can be blocked; the page then follows the system theme */
  }
})();