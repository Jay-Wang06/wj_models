/* 本地笔记 - 前端逻辑 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);

  const els = {
    banner: $("banner"),
    captureInput: $("capture-input"),
    captureTags: $("capture-tags"),
    captureBtn: $("capture-btn"),
    searchInput: $("search-input"),
    tagCloud: $("tag-cloud"),
    listCount: $("list-count"),
    newBtn: $("new-btn"),
    noteList: $("note-list"),
    empty: $("empty"),
    editor: $("editor"),
    titleInput: $("title-input"),
    typeSelect: $("type-select"),
    tagsInput: $("tags-input"),
    urlInput: $("url-input"),
    bodyInput: $("body-input"),
    preview: $("preview"),
    previewToggle: $("preview-toggle"),
    saveBtn: $("save-btn"),
    deleteBtn: $("delete-btn"),
    metaLine: $("meta-line"),
    editorBody: document.querySelector(".editor-body"),
  };

  let state = {
    notes: [],
    currentId: null,
    activeTag: "",
    previewOn: false,
    dirty: false,
  };

  const TYPE_LABEL = { note: "笔记", fleeting: "闪念", bookmark: "书签" };

  function showBanner(text, type) {
    els.banner.textContent = text;
    els.banner.className = "banner " + (type || "warn");
  }
  function hideBanner() {
    els.banner.classList.add("hidden");
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

  function parseTags(str) {
    return String(str || "")
      .split(/[,，\s]+/)
      .map((t) => t.trim().replace(/^#/, ""))
      .filter(Boolean);
  }

  function formatTime(iso) {
    if (!iso) return "";
    try {
      return new Date(iso).toLocaleString();
    } catch (_) {
      return iso;
    }
  }

  async function loadList() {
    const q = (els.searchInput.value || "").trim();
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (state.activeTag) params.set("tag", state.activeTag);
    const qs = params.toString();
    const data = await api("/api/notes" + (qs ? "?" + qs : ""));
    state.notes = data.items || [];
    renderList();
    await loadTags();
  }

  async function loadTags() {
    const data = await api("/api/tags");
    const items = data.items || [];
    els.tagCloud.innerHTML = "";
    const all = document.createElement("button");
    all.className = "tag-chip" + (!state.activeTag ? " active" : "");
    all.textContent = "全部";
    all.addEventListener("click", () => {
      state.activeTag = "";
      loadList();
    });
    els.tagCloud.appendChild(all);
    items.forEach((it) => {
      const btn = document.createElement("button");
      btn.className = "tag-chip" + (state.activeTag.toLowerCase() === it.tag.toLowerCase() ? " active" : "");
      btn.textContent = it.tag + " " + it.count;
      btn.addEventListener("click", () => {
        state.activeTag = it.tag;
        loadList();
      });
      els.tagCloud.appendChild(btn);
    });
  }

  function renderList() {
    els.listCount.textContent = state.notes.length + " 篇";
    els.noteList.innerHTML = "";
    if (!state.notes.length) {
      els.noteList.innerHTML = '<p style="color:var(--text-dim);font-size:13px;padding:8px">暂无笔记</p>';
      return;
    }
    state.notes.forEach((n) => {
      const el = document.createElement("div");
      el.className = "note-item" + (n.id === state.currentId ? " active" : "");
      el.innerHTML =
        "<h3></h3><div class='meta'></div><div class='excerpt'></div>";
      el.querySelector("h3").textContent = n.title || "未命名";
      const type = TYPE_LABEL[n.type] || n.type || "笔记";
      el.querySelector(".meta").innerHTML =
        '<span class="type-badge"></span>' + formatTime(n.updated_at || n.created_at);
      el.querySelector(".type-badge").textContent = type;
      el.querySelector(".excerpt").textContent = n.excerpt || "";
      el.addEventListener("click", () => openNote(n.id));
      els.noteList.appendChild(el);
    });
  }

  function syncUrlField() {
    const isBm = els.typeSelect.value === "bookmark";
    els.urlInput.classList.toggle("hidden", !isBm);
  }

  function renderPreview() {
    if (!state.previewOn) return;
    const md = els.bodyInput.value || "";
    els.preview.innerHTML = window.marked ? marked.parse(md) : md;
  }

  function setPreview(on) {
    state.previewOn = on;
    els.previewToggle.textContent = on ? "编辑" : "预览";
    els.editorBody.classList.toggle("split", on);
    els.preview.classList.toggle("hidden", !on);
    if (on) renderPreview();
  }

  function showEditor(note) {
    els.empty.classList.add("hidden");
    els.editor.classList.remove("hidden");
    state.currentId = note.id;
    els.titleInput.value = note.title || "";
    els.typeSelect.value = note.type || "note";
    els.tagsInput.value = (note.tags || []).join(", ");
    els.urlInput.value = note.url || "";
    els.bodyInput.value = note.body || "";
    els.metaLine.textContent =
      "创建 " +
      formatTime(note.created_at) +
      " · 更新 " +
      formatTime(note.updated_at);
    syncUrlField();
    setPreview(false);
    state.dirty = false;
    renderList();
  }

  async function openNote(id) {
    if (state.dirty && !confirm("当前笔记未保存，确定切换？")) return;
    hideBanner();
    try {
      const note = await api("/api/notes/" + id);
      showEditor(note);
    } catch (err) {
      showBanner(err.message || String(err), "error");
    }
  }

  async function newNote() {
    if (state.dirty && !confirm("当前笔记未保存，确定新建？")) return;
    hideBanner();
    try {
      const note = await api("/api/notes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: "未命名笔记",
          body: "# 未命名笔记\n\n",
          tags: [],
          type: "note",
        }),
      });
      showBanner("已新建", "ok");
      await loadList();
      showEditor(note);
    } catch (err) {
      showBanner(err.message || String(err), "error");
    }
  }

  async function saveNote() {
    if (!state.currentId) return;
    hideBanner();
    try {
      const note = await api("/api/notes/" + state.currentId, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: els.titleInput.value,
          body: els.bodyInput.value,
          tags: parseTags(els.tagsInput.value),
          type: els.typeSelect.value,
          url: els.typeSelect.value === "bookmark" ? els.urlInput.value : "",
        }),
      });
      state.dirty = false;
      showBanner("已保存", "ok");
      await loadList();
      showEditor(note);
    } catch (err) {
      showBanner(err.message || String(err), "error");
    }
  }

  async function deleteNote() {
    if (!state.currentId) return;
    if (!confirm("确定删除这篇笔记？")) return;
    try {
      await api("/api/notes/" + state.currentId, { method: "DELETE" });
      state.currentId = null;
      state.dirty = false;
      els.editor.classList.add("hidden");
      els.empty.classList.remove("hidden");
      showBanner("已删除", "ok");
      await loadList();
    } catch (err) {
      showBanner(err.message || String(err), "error");
    }
  }

  async function doCapture() {
    const text = (els.captureInput.value || "").trim();
    if (!text) {
      showBanner("请先粘贴文字或 URL", "warn");
      return;
    }
    hideBanner();
    try {
      const note = await api("/api/capture", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text,
          tags: parseTags(els.captureTags.value),
        }),
      });
      els.captureInput.value = "";
      showBanner(
        (note.type === "bookmark" ? "已存书签：" : "已存闪念：") + (note.title || ""),
        "ok"
      );
      await loadList();
      showEditor(note);
    } catch (err) {
      showBanner(err.message || String(err), "error");
    }
  }

  function markDirty() {
    state.dirty = true;
  }

  els.captureBtn.addEventListener("click", doCapture);
  els.captureInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      doCapture();
    }
  });
  els.newBtn.addEventListener("click", newNote);
  els.saveBtn.addEventListener("click", saveNote);
  els.deleteBtn.addEventListener("click", deleteNote);
  els.previewToggle.addEventListener("click", () => setPreview(!state.previewOn));
  els.typeSelect.addEventListener("change", () => {
    syncUrlField();
    markDirty();
  });
  els.titleInput.addEventListener("input", markDirty);
  els.tagsInput.addEventListener("input", markDirty);
  els.urlInput.addEventListener("input", markDirty);
  els.bodyInput.addEventListener("input", () => {
    markDirty();
    renderPreview();
  });

  let searchTimer = null;
  els.searchInput.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => loadList().catch((e) => showBanner(e.message, "error")), 220);
  });

  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
      if (!els.editor.classList.contains("hidden")) {
        e.preventDefault();
        saveNote();
      }
    }
  });

  loadList().catch((e) => showBanner(e.message || String(e), "error"));
})();
