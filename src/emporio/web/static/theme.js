// Runs before the first paint so a saved theme never flashes the wrong colors.
(function () {
  try {
    var saved = localStorage.getItem("emporio-theme");
    if (saved === "light" || saved === "dark") document.documentElement.dataset.theme = saved;
  } catch (error) {
    /* storage can be blocked; the page then follows the system theme */
  }
})();