(function () {
  var root = document.documentElement;
  var stored = null;
  try {
    stored = localStorage.getItem("cbrowser.theme");
  } catch (error) {
    stored = null;
  }
  var preference =
    stored === "light" || stored === "dark" || stored === "system"
      ? stored
      : "dark";
  var systemPrefersDark = false;
  try {
    systemPrefersDark =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches;
  } catch (error) {
    systemPrefersDark = false;
  }
  var dark =
    preference === "dark" ||
    (preference === "system" && systemPrefersDark);
  root.classList.toggle("dark", dark);
  root.classList.toggle("light", !dark);
  root.style.colorScheme = dark ? "dark" : "light";
})();
