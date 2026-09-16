/* OCR 截图翻译 - 前端逻辑 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);

  const els = {
    banner: $("banner"),
    direction: $("direction"),
    autoTranslate: $("auto-translate"),
    pasteBtn: $("paste-btn"),
    fileInput: $("file-input"),
    clearBtn: $("clear-btn"),
    dropzone: $("dropzone"),
    placeholder: $("placeholder"),
    preview: $("preview"),
    loading: $("loading"),
    loadingText: $("loading-text"),
    result: $("result"),
    ocrText: $("ocr-text"),
    ocrMeta: $("ocr-meta"),
    trText: $("tr-text"),
    trMeta: $("tr-meta"),
    copyOcr: $("copy-ocr"),
    copyTr: $("copy-tr"),
    copyBi: $("copy-bi"),
    translateBtn: $("translate-btn"),
  };

  let state = {
    objectUrl: null,
    bilingual: "",
    translated: "",
    tab: "translated",
  };

  function showBanner(text, type) {
    els.banner.textContent = text;
    els.banner.className = "banner " + (type || "warn");
  }
  function hideBanner() {
    els.banner.classList.add("hidden");
  }
  function showLoading(text) {
    els.loadingText.textContent = text || "处理中…";
    els.loading.classList.remove("hidden");
  }
  function hideLoading() {
    els.loading.classList.add("hidden");
  }

  async function api(path, options) {
    const res = await fetch(path, options);
    let data = null;
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) data = await res.json();
    else data = await res.text();
    if (!res.ok) {
      const detail = (data && data.detail) || data || res.statusText;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return data;
  }

  function setPreviewFromBlob(blob) {
    if (state.objectUrl) URL.revokeObjectURL(state.objectUrl);
    state.objectUrl = URL.createObjectURL(blob);
    els.preview.src = state.objectUrl;
    els.preview.classList.remove("hidden");
    els.placeholder.classList.add("hidden");
  }

  function clearAll() {
    if (state.objectUrl) URL.revokeObjectURL(state.objectUrl);
    state = { objectUrl: null, bilingual: "", translated: "", tab: "translated" };
    els.preview.src = "";
    els.preview.classList.add("hidden");
    els.placeholder.classList.remove("hidden");
    els.result.classList.add("hidden");
    els.ocrText.value = "";
    els.trText.value = "";
    els.ocrMeta.textContent = "";
    els.trMeta.textContent = "";
    hideBanner();
    document.querySelectorAll(".tab").forEach((t) => {
      t.classList.toggle("active", t.dataset.tab === "translated");
    });
  }

  function blobToDataUrl(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(new Error("读取图片失败"));
      reader.readAsDataURL(blob);
    });
  }

  async function runOcrFromBlob(blob) {
    hideBanner();
    setPreviewFromBlob(blob);
    showLoading("正在识别文字…");
    els.result.classList.add("hidden");
    try {
      const dataUrl = await blobToDataUrl(blob);
      const doTranslate = !!els.autoTranslate.checked;
      if (doTranslate) els.loadingText.textContent = "正在识别并翻译…";
      const data = await api("/api/ocr/base64", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          image: dataUrl,
          translate: doTranslate,
          direction: els.direction.value,
        }),
      });
      showOcrResult(data);
    } catch (err) {
      showBanner(err.message || String(err), "error");
    } finally {
      hideLoading();
    }
  }

  function showOcrResult(data) {
    els.ocrText.value = data.text || "";
    const conf =
      data.lines && data.lines.length
        ? (
            data.lines.reduce((s, x) => s + (x.confidence || 0), 0) /
            data.lines.length
          ).toFixed(2)
        : "-";
    els.ocrMeta.textContent =
      (data.line_count || 0) +
      " 行 · " +
      (data.elapsed_ms || "?") +
      " ms · 均置信度 " +
      conf;

    state.translated = "";
    state.bilingual = "";
    if (data.translation) {
      applyTranslation(data.translation);
    } else {
      els.trText.value = "";
      els.trMeta.textContent = els.autoTranslate.checked ? "" : "未开启自动翻译";
    }

    els.result.classList.remove("hidden");
    if (!(data.text || "").trim()) {
      showBanner("未识别到文字，可换更清晰的截图再试", "warn");
    } else if (data.translation) {
      showBanner("识别完成", "ok");
    } else {
      showBanner("识别完成，可点击「重新翻译」生成对照", "ok");
    }
  }

  function applyTranslation(tr) {
    state.translated = tr.translated || "";
    state.bilingual = tr.bilingual || "";
    els.trMeta.textContent =
      (tr.source_lang || "?") +
      " → " +
      (tr.target_lang || "?") +
      (tr.provider ? " · " + tr.provider : "");
    renderTranslateTab();
  }

  function renderTranslateTab() {
    els.trText.value =
      state.tab === "bilingual" ? state.bilingual : state.translated;
  }

  async function translateCurrent() {
    const text = (els.ocrText.value || "").trim();
    if (!text) {
      showBanner("没有可翻译的原文", "warn");
      return;
    }
    hideBanner();
    showLoading("正在翻译…");
    try {
      const data = await api("/api/translate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, direction: els.direction.value }),
      });
      applyTranslation(data);
      showBanner("翻译完成", "ok");
    } catch (err) {
      showBanner(err.message || String(err), "error");
    } finally {
      hideLoading();
    }
  }

  async function copyText(text, okMsg) {
    const value = (text || "").trim();
    if (!value) {
      showBanner("没有可复制的内容", "warn");
      return;
    }
    try {
      await navigator.clipboard.writeText(value);
      showBanner(okMsg || "已复制", "ok");
    } catch (_) {
      // fallback
      const ta = document.createElement("textarea");
      ta.value = value;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      showBanner(okMsg || "已复制", "ok");
    }
  }

  async function pasteFromClipboard() {
    try {
      if (!navigator.clipboard || !navigator.clipboard.read) {
        showBanner("当前浏览器不支持读取剪贴板图片，请用 Ctrl+V 粘贴到虚线框", "warn");
        els.dropzone.focus();
        return;
      }
      const items = await navigator.clipboard.read();
      for (const item of items) {
        const type = item.types.find((t) => t.startsWith("image/"));
        if (type) {
          const blob = await item.getType(type);
          await runOcrFromBlob(blob);
          return;
        }
      }
      showBanner("剪贴板里没有图片，请先截图再粘贴", "warn");
    } catch (err) {
      showBanner("无法读取剪贴板：" + (err.message || err) + "。可改用 Ctrl+V。", "warn");
      els.dropzone.focus();
    }
  }

  // ---- events ----
  document.addEventListener("paste", async (e) => {
    const items = e.clipboardData && e.clipboardData.items;
    if (!items) return;
    for (const item of items) {
      if (item.type && item.type.startsWith("image/")) {
        e.preventDefault();
        const blob = item.getAsFile();
        if (blob) await runOcrFromBlob(blob);
        return;
      }
    }
  });

  els.dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    els.dropzone.classList.add("dragover");
  });
  els.dropzone.addEventListener("dragleave", () => {
    els.dropzone.classList.remove("dragover");
  });
  els.dropzone.addEventListener("drop", async (e) => {
    e.preventDefault();
    els.dropzone.classList.remove("dragover");
    const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    if (file && file.type.startsWith("image/")) {
      await runOcrFromBlob(file);
    } else {
      showBanner("请拖入图片文件", "warn");
    }
  });

  els.fileInput.addEventListener("change", async () => {
    const file = els.fileInput.files && els.fileInput.files[0];
    if (file) await runOcrFromBlob(file);
    els.fileInput.value = "";
  });

  els.pasteBtn.addEventListener("click", pasteFromClipboard);
  els.clearBtn.addEventListener("click", clearAll);
  els.translateBtn.addEventListener("click", translateCurrent);
  els.copyOcr.addEventListener("click", () => copyText(els.ocrText.value, "原文已复制"));
  els.copyTr.addEventListener("click", () => copyText(state.translated, "译文已复制"));
  els.copyBi.addEventListener("click", () => copyText(state.bilingual, "对照文本已复制"));

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      state.tab = tab.dataset.tab;
      document.querySelectorAll(".tab").forEach((t) => {
        t.classList.toggle("active", t === tab);
      });
      renderTranslateTab();
    });
  });

  // 启动检查
  api("/api/health")
    .then((h) => {
      if (h && h.ocr_ready === false && h.ocr_error) {
        showBanner("OCR 引擎尚未就绪：" + h.ocr_error, "warn");
      }
    })
    .catch(() => showBanner("后端未就绪，请先启动服务", "error"));

  els.dropzone.focus();
})();
