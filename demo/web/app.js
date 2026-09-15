/* 网页剪藏器 - 前端逻辑 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);

  const els = {
    urlInput: $("url-input"),
    previewBtn: $("preview-btn"),
    clipBtn: $("clip-btn"),
    proxy: $("proxy"),
    banner: $("banner"),
    loading: $("loading"),
    loadingText: $("loading-text"),
    preview: $("preview"),
    previewTitle: $("preview-title"),
    previewTags: $("preview-tags"),
    previewExcerpt: $("preview-excerpt"),
    previewMd: $("preview-md"),
    savePreviewBtn: $("save-preview-btn"),
    searchInput: $("search-input"),
    searchBtn: $("search-btn"),
    clipList: $("clip-list"),
    reader: $("reader"),
    backBtn: $("back-btn"),
    dlMd: $("dl-md"),
    dlPdf: $("dl-pdf"),
    openSource: $("open-source"),
    deleteBtn: $("delete-btn"),
    readerTitle: $("reader-title"),
    readerMeta: $("reader-meta"),
    readerBody: $("reader-body"),
    libraryCard: document.querySelector(".library-card"),
  };

  // 预览后「确认剪藏」必须用用户粘贴的原始 URL。
  // 若改用预览返回的跳转后地址，部分站点二次请求会返回 521。
  let previewSourceUrl = "";
  let currentClipId = null;

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

  function tag(text) {
    const span = document.createElement("span");
    span.className = "tag";
    span.textContent = text;
    return span;
  }

  function proxyValue() {
    return (els.proxy.value || "").trim() || null;
  }

  async function api(path, options) {
    const res = await fetch(path, options);
    let data = null;
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) {
      data = await res.json();
    } else {
      data = await res.text();
    }
    if (!res.ok) {
      const detail = (data && data.detail) || data || res.statusText;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return data;
  }

  async function doPreview() {
    const url = (els.urlInput.value || "").trim();
    if (!url) {
      showBanner("请先粘贴网页地址", "warn");
      return;
    }
    hideBanner();
    els.preview.classList.add("hidden");
    showLoading("正在预览抽取结果（不下载图片）…");
    try {
      const data = await api("/api/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, proxy: proxyValue() }),
      });
      previewSourceUrl = url;
      els.previewTitle.textContent = data.title || "未命名";
      els.previewExcerpt.textContent = data.excerpt || "";
      els.previewMd.textContent = data.markdown_preview || "";
      els.previewTags.innerHTML = "";
      if (data.site) els.previewTags.appendChild(tag(data.site));
      if (data.author) els.previewTags.appendChild(tag("作者 " + data.author));
      if (data.date) els.previewTags.appendChild(tag(data.date));
      els.previewTags.appendChild(tag("约 " + (data.text_length || 0) + " 字"));
      els.preview.classList.remove("hidden");
      showBanner("预览成功，确认无误后可剪藏", "ok");
    } catch (err) {
      showBanner(err.message || String(err), "error");
    } finally {
      hideLoading();
    }
  }

  async function doClip(url) {
    const target = (url || els.urlInput.value || "").trim();
    if (!target) {
      showBanner("请先粘贴网页地址", "warn");
      return;
    }
    hideBanner();
    showLoading("正在抽取正文并下载图片…");
    els.preview.classList.add("hidden");
    try {
      const item = await api("/api/clip", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: target, proxy: proxyValue() }),
      });
      showBanner("已剪藏：" + (item.title || ""), "ok");
      els.urlInput.value = "";
      previewSourceUrl = "";
      await loadList();
      if (item.id) openReader(item.id);
    } catch (err) {
      showBanner(err.message || String(err), "error");
    } finally {
      hideLoading();
    }
  }

  function formatTime(iso) {
    if (!iso) return "";
    try {
      const d = new Date(iso);
      return d.toLocaleString();
    } catch (_) {
      return iso;
    }
  }

  async function loadList(q) {
    const query = q !== undefined ? q : (els.searchInput.value || "").trim();
    const path = query ? "/api/clips?q=" + encodeURIComponent(query) : "/api/clips";
    try {
      const data = await api(path);
      renderList(data.items || []);
    } catch (err) {
      els.clipList.innerHTML = '<p class="empty">加载失败：' + escapeHtml(err.message) + "</p>";
    }
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderList(items) {
    if (!items.length) {
      els.clipList.innerHTML = '<p class="empty">没有匹配的剪藏</p>';
      return;
    }
    els.clipList.innerHTML = "";
    items.forEach((item) => {
      const row = document.createElement("div");
      row.className = "clip-item";
      row.innerHTML =
        '<div class="clip-main">' +
        "<h3></h3>" +
        '<div class="meta"></div>' +
        '<div class="excerpt-sm"></div>' +
        "</div>" +
        '<div class="clip-item-actions">' +
        '<button class="btn btn-ghost btn-sm open-btn">阅读</button>' +
        "</div>";
      row.querySelector("h3").textContent = item.title || "未命名";
      const metaParts = [];
      if (item.site) metaParts.push(item.site);
      if (item.image_count) metaParts.push(item.image_count + " 张图");
      metaParts.push(formatTime(item.created_at));
      row.querySelector(".meta").textContent = metaParts.join(" · ");
      row.querySelector(".excerpt-sm").textContent = item.excerpt || "";
      const open = () => openReader(item.id);
      row.addEventListener("click", open);
      row.querySelector(".open-btn").addEventListener("click", (e) => {
        e.stopPropagation();
        open();
      });
      els.clipList.appendChild(row);
    });
  }

  async function openReader(id) {
    hideBanner();
    showLoading("加载文章…");
    try {
      const data = await api("/api/clips/" + id + "/content");
      currentClipId = id;
      els.readerTitle.textContent = data.title || "未命名";
      els.readerMeta.innerHTML = "";
      if (data.site) els.readerMeta.appendChild(tag(data.site));
      if (data.author) els.readerMeta.appendChild(tag(data.author));
      if (data.created_at) els.readerMeta.appendChild(tag("剪藏于 " + formatTime(data.created_at)));

      if (window.marked) {
        els.readerBody.innerHTML = marked.parse(data.markdown || "");
      } else {
        els.readerBody.textContent = data.markdown || "";
      }

      els.dlMd.href = "/api/clips/" + id + "/markdown";
      els.dlPdf.href = "/api/clips/" + id + "/pdf";
      els.openSource.href = data.url || "#";

      els.libraryCard.classList.add("hidden");
      els.preview.classList.add("hidden");
      els.reader.classList.remove("hidden");
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      showBanner(err.message || String(err), "error");
    } finally {
      hideLoading();
    }
  }

  function backToList() {
    currentClipId = null;
    els.reader.classList.add("hidden");
    els.libraryCard.classList.remove("hidden");
  }

  async function deleteCurrent() {
    if (!currentClipId) return;
    if (!confirm("确定删除这篇剪藏？本地 Markdown / 图片将一并删除。")) return;
    try {
      await api("/api/clips/" + currentClipId, { method: "DELETE" });
      showBanner("已删除", "ok");
      backToList();
      await loadList();
    } catch (err) {
      showBanner(err.message || String(err), "error");
    }
  }

  els.previewBtn.addEventListener("click", doPreview);
  els.clipBtn.addEventListener("click", () => doClip());
  els.savePreviewBtn.addEventListener("click", () => doClip(previewSourceUrl || els.urlInput.value));
  els.searchBtn.addEventListener("click", () => loadList());
  els.searchInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") loadList();
  });
  els.urlInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") doClip();
  });
  els.backBtn.addEventListener("click", backToList);
  els.deleteBtn.addEventListener("click", deleteCurrent);

  // 初始加载
  loadList();
  api("/api/health")
    .then((h) => {
      if (h && h.clips === 0) {
        /* noop */
      }
    })
    .catch(() => showBanner("后端未就绪，请确认已启动服务", "error"));
})();
