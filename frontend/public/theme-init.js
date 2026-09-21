// Applies the saved or system colour theme before the first paint, so dark-mode
// users never see a white flash. A file (not an inline script) so the strict CSP
// from guide 12.5 needs no exception. Keep in sync with src/lib/theme.ts.
(function () {
  var theme = "system";
  try {
    var saved = localStorage.getItem("winnow-theme");
    if (saved === "light" || saved === "dark" || saved === "system") theme = saved;
  } catch (e) {
    /* storage unavailable (private mode): follow the system */
  }
  var dark =
    theme === "dark" ||
    (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  var root = document.documentElement;
  root.classList.toggle("dark", dark);
  root.style.colorScheme = dark ? "dark" : "light";
})();
