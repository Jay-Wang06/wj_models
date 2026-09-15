/* 视频下载助手 - 前端逻辑 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);

  const els = {
    urlInput: $("url-input"),
    parseBtn: $("parse-btn"),
    diagBtn: $("diag-btn"),
    diagSummary: $("diag-summary"),
    sessdata: $("sessdata"),
    proxy: $("proxy"),
    banner: $("banner"),
    loading: $("loading"),
    loadingText: $("loading-text"),
    result: $("result"),
    playlistPanel: $("playlist-panel"),
    playlist: $("playlist"),
    videoPanel: $("video-panel"),
    thumb: $("thumb"),
    videoTitle: $("video-title"),
    videoUploader: $("video-uploader"),
    videoDuration: $("video-duration"),
    videoViews: $("video-views"),
    videoSource: $("video-source"),
    options: $("options"),
    ffmpegTip: $("ffmpeg-tip"),
    installFfmpegBtn: $("install-ffmpeg-btn"),
    ffmpegProgress: $("ffmpeg-progress"),
    downloadBtn: $("download-btn"),
    selectionSummary: $("selection-summary"),
    progressPanel: $("progress-panel"),
    taskStatus: $("task-status"),
    progressBar: $("progress-bar"),
    progressPct: $("progress-pct"),
    progressSize: $("progress-size"),
    progressSpeed: $("progress-speed"),
    progressEta: $("progress-eta"),
    progressFile: $("progress-file"),
    doneActions: $("done-actions"),
    downloadFileBtn: $("download-file-btn"),
    openFolderBtn: $("open-folder-btn"),
    errorBox: $("error-box"),
    cancelBtn: $("cancel-btn"),
    history: $("history"),
    historyList: $("history-list"),
  };

  let state = {
    meta: null,             // 当前解析出的视频信息
    selected: null,         // 当前选中的清晰度选项
    currentUrl: "",
    currentTaskId: null,
    pollTimer: null,
    ffmpegOk: false,
    sessdata: "",
    proxy: "",
  };

  const STATUS_TEXT = {
    pending: "排队中",
    downloading: "下载中",
    processing: "合并处理中",
    done: "已完成",
    error: "失败",
    cancelled: "已取消",
  };

  /* ---------- 工具 ---------- */
  function showBanner(text, type) {
    els.banner.textContent = text;
    els.banner.className = "banner " + (type || "warn");
  }
  function hideBanner() {
    els.banner.classList.add("hidden");
  }
  function showLoading(text) {
    els.loadingText.textContent = text || "正在解析视频信息…";
    els.loading.classList.remove("hidden");
    els.result.classList.add("hidden");
  }
  function hideLoading() {
    els.loading.classList.add("hidden");
    els.result.classList.remove("hidden");
  }
  function fmtBytes(n) {
    if (n == null || isNaN(n)) return "";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let v = Number(n);
    let i = 0;
    while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
    return (i === 0 ? v.toFixed(0) : v.toFixed(1)) + " " + units[i];
  }
  function fmtSpeed(bps) {
    if (!bps) return "";
    return fmtBytes(bps) + "/s";
  }
  function fmtEta(sec) {
    if (sec == null || isNaN(sec)) return "";
    sec = Math.max(0, Math.round(sec));
    if (sec < 60) return "剩余 " + sec + " 秒";
    const m = Math.floor(sec / 60);
    if (m < 60) return "剩余 " + m + " 分 " + (sec % 60) + " 秒";
    const h = Math.floor(m / 60);
    return "剩余 " + h + " 小时 " + (m % 60) + " 分";
  }

  async function api(path, options) {
    const res = await fetch(path, options);
    let data = null;
    try { data = await res.json(); } catch (e) { /* 非 JSON */ }
    if (!res.ok) {
      const msg = (data && (data.detail || data.message)) || ("请求失败 (" + res.status + ")");
      throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    }
    return data;
  }
  const post = (path, body) =>
    api(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });

  /* ---------- 初始化 ---------- */
  async function init() {
    try {
      const h = await api("/api/health");
      state.ffmpegOk = !!h.ffmpeg;
      els.installFfmpegBtn.classList.toggle("hidden", state.ffmpegOk);
      els.installFfmpegBtn.addEventListener("click", handleInstallFfmpeg);
      els.ffmpegProgress.addEventListener("click", () => {});
    } catch (e) {
      showBanner("无法连接服务：" + e.message, "warn");
    }
    refreshHistory();
    setInterval(refreshHistory, 4000);
  }

  /* ---------- 解析 ---------- */
  async function handleParse() {
    const url = els.urlInput.value.trim();
    if (!url) {
      els.urlInput.focus();
      showBanner("请先输入视频网址", "warn");
      return;
    }
    hideBanner();
    state.sessdata = els.sessdata.value.trim();
    state.proxy = els.proxy.value.trim();
    els.parseBtn.disabled = true;
    showLoading("正在解析视频信息…");
    state.currentTaskId = null;
    stopPolling();

    try {
      const meta = await post("/api/parse", { url, sessdata: state.sessdata || null, proxy: state.proxy || null });
      state.meta = meta;
      state.currentUrl = meta.webpage_url || url;
      renderResult(meta);
      hideLoading();
      refreshHistory();
    } catch (e) {
      hideLoading();
      showBanner("❌ " + e.message, "warn");
      els.result.classList.add("hidden");
    } finally {
      els.parseBtn.disabled = false;
    }
  }

  /* ---------- 渲染结果 ---------- */
  function renderResult(meta) {
    if (meta.playlists && meta.playlists.length > 0) {
      els.videoPanel.classList.add("hidden");
      els.playlistPanel.classList.remove("hidden");
      renderPlaylist(meta);
      return;
    }
    els.playlistPanel.classList.add("hidden");
    els.videoPanel.classList.remove("hidden");

    els.videoTitle.textContent = meta.title || "未命名视频";
    els.videoUploader.textContent = meta.uploader ? "UP主：" + meta.uploader : "";
    els.videoUploader.classList.toggle("hidden", !meta.uploader);
    els.videoDuration.textContent = meta.duration_text || "";
    els.videoDuration.classList.toggle("hidden", !meta.duration_text);
    els.videoViews.textContent = meta.view_count != null ? "播放 " + fmtCount(meta.view_count) : "";
    els.videoViews.classList.toggle("hidden", meta.view_count == null);
    els.videoSource.textContent = meta.extractor_key ? meta.extractor_key.replace(/_/g, " ") : "";
    els.videoSource.classList.toggle("hidden", !meta.extractor_key);

    if (meta.thumbnail) {
      els.thumb.src = meta.thumbnail;
      els.thumb.classList.remove("hidden");
    } else {
      els.thumb.classList.add("hidden");
    }

    renderOptions(meta.options || []);
  }

  function fmtCount(n) {
    if (n >= 10000) return (n / 10000).toFixed(1) + " 万";
    return String(n);
  }

  function renderPlaylist(meta) {
    els.playlist.innerHTML = "";
    meta.playlists.forEach((p, i) => {
      const item = document.createElement("button");
      item.className = "playlist-item";
      item.innerHTML =
        '<span class="p-index" style="color:var(--text-dim);font-size:12px;flex-shrink:0">' + (i + 1) + "</span>" +
        (p.thumbnail ? '<img src="' + esc(p.thumbnail) + '" alt="" loading="lazy"/>' : "") +
        '<span class="p-title">' + esc(p.title) + "</span>" +
        '<span class="p-dur">' + esc(p.duration_text || "") + "</span>";
      item.addEventListener("click", async () => {
        try {
          showLoading("正在解析分P " + (i + 1) + "…");
          const m = await post("/api/parse", { url: p.webpage_url, sessdata: state.sessdata || null });
          state.meta = m;
          state.currentUrl = m.webpage_url || p.webpage_url;
          renderResult(m);
          hideLoading();
        } catch (e) {
          hideLoading();
          showBanner("❌ " + e.message, "warn");
        }
      });
      els.playlist.appendChild(item);
    });
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  function renderOptions(options) {
    els.options.innerHTML = "";
    state.selected = null;
    els.downloadBtn.disabled = true;
    els.selectionSummary.textContent = "";

    // ffmpeg 提示
    els.ffmpegTip.classList.toggle("hidden", state.ffmpegOk);
    els.installFfmpegBtn.classList.toggle("hidden", state.ffmpegOk);
    els.ffmpegProgress.classList.toggle("hidden", state.ffmpegOk || !els.ffmpegProgress.textContent);
    if (!state.ffmpegOk) {
      els.ffmpegTip.textContent = "提示：标虚线边框的选项需要 ffmpeg 合并，当前不可用";
    }

    options.forEach((opt) => {
      const div = document.createElement("div");
      const unavailable = opt.merge && !state.ffmpegOk;
      div.className = "option" + (opt.merge ? " merge-hint" : "") + (unavailable ? " disabled" : "");
      if (unavailable) div.style.opacity = "0.45";
      div.innerHTML =
        '<div class="option-top">' +
        '<span class="option-label">' + esc(opt.label) + "</span>" +
        (opt.tag ? '<span class="option-tag">' + esc(opt.tag) + "</span>" : "") +
        "</div>" +
        '<div class="option-sub">' + esc(opt.sub || "") + "</div>" +
        '<div class="option-bottom">' +
        "<span>" + esc(opt.size_text || "") + "</span>" +
        '<span class="option-note">' + esc(opt.note || "") + "</span>" +
        "</div>";

      if (!unavailable) {
        div.addEventListener("click", () => selectOption(opt, div));
      }
      els.options.appendChild(div);
    });
  }

  function selectOption(opt, el) {
    state.selected = opt;
    els.options.querySelectorAll(".option").forEach((o) => o.classList.remove("selected"));
    el.classList.add("selected");
    els.downloadBtn.disabled = false;
    els.selectionSummary.textContent = opt.label + " · " + (opt.ext || "") + " · " + (opt.size_text || "");
  }

  /* ---------- 安装 ffmpeg ---------- */
  async function handleInstallFfmpeg() {
    els.installFfmpegBtn.disabled = true;
    els.ffmpegProgress.classList.remove("hidden");
    els.ffmpegProgress.textContent = "正在启动下载…";
    try {
      await post("/api/ffmpeg/install", {});
    } catch (e) {
      els.ffmpegProgress.textContent = "启动失败：" + e.message;
      els.installFfmpegBtn.disabled = false;
      return;
    }
    const timer = setInterval(async () => {
      try {
        const s = await api("/api/ffmpeg/status");
        const ins = s.install || {};
        if (ins.stage === "downloading") {
          const pct = ((ins.progress || 0) * 100).toFixed(0);
          const mb = ((ins.received || 0) / 1048576).toFixed(1);
          els.ffmpegProgress.textContent = "下载中 " + pct + "% (" + mb + " MB)";
        } else if (ins.stage === "extracting") {
          els.ffmpegProgress.textContent = "下载完成，正在解压…";
        } else if (ins.stage === "done") {
          els.ffmpegProgress.textContent = "✓ 已安装";
          clearInterval(timer);
          state.ffmpegOk = true;
          if (state.meta) renderOptions(state.meta.options || []);
          setTimeout(() => {
            els.ffmpegProgress.classList.add("hidden");
            els.ffmpegProgress.textContent = "";
          }, 4000);
        } else if (ins.stage === "error") {
          els.ffmpegProgress.textContent = "✗ " + (ins.error || "安装失败");
          els.installFfmpegBtn.disabled = false;
          clearInterval(timer);
        }
      } catch (e) {
        els.ffmpegProgress.textContent = "查询失败：" + e.message;
      }
    }, 500);
  }

  /* ---------- 下载 ---------- */
  async function handleDownload() {
    if (!state.selected || !state.currentUrl) return;
    const opt = state.selected;
    els.downloadBtn.disabled = true;
    els.doneActions.classList.add("hidden");
    els.errorBox.classList.add("hidden");
    els.cancelBtn.classList.remove("hidden");
    els.progressPanel.classList.remove("hidden");
    els.taskStatus.textContent = "开始下载…";
    setProgress(0, 0, null, null, null);

    try {
      const body = {
        url: state.currentUrl,
        selector: opt.selector,
        title: state.meta && state.meta.title ? state.meta.title : "未命名视频",
        sessdata: state.sessdata || null,
        proxy: state.proxy || null,
        audio_mp3: opt.id === "audio_mp3",
        merge_ext: opt.merge ? opt.ext : null,
      };
      const r = await post("/api/download", body);
      state.currentTaskId = r.task_id;
      startPolling(r.task_id);
    } catch (e) {
      els.taskStatus.textContent = "启动失败";
      showError(e.message);
    }
  }

  function startPolling(taskId) {
    stopPolling();
    state.pollTimer = setInterval(() => pollTask(taskId), 700);
    pollTask(taskId);
  }
  function stopPolling() {
    if (state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
  }

  async function pollTask(taskId) {
    try {
      const t = await api("/api/tasks/" + taskId);
      renderTaskProgress(t);
      if (t.status === "done" || t.status === "error" || t.status === "cancelled") {
        stopPolling();
        refreshHistory();
      }
    } catch (e) {
      /* 忽略瞬时错误，继续轮询 */
    }
  }

  function setProgress(pct, sizeText, speedText, etaText, fileText) {
    els.progressBar.style.width = Math.min(100, pct) + "%";
    els.progressPct.textContent = pct.toFixed(1) + "%";
    els.progressSize.textContent = sizeText || "";
    els.progressSpeed.textContent = speedText || "";
    els.progressEta.textContent = etaText || "";
    els.progressFile.textContent = fileText || "";
  }

  function renderTaskProgress(t) {
    els.taskStatus.textContent = STATUS_TEXT[t.status] || t.status;
    switch (t.status) {
      case "downloading":
        setProgress(
          t.progress || 0,
          fmtBytes(t.downloaded_bytes) + " / " + fmtBytes(t.total_bytes),
          fmtSpeed(t.speed),
          fmtEta(t.eta),
          t.current_file ? "正在下载：" + t.current_file : ""
        );
        break;
      case "processing":
        setProgress(99, "", "", "", "正在合并视频与音轨…");
        break;
      case "done": {
        setProgress(100, "", "", "", "");
        els.taskStatus.textContent = "✅ 下载完成";
        els.doneActions.classList.remove("hidden");
        els.downloadFileBtn.href = "/api/tasks/" + t.id + "/file";
        els.downloadFileBtn.setAttribute("download", "");
        els.cancelBtn.classList.add("hidden");
        break;
      }
      case "error":
        els.cancelBtn.classList.add("hidden");
        setProgress(0, "", "", "", "");
        showError(t.error || "下载失败，未知错误");
        break;
      case "cancelled":
        els.cancelBtn.classList.add("hidden");
        els.taskStatus.textContent = "已取消";
        break;
      default:
        setProgress(t.progress || 0, fmtBytes(t.downloaded_bytes) + " / " + fmtBytes(t.total_bytes), "", "", "");
    }
  }

  function showError(msg) {
    els.errorBox.textContent = msg;
    els.errorBox.classList.remove("hidden");
  }

  async function handleCancel() {
    if (!state.currentTaskId) return;
    try {
      await post("/api/tasks/" + state.currentTaskId + "/cancel");
      els.cancelBtn.disabled = true;
    } catch (e) { /* ignore */ }
  }

  async function openFolder() {
    if (!state.currentTaskId) return;
    try { await post("/api/tasks/" + state.currentTaskId + "/open"); } catch (e) { /* ignore */ }
  }

  /* ---------- 网络诊断 ---------- */
  async function runDiag() {
    const btn = els.diagBtn;
    btn.disabled = true;
    btn.textContent = "诊断中…";
    els.diagSummary.textContent = "";
    try {
      const d = await api("/api/diag");
      const results = d.results || [];
      const okCount = results.filter((r) => r.ok).length;
      const fail = results.filter((r) => !r.ok);
      const lines = results.map((r) =>
        (r.ok ? "✅" : "❌") + " " + r.host + "（" + r.note + "）" +
        (r.ok ? " · " + r.ms + "ms" : " · " + r.detail)
      );
      showBanner(
        "网络诊断：" + okCount + "/" + results.length + " 个站点可连接\n" +
        lines.join("\n") +
        (fail.length
          ? "\n\n若 B 站主站/API 不可连接，说明当前网络被 B 站拦截，" +
            "请在「高级选项」填写可用的代理地址后重试。"
          : ""),
        fail.length ? "warn" : "warn"
      );
    } catch (e) {
      showBanner("网络诊断失败：" + e.message, "warn");
    } finally {
      btn.disabled = false;
      btn.textContent = "网络诊断";
    }
  }

  /* ---------- 下载记录 ---------- */
  async function refreshHistory() {
    try {
      const tasks = await api("/api/tasks");
      if (!tasks.length) {
        els.history.classList.add("hidden");
        return;
      }
      els.history.classList.remove("hidden");
      els.historyList.innerHTML = "";
      tasks.slice(0, 20).forEach(renderHistoryItem);
    } catch (e) { /* ignore */ }
  }

  function renderHistoryItem(t) {
    const item = document.createElement("div");
    item.className = "history-item";
    const status = STATUS_TEXT[t.status] || t.status;
    const statusCls = t.status === "done" && t.can_download ? "done" : t.status;
    let actions = "";
    if (t.status === "done" && t.can_download) {
      actions +=
        '<a class="btn btn-primary btn-sm" href="/api/tasks/' + t.id + '/file" download>保存</a>' +
        '<button class="btn btn-ghost btn-sm" data-act="del">删除</button>';
    } else if (t.status === "error" || t.status === "cancelled") {
      actions += '<button class="btn btn-ghost btn-sm" data-act="del">删除</button>';
    } else {
      actions += '<button class="btn btn-ghost btn-sm" data-act="cancel" ' + (t.status === "processing" ? "disabled" : "") + '>取消</button>';
    }
    item.innerHTML =
      '<div class="h-title">' + esc(t.title || "未命名") + "</div>" +
      '<span class="h-status ' + statusCls + '">' + esc(status) + (t.status === "downloading" && t.progress ? " " + t.progress.toFixed(0) + "%" : "") + "</span>" +
      '<div class="h-actions">' + actions + "</div>";

    item.querySelectorAll("[data-act='del']").forEach((b) =>
      b.addEventListener("click", async () => {
        try {
          await api("/api/tasks/" + t.id, { method: "DELETE" });
          item.remove();
          refreshHistory();
        } catch (e) { alert("删除失败：" + e.message); }
      })
    );
    item.querySelectorAll("[data-act='cancel']").forEach((b) =>
      b.addEventListener("click", async () => {
        try { await post("/api/tasks/" + t.id + "/cancel"); } catch (e) { /* ignore */ }
      })
    );
    els.historyList.appendChild(item);
  }

  /* ---------- 事件绑定 ---------- */
  els.parseBtn.addEventListener("click", handleParse);
  els.diagBtn.addEventListener("click", runDiag);
  els.urlInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") handleParse();
  });
  els.downloadBtn.addEventListener("click", handleDownload);
  els.cancelBtn.addEventListener("click", handleCancel);
  els.openFolderBtn.addEventListener("click", openFolder);

  init();
})();
