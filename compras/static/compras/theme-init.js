/* Synchronous, before CSS: resolve theme without a light/dark flash. */
(function () {
  "use strict";
  var root = document.documentElement;
  root.classList.add("js");
  var theme = null;
  try { theme = localStorage.getItem("kawa.theme"); } catch (_) {}
  if (theme !== "light" && theme !== "dark") {
    theme = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  root.dataset.theme = theme;
  try { root.dataset.sidebar = localStorage.getItem("kawa.sidebar.collapsed") === "1" ? "collapsed" : "expanded"; } catch (_) {}
}());
