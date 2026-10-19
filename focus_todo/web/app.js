(() => {
  const $ = (id) => document.getElementById(id);
  const CIRC = 2 * Math.PI * 52;

  const els = {
    banner: $("banner"),
    dateLine: $("date-line"),
    statFocus: $("stat-focus"),
    statMinutes: $("stat-minutes"),
    statPending: $("stat-pending"),
    time: $("time-display"),
    phase: $("phase-label"),
    ringFg: $("ring-fg"),
    ringWrap: document.querySelector(".ring-wrap"),
    startBtn: $("start-btn"),
    resetBtn: $("reset-btn"),
    focusTodo: $("focus-todo"),
    todoForm: $("todo-form"),
    todoInput: $("todo-input"),
    todoList: $("todo-list"),
    todoEmpty: $("todo-empty"),
    clearDone: $("clear-done-btn"),
    setFocus: $("set-focus"),
    setShort: $("set-short"),
    setLong: $("set-long"),
    setEvery: $("set-every"),
    saveSettings: $("save-settings"),
  };

  const state = {
    settings: {
      focus_minutes: 25,
      short_break_minutes: 5,
      long_break_minutes: 15,
      long_break_every: 4,
    },
    todos: [],
    stats: {},
    mode: "focus",
    running: false,
    remainingMs: 25 * 60 * 1000,
    durationMs: 25 * 60 * 1000,
    tickId: null,
    endAt: null,
    focusStreak: 0,
  };

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

  function modeMinutes(mode) {
    const s = state.settings;
    if (mode === "short_break") return s.short_break_minutes;
    if (mode === "long_break") return s.long_break_minutes;
    return s.focus_minutes;
  }

  function modeLabel(mode) {
    if (mode === "short_break") return "短休";
    if (mode === "long_break") return "长休";
    return "专注";
  }

  function formatMs(ms) {
    const total = Math.max(0, Math.ceil(ms / 1000));
    const m = Math.floor(total / 60);
    const s = total % 60;
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }

  function setMode(mode, { reset = true } = {}) {
    state.mode = mode;
    document.querySelectorAll(".mode-btn").forEach((btn) => {
      const active = btn.dataset.mode === mode;
      btn.classList.toggle("active", active);
      btn.classList.toggle("break", active && mode !== "focus");
    });
    const isBreak = mode !== "focus";
    els.ringWrap.classList.toggle("break", isBreak);
    if (reset) {
      stopTick();
      state.running = false;
      state.endAt = null;
      state.durationMs = modeMinutes(mode) * 60 * 1000;
      state.remainingMs = state.durationMs;
      els.startBtn.textContent = "开始";
      els.phase.textContent = `${modeLabel(mode)}待命`;
      renderTimer();
    }
  }

  function renderTimer() {
    els.time.textContent = formatMs(state.remainingMs);
    const ratio = state.durationMs > 0 ? state.remainingMs / state.durationMs : 0;
    els.ringFg.style.strokeDasharray = String(CIRC);
    els.ringFg.style.strokeDashoffset = String(CIRC * (1 - Math.min(1, Math.max(0, ratio))));
    document.title = state.running
      ? `${formatMs(state.remainingMs)} · ${modeLabel(state.mode)}`
      : "番茄钟 · 今日待办";
  }

  function stopTick() {
    if (state.tickId) {
      clearInterval(state.tickId);
      state.tickId = null;
    }
  }

  function playChime() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.type = "sine";
      o.frequency.value = state.mode === "focus" ? 880 : 660;
      g.gain.value = 0.0001;
      o.connect(g);
      g.connect(ctx.destination);
      const now = ctx.currentTime;
      g.gain.exponentialRampToValueAtTime(0.08, now + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, now + 0.7);
      o.start(now);
      o.stop(now + 0.75);
    } catch {
      // ignore audio failures
    }
  }

  async function notifyDone() {
    playChime();
    const title = `${modeLabel(state.mode)}结束`;
    const body =
      state.mode === "focus"
        ? "休息一下，或开始下一段专注。"
        : "可以开始下一段专注了。";
    showBanner(`${title} — ${body}`, "ok");
    if ("Notification" in window) {
      try {
        if (Notification.permission === "default") {
          await Notification.requestPermission();
        }
        if (Notification.permission === "granted") {
          new Notification(title, { body });
        }
      } catch {
        // ignore
      }
    }
  }

  async function onTimerFinished() {
    stopTick();
    state.running = false;
    state.remainingMs = 0;
    state.endAt = null;
    els.startBtn.textContent = "开始";
    renderTimer();
    els.phase.textContent = `${modeLabel(state.mode)}完成`;

    const todoId = els.focusTodo.value || null;
    try {
      await api("/api/pomodoro/complete", {
        method: "POST",
        body: JSON.stringify({
          mode: state.mode,
          minutes: modeMinutes(state.mode),
          todo_id: state.mode === "focus" ? todoId : null,
        }),
      });
      await loadToday(true);
    } catch (err) {
      showBanner(err.message || String(err), "error");
    }

    await notifyDone();

    if (state.mode === "focus") {
      state.focusStreak += 1;
      const every = state.settings.long_break_every || 4;
      const next = state.focusStreak % every === 0 ? "long_break" : "short_break";
      setMode(next, { reset: true });
    } else {
      setMode("focus", { reset: true });
    }
  }

  function tick() {
    if (!state.running || !state.endAt) return;
    state.remainingMs = Math.max(0, state.endAt - Date.now());
    renderTimer();
    if (state.remainingMs <= 0) {
      onTimerFinished();
    }
  }

  function toggleTimer() {
    if (state.running) {
      stopTick();
      state.running = false;
      if (state.endAt) {
        state.remainingMs = Math.max(0, state.endAt - Date.now());
      }
      state.endAt = null;
      els.startBtn.textContent = "继续";
      els.phase.textContent = `${modeLabel(state.mode)}已暂停`;
      renderTimer();
      return;
    }

    if (state.remainingMs <= 0) {
      state.durationMs = modeMinutes(state.mode) * 60 * 1000;
      state.remainingMs = state.durationMs;
    }
    state.running = true;
    state.endAt = Date.now() + state.remainingMs;
    els.startBtn.textContent = "暂停";
    els.phase.textContent = `${modeLabel(state.mode)}进行中`;
    stopTick();
    state.tickId = setInterval(tick, 250);
    tick();
    hideBanner();
  }

  function resetTimer() {
    setMode(state.mode, { reset: true });
    hideBanner();
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderStats(stats) {
    els.statFocus.textContent = String(stats.focus_completed || 0);
    els.statMinutes.textContent = String(stats.focus_minutes_total || 0);
    els.statPending.textContent = String(stats.pending || 0);
  }

  function renderFocusSelect() {
    const current = els.focusTodo.value;
    const pending = state.todos.filter((t) => !t.done);
    els.focusTodo.innerHTML =
      `<option value="">不关联</option>` +
      pending
        .map(
          (t) =>
            `<option value="${escapeHtml(t.id)}">${escapeHtml(t.text.slice(0, 40))}</option>`
        )
        .join("");
    if (current && pending.some((t) => t.id === current)) {
      els.focusTodo.value = current;
    }
  }

  function renderTodos() {
    const list = state.todos || [];
    els.todoEmpty.classList.toggle("hidden", list.length > 0);
    els.todoList.innerHTML = list
      .map((t) => {
        const pomos = t.pomos ? ` · 🍅 ${t.pomos}` : "";
        return `
        <article class="todo-item ${t.done ? "done" : ""}" data-id="${escapeHtml(t.id)}">
          <input type="checkbox" ${t.done ? "checked" : ""} data-action="toggle" aria-label="完成" />
          <div>
            <div class="todo-text">${escapeHtml(t.text)}</div>
            <div class="todo-meta">${escapeHtml((t.created_at || "").replace("T", " ").slice(0, 16))}${pomos}</div>
          </div>
          <button type="button" class="btn-danger-ghost" data-action="delete">删除</button>
        </article>`;
      })
      .join("");
    renderFocusSelect();
  }

  function fillSettings() {
    const s = state.settings;
    els.setFocus.value = s.focus_minutes;
    els.setShort.value = s.short_break_minutes;
    els.setLong.value = s.long_break_minutes;
    els.setEvery.value = s.long_break_every;
  }

  async function loadToday(quiet = false) {
    const data = await api("/api/today");
    state.settings = data.settings || state.settings;
    state.todos = data.todos || [];
    state.stats = data.stats || {};
    els.dateLine.textContent = `今天 ${data.date || ""}`;
    renderStats(state.stats);
    renderTodos();
    fillSettings();
    if (!state.running) {
      // 仅在未运行时同步当前模式时长（避免改设置打断计时）
      const mins = modeMinutes(state.mode);
      if (Math.abs(state.durationMs - mins * 60 * 1000) > 500) {
        state.durationMs = mins * 60 * 1000;
        state.remainingMs = state.durationMs;
        renderTimer();
      }
    }
    if (!quiet) hideBanner();
  }

  // events
  document.querySelectorAll(".mode-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (state.running) {
        showBanner("请先暂停或等当前计时结束，再切换模式", "error");
        return;
      }
      setMode(btn.dataset.mode, { reset: true });
    });
  });

  els.startBtn.addEventListener("click", toggleTimer);
  els.resetBtn.addEventListener("click", () => {
    if (state.running) {
      showBanner("请先暂停再重置", "error");
      return;
    }
    resetTimer();
  });

  els.todoForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = els.todoInput.value.trim();
    if (!text) return;
    try {
      await api("/api/todos", { method: "POST", body: JSON.stringify({ text }) });
      els.todoInput.value = "";
      await loadToday(true);
    } catch (err) {
      showBanner(err.message || String(err), "error");
    }
  });

  els.todoList.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-action]");
    if (!btn) return;
    const item = btn.closest(".todo-item");
    if (!item) return;
    const id = item.dataset.id;
    const action = btn.dataset.action;
    try {
      if (action === "delete") {
        await api(`/api/todos/${encodeURIComponent(id)}`, { method: "DELETE" });
      } else if (action === "toggle") {
        const checked = btn.checked;
        await api(`/api/todos/${encodeURIComponent(id)}`, {
          method: "PATCH",
          body: JSON.stringify({ done: checked }),
        });
      }
      await loadToday(true);
    } catch (err) {
      showBanner(err.message || String(err), "error");
      await loadToday(true);
    }
  });

  els.clearDone.addEventListener("click", async () => {
    try {
      const res = await api("/api/todos/clear-done", { method: "POST" });
      showBanner(`已清除 ${res.removed || 0} 条已完成`, "ok");
      await loadToday(true);
    } catch (err) {
      showBanner(err.message || String(err), "error");
    }
  });

  els.saveSettings.addEventListener("click", async () => {
    try {
      const settings = await api("/api/settings", {
        method: "PUT",
        body: JSON.stringify({
          focus_minutes: Number(els.setFocus.value),
          short_break_minutes: Number(els.setShort.value),
          long_break_minutes: Number(els.setLong.value),
          long_break_every: Number(els.setEvery.value),
        }),
      });
      state.settings = settings;
      fillSettings();
      if (!state.running) setMode(state.mode, { reset: true });
      showBanner("设置已保存", "ok");
    } catch (err) {
      showBanner(err.message || String(err), "error");
    }
  });

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && state.running) tick();
  });

  els.ringFg.style.strokeDasharray = String(CIRC);
  setMode("focus", { reset: true });
  loadToday(false).catch((err) => showBanner(err.message || String(err), "error"));
})();
