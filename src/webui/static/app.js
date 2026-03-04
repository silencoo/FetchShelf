const state = {
  token: "",
  logAfterId: 0,
  logCount: 0,
  ws: null,
  wsActive: false,
  wsConnecting: false,
  autoScroll: true,
  currentScope: "download",
  currentPath: "",
  selectedFilePath: "",
  selectedTaskId: "",
};

const refs = {
  tokenInput: document.getElementById("token-input"),
  applyTokenBtn: document.getElementById("apply-token-btn"),
  wsStatus: document.getElementById("ws-status"),
  apiStatus: document.getElementById("api-status"),

  settingsForm: document.getElementById("settings-form"),
  settingsReloadBtn: document.getElementById("settings-reload-btn"),
  settingsSaveBtn: document.getElementById("settings-save-btn"),
  settingsStatus: document.getElementById("settings-status"),
  settingsRawEditor: document.getElementById("settings-raw-editor"),
  settingsRawLoadBtn: document.getElementById("settings-raw-load-btn"),
  settingsRawSaveBtn: document.getElementById("settings-raw-save-btn"),
  settingsRawFormatBtn: document.getElementById("settings-raw-format-btn"),
  settingsRawStatus: document.getElementById("settings-raw-status"),

  logStream: document.getElementById("log-stream"),
  logsAutoscroll: document.getElementById("logs-autoscroll"),
  logsClearBtn: document.getElementById("logs-clear-btn"),
  logCount: document.getElementById("log-count"),

  filesScope: document.getElementById("files-scope"),
  filesPath: document.getElementById("files-path"),
  filesOpenBtn: document.getElementById("files-open-btn"),
  filesUpBtn: document.getElementById("files-up-btn"),
  filesRefreshBtn: document.getElementById("files-refresh-btn"),
  filesMeta: document.getElementById("files-meta"),
  filesList: document.getElementById("files-list"),
  filePreview: document.getElementById("file-preview"),

  sharePlatform: document.getElementById("share-platform"),
  shareInput: document.getElementById("share-input"),
  shareResolveBtn: document.getElementById("share-resolve-btn"),
  shareCopyBtn: document.getElementById("share-copy-btn"),
  shareStatus: document.getElementById("share-status"),
  shareResult: document.getElementById("share-result"),

  taskEndpoint: document.getElementById("task-endpoint"),
  taskPayload: document.getElementById("task-payload"),
  taskTemplateBtn: document.getElementById("task-template-btn"),
  taskRunBtn: document.getElementById("task-run-btn"),
  taskCopyBtn: document.getElementById("task-copy-btn"),
  taskStatus: document.getElementById("task-status"),
  taskSummary: document.getElementById("task-summary"),
  taskResult: document.getElementById("task-result"),
  taskQueueRefreshBtn: document.getElementById("task-queue-refresh-btn"),
  taskQueueMeta: document.getElementById("task-queue-meta"),
  taskQueueList: document.getElementById("task-queue-list"),
};

const TASK_TEMPLATES = {
  "/douyin/detail": {
    detail_id: "7399999999999999999",
    cookie: "",
    proxy: "",
    source: false,
  },
  "/douyin/account": {
    sec_user_id: "MS4wLjABAAAA...",
    tab: "post",
    pages: 1,
    cookie: "",
    proxy: "",
    source: false,
  },
  "/douyin/mix": {
    mix_id: "7399999999999999999",
    detail_id: "",
    cursor: 0,
    count: 12,
    cookie: "",
    proxy: "",
    source: false,
  },
  "/douyin/live": {
    web_rid: "",
    cookie: "",
    proxy: "",
    source: false,
  },
  "/douyin/comment": {
    detail_id: "7399999999999999999",
    pages: 1,
    cursor: 0,
    count: 20,
    count_reply: 3,
    reply: false,
    cookie: "",
    proxy: "",
    source: false,
  },
  "/tiktok/detail": {
    detail_id: "7399999999999999999",
    cookie: "",
    proxy: "",
    source: false,
  },
  "/tiktok/account": {
    sec_user_id: "MS4wLjABAAAA...",
    tab: "post",
    pages: 1,
    cookie: "",
    proxy: "",
    source: false,
  },
  "/tiktok/mix": {
    mix_id: "7399999999999999999",
    cursor: 0,
    count: 30,
    cookie: "",
    proxy: "",
    source: false,
  },
  "/tiktok/live": {
    room_id: "",
    cookie: "",
    proxy: "",
    source: false,
  },
};

