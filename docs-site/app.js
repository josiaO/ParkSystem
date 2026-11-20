(function () {
  "use strict";

  var THEME_KEY = "zirp-docs-theme";
  var REPO = "josiaO/ParkSystem";

  function getTheme() {
    var saved = localStorage.getItem(THEME_KEY);
    if (saved) return saved;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function setTheme(theme) {
    localStorage.setItem(THEME_KEY, theme);
    document.documentElement.setAttribute("data-theme", theme);
    var btn = document.getElementById("theme-toggle");
    if (btn) btn.textContent = theme === "light" ? "☀" : "☾";
  }

  // Highlight the sidebar link for the section on screen.
  function initScrollSpy() {
    var links = Array.prototype.slice.call(document.querySelectorAll("nav.sidebar a[href^='#']"));
    var sections = links
      .map(function (a) { return document.querySelector(a.getAttribute("href")); })
      .filter(Boolean);
    function onScroll() {
      var current = sections[0];
      for (var i = 0; i < sections.length; i++) {
        if (sections[i].getBoundingClientRect().top <= 120) current = sections[i];
      }
      links.forEach(function (a) {
        a.classList.toggle("active", current && a.getAttribute("href") === "#" + current.id);
      });
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  function formatSize(bytes) {
    return Math.round(bytes / (1024 * 1024)) + " MB";
  }

  // Show the newest published release (pre-releases included). Without
  // internet the card keeps the version written into the page.
  function loadLatestRelease() {
    if (!window.fetch) return;
    fetch("https://api.github.com/repos/" + REPO + "/releases?per_page=10")
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (releases) {
        var rel = (releases || []).filter(function (x) { return !x.draft; })[0];
        if (!rel) return;
        var exe = (rel.assets || []).filter(function (a) { return /\.exe$/i.test(a.name); })[0];
        var sha = (rel.assets || []).filter(function (a) { return /\.sha256$/i.test(a.name); })[0];
        if (!exe) return;
        document.getElementById("rel-title").textContent = exe.name;
        document.getElementById("rel-meta").textContent =
          (rel.prerelease ? "Release candidate" : "Stable release") + " · " + rel.tag_name +
          " · Windows 10/11 64-bit · " + formatSize(exe.size) +
          " · published " + new Date(rel.published_at).toLocaleDateString();
        document.getElementById("rel-download").href = exe.browser_download_url;
        document.getElementById("rel-notes").href = rel.html_url;
        var shaEl = document.getElementById("rel-sha");
        var match = (rel.body || "").match(/[0-9a-f]{64}/i);
        if (match) {
          shaEl.textContent = "SHA-256 " + match[0].toLowerCase();
        } else if (sha) {
          shaEl.innerHTML = 'SHA-256 in <a href="' + sha.browser_download_url + '">' + sha.name + "</a>";
        }
      })
      .catch(function () { /* offline: keep the static details */ });
  }

  document.addEventListener("DOMContentLoaded", function () {
    setTheme(getTheme());
    var themeBtn = document.getElementById("theme-toggle");
    if (themeBtn) {
      themeBtn.addEventListener("click", function () {
        setTheme(getTheme() === "dark" ? "light" : "dark");
      });
    }
    initScrollSpy();
    loadLatestRelease();
  });
})();
