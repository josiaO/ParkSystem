(function () {
  "use strict";

  const STORAGE_LANG = "smartpark-docs-lang";
  const STORAGE_THEME = "smartpark-docs-theme";

  function getLang() {
    return localStorage.getItem(STORAGE_LANG) || "en";
  }

  function getTheme() {
    return localStorage.getItem(STORAGE_THEME) || "dark";
  }

  function setLang(lang) {
    localStorage.setItem(STORAGE_LANG, lang);
    document.documentElement.lang = lang === "sw" ? "sw" : "en";
    applyTranslations(lang);
    document.querySelectorAll("[data-lang-btn]").forEach(function (btn) {
      btn.classList.toggle("active", btn.getAttribute("data-lang-btn") === lang);
    });
    updateSvgLabels(lang);
  }

  function setTheme(theme) {
    localStorage.setItem(STORAGE_THEME, theme);
    document.documentElement.setAttribute("data-theme", theme);
    var btn = document.getElementById("theme-toggle");
    if (btn) btn.textContent = theme === "light" ? "☀" : "☾";
    if (btn) btn.title = theme === "light"
      ? (I18N[getLang()].theme_light || "Light")
      : (I18N[getLang()].theme_dark || "Dark");
  }

  function t(lang, key) {
    var pack = I18N[lang] || I18N.en;
    return pack[key] != null ? pack[key] : (I18N.en[key] || key);
  }

  function applyTranslations(lang) {
    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      var key = el.getAttribute("data-i18n");
      el.textContent = t(lang, key);
    });
    document.querySelectorAll("[data-i18n-html]").forEach(function (el) {
      var key = el.getAttribute("data-i18n-html");
      el.innerHTML = t(lang, key);
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach(function (el) {
      el.placeholder = t(lang, el.getAttribute("data-i18n-placeholder"));
    });
    document.title = t(lang, "meta_title");
    var meta = document.querySelector('meta[name="description"]');
    if (meta) meta.setAttribute("content", t(lang, "meta_desc"));
  }

  function updateSvgLabels(lang) {
    document.querySelectorAll("[data-i18n-svg]").forEach(function (el) {
      el.textContent = t(lang, el.getAttribute("data-i18n-svg"));
    });
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

  document.addEventListener("DOMContentLoaded", function () {
    setTheme(getTheme());
    setLang(getLang());

    document.querySelectorAll("[data-lang-btn]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        setLang(btn.getAttribute("data-lang-btn"));
      });
    });

    var themeBtn = document.getElementById("theme-toggle");
    if (themeBtn) {
      themeBtn.addEventListener("click", function () {
        setTheme(getTheme() === "dark" ? "light" : "dark");
      });
    }

    initScrollSpy();
  });
})();