function setBadge(element, text, kind = "") {
  element.textContent = text;
  element.classList.remove("ok", "warn", "error");
  if (kind) {
    element.classList.add(kind);
  }
}

function setApiStatus(text, kind = "") {
  setBadge(refs.apiStatus, `API: ${text}`, kind);
}

function setWsStatus(text, kind = "") {
  setBadge(refs.wsStatus, `日志: ${text}`, kind);
}

function headerOptions(json = true) {
  const headers = {};
  if (json) {
    headers["Content-Type"] = "application/json";
  }
  if (state.token) {
    headers.token = state.token;
  }
  return headers;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const contentType = response.headers.get("content-type") || "";
  let payload = null;
  if (contentType.includes("application/json")) {
    payload = await response.json();
  } else {
    payload = await response.text();
  }
  if (!response.ok) {
    let detail = "请求失败";
    if (typeof payload === "string" && payload.trim()) {
      detail = payload;
    } else if (payload && typeof payload === "object") {
      detail = payload.detail || payload.message || JSON.stringify(payload);
    }
    throw new Error(detail);
  }
  return payload;
}

function parseLogPayload(payload) {
  if (!payload) {
    return [];
  }
  if (Array.isArray(payload)) {
    return payload;
  }
  if (Array.isArray(payload.logs)) {
    return payload.logs;
  }
  if (Array.isArray(payload.items)) {
    return payload.items;
  }
  if (Array.isArray(payload.data)) {
    return payload.data;
  }
  if (payload.id && payload.message) {
    return [payload];
  }
  return [];
}

function updateLogCount() {
  refs.logCount.textContent = `${state.logCount} 条日志`;
}

function appendLogs(logs) {
  if (!logs.length) {
    return;
  }
  const fragment = document.createDocumentFragment();
  for (const item of logs) {
    const row = document.createElement("p");
    const level = String(item.level || "INFO").toUpperCase();
    row.className = "log-row";
    row.dataset.level = level;
    row.textContent = `[${item.timestamp || "--"}] [${level}] ${item.message || ""}`;
    fragment.appendChild(row);
    const id = Number(item.id || 0);
    if (id > state.logAfterId) {
      state.logAfterId = id;
    }
    state.logCount += 1;
  }
  refs.logStream.appendChild(fragment);
  updateLogCount();
  if (state.autoScroll) {
    refs.logStream.scrollTop = refs.logStream.scrollHeight;
  }
}

function clearLogs() {
  refs.logStream.innerHTML = "";
  state.logCount = 0;
  updateLogCount();
}

