(function () {
  "use strict";

  const STORAGE_THEME = "smartpark-docs-theme";

  function getTheme() {
    return localStorage.getItem(STORAGE_THEME) || "dark";
  }

  function setTheme(theme) {
    localStorage.setItem(STORAGE_THEME, theme);
    document.documentElement.setAttribute("data-theme", theme);
    var btn = document.getElementById("theme-toggle");
    if (btn) btn.textContent = theme === "light" ? "☀" : "☾";
  }

  function initScrollSpy() {
    var links = document.querySelectorAll("nav.sidebar a[href^='#']");
    var sections = Array.prototype.slice.call(links)
      .map(function (a) { return document.querySelector(a.getAttribute("href")); })
      .filter(Boolean);
    function onScroll() {
      var current = sections[0];
      for (var i = 0; i < sections.length; i++) {
        if (sections[i].getBoundingClientRect().top <= 100) current = sections[i];
      }
      links.forEach(function (a) {
        a.classList.toggle("active", a.getAttribute("href") === "#" + current.id);
      });
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  function initReferenceLinks() {
    document.querySelectorAll("[data-doc]").forEach(function (link) {
      var name = link.getAttribute("data-doc");
      // In the source tree the markdown lives in ../docs. The packaged site
      // places the same references beside index.html.
      link.href = window.location.pathname.indexOf("/docs-site/") !== -1
        ? "../docs/" + name
        : name;
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    setTheme(getTheme());

    var themeBtn = document.getElementById("theme-toggle");
    if (themeBtn) {
      themeBtn.addEventListener("click", function () {
        setTheme(getTheme() === "dark" ? "light" : "dark");
      });
    }

    initReferenceLinks();
    initScrollSpy();
  });
})();
