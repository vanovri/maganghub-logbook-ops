// MagangHub Monev - iOS Shortcuts "Run JavaScript on Web Page"
// License: MIT
// Usage:
//   1. Generate embedded script with:
//        python ios-safari/excel_to_ios_json.py logbook.xlsx --emit-shortcut-js my_shortcut.js
//      OR paste the contents of logbooks.json below (or via Shortcuts Magic Variable).
//   2. Open https://monev.maganghub.kemnaker.go.id/dashboard/riwayat?date=YYYY-MM-DD&view=edit
//      (or click "Isi Laporan Hari Ini") in iOS Safari while logged in at your placement location.
//   3. Share -> Run your Shortcut. Never bypasses login/SSO, CAPTCHA, or server geofence.

(async () => {
  const CONFIG = {
    autoSubmit: /* __MAGANGHUB_AUTO_SUBMIT__ */ true,
    expectedHost: "monev.maganghub.kemnaker.go.id",
    minChars: 100,
    maxChars: 5000,
    parityDelayMs: 150,
    submitDelayMs: 200
  };

  const LOGBOOKS_DATA = /* __MAGANGHUB_LOGBOOKS_JSON__ */ {
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

  const CHECKBOX_LABEL_FRAGMENT = "Saya menyatakan telah meninjau dan memastikan isian laporan ini sudah benar";
  const SUBMIT_BUTTON_LABEL = "Simpan dan Kirim";

  const done = (payload) => {
    const out = typeof payload === "string" ? payload : JSON.stringify(payload, null, 2);
    if (typeof completion === "function") {
      completion(out);
    } else {
      console.log(out);
    }
  };

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

  try {
    if (window.location.hostname !== CONFIG.expectedHost) {
      return done({
        ok: false,
        error: "WRONG_HOST",
        message: `Buka portal ${CONFIG.expectedHost} dulu sebelum menjalankan Shortcut.`
      });
    }

    const params = new URLSearchParams(window.location.search);
    if (params.get("view") === "detail") {
      return done({
        ok: false,
        error: "ALREADY_SUBMITTED_VIEW",
        message: "Halaman sedang dalam mode detail (sudah terkirim). Dilarang menimpa laporan yang sudah terkirim."
      });
    }

    const targetDate = resolveTargetDate();
    const pageText = (document.body && document.body.innerText) || "";

    const textareas = PLACEHOLDERS.map((spec) => ({
      spec,
      el: document.querySelector(`textarea[placeholder="${spec.placeholder}"]`)
    }));

    if (textareas.some((item) => !item.el)) {
      if (pageText.includes("Memuat halaman")) {
        return done({
          ok: false,
          error: "PAGE_LOADING",
          message: "Halaman masih memuat. Tunggu 2-3 detik lalu jalankan ulang Shortcut."
        });
      }
      if (pageText.includes("Menunggu Persetujuan") || pageText.includes("Telah Disetujui")) {
        return done({
          ok: false,
          error: "ALREADY_SUBMITTED",
          message: `Laporan tanggal ${targetDate} sudah berstatus terkirim/disetujui.`
        });
      }
      return done({
        ok: false,
        error: "FORM_NOT_FOUND",
        message: `Kotak edit form tidak ditemukan. Pastikan sudah login SSO dan buka "Isi Laporan Hari Ini" atau ?date=${targetDate}&view=edit.`
      });
    }

    if (textareas.some((item) => item.el.disabled || item.el.readOnly)) {
      return done({
        ok: false,
        error: "FORM_READONLY",
        message: `Form tanggal ${targetDate} terkunci/read-only dan tidak dapat diubah.`
      });
    }

    const entryMap = (LOGBOOKS_DATA && LOGBOOKS_DATA.entries) ? LOGBOOKS_DATA.entries : LOGBOOKS_DATA;
    const entry = entryMap ? entryMap[targetDate] : null;
    if (!entry) {
      return done({
        ok: false,
        error: "DATE_NOT_FOUND",
        date: targetDate,
        message: `Tidak ada entri untuk tanggal ${targetDate} di data JSON.`
      });
    }

    const values = {};
    for (const { spec } of textareas) {
      const val = String(entry[spec.key] || entry[spec.altKey] || "").replace(/\r\n/g, "\n").trim();
      if (val.length < CONFIG.minChars || val.length > CONFIG.maxChars) {
        return done({
          ok: false,
          error: "INVALID_LENGTH",
          field: spec.label,
          length: val.length,
          message: `Panjang kolom "${spec.label}" (${val.length} karakter) harus antara ${CONFIG.minChars}-${CONFIG.maxChars} karakter.`
        });
      }
      values[spec.key] = val;
    }

    for (const { spec, el } of textareas) {
      setNativeTextareaValue(el, values[spec.key]);
    }

    await sleep(CONFIG.parityDelayMs);

    const charCounts = {};
    for (const { spec, el } of textareas) {
      const actual = el.value;
      const expected = values[spec.key];
      if (actual !== expected || actual.length < CONFIG.minChars || actual.length > CONFIG.maxChars) {
        return done({
          ok: false,
          error: "PARITY_MISMATCH",
          date: targetDate,
          field: spec.label,
          expectedLength: expected.length,
          actualLength: actual.length,
          message: `Verifikasi parity gagal pada "${spec.label}". Dihentikan sebelum centang dan kirim.`
        });
      }
      charCounts[spec.key] = actual.length;
    }

    if (!CONFIG.autoSubmit) {
      return done({
        ok: true,
        mode: "draft_only",
        date: targetDate,
        charCounts,
        message: `3 kolom tanggal ${targetDate} terisi & parity cocok (mode draft-only). Tinjau, centang pernyataan, lalu klik Simpan dan Kirim manual.`
      });
    }

    const checkbox = findConfirmationCheckbox();
    if (!checkbox) {
      return done({
        ok: false,
        error: "CHECKBOX_NOT_FOUND",
        date: targetDate,
        charCounts,
        message: "3 kolom terisi, tetapi kotak centang konfirmasi tidak ditemukan. Centang dan kirim manual."
      });
    }

    if (!checkbox.checked) {
      checkbox.click();
    }
    if (!checkbox.checked) {
      checkbox.checked = true;
      checkbox.dispatchEvent(new Event("change", { bubbles: true }));
    }

    await sleep(CONFIG.submitDelayMs);

    const submitBtn = findSubmitButton();
    if (!submitBtn) {
      return done({
        ok: false,
        error: "SUBMIT_BUTTON_NOT_FOUND",
        date: targetDate,
        charCounts,
        message: "Kotak konfirmasi sudah dicentang, tetapi tombol Simpan dan Kirim tidak ditemukan."
      });
    }
    if (submitBtn.disabled || submitBtn.getAttribute("aria-disabled") === "true") {
      return done({
        ok: false,
        error: "SUBMIT_BUTTON_DISABLED",
        date: targetDate,
        charCounts,
        message: "Tombol Simpan dan Kirim masih nonaktif. Periksa syarat form atau status lokasi/tanggal."
      });
    }

    submitBtn.click();
    return done({
      ok: true,
      mode: "auto_submit",
      date: targetDate,
      charCounts,
      message: `Sukses mengisi ${targetDate}, parity cocok, dan tombol Simpan dan Kirim sudah diklik sekali. Cek notifikasi hasil dari portal.`
    });
  } catch (err) {
    return done({
      ok: false,
      error: "UNEXPECTED_ERROR",
      message: String(err && err.message ? err.message : err)
    });
  }
})();