async function pollLogs() {
  try {
    const query = new URLSearchParams({
      after_id: String(state.logAfterId),
      limit: "200",
    });
    const payload = await fetchJson(`/ui/api/logs?${query.toString()}`, {
      method: "GET",
      headers: headerOptions(false),
    });
    appendLogs(parseLogPayload(payload));
    setApiStatus("就绪", "ok");
  } catch (error) {
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

function closeLogSocket() {
  if (state.ws) {
    state.ws.close();
    state.ws = null;
    state.wsActive = false;
    state.wsConnecting = false;
  }
}

function connectLogSocket() {
  if (state.wsConnecting) {
    return;
  }
  closeLogSocket();
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const params = new URLSearchParams();
  params.set("after_id", String(state.logAfterId || 0));
  if (state.token) {
    params.set("token", state.token);
  }
  const wsUrl = `${protocol}//${location.host}/ui/ws/logs?${params.toString()}`;
  state.wsConnecting = true;
  const ws = new WebSocket(wsUrl);
  state.ws = ws;

  ws.addEventListener("open", () => {
    state.wsActive = true;
    state.wsConnecting = false;
    setWsStatus("WebSocket", "ok");
  });

  ws.addEventListener("message", (event) => {
    try {
      const payload = JSON.parse(event.data);
      appendLogs(parseLogPayload(payload));
    } catch {
      appendLogs([
        {
          id: 0,
          timestamp: new Date().toISOString().slice(0, 19).replace("T", " "),
          level: "INFO",
          message: String(event.data || ""),
        },
      ]);
    }
  });

  ws.addEventListener("close", () => {
    state.wsActive = false;
    state.wsConnecting = false;
    setWsStatus("轮询", "warn");
  });

  ws.addEventListener("error", () => {
    state.wsActive = false;
    state.wsConnecting = false;
    setWsStatus("轮询", "warn");
  });
}

function mapSettingsToForm(settings) {
  const fields = [
    "root",
    "folder_name",
    "storage_format",
    "proxy",
    "proxy_tiktok",
    "run_command",
  ];
  for (const name of fields) {
    const element = refs.settingsForm.elements.namedItem(name);
    if (!element) {
      continue;
    }
    element.value = settings?.[name] ?? "";
  }

  const boolFields = ["download", "folder_mode", "music", "dynamic_cover", "static_cover"];
  for (const name of boolFields) {
    const element = refs.settingsForm.elements.namedItem(name);
    if (!element) {
      continue;
    }
    element.checked = Boolean(settings?.[name]);
  }
}

function collectSettingsPayload() {
  const formData = new FormData(refs.settingsForm);
  const payload = {
    root: String(formData.get("root") || "").trim(),
    folder_name: String(formData.get("folder_name") || "").trim(),
    storage_format: String(formData.get("storage_format") || "").trim(),
    proxy: String(formData.get("proxy") || "").trim(),
    proxy_tiktok: String(formData.get("proxy_tiktok") || "").trim(),
    run_command: String(formData.get("run_command") || "").trim(),
    download: refs.settingsForm.elements.namedItem("download").checked,
    folder_mode: refs.settingsForm.elements.namedItem("folder_mode").checked,
    music: refs.settingsForm.elements.namedItem("music").checked,
    dynamic_cover: refs.settingsForm.elements.namedItem("dynamic_cover").checked,
    static_cover: refs.settingsForm.elements.namedItem("static_cover").checked,
  };
  return payload;
}

async function loadSettings() {
  refs.settingsStatus.textContent = "正在加载配置…";
  try {
    const settings = await fetchJson("/settings", {
      method: "GET",
      headers: headerOptions(false),
    });
    mapSettingsToForm(settings);
    refs.settingsStatus.textContent = "配置已加载";
    setApiStatus("就绪", "ok");
  } catch (error) {
    refs.settingsStatus.textContent = `加载失败: ${error.message}`;
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

async function saveSettings() {
  refs.settingsStatus.textContent = "正在保存配置…";
  try {
    const payload = collectSettingsPayload();
    const settings = await fetchJson("/settings", {
      method: "POST",
      headers: headerOptions(true),
      body: JSON.stringify(payload),
    });
    mapSettingsToForm(settings);
    refs.settingsStatus.textContent = "保存成功";
    setApiStatus("就绪", "ok");
  } catch (error) {
    refs.settingsStatus.textContent = `保存失败: ${error.message}`;
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

async function loadRawSettings() {
  refs.settingsRawStatus.textContent = "正在读取 settings.json 原文…";
  try {
    const payload = await fetchJson("/ui/api/settings/raw", {
      method: "GET",
      headers: headerOptions(false),
    });
    refs.settingsRawEditor.value = String(payload?.text || "");
    refs.settingsRawStatus.textContent = `已加载: ${payload?.path || ""}`;
    setApiStatus("就绪", "ok");
  } catch (error) {
    refs.settingsRawStatus.textContent = `读取失败: ${error.message}`;
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

function formatRawSettings() {
  try {
    const parsed = JSON.parse(refs.settingsRawEditor.value || "{}");
    refs.settingsRawEditor.value = JSON.stringify(parsed, null, 2);
    refs.settingsRawStatus.textContent = "JSON 格式化完成";
  } catch (error) {
    refs.settingsRawStatus.textContent = `格式化失败: ${error.message}`;
  }
}

async function saveRawSettings() {
  refs.settingsRawStatus.textContent = "正在保存 settings.json 原文…";
  try {
    const text = refs.settingsRawEditor.value || "{}";
    const payload = await fetchJson("/ui/api/settings/raw", {
      method: "PUT",
      headers: headerOptions(true),
      body: JSON.stringify({ text }),
    });
    refs.settingsRawStatus.textContent = payload?.message || "保存成功";
    if (payload?.settings) {
      mapSettingsToForm(payload.settings);
    } else {
      await loadSettings();
    }
    setApiStatus("就绪", "ok");
  } catch (error) {
    refs.settingsRawStatus.textContent = `保存失败: ${error.message}`;
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

function normalizeEntries(payload) {
  if (!payload) {
    return { entries: [], currentPath: "", total: 0 };
  }
  if (Array.isArray(payload)) {
    return {
      entries: payload,
      currentPath: state.currentPath,
      total: payload.length,
    };
  }
  return {
    entries: payload.entries || payload.items || payload.data || [],
    currentPath: payload.current_path ?? payload.path ?? state.currentPath,
    total: payload.total ?? (payload.entries || payload.items || payload.data || []).length,
  };
}

function iconForEntry(entry) {
  if (entry.is_dir || entry.kind === "dir") {
    return "📁";
  }
  if (entry.kind === "image") {
    return "🖼️";
  }
  if (entry.kind === "video") {
    return "🎬";
  }
  if (entry.kind === "audio") {
    return "🎵";
  }
  if (entry.kind === "text") {
    return "📄";
  }
  return "📦";
}

function renderFilePreview(entry) {
  refs.filePreview.innerHTML = "";
  const title = document.createElement("div");
  title.className = "status-line";
  title.textContent = `${entry.name} (${entry.kind || "file"})`;
  refs.filePreview.appendChild(title);

  if (entry.is_dir || entry.kind === "dir") {
    const tip = document.createElement("div");
    tip.className = "empty-tip";
    tip.textContent = "目录不支持预览";
    refs.filePreview.appendChild(tip);
    return;
  }

  const fileUrl = `/ui/api/file?scope=${encodeURIComponent(state.currentScope)}&path=${encodeURIComponent(
    entry.path || "",
  )}`;

  if (entry.kind === "image") {
    const image = document.createElement("img");
    image.src = fileUrl;
    image.alt = entry.name;
    refs.filePreview.appendChild(image);
    return;
  }

  if (entry.kind === "video") {
    const video = document.createElement("video");
    video.src = fileUrl;
    video.controls = true;
    refs.filePreview.appendChild(video);
    return;
  }

  if (entry.kind === "audio") {
    const audio = document.createElement("audio");
    audio.src = fileUrl;
    audio.controls = true;
    refs.filePreview.appendChild(audio);
    return;
  }

  if (entry.kind === "text") {
    fetch(fileUrl, {
      headers: headerOptions(false),
    })
      .then((response) => response.text())
      .then((text) => {
        const pre = document.createElement("pre");
        pre.textContent = text.slice(0, 12000);
        refs.filePreview.appendChild(pre);
      })
      .catch((error) => {
        const tip = document.createElement("div");
        tip.className = "empty-tip";
        tip.textContent = `文本预览失败: ${error.message}`;
        refs.filePreview.appendChild(tip);
      });
    return;
  }

  const link = document.createElement("a");
  link.href = fileUrl;
  link.textContent = "打开文件";
  link.target = "_blank";
  link.rel = "noreferrer";
  refs.filePreview.appendChild(link);
}

function renderFiles(entries) {
  refs.filesList.innerHTML = "";
  if (!entries.length) {
    refs.filesList.innerHTML = `<div class="file-row"><span class="file-name">目录为空</span></div>`;
    return;
  }

  const fragment = document.createDocumentFragment();
  for (const entry of entries) {
    const row = document.createElement("div");
    row.className = "file-row";
    row.dataset.path = entry.path || "";

    const icon = document.createElement("span");
    icon.textContent = iconForEntry(entry);

    const name = document.createElement("span");
    name.className = "file-name";
    name.textContent = entry.name || entry.path || "(unknown)";

    const kind = document.createElement("span");
    kind.className = "file-kind";
    kind.textContent = entry.kind || (entry.is_dir ? "dir" : "file");

    row.appendChild(icon);
    row.appendChild(name);
    row.appendChild(kind);

    row.addEventListener("click", () => {
      for (const active of refs.filesList.querySelectorAll(".file-row.active")) {
        active.classList.remove("active");
      }
      row.classList.add("active");
      state.selectedFilePath = entry.path || "";

      if (entry.is_dir || entry.kind === "dir") {
        state.currentPath = entry.path || "";
        refs.filesPath.value = state.currentPath;
        loadFiles();
      } else {
        renderFilePreview(entry);
      }
    });

    fragment.appendChild(row);
  }
  refs.filesList.appendChild(fragment);
}

async function loadFiles() {
  refs.filesMeta.textContent = "正在加载目录…";
  refs.filePreview.innerHTML = '<div class="empty-tip">选择文件后显示预览</div>';
  try {
    const query = new URLSearchParams({
      scope: state.currentScope,
      path: state.currentPath || "",
    });
    const payload = await fetchJson(`/ui/api/files?${query.toString()}`, {
      method: "GET",
      headers: headerOptions(false),
    });
    const normalized = normalizeEntries(payload);
    state.currentPath = normalized.currentPath || state.currentPath || "";
    refs.filesPath.value = state.currentPath;
    renderFiles(normalized.entries);
    refs.filesMeta.textContent = `scope=${state.currentScope} · path=/${state.currentPath || ""} · ${normalized.total} 项`;
    setApiStatus("就绪", "ok");
  } catch (error) {
    refs.filesList.innerHTML = "";
    refs.filesMeta.textContent = `加载失败: ${error.message}`;
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

function parentPath(path) {
  if (!path) {
    return "";
  }
  const items = path.split("/").filter(Boolean);
  items.pop();
  return items.join("/");
}

async function resolveShareLink() {
  const platform = refs.sharePlatform.value;
  const text = refs.shareInput.value.trim();
  if (!text) {
    refs.shareStatus.textContent = "请输入分享文本";
    return;
  }
  refs.shareStatus.textContent = "解析中…";
  refs.shareResult.textContent = "";
  refs.shareResult.removeAttribute("href");
  try {
    const payload = await fetchJson(`/${platform}/share`, {
      method: "POST",
      headers: headerOptions(true),
      body: JSON.stringify({ text }),
    });
    const url = payload?.url || "";
    refs.shareStatus.textContent = payload?.message || "解析完成";
    if (url) {
      refs.shareResult.textContent = url;
      refs.shareResult.href = url;
    }
    setApiStatus("就绪", "ok");
  } catch (error) {
    refs.shareStatus.textContent = `解析失败: ${error.message}`;
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

async function copyShareResult() {
  const text = refs.shareResult.textContent?.trim();
  if (!text) {
    refs.shareStatus.textContent = "暂无可复制结果";
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    refs.shareStatus.textContent = "结果已复制";
  } catch (error) {
    refs.shareStatus.textContent = `复制失败: ${error.message}`;
  }
}

function getTaskTemplate(endpoint) {
  const template = TASK_TEMPLATES[endpoint] || {
    cookie: "",
    proxy: "",
    source: false,
  };
  return JSON.stringify(template, null, 2);
}

function loadTaskTemplate() {
  refs.taskPayload.value = getTaskTemplate(refs.taskEndpoint.value);
  refs.taskStatus.textContent = "已加载模板，可直接修改后执行";
}

function summarizeTaskResponse(payload) {
  const parts = [];
  if (payload?.message) {
    parts.push(`message: ${payload.message}`);
  }
  if (Array.isArray(payload?.data)) {
    parts.push(`data items: ${payload.data.length}`);
  } else if (payload?.data && typeof payload.data === "object") {
    parts.push(`data fields: ${Object.keys(payload.data).length}`);
  } else if (payload?.url) {
    parts.push("url ready");
  }
  if (payload?.time) {
    parts.push(`time: ${payload.time}`);
  }
  return parts.join(" · ");
}

function parseTaskPayload(text) {
  if (!text.trim()) {
    return {};
  }
  let payload = {};
  try {
    payload = JSON.parse(text);
  } catch (error) {
    throw new Error(`Payload JSON 解析失败: ${error.message}`);
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("Payload 必须是 JSON 对象");
  }
  return payload;
}

async function runTaskRequest() {
  const endpoint = refs.taskEndpoint.value;
  refs.taskStatus.textContent = "任务入队中…";
  refs.taskSummary.textContent = "";
  try {
    const payload = parseTaskPayload(refs.taskPayload.value);
    const result = await fetchJson("/ui/api/tasks", {
      method: "POST",
      headers: headerOptions(true),
      body: JSON.stringify({
        endpoint,
        payload,
      }),
    });
    const task = result?.task;
    state.selectedTaskId = task?.task_id || "";
    refs.taskStatus.textContent = `已入队: ${state.selectedTaskId || endpoint}`;
    refs.taskSummary.textContent = task
      ? `${task.task_id} · ${task.status} · ${task.endpoint}`
      : "";
    if (task) {
      refs.taskResult.textContent = JSON.stringify(task, null, 2);
    }
    await loadTaskList();
    setApiStatus("就绪", "ok");
  } catch (error) {
    refs.taskStatus.textContent = `执行失败: ${error.message}`;
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

function renderTaskResult(task) {
  if (!task) {
    return;
  }
  state.selectedTaskId = task.task_id || "";
  refs.taskSummary.textContent = `${task.task_id || "-"} · ${task.status || "-"} · ${
    task.endpoint || "-"
  }`;
  refs.taskStatus.textContent =
    task.message || task.error || `任务状态: ${task.status || "-"}`;
  if (typeof task.result !== "undefined" && task.result !== null) {
    refs.taskResult.textContent = JSON.stringify(task.result, null, 2);
    return;
  }
  if (task.error) {
    refs.taskResult.textContent = JSON.stringify(
      {
        error: task.error,
      },
      null,
      2,
    );
    return;
  }
  refs.taskResult.textContent = "暂无结果";
}

async function taskControl(taskId, action) {
  try {
    const result = await fetchJson(`/ui/api/tasks/${encodeURIComponent(taskId)}/${action}`, {
      method: "POST",
      headers: headerOptions(false),
    });
    if (result?.task) {
      renderTaskResult(result.task);
    }
    await loadTaskList();
    setApiStatus("就绪", "ok");
  } catch (error) {
    refs.taskStatus.textContent = `${action} 失败: ${error.message}`;
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

function renderTaskList(items) {
  refs.taskQueueList.innerHTML = "";
  if (!Array.isArray(items) || !items.length) {
    refs.taskQueueList.innerHTML =
      '<div class="task-row"><div class="task-main"><span class="task-endpoint">暂无任务</span></div></div>';
    return;
  }
  const fragment = document.createDocumentFragment();
  for (const task of items) {
    const row = document.createElement("div");
    row.className = "task-row";
    row.dataset.taskId = task.task_id || "";

    const status = document.createElement("span");
    status.className = `task-status ${task.status || ""}`;
    status.textContent = task.status || "-";

    const main = document.createElement("div");
    main.className = "task-main";
    main.innerHTML = `
      <span class="task-id">${task.task_id || "-"}</span>
      <span class="task-endpoint">${task.endpoint || "-"}</span>
      <span class="task-time">${task.updated_at || task.created_at || ""}</span>
    `;

    const actions = document.createElement("div");
    actions.className = "task-actions";

    const viewBtn = document.createElement("button");
    viewBtn.className = "btn ghost";
    viewBtn.textContent = "查看";
    viewBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      renderTaskResult(task);
    });
    actions.appendChild(viewBtn);

    if (["pending", "running", "canceling"].includes(task.status)) {
      const cancelBtn = document.createElement("button");
      cancelBtn.className = "btn ghost";
      cancelBtn.textContent = "取消";
      cancelBtn.addEventListener("click", (event) => {
        event.stopPropagation();
        taskControl(task.task_id, "cancel");
      });
      actions.appendChild(cancelBtn);
    } else {
      const retryBtn = document.createElement("button");
      retryBtn.className = "btn ghost";
      retryBtn.textContent = "重试";
      retryBtn.addEventListener("click", (event) => {
        event.stopPropagation();
        taskControl(task.task_id, "retry");
      });
      actions.appendChild(retryBtn);
    }

    row.appendChild(status);
    row.appendChild(main);
    row.appendChild(actions);

    row.addEventListener("click", () => {
      renderTaskResult(task);
    });

    fragment.appendChild(row);
  }
  refs.taskQueueList.appendChild(fragment);
}

async function loadTaskList() {
  try {
    const payload = await fetchJson("/ui/api/tasks?limit=120", {
      method: "GET",
      headers: headerOptions(false),
    });
    const items = payload?.items || [];
    renderTaskList(items);
    refs.taskQueueMeta.textContent = `任务: ${payload?.count ?? items.length} · pending: ${
      payload?.pending ?? 0
    } · running: ${payload?.running ?? 0}`;
    if (state.selectedTaskId) {
      const selected = items.find((item) => item.task_id === state.selectedTaskId);
      if (selected) {
        renderTaskResult(selected);
      }
    }
  } catch (error) {
    refs.taskQueueMeta.textContent = `队列加载失败: ${error.message}`;
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

async function copyTaskResult() {
  const text = refs.taskResult.textContent?.trim();
  if (!text) {
    refs.taskStatus.textContent = "暂无可复制内容";
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    refs.taskStatus.textContent = "结果已复制";
  } catch (error) {
    refs.taskStatus.textContent = `复制失败: ${error.message}`;
  }
}

function bindEvents() {
  refs.applyTokenBtn.addEventListener("click", () => {
    state.token = refs.tokenInput.value.trim();
    setApiStatus("令牌已应用", "ok");
    loadSettings();
    loadRawSettings();
    loadFiles();
    loadTaskList();
    connectLogSocket();
  });

  refs.logsAutoscroll.addEventListener("change", (event) => {
    state.autoScroll = Boolean(event.target.checked);
  });

  refs.logsClearBtn.addEventListener("click", () => {
    clearLogs();
  });

  refs.settingsReloadBtn.addEventListener("click", () => {
    loadSettings();
  });

  refs.settingsSaveBtn.addEventListener("click", () => {
    saveSettings();
  });

  refs.settingsRawLoadBtn.addEventListener("click", () => {
    loadRawSettings();
  });

  refs.settingsRawFormatBtn.addEventListener("click", () => {
    formatRawSettings();
  });

  refs.settingsRawSaveBtn.addEventListener("click", () => {
    saveRawSettings();
  });

  refs.filesScope.addEventListener("change", () => {
    state.currentScope = refs.filesScope.value;
    state.currentPath = "";
    refs.filesPath.value = "";
    loadFiles();
  });

  refs.filesOpenBtn.addEventListener("click", () => {
    state.currentPath = refs.filesPath.value.trim();
    loadFiles();
  });

  refs.filesUpBtn.addEventListener("click", () => {
    state.currentPath = parentPath(state.currentPath);
    refs.filesPath.value = state.currentPath;
    loadFiles();
  });

  refs.filesRefreshBtn.addEventListener("click", () => {
    loadFiles();
  });

  refs.shareResolveBtn.addEventListener("click", () => {
    resolveShareLink();
  });

  refs.shareCopyBtn.addEventListener("click", () => {
    copyShareResult();
  });

  refs.taskEndpoint.addEventListener("change", () => {
    loadTaskTemplate();
  });

  refs.taskTemplateBtn.addEventListener("click", () => {
    loadTaskTemplate();
  });

  refs.taskRunBtn.addEventListener("click", () => {
    runTaskRequest();
  });

  refs.taskCopyBtn.addEventListener("click", () => {
    copyTaskResult();
  });

  refs.taskQueueRefreshBtn.addEventListener("click", () => {
    loadTaskList();
  });
}

function startLogFallbackPolling() {
  setInterval(() => {
    if (!state.wsActive) {
      pollLogs();
    }
  }, 1500);

  setInterval(() => {
    if (!state.wsActive) {
      connectLogSocket();
    }
  }, 6000);
}

function startTaskPolling() {
  setInterval(() => {
    loadTaskList();
  }, 2000);
}

function bootstrap() {
  bindEvents();
  state.currentScope = refs.filesScope.value;
  state.currentPath = refs.filesPath.value.trim();
  loadTaskTemplate();
  connectLogSocket();
  startLogFallbackPolling();
  startTaskPolling();
  pollLogs();
  loadSettings();
  loadRawSettings();
  loadFiles();
  loadTaskList();
}

bootstrap();
