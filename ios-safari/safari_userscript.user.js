// ==UserScript==
// @name         MagangHub Logbook Ops (Safari iOS & Desktop)
// @namespace    https://github.com/vanovri/maganghub-logbook-ops
// @version      1.0.0
// @description  Pre-fill dan gate-verified auto-submit logbook MagangHub Monev dari JSON ekspor Excel/CSV tanpa keluar aplikasi.
// @author       vanovri
// @license      MIT
// @match        https://monev.maganghub.kemnaker.go.id/*
// @grant        none
// @run-at       document-idle
// ==/UserScript==

(() => {
  "use strict";

  const STORAGE_ENTRIES_KEY = "maganghub_logbook_ops_entries_v1";
  const STORAGE_AUTOSUBMIT_KEY = "maganghub_logbook_ops_autosubmit_v1";
  const DEFAULT_AUTO_SUBMIT = /* __MAGANGHUB_AUTO_SUBMIT__ */ true;

  const PRELOADED_LOGBOOKS = /* __MAGANGHUB_LOGBOOKS_JSON__ */ {
    "schema_version": 1,
    "entries": {}
  } /* __MAGANGHUB_LOGBOOKS_JSON_END__ */;

  const PLACEHOLDERS = [
    {
      key: "aktivitas",
      altKey: "uraian_aktivitas",
      label: "Uraian aktivitas",
      placeholder: "Tulis uraian aktivitas minimal 100 karakter"
    },
    {
      key: "pelajaran",
      altKey: "pembelajaran",
      label: "Pembelajaran yang diperoleh",
      placeholder: "Tulis ilmu/pembelajaran yang diperoleh minimal 100 karakter"
    },
    {
      key: "kendala",
      altKey: "kendala",
      label: "Kendala yang dialami",
      placeholder: "Tulis kendala/hambatan yang dialami minimal 100 karakter"
    }
  ];

  const MIN_CHARS = 100;
  const MAX_CHARS = 5000;
  const CHECKBOX_LABEL_FRAGMENT = "Saya menyatakan telah meninjau dan memastikan isian laporan ini sudah benar";
  const SUBMIT_BUTTON_LABEL = "Simpan dan Kirim";

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  const getLocalDateISO = () => {
    const now = new Date();
    const yyyy = String(now.getFullYear());
    const mm = String(now.getMonth() + 1).padStart(2, "0");
    const dd = String(now.getDate()).padStart(2, "0");
    return `${yyyy}-${mm}-${dd}`;
  };

  const resolveTargetDate = () => {
    const params = new URLSearchParams(window.location.search);
    const qDate = (params.get("date") || "").trim();
    if (/^\d{4}-\d{2}-\d{2}$/.test(qDate)) {
      return qDate;
    }
    return getLocalDateISO();
  };

  const extractEntries = (raw) => {
    if (!raw || typeof raw !== "object") {
      return {};
    }
    const source = (raw.entries && typeof raw.entries === "object") ? raw.entries : raw;
    const clean = {};
    for (const [k, v] of Object.entries(source)) {
      if (/^\d{4}-\d{2}-\d{2}$/.test(k) && v && typeof v === "object") {
        clean[k] = v;
      }
    }
    return clean;
  };

  const loadEntries = () => {
    const base = extractEntries(PRELOADED_LOGBOOKS);
    try {
      const saved = window.localStorage.getItem(STORAGE_ENTRIES_KEY);
      if (saved) {
        return { ...base, ...extractEntries(JSON.parse(saved)) };
      }
    } catch (_err) {
      // Ignore corrupt localStorage and fall back to preloaded entries.
    }
    return base;
  };

  const getAutoSubmit = () => {
    try {
      const saved = window.localStorage.getItem(STORAGE_AUTOSUBMIT_KEY);
      if (saved === "true") return true;
      if (saved === "false") return false;
    } catch (_err) {
      // Ignore storage access restriction.
    }
    return DEFAULT_AUTO_SUBMIT;
  };

  const setAutoSubmit = (val) => {
    try {
      window.localStorage.setItem(STORAGE_AUTOSUBMIT_KEY, val ? "true" : "false");
    } catch (_err) {
      // Ignore storage access restriction.
    }
  };

  const setNativeTextareaValue = (textarea, value) => {
    const desc = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value");
    const setter = desc && desc.set;
    textarea.focus();
    if (setter) {
      setter.call(textarea, value);
    } else {
      textarea.value = value;
    }
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
    textarea.dispatchEvent(new Event("change", { bubbles: true }));
    textarea.blur();
  };

  const findConfirmationCheckbox = () => {
    const labels = Array.from(document.querySelectorAll("label"));
    for (const label of labels) {
      const txt = (label.textContent || "").replace(/\s+/g, " ").trim();
      if (txt.includes("Saya menyatakan telah meninjau")) {
        if (label.control && label.control.type === "checkbox") {
          return label.control;
        }
        const inside = label.querySelector('input[type="checkbox"]');
        if (inside) {
          return inside;
        }
        if (label.htmlFor) {
          const byId = document.getElementById(label.htmlFor);
          if (byId && byId.type === "checkbox") {
            return byId;
          }
        }
      }
    }
    const boxes = Array.from(document.querySelectorAll('input[type="checkbox"]'));
    for (const box of boxes) {
      const container = box.closest("label, div, section, form");
      const txt = ((container && container.textContent) || "").replace(/\s+/g, " ").trim();
      if (txt.includes(CHECKBOX_LABEL_FRAGMENT) || txt.includes("Saya menyatakan telah meninjau")) {
        return box;
      }
    }
    return null;
  };

  const findSubmitButton = () => {
    const candidates = Array.from(document.querySelectorAll('button, input[type="submit"], [role="button"]'));
    for (const el of candidates) {
      const raw = el.tagName === "INPUT" ? (el.value || "") : (el.textContent || "");
      const text = raw.replace(/\s+/g, " ").trim();
      if (text === SUBMIT_BUTTON_LABEL || text.toLowerCase().includes("simpan dan kirim")) {
        return el;
      }
    }
    return null;
  };

  async function fillCurrentPage(autoSubmit, onStatus) {
    const params = new URLSearchParams(window.location.search);
    if (params.get("view") === "detail") {
      onStatus("Mode detail (sudah terkirim). Tidak menimpa.", true);
      return;
    }

    const targetDate = resolveTargetDate();
    const pageText = (document.body && document.body.innerText) || "";
    const textareas = PLACEHOLDERS.map((spec) => ({
      spec,
      el: document.querySelector(`textarea[placeholder="${spec.placeholder}"]`)
    }));

    if (textareas.some((item) => !item.el)) {
      if (pageText.includes("Memuat halaman")) {
        onStatus("Halaman masih memuat, coba lagi sebentar.", true);
      } else if (pageText.includes("Menunggu Persetujuan") || pageText.includes("Telah Disetujui")) {
        onStatus(`Tanggal ${targetDate} sudah terkirim.`, true);
      } else {
        onStatus("Buka halaman edit (Isi Laporan Hari Ini) dulu.", true);
      }
      return;
    }

    if (textareas.some((item) => item.el.disabled || item.el.readOnly)) {
      onStatus(`Form ${targetDate} terkunci/read-only.`, true);
      return;
    }

    const entries = loadEntries();
    const entry = entries[targetDate];
    if (!entry) {
      onStatus(`Entri ${targetDate} tidak ditemukan di JSON.`, true);
      return;
    }

    const values = {};
    for (const { spec } of textareas) {
      const val = String(entry[spec.key] || entry[spec.altKey] || "").replace(/\r\n/g, "\n").trim();
      if (val.length < MIN_CHARS || val.length > MAX_CHARS) {
        onStatus(`Panjang "${spec.label}" (${val.length}) di luar 100-5000.`, true);
        return;
      }
      values[spec.key] = val;
    }

    for (const { spec, el } of textareas) {
      setNativeTextareaValue(el, values[spec.key]);
    }

    await sleep(150);

    for (const { spec, el } of textareas) {
      if (el.value !== values[spec.key] || el.value.length < MIN_CHARS || el.value.length > MAX_CHARS) {
        onStatus(`Parity gagal di "${spec.label}". Batal kirim.`, true);
        return;
      }
    }

    if (!autoSubmit) {
      onStatus(`Terisi & parity cocok (${targetDate}). Silakan tinjau & kirim.`, false);
      return;
    }

    const checkbox = findConfirmationCheckbox();
    if (!checkbox) {
      onStatus("Terisi, tapi checkbox konfirmasi tidak ketemu.", true);
      return;
    }
    if (!checkbox.checked) {
      checkbox.click();
    }
    if (!checkbox.checked) {
      checkbox.checked = true;
      checkbox.dispatchEvent(new Event("change", { bubbles: true }));
    }

    await sleep(200);

    const submitBtn = findSubmitButton();
    if (!submitBtn) {
      onStatus("Checkbox tercentang, tombol Simpan dan Kirim tidak ketemu.", true);
      return;
    }
    if (submitBtn.disabled || submitBtn.getAttribute("aria-disabled") === "true") {
      onStatus("Tombol Simpan dan Kirim masih nonaktif.", true);
      return;
    }

    submitBtn.click();
    onStatus(`Dikirim (${targetDate})! Cek respon portal.`, false);
  }

  function mountWidget() {
    if (document.getElementById("maganghub-ops-pill")) {
      return;
    }

    const root = document.createElement("div");
    root.id = "maganghub-ops-pill";
    root.style.cssText = [
      "position:fixed",
      "right:12px",
      "bottom:12px",
      "z-index:2147483647",
      "background:#0f172a",
      "color:#f8fafc",
      "border:1px solid #334155",
      "border-radius:12px",
      "padding:10px 12px",
      "font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif",
      "font-size:12px",
      "line-height:1.35",
      "box-shadow:0 8px 24px rgba(0,0,0,0.35)",
      "max-width:290px"
    ].join(";");

    const header = document.createElement("div");
    header.style.cssText = "display:flex;align-items:center;justify-content:space-between;gap:8px;font-weight:600;";
    const title = document.createElement("span");
    title.textContent = "Logbook Ops";
    const toggleMinBtn = document.createElement("button");
    toggleMinBtn.type = "button";
    toggleMinBtn.textContent = "−";
    toggleMinBtn.style.cssText = "background:#1e293b;color:#cbd5e1;border:1px solid #475569;border-radius:6px;padding:1px 7px;cursor:pointer;font-size:12px;";
    header.append(title, toggleMinBtn);

    const body = document.createElement("div");
    body.style.cssText = "margin-top:8px;display:flex;flex-direction:column;gap:6px;";

    const metaLine = document.createElement("div");
    metaLine.style.cssText = "color:#cbd5e1;font-size:11px;";

    const btnRow = document.createElement("div");
    btnRow.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;";

    const fillBtn = document.createElement("button");
    fillBtn.type = "button";
    fillBtn.textContent = "Isi Logbook";
    fillBtn.style.cssText = "flex:1;background:#16a34a;color:#fff;border:none;border-radius:8px;padding:7px 10px;font-weight:600;cursor:pointer;font-size:12px;";

    const importBtn = document.createElement("button");
    importBtn.type = "button";
    importBtn.textContent = "Import JSON";
    importBtn.style.cssText = "background:#1e293b;color:#e2e8f0;border:1px solid #475569;border-radius:8px;padding:7px 9px;cursor:pointer;font-size:11px;";

    const fileInput = document.createElement("input");
    fileInput.type = "file";
    fileInput.accept = ".json,application/json";
    fileInput.style.display = "none";

    btnRow.append(fillBtn, importBtn);

    const autoRow = document.createElement("label");
    autoRow.style.cssText = "display:flex;align-items:center;gap:6px;cursor:pointer;font-size:11px;color:#e2e8f0;";
    const autoCheck = document.createElement("input");
    autoCheck.type = "checkbox";
    autoCheck.checked = getAutoSubmit();
    const autoLabel = document.createElement("span");
    autoLabel.textContent = "Auto-submit (setelah parity cocok)";
    autoRow.append(autoCheck, autoLabel);

    const statusLine = document.createElement("div");
    statusLine.style.cssText = "font-size:11px;color:#93c5fd;min-height:14px;word-break:break-word;";

    body.append(metaLine, btnRow, autoRow, statusLine, fileInput);
    root.append(header, body);
    document.body.appendChild(root);

    const setStatus = (msg, isError) => {
      statusLine.textContent = msg;
      statusLine.style.color = isError ? "#fca5a5" : "#86efac";
    };

    const refreshMeta = () => {
      const entries = loadEntries();
      const count = Object.keys(entries).length;
      const targetDate = resolveTargetDate();
      const hasEntry = Boolean(entries[targetDate]);
      metaLine.textContent = `Tgl: ${targetDate} (${hasEntry ? "ada draf" : "belum ada"}) • Total: ${count} hari`;
    };

    let collapsed = false;
    toggleMinBtn.addEventListener("click", () => {
      collapsed = !collapsed;
      body.style.display = collapsed ? "none" : "flex";
      toggleMinBtn.textContent = collapsed ? "+" : "−";
    });

    autoCheck.addEventListener("change", () => {
      setAutoSubmit(autoCheck.checked);
      setStatus(autoCheck.checked ? "Mode: Auto-submit aktif." : "Mode: Draft-only (henti sebelum kirim).", false);
    });

    fillBtn.addEventListener("click", () => {
      refreshMeta();
      fillCurrentPage(autoCheck.checked, setStatus);
    });

    importBtn.addEventListener("click", () => fileInput.click());

    fileInput.addEventListener("change", async () => {
      const file = fileInput.files && fileInput.files[0];
      if (!file) return;
      try {
        const parsed = JSON.parse(await file.text());
        const imported = extractEntries(parsed);
        const n = Object.keys(imported).length;
        if (n === 0) {
          setStatus("File JSON tidak punya entri tanggal YYYY-MM-DD.", true);
          return;
        }
        window.localStorage.setItem(STORAGE_ENTRIES_KEY, JSON.stringify({ schema_version: 1, entries: imported }));
        refreshMeta();
        setStatus(`Berhasil impor ${n} hari dari ${file.name}.`, false);
      } catch (err) {
        setStatus(`Gagal baca JSON: ${err && err.message ? err.message : err}`, true);
      } finally {
        fileInput.value = "";
      }
    });

    refreshMeta();
    let lastHref = window.location.href;
    window.setInterval(() => {
      if (window.location.href !== lastHref) {
        lastHref = window.location.href;
        refreshMeta();
      }
    }, 1000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountWidget, { once: true });
  } else {
    mountWidget();
  }
})();
