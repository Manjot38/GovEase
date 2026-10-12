/* ==========================================================================
   GovEase.docs - Smart Document & Form Tool (Member 3)

   Lives in the GovEase.docs namespace reserved in script.js, so it can
   fail without affecting the news module or the assistant. Include it
   after script.js so GovEase.config.API_BASE is available.

     documents.html  the full tool (five tabs)
     index.html      quick links rendered into #documents-panel

   All text from the server or from file names is inserted with
   textContent, never innerHTML.
   ========================================================================== */
(function () {
  "use strict";

  var GovEase = (window.GovEase = window.GovEase || {});
  var API_BASE = (GovEase.config && GovEase.config.API_BASE) || "/api";
  var API = API_BASE + "/documents";
  var MAX_FILE_BYTES = 10 * 1024 * 1024;
  var objectUrls = [];

  // ------------------------------------------------------------------
  // Small helpers
  // ------------------------------------------------------------------
  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (key) {
      if (key === "text") node.textContent = attrs[key];
      else if (key === "className") node.className = attrs[key];
      else node.setAttribute(key, attrs[key]);
    });
    (children || []).forEach(function (child) {
      if (child) node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
    });
    return node;
  }

  function formatSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / 1024 / 1024).toFixed(2) + " MB";
  }

  function isPdf(file) {
    return file.type === "application/pdf" || /\.pdf$/i.test(file.name);
  }

  function parseJsonHeader(response, name, fallback) {
    try {
      var raw = response.headers.get(name);
      return raw ? JSON.parse(raw) : fallback;
    } catch (e) {
      return fallback;
    }
  }

  function filenameFrom(response, fallback) {
    var header = response.headers.get("Content-Disposition") || "";
    var star = /filename\*=UTF-8''([^;]+)/i.exec(header);
    if (star) return decodeURIComponent(star[1]);
    var plain = /filename="?([^";]+)"?/i.exec(header);
    return plain ? plain[1] : fallback;
  }

  function trackUrl(url) {
    objectUrls.push(url);
    return url;
  }

  function releaseUrls() {
    objectUrls.forEach(URL.revokeObjectURL);
    objectUrls = [];
  }

  // ------------------------------------------------------------------
  // API client
  // ------------------------------------------------------------------
  function request(path, formData) {
    return fetch(API + path, { method: "POST", body: formData }).then(
      function (response) {
        if (!response.ok) {
          return response
            .json()
            .catch(function () { return {}; })
            .then(function (body) {
              throw new Error(body.message || "The file could not be processed (HTTP " + response.status + ").");
            });
        }
        var type = response.headers.get("Content-Type") || "";
        if (type.indexOf("application/json") === 0) return response.json();
        return response.blob().then(function (blob) {
          return {
            blob: blob,
            filename: filenameFrom(response, "govease_document"),
            meta: parseJsonHeader(response, "X-GovEase-Meta", {}),
            warnings: parseJsonHeader(response, "X-GovEase-Warnings", []),
          };
        });
      },
      function () {
        throw new Error("Could not connect to GovEase. Please check your connection and try again.");
      }
    );
  }

  // ------------------------------------------------------------------
  // Tabs (WAI-ARIA tabs pattern, arrow-key navigation)
  // ------------------------------------------------------------------
  function initTabs() {
    var tabs = Array.prototype.slice.call(document.querySelectorAll(".docs-tabs [role=tab]"));
    function select(tab, focus) {
      tabs.forEach(function (t) {
        var active = t === tab;
        t.setAttribute("aria-selected", active ? "true" : "false");
        t.tabIndex = active ? 0 : -1;
        document.getElementById(t.getAttribute("aria-controls")).hidden = !active;
      });
      if (focus) tab.focus();
      if (tab.scrollIntoView) tab.scrollIntoView({ block: "nearest", inline: "nearest" });
      try { history.replaceState(null, "", "#" + tab.dataset.tool); } catch (e) { /* ignore */ }
    }
    tabs.forEach(function (tab, i) {
      tab.addEventListener("click", function () { select(tab, false); });
      tab.addEventListener("keydown", function (event) {
        var next = null;
        if (event.key === "ArrowDown" || event.key === "ArrowRight") next = tabs[(i + 1) % tabs.length];
        if (event.key === "ArrowUp" || event.key === "ArrowLeft") next = tabs[(i - 1 + tabs.length) % tabs.length];
        if (event.key === "Home") next = tabs[0];
        if (event.key === "End") next = tabs[tabs.length - 1];
        if (next) { event.preventDefault(); select(next, true); }
      });
    });
    var fromHash = tabs.filter(function (t) { return "#" + t.dataset.tool === location.hash; })[0];
    if (fromHash) select(fromHash, false);
  }

  // ------------------------------------------------------------------
  // Drop zones and file summaries
  // ------------------------------------------------------------------
  function initDropZone(zone) {
    var input = zone.querySelector("input[type=file]");
    ["dragenter", "dragover"].forEach(function (name) {
      zone.addEventListener(name, function (event) {
        event.preventDefault();
        zone.classList.add("is-dragging");
      });
    });
    ["dragleave", "drop"].forEach(function (name) {
      zone.addEventListener(name, function () { zone.classList.remove("is-dragging"); });
    });
    zone.addEventListener("drop", function (event) {
      event.preventDefault();
      var dropped = event.dataTransfer.files;
      if (!dropped.length) return;
      var transfer = new DataTransfer();
      var count = input.multiple ? dropped.length : 1;
      for (var i = 0; i < count; i++) transfer.items.add(dropped[i]);
      input.files = transfer.files;
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
  }

  function describeFiles(panel, files) {
    var box = panel.querySelector(".docs-file-info");
    if (!box) return;
    box.textContent = "";
    Array.prototype.forEach.call(files, function (file) {
      var chip = el("div", { className: "docs-file-chip" }, [
        el("strong", { text: file.name }),
        el("span", { text: formatSize(file.size) }),
      ]);
      if (file.size > MAX_FILE_BYTES) {
        chip.classList.add("is-bad");
        chip.appendChild(el("span", { text: "Larger than 10 MB" }));
      }
      if (/^image\//.test(file.type)) {
        var url = URL.createObjectURL(file);
        var img = new Image();
        img.onload = function () {
          chip.appendChild(el("span", { text: img.naturalWidth + " × " + img.naturalHeight + " px" }));
          URL.revokeObjectURL(url);
        };
        img.onerror = function () { URL.revokeObjectURL(url); };
        img.src = url;
      }
      box.appendChild(chip);
    });
  }

  // ------------------------------------------------------------------
  // Result rendering
  // ------------------------------------------------------------------
  function showError(panel, message) {
    var box = panel.querySelector(".docs-result");
    box.textContent = "";
    box.appendChild(el("div", { className: "docs-alert docs-alert-error", role: "alert" }, [
      el("strong", { text: "Could not process the file. " }), message,
    ]));
  }

  function renderChecks(checks, title) {
    var list = el("ul", { className: "docs-checks" });
    checks.forEach(function (check) {
      list.appendChild(el("li", { className: check.ok ? "is-ok" : "is-bad" }, [
        el("span", { className: "docs-check-icon", "aria-hidden": "true", text: check.ok ? "✓" : "✕" }),
        el("span", { className: "docs-visually-hidden", text: check.ok ? "Meets requirement: " : "Does not meet requirement: " }),
        el("strong", { text: check.label }),
        el("span", { text: check.actual + " (" + check.expected + ")" }),
      ]));
    });
    return el("div", { className: "docs-checks-wrap" }, [el("h3", { text: title }), list]);
  }

  function showResult(panel, result) {
    releaseUrls();
    var box = panel.querySelector(".docs-result");
    box.textContent = "";
    var meta = result.meta || {};
    var url = trackUrl(URL.createObjectURL(result.blob));

    var stats = el("dl", { className: "docs-stats" });
    function stat(label, value) {
      if (value === undefined || value === null || value === "") return;
      stats.appendChild(el("div", {}, [el("dt", { text: label }), el("dd", { text: String(value) })]));
    }
    stat("Original", meta.original_kb !== undefined ? meta.original_kb + " KB" : "");
    stat("Result", formatSize(result.blob.size));
    if (meta.saved_percent > 0) stat("Saved", meta.saved_percent + "%");
    if (meta.width) stat("Dimensions", meta.width + " × " + meta.height + " px");
    if (meta.pages) stat("Pages", meta.pages);
    if (meta.quality) stat("Quality", meta.quality);

    var card = el("div", { className: "docs-result-card" });
    card.appendChild(el("h3", { text: "Your file is ready" }));
    if (/^image\//.test(result.blob.type)) {
      card.appendChild(el("div", { className: "docs-preview" }, [
        el("img", { src: url, alt: "Preview of the processed image" }),
      ]));
    }
    card.appendChild(stats);
    if (meta.checks && meta.checks.length) card.appendChild(renderChecks(meta.checks, "Requirement check"));
    (result.warnings || []).forEach(function (warning) {
      card.appendChild(el("div", { className: "docs-alert docs-alert-warn" }, [warning]));
    });
    card.appendChild(el("a", {
      className: "btn docs-download", href: url, download: result.filename,
    }, ["Download " + result.filename]));
    box.appendChild(card);
    box.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function run(panel, path, formData) {
    var button = panel.querySelector("button[type=submit]");
    var label = button.textContent;
    button.disabled = true;
    button.textContent = "Processing…";
    panel.querySelector(".docs-result").textContent = "";
    return request(path, formData)
      .then(function (result) { showResult(panel, result); })
      .catch(function (err) { showError(panel, err.message); })
      .then(function () {
        button.disabled = false;
        button.textContent = label;
      });
  }

  function requireFiles(panel, input, min) {
    var files = input.files;
    if (!files || files.length < (min || 1)) {
      showError(panel, min > 1 ? "Choose at least " + min + " files." : "Choose a file first.");
      return null;
    }
    for (var i = 0; i < files.length; i++) {
      if (files[i].size > MAX_FILE_BYTES) {
        showError(panel, "“" + files[i].name + "” is larger than 10 MB.");
        return null;
      }
    }
    return files;
  }

  // ------------------------------------------------------------------
  // Tool: Ready for application (presets)
  // ------------------------------------------------------------------
  function initPrepare(panel) {
    var form = panel.querySelector("form");
    var select = panel.querySelector("#preset-select");
    var desc = panel.querySelector("#preset-desc");
    var input = form.querySelector("input[type=file]");
    var presets = {};

    fetch(API + "/presets")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        select.textContent = "";
        select.appendChild(el("option", { value: "", text: "Select what the form asks for…" }));
        var groups = { image: el("optgroup", { label: "Photos and images" }), pdf: el("optgroup", { label: "PDF documents" }) };
        data.presets.forEach(function (p) {
          presets[p.id] = p;
          groups[p.kind].appendChild(el("option", { value: p.id, text: p.label }));
        });
        select.appendChild(groups.image);
        select.appendChild(groups.pdf);
      })
      .catch(function () {
        select.textContent = "";
        select.appendChild(el("option", { value: "", text: "Presets unavailable — is the server running?" }));
      });

    function inspectOriginal() {
      var preset = select.value;
      var file = input.files && input.files[0];
      var box = panel.querySelector(".docs-file-info");
      describeFiles(panel, input.files || []);
      if (!preset || !file || file.size > MAX_FILE_BYTES) return;
      var fd = new FormData();
      fd.append("file", file);
      fd.append("preset", preset);
      request("/inspect", fd)
        .then(function (info) {
          if (info.checks) box.appendChild(renderChecks(info.checks, "Your original file"));
        })
        .catch(function () { /* the submit step reports errors */ });
    }

    select.addEventListener("change", function () {
      var p = presets[select.value];
      desc.textContent = p ? p.description : "";
      inspectOriginal();
    });
    input.addEventListener("change", inspectOriginal);

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      if (!select.value) return showError(panel, "Choose the document type the form asks for.");
      var files = requireFiles(panel, input);
      if (!files) return;
      var fd = new FormData();
      fd.append("file", files[0]);
      fd.append("preset", select.value);
      run(panel, "/prepare", fd);
    });
  }

  // ------------------------------------------------------------------
  // Tool: Resize
  // ------------------------------------------------------------------
  function initResize(panel) {
    var form = panel.querySelector("form");
    var input = form.querySelector("input[type=file]");
    var unit = form.querySelector("[data-unit]");
    var note = form.querySelector("[data-cm-note]");
    input.addEventListener("change", function () { describeFiles(panel, input.files); });
    unit.addEventListener("change", function () { note.hidden = unit.value === "px"; });

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var files = requireFiles(panel, input);
      if (!files) return;
      var dpi = parseFloat(form.dpi.value) || 200;
      var factor = { px: 1, cm: dpi / 2.54, mm: dpi / 25.4 }[unit.value];
      var w = parseFloat(form.w.value);
      var h = parseFloat(form.h.value);
      if (!(w > 0) && !(h > 0)) return showError(panel, "Enter a width, a height, or both.");
      var fd = new FormData();
      fd.append("file", files[0]);
      if (w > 0) fd.append("width", Math.round(w * factor));
      if (h > 0) fd.append("height", Math.round(h * factor));
      fd.append("mode", form.mode.value);
      fd.append("format", form.format.value);
      fd.append("dpi", Math.round(dpi));
      run(panel, "/image/resize", fd);
    });
  }

  // ------------------------------------------------------------------
  // Tool: Compress (image or PDF, chosen from the file)
  // ------------------------------------------------------------------
  function initCompress(panel) {
    var form = panel.querySelector("form");
    var input = form.querySelector("input[type=file]");
    var imageOnly = form.querySelectorAll("[data-image-only]");
    input.addEventListener("change", function () {
      describeFiles(panel, input.files);
      var pdf = input.files[0] && isPdf(input.files[0]);
      Array.prototype.forEach.call(imageOnly, function (n) { n.hidden = !!pdf; });
    });
    Array.prototype.forEach.call(form.querySelectorAll("[data-kb]"), function (chip) {
      chip.addEventListener("click", function () { form.max_kb.value = chip.dataset.kb; });
    });

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var files = requireFiles(panel, input);
      if (!files) return;
      var maxKb = parseFloat(form.max_kb.value);
      if (!(maxKb > 0)) return showError(panel, "Enter the maximum size in KB.");
      var fd = new FormData();
      fd.append("file", files[0]);
      fd.append("max_kb", maxKb);
      if (isPdf(files[0])) return run(panel, "/pdf/compress", fd);
      if (form.min_kb.value) fd.append("min_kb", form.min_kb.value);
      fd.append("format", form.format.value);
      run(panel, "/image/compress", fd);
    });
  }

  // ------------------------------------------------------------------
  // Tool: Convert
  // ------------------------------------------------------------------
  function initConvert(panel) {
    var form = panel.querySelector("form");
    var input = form.querySelector("input[type=file]");
    var hint = form.querySelector("[data-convert-hint]");
    var webp = form.querySelector("option[value=webp]");

    function mode() { return form.conversion.value; }
    function sync() {
      var m = mode();
      Array.prototype.forEach.call(form.querySelectorAll("[data-show]"), function (n) {
        if (n.tagName !== "OPTION") n.hidden = n.dataset.show.split(" ").indexOf(m) === -1;
      });
      webp.disabled = m !== "image";
      if (webp.disabled && form.format.value === "webp") form.format.value = "jpg";
      input.multiple = m === "images-pdf";
      input.accept = m === "pdf-images" ? "application/pdf" : "image/*";
      hint.textContent = {
        "image": "One image · up to 10 MB",
        "images-pdf": "One or more images (up to 20) · 10 MB each",
        "pdf-images": "One PDF · up to 30 pages",
      }[m];
      input.value = "";
      describeFiles(panel, []);
      panel.querySelector(".docs-result").textContent = "";
    }
    Array.prototype.forEach.call(form.conversion, function (r) { r.addEventListener("change", sync); });
    input.addEventListener("change", function () { describeFiles(panel, input.files); });
    sync();

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var files = requireFiles(panel, input);
      if (!files) return;
      var fd = new FormData();
      var m = mode();
      if (m === "images-pdf") {
        Array.prototype.forEach.call(files, function (f) { fd.append("files", f); });
        fd.append("page_size", form.page_size.value);
        return run(panel, "/pdf/from-images", fd);
      }
      fd.append("file", files[0]);
      fd.append("format", form.format.value);
      if (m === "pdf-images") {
        fd.append("dpi", form.dpi.value);
        return run(panel, "/pdf/to-images", fd);
      }
      run(panel, "/image/convert", fd);
    });
  }

  // ------------------------------------------------------------------
  // Tool: Merge PDFs (with reorderable list)
  // ------------------------------------------------------------------
  function initMerge(panel) {
    var form = panel.querySelector("form");
    var input = form.querySelector("input[type=file]");
    var list = panel.querySelector(".docs-order");
    var order = [];

    function render() {
      list.textContent = "";
      order.forEach(function (file, i) {
        function move(delta) {
          var j = i + delta;
          if (j < 0 || j >= order.length) return;
          order.splice(j, 0, order.splice(i, 1)[0]);
          render();
        }
        var up = el("button", { type: "button", "aria-label": "Move " + file.name + " up", text: "↑" });
        var down = el("button", { type: "button", "aria-label": "Move " + file.name + " down", text: "↓" });
        var remove = el("button", { type: "button", "aria-label": "Remove " + file.name, text: "✕" });
        up.disabled = i === 0;
        down.disabled = i === order.length - 1;
        up.addEventListener("click", function () { move(-1); });
        down.addEventListener("click", function () { move(1); });
        remove.addEventListener("click", function () { order.splice(i, 1); render(); });
        list.appendChild(el("li", {}, [
          el("span", { className: "docs-order-name", text: file.name }),
          el("span", { className: "docs-order-size", text: formatSize(file.size) }),
          el("span", { className: "docs-order-actions" }, [up, down, remove]),
        ]));
      });
    }

    input.addEventListener("change", function () {
      Array.prototype.forEach.call(input.files, function (f) { order.push(f); });
      input.value = "";
      render();
    });

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      if (order.length < 2) return showError(panel, "Choose at least two PDF files.");
      var big = order.filter(function (f) { return f.size > MAX_FILE_BYTES; })[0];
      if (big) return showError(panel, "“" + big.name + "” is larger than 10 MB.");
      var fd = new FormData();
      order.forEach(function (f) { fd.append("files", f); });
      run(panel, "/pdf/merge", fd);
    });
  }

  // ------------------------------------------------------------------
  // Boot
  // ------------------------------------------------------------------
  /* Homepage module card: quick links that open a specific tab. */
  var QUICK_LINKS = [
    { tool: "prepare", label: "Photo & signature for a form" },
    { tool: "compress", label: "Compress to a size limit" },
    { tool: "convert", label: "Images to PDF" },
    { tool: "merge", label: "Merge PDFs" },
  ];

  function mountHome(panel) {
    var list = el("ul", { className: "docs-quick" });
    QUICK_LINKS.forEach(function (link) {
      list.appendChild(el("li", {}, [
        el("a", { href: "documents.html#" + link.tool, text: link.label }),
      ]));
    });
    panel.textContent = "";
    panel.appendChild(list);
  }

  /* The utility strip says whether the document service answered. The news
     pages fill the same element from /api/meta; this page has no news. */
  function renderStripStatus() {
    var box = document.getElementById("strip-status");
    var label = box && box.querySelector(".status-text");
    if (!label) return;
    fetch(API + "/health")
      .then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
      .then(function () {
        box.classList.remove("is-offline");
        label.textContent = "Document tool · ready";
      })
      .catch(function () {
        box.classList.add("is-offline");
        label.textContent = "Document tool offline";
      });
  }

  function init() {
    var homePanel = document.getElementById("documents-panel");
    if (homePanel) mountHome(homePanel);

    if (!document.querySelector(".docs-panels")) return;
    renderStripStatus();
    initTabs();
    Array.prototype.forEach.call(document.querySelectorAll(".docs-drop"), initDropZone);
    initPrepare(document.getElementById("panel-prepare"));
    initResize(document.getElementById("panel-resize"));
    initCompress(document.getElementById("panel-compress"));
    initConvert(document.getElementById("panel-convert"));
    initMerge(document.getElementById("panel-merge"));
    window.addEventListener("pagehide", releaseUrls);
  }

  GovEase.docs = { api: API, request: request, init: init };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
