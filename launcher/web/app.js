(() => {
  const $ = (id) => document.getElementById(id);
  const els = {
    grid: $("tool-grid"),
    banner: $("banner"),
    online: $("stat-online"),
    total: $("stat-total"),
    refresh: $("refresh-btn"),
    startAll: $("start-all-btn"),
  };

  let busy = false;
  let timer = null;

  function showBanner(text, kind = "") {
    els.banner.textContent = text;
    els.banner.classList.remove("hidden", "error", "ok");
    if (kind) els.banner.classList.add(kind);
  }

  function hideBanner() {
    els.banner.classList.add("hidden");
  }

  async function api(path, options) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    let data = null;
    try {
      data = await res.json();
    } catch {
      data = null;
    }
    if (!res.ok) {
      const detail = data && (data.detail || data.message);
      throw new Error(typeof detail === "string" ? detail : `请求失败 (${res.status})`);
    }
    return data;
  }

  function statusPill(tool) {
    if (!tool.exists) {
      return `<span class="pill miss"><span class="dot"></span>目录缺失</span>`;
    }
    if (tool.online) {
      const label = tool.healthy ? "运行中" : "端口占用";
      return `<span class="pill on"><span class="dot"></span>${label}</span>`;
    }
    return `<span class="pill off"><span class="dot"></span>未启动</span>`;
  }

  function renderCard(tool) {
    const accent = tool.accent || "#1f9d8f";
    const online = !!tool.online;
    const missing = !tool.exists;

    const openBtn = online
      ? `<a class="btn btn-primary btn-sm" href="${tool.url}" target="_blank" rel="noopener">打开</a>`
      : `<button class="btn btn-primary btn-sm" data-action="start" data-id="${tool.id}" ${missing ? "disabled" : ""}>启动</button>`;

    const stopBtn = online
      ? `<button class="btn btn-danger btn-sm" data-action="stop" data-id="${tool.id}">停止</button>`
      : "";

    return `
      <article class="card ${online ? "online" : ""}" data-id="${tool.id}">
        <div class="card-top">
          <div class="logo" style="background: linear-gradient(135deg, ${accent}, #0f172a);">${escapeHtml(tool.logo || "?")}</div>
          <div class="card-meta">
            <h2>${escapeHtml(tool.name)}</h2>
            <p>${escapeHtml(tool.desc || "")}</p>
          </div>
        </div>
        <div class="status-row">
          ${statusPill(tool)}
          <span class="pill">端口 ${tool.port}</span>
          <span class="pill">${escapeHtml(tool.dir)}</span>
          ${tool.has_venv ? "" : `<span class="pill miss"><span class="dot"></span>无 venv</span>`}
        </div>
        <div class="card-actions">
          ${openBtn}
          ${stopBtn}
        </div>
      </article>
    `;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function render(items) {
    const list = items || [];
    els.total.textContent = String(list.length);
    els.online.textContent = String(list.filter((t) => t.online).length);
    els.grid.innerHTML = list.map(renderCard).join("") || `<p class="subtitle">暂无工具配置</p>`;
  }

  async function refresh(quiet = false) {
    try {
      const data = await api("/api/tools");
      render(data.items || []);
      if (!quiet) hideBanner();
    } catch (err) {
      showBanner(err.message || String(err), "error");
    }
  }

  async function withBusy(fn) {
    if (busy) return;
    busy = true;
    els.refresh.disabled = true;
    els.startAll.disabled = true;
    try {
      await fn();
    } finally {
      busy = false;
      els.refresh.disabled = false;
      els.startAll.disabled = false;
    }
  }

  els.grid.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-action]");
    if (!btn) return;
    const id = btn.getAttribute("data-id");
    const action = btn.getAttribute("data-action");
    withBusy(async () => {
      btn.disabled = true;
      try {
        if (action === "start") {
          showBanner(`正在启动 ${id} …`);
          const res = await api(`/api/tools/${encodeURIComponent(id)}/start`, { method: "POST" });
          showBanner(res.message || "已启动", res.tool && res.tool.online ? "ok" : "");
        } else if (action === "stop") {
          showBanner(`正在停止 ${id} …`);
          const res = await api(`/api/tools/${encodeURIComponent(id)}/stop`, { method: "POST" });
          showBanner(res.message || "已停止", "ok");
        }
        await refresh(true);
      } catch (err) {
        showBanner(err.message || String(err), "error");
        await refresh(true);
      }
    });
  });

  els.refresh.addEventListener("click", () => withBusy(() => refresh(false)));

  els.startAll.addEventListener("click", () =>
    withBusy(async () => {
      showBanner("正在启动全部工具…");
      try {
        const res = await api("/api/tools/start-all", { method: "POST" });
        const items = res.items || [];
        const ok = items.filter((x) => x.ok).length;
        showBanner(`已处理 ${items.length} 个工具，成功 ${ok} 个`, "ok");
        // 依赖安装可能较慢，多刷几次
        await refresh(true);
        setTimeout(() => refresh(true), 2500);
        setTimeout(() => refresh(true), 6000);
      } catch (err) {
        showBanner(err.message || String(err), "error");
      }
    })
  );

  refresh(false);
  timer = setInterval(() => refresh(true), 4000);
  window.addEventListener("beforeunload", () => {
    if (timer) clearInterval(timer);
  });
})();
