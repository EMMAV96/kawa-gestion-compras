/* Presentation only. No network calls, form submissions or business changes. */
(function () {
  "use strict";
  var root = document.documentElement;
  root.classList.add("js");
  function read(key) { try { return localStorage.getItem(key); } catch (_) { return null; } }
  function save(key, value) { try { localStorage.setItem(key, value); } catch (_) {} }
  var explicitTheme = read("kawa.theme");
  var systemTheme = window.matchMedia("(prefers-color-scheme: dark)");
  function setTheme(theme) {
    root.dataset.theme = theme;
    document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
      var dark = theme === "dark";
      button.setAttribute("aria-pressed", String(dark));
      button.setAttribute("aria-label", dark ? "Activar modo claro" : "Activar modo oscuro");
      button.title = dark ? "Activar modo claro" : "Activar modo oscuro";
    });
  }
  setTheme(root.dataset.theme || (systemTheme.matches ? "dark" : "light"));
  document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
    button.addEventListener("click", function () {
      explicitTheme = root.dataset.theme === "dark" ? "light" : "dark";
      save("kawa.theme", explicitTheme);
      setTheme(explicitTheme);
    });
  });
  systemTheme.addEventListener("change", function (event) {
    if (explicitTheme !== "light" && explicitTheme !== "dark") setTheme(event.matches ? "dark" : "light");
  });
  window.addEventListener("storage", function (event) {
    if (event.key === "kawa.theme") {
      explicitTheme = event.newValue;
      setTheme(explicitTheme === "light" || explicitTheme === "dark" ? explicitTheme : (systemTheme.matches ? "dark" : "light"));
    }
  });

  var sidebar = document.getElementById("app-sidebar");
  var main = document.getElementById("app-main");
  var toggle = document.getElementById("menu-toggle");
  var overlay = document.querySelector(".sidebar-backdrop");
  var mobile = window.matchMedia("(max-width: 1023px)");
  var open = false;
  function syncShell() {
    if (!sidebar || !toggle) return;
    var narrow = mobile.matches;
    sidebar.inert = narrow && !open;
    main.inert = narrow && open;
    root.classList.toggle("menu-open", narrow && open);
    overlay.hidden = !(narrow && open);
    toggle.setAttribute("aria-expanded", String(narrow ? open : root.dataset.sidebar !== "collapsed"));
    toggle.setAttribute("aria-label", narrow ? (open ? "Cerrar menú" : "Abrir menú") : (root.dataset.sidebar === "collapsed" ? "Expandir menú lateral" : "Contraer menú lateral"));
    if (narrow && open) {
      sidebar.setAttribute("role", "dialog");
      sidebar.setAttribute("aria-modal", "true");
    } else {
      sidebar.removeAttribute("role");
      sidebar.removeAttribute("aria-modal");
    }
  }
  function closeMenu(restoreFocus) {
    open = false;
    syncShell();
    if (restoreFocus && toggle) toggle.focus();
  }
  if (sidebar && toggle) {
    syncShell();
    toggle.addEventListener("click", function () {
      if (mobile.matches) {
        open = !open;
        syncShell();
        if (open) sidebar.querySelector("[data-menu-close]").focus();
      } else {
        root.dataset.sidebar = root.dataset.sidebar === "collapsed" ? "expanded" : "collapsed";
        save("kawa.sidebar.collapsed", root.dataset.sidebar === "collapsed" ? "1" : "0");
        syncShell();
      }
    });
    document.querySelectorAll("[data-menu-close]").forEach(function (button) {
      button.addEventListener("click", function () { closeMenu(true); });
    });
    mobile.addEventListener("change", function () { closeMenu(false); });
    document.addEventListener("keydown", function (event) {
      if (!open || !mobile.matches) return;
      if (event.key === "Escape") { event.preventDefault(); closeMenu(true); }
      if (event.key === "Tab") {
        var nodes = Array.from(sidebar.querySelectorAll("a[href],button:not([disabled]),summary,input:not([type=hidden])")).filter(function (node) { return node.getClientRects().length > 0; });
        var first = nodes[0], last = nodes[nodes.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    });
    sidebar.querySelectorAll("[data-nav-link]").forEach(function (link) {
      link.addEventListener("click", function () { if (mobile.matches) closeMenu(false); });
    });
    var groups = {};
    try { groups = JSON.parse(read("kawa.nav.groups") || "{}"); } catch (_) {}
    if (!groups || typeof groups !== "object" || Array.isArray(groups)) groups = {};
    sidebar.querySelectorAll("[data-nav-group]").forEach(function (group) {
      if (group.hasAttribute("data-active-group")) group.open = true;
      else if (Object.prototype.hasOwnProperty.call(groups, group.id)) group.open = !!groups[group.id];
      group.addEventListener("toggle", function () { groups[group.id] = group.open; save("kawa.nav.groups", JSON.stringify(groups)); });
      group.querySelector("summary").addEventListener("click", function (event) {
        if (!mobile.matches && root.dataset.sidebar === "collapsed") {
          event.preventDefault(); root.dataset.sidebar = "expanded";
          save("kawa.sidebar.collapsed", "0"); group.open = true; syncShell();
        }
      });
    });
    function selectAnchor() {
      var received = window.location.hash === "#cotizaciones-recibidas";
      var links = Array.from(sidebar.querySelectorAll("a[data-nav-link]"));
      var anchored = links.find(function (link) { return link.dataset.anchor === "cotizaciones-recibidas"; });
      if (!anchored || new URL(anchored.href).pathname !== window.location.pathname) return;
      links.filter(function (link) { return new URL(link.href).pathname === window.location.pathname; }).forEach(function (link) {
        var active = received ? link === anchored : !link.dataset.anchor;
        link.classList.toggle("is-active", active);
        if (active) link.setAttribute("aria-current", "page"); else link.removeAttribute("aria-current");
      });
    }
    selectAnchor(); window.addEventListener("hashchange", selectAnchor);
  }
  // Overflow tables can be focused and scrolled with the keyboard.
  document.querySelectorAll(".scroll").forEach(function (region) {
    if (!region.querySelector("table")) return;
    region.tabIndex = 0;
    region.setAttribute("role", "region");
    var heading = region.closest("section") && region.closest("section").querySelector("h2,h3");
    region.setAttribute("aria-label", heading ? heading.textContent.trim() : "Tabla de datos, desplazamiento horizontal disponible");
  });
  document.querySelectorAll("input[required]:not([type=hidden]),select[required],textarea[required]").forEach(function (control) {
    var label = control.labels && control.labels[0];
    if (label && !label.querySelector(".required-mark") && control.type !== "checkbox") {
      var mark = document.createElement("span"); mark.className = "required-mark"; mark.textContent = " *"; mark.setAttribute("aria-hidden", "true"); label.appendChild(mark);
    }
  });
  document.querySelectorAll(".tabla input:not([type=hidden]),.tabla select").forEach(function (control) {
    if (control.hasAttribute("aria-label") || (control.labels && control.labels.length)) return;
    var cell = control.closest("td"), table = control.closest("table");
    if (cell && table && table.tHead) {
      var header = table.tHead.rows[0].cells[cell.cellIndex];
      if (header) control.setAttribute("aria-label", header.textContent.trim());
    }
  });
  document.querySelectorAll("ul.errorlist").forEach(function (list) { list.setAttribute("role", "alert"); });
}());
