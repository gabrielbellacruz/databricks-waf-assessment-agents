/* WAF Assessment Tool — documentation site chrome.
 *
 * One script, loaded by every page. It renders the left sidebar navigation and
 * the right-hand "on this page" list from a single source of truth (PAGES),
 * marks the current page and section active, and wires the mobile drawer. This
 * keeps navigation identical across pages with no build step: add a page here
 * and every sidebar updates.
 *
 * Links in PAGES are written relative to the docs root; the root prefix for the
 * current page is derived from this script's own src, so the same list works
 * whether a page sits at docs/ or docs/guide/.
 */
(function () {
  "use strict";

  // Sidebar structure — the canonical page list for the whole site.
  var PAGES = [
    {
      group: "Overview",
      items: [{ href: "index.html", title: "Home" }],
    },
    {
      group: "Get started",
      items: [{ href: "guide/getting-started.html", title: "Getting started" }],
    },
    {
      group: "Concepts",
      items: [
        { href: "guide/framework.html", title: "The framework & scoring" },
        { href: "guide/agents.html", title: "How the agents work" },
        { href: "guide/system-tables.html", title: "System tables & signals" },
      ],
    },
    {
      group: "Help",
      items: [
        { href: "guide/faq.html", title: "FAQ" },
        { href: "guide/troubleshooting.html", title: "Troubleshooting" },
      ],
    },
  ];

  var REPO = "https://github.com/databricks-solutions/waf-assessment-tool";

  // Root prefix ("" at docs/, "../" under docs/guide/), from this script's src.
  var self = document.currentScript;
  var src = self ? self.getAttribute("src") || "" : "";
  var ROOT = src.replace(/assets\/nav\.js.*$/, "");

  // Which PAGES item is the current page? Match by the file the URL ends with.
  var path = location.pathname.replace(/\/+$/, "/"); // keep a trailing slash if present
  function isCurrent(href) {
    var file = href.split("/").pop(); // e.g. "agents.html" or "index.html"
    if (href === "index.html") {
      return (
        path === "" ||
        /\/$/.test(path) ||
        path.endsWith("/index.html") ||
        path.endsWith("index.html")
      );
    }
    return path.endsWith("/" + file) || path.endsWith(file);
  }

  // ---- Left sidebar -------------------------------------------------------
  var sidebar = document.getElementById("sidebar");
  if (sidebar) {
    var html =
      '<a class="sb-brand" href="' +
      ROOT +
      'index.html"><img class="mark" src="' +
      ROOT +
      'logo-waf.svg" alt="" /><span>WAF Assessment Tool<small>Documentation</small></span></a>' +
      '<div class="sb-links"><a href="' +
      ROOT +
      'index.html">Home</a><a href="' +
      REPO +
      '">GitHub</a></div><nav class="sb-nav">';

    PAGES.forEach(function (grp) {
      html += '<div class="sb-group"><h4>' + grp.group + "</h4>";
      grp.items.forEach(function (it) {
        var active = isCurrent(it.href) ? ' class="active"' : "";
        html += '<a href="' + ROOT + it.href + '"' + active + ">" + it.title + "</a>";
      });
      html += "</div>";
    });
    html += "</nav>";
    sidebar.innerHTML = html;
  }

  // ---- Right-hand "on this page" from the article's <h2 id> ---------------
  var tocNav = document.getElementById("toc-right-nav");
  var tocAside = tocNav ? tocNav.closest(".toc-right") : null;
  var headings = Array.prototype.slice.call(
    document.querySelectorAll(".doc h2[id]")
  );
  if (tocNav) {
    if (headings.length) {
      tocNav.innerHTML = headings
        .map(function (h) {
          return (
            '<a href="#' +
            h.id +
            '" data-spy>' +
            (h.getAttribute("data-toc") || h.textContent) +
            "</a>"
          );
        })
        .join("");
    } else if (tocAside) {
      tocAside.hidden = true;
    }
  }

  // ---- Scroll-spy: highlight the section currently in view ----------------
  var spyLinks = Array.prototype.slice.call(document.querySelectorAll("a[data-spy]"));
  if (spyLinks.length && headings.length && "IntersectionObserver" in window) {
    var byId = {};
    spyLinks.forEach(function (a) {
      var id = a.getAttribute("href").slice(1);
      (byId[id] = byId[id] || []).push(a);
    });
    var ids = headings.map(function (h) { return h.id; });
    var visible = {};

    function setActive(id) {
      spyLinks.forEach(function (a) { a.classList.remove("active"); });
      (byId[id] || []).forEach(function (a) { a.classList.add("active"); });
    }

    var obs = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (e) {
          visible[e.target.id] = e.isIntersecting ? e.intersectionRatio : 0;
        });
        var best = null, bestRatio = -1;
        ids.forEach(function (id) {
          if ((visible[id] || 0) > bestRatio) { bestRatio = visible[id] || 0; best = id; }
        });
        if (best && bestRatio > 0) setActive(best);
      },
      { rootMargin: "-15% 0px -70% 0px", threshold: [0, 0.25, 0.5, 1] }
    );
    headings.forEach(function (h) { obs.observe(h); });
  }

  // ---- Close the mobile drawer after tapping a link -----------------------
  var toggle = document.getElementById("nav-toggle");
  if (toggle) {
    document.querySelectorAll(".sidebar a").forEach(function (a) {
      a.addEventListener("click", function () { toggle.checked = false; });
    });
  }
})();
