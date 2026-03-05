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
  settingsData: {},
  accountRows: {
    douyin: [],
    tiktok: [],
  },
  deletedRows: {
    douyin: [],
    tiktok: [],
  },
  activeTab: "workbench",
  selectionAnchors: {
    active: {
      douyin: null,
      tiktok: null,
    },
    deleted: {
      douyin: null,
      tiktok: null,
    },
  },
};

const refs = {
  tabButtons: Array.from(document.querySelectorAll(".tab-btn")),
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
  accountsSettingsBlock: document.getElementById("accounts-settings-block"),
  accountsToggleBtn: document.getElementById("accounts-toggle-btn"),
  accountsDouyinBody: document.getElementById("accounts-douyin-body"),
  accountsTiktokBody: document.getElementById("accounts-tiktok-body"),
  accountsDouyinAddBtn: document.getElementById("accounts-douyin-add-btn"),
  accountsTiktokAddBtn: document.getElementById("accounts-tiktok-add-btn"),
  accountsExportJsonBtn: document.getElementById("accounts-export-json-btn"),
  accountsImportJsonBtn: document.getElementById("accounts-import-json-btn"),
  accountsImportJsonFile: document.getElementById("accounts-import-json-file"),
  accountsIoStatus: document.getElementById("accounts-io-status"),
  accountsDouyinSearch: document.getElementById("accounts-douyin-search"),
  accountsTikTokSearch: document.getElementById("accounts-tiktok-search"),
  accountsDouyinFormatBtn: document.getElementById("accounts-douyin-format-btn"),
  accountsTikTokFormatBtn: document.getElementById("accounts-tiktok-format-btn"),
  accountsDouyinCheckBtn: document.getElementById("accounts-douyin-check-btn"),
  accountsTikTokCheckBtn: document.getElementById("accounts-tiktok-check-btn"),
  accountsDouyinSelectAllBtn: document.getElementById("accounts-douyin-select-all-btn"),
  accountsDouyinClearSelectBtn: document.getElementById("accounts-douyin-clear-select-btn"),
  accountsDouyinOpenSelectedBtn: document.getElementById("accounts-douyin-open-selected-btn"),
  accountsDouyinBatchEarliest: document.getElementById("accounts-douyin-batch-earliest"),
  accountsDouyinApplyEarliestBtn: document.getElementById("accounts-douyin-apply-earliest-btn"),
  accountsDouyinDeleteSelectedBtn: document.getElementById("accounts-douyin-delete-selected-btn"),
  accountsDouyinStatus: document.getElementById("accounts-douyin-status"),
  accountsTikTokSelectAllBtn: document.getElementById("accounts-tiktok-select-all-btn"),
  accountsTikTokClearSelectBtn: document.getElementById("accounts-tiktok-clear-select-btn"),
  accountsTikTokOpenSelectedBtn: document.getElementById("accounts-tiktok-open-selected-btn"),
  accountsTikTokBatchEarliest: document.getElementById("accounts-tiktok-batch-earliest"),
  accountsTikTokApplyEarliestBtn: document.getElementById("accounts-tiktok-apply-earliest-btn"),
  accountsTikTokDeleteSelectedBtn: document.getElementById("accounts-tiktok-delete-selected-btn"),
  accountsTikTokStatus: document.getElementById("accounts-tiktok-status"),
  deletedDouyinBody: document.getElementById("deleted-douyin-body"),
  deletedTikTokBody: document.getElementById("deleted-tiktok-body"),
  deletedDouyinSelectAllBtn: document.getElementById("deleted-douyin-select-all-btn"),
  deletedDouyinClearSelectBtn: document.getElementById("deleted-douyin-clear-select-btn"),
  deletedDouyinOpenSelectedBtn: document.getElementById("deleted-douyin-open-selected-btn"),
  deletedDouyinRestoreSelectedBtn: document.getElementById("deleted-douyin-restore-selected-btn"),
  deletedTikTokSelectAllBtn: document.getElementById("deleted-tiktok-select-all-btn"),
  deletedTikTokClearSelectBtn: document.getElementById("deleted-tiktok-clear-select-btn"),
  deletedTikTokOpenSelectedBtn: document.getElementById("deleted-tiktok-open-selected-btn"),
  deletedTikTokRestoreSelectedBtn: document.getElementById("deleted-tiktok-restore-selected-btn"),

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

  workflowAccountPlatform: document.getElementById("workflow-account-platform"),
  workflowAccountSource: document.getElementById("workflow-account-source"),
  workflowAccountCookie: document.getElementById("workflow-account-cookie"),
  workflowAccountProxy: document.getElementById("workflow-account-proxy"),
  workflowAccountRunBtn: document.getElementById("workflow-account-run-btn"),
  workflowAccountStatus: document.getElementById("workflow-account-status"),
  workflowAccountSummary: document.getElementById("workflow-account-summary"),

  workflowDetailPlatform: document.getElementById("workflow-detail-platform"),
  workflowDetailLinks: document.getElementById("workflow-detail-links"),
  workflowDetailCookie: document.getElementById("workflow-detail-cookie"),
  workflowDetailProxy: document.getElementById("workflow-detail-proxy"),
  workflowDetailRunBtn: document.getElementById("workflow-detail-run-btn"),
  workflowDetailStatus: document.getElementById("workflow-detail-status"),
  workflowDetailSummary: document.getElementById("workflow-detail-summary"),

  scheduleName: document.getElementById("schedule-name"),
  schedulePlatform: document.getElementById("schedule-platform"),
  scheduleSource: document.getElementById("schedule-source"),
  scheduleHour: document.getElementById("schedule-hour"),
  scheduleMinute: document.getElementById("schedule-minute"),
  scheduleCookie: document.getElementById("schedule-cookie"),
  scheduleProxy: document.getElementById("schedule-proxy"),
  scheduleCreateBtn: document.getElementById("schedule-create-btn"),
  scheduleRefreshBtn: document.getElementById("schedule-refresh-btn"),
  scheduleStatus: document.getElementById("schedule-status"),
  scheduleList: document.getElementById("schedule-list"),

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
  "/workflow/douyin/account_batch": {
    use_settings: false,
    items: [
      {
        mark: "",
        url: "https://www.douyin.com/user/MS4wLjABAAAA...",
        tab: "post",
        earliest: "",
        latest: "",
        enable: true,
      },
    ],
    cookie: "",
    proxy: "",
  },
  "/workflow/tiktok/account_batch": {
    use_settings: false,
    items: [
      {
        mark: "",
        url: "https://www.tiktok.com/@username",
        tab: "post",
        earliest: "",
        latest: "",
        enable: true,
      },
    ],
    cookie: "",
    proxy: "",
  },
  "/workflow/douyin/detail_links": {
    links: ["https://www.douyin.com/video/7399999999999999999"],
    cookie: "",
    proxy: "",
  },
  "/workflow/tiktok/detail_links": {
    links: ["https://www.tiktok.com/@username/video/7399999999999999999"],
    cookie: "",
    proxy: "",
  },
};

const ACCOUNTS_COLLAPSE_STORAGE_KEY = "webui.accounts.collapsed";
const ACTIVE_TAB_STORAGE_KEY = "webui.active.tab";

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

function switchTab(tab) {
  state.activeTab = tab;
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("hidden-panel", panel.dataset.tabPanel !== tab);
  });
  refs.tabButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.tabTarget === tab);
  });
  try {
    localStorage.setItem(ACTIVE_TAB_STORAGE_KEY, tab);
  } catch {}
}

function defaultAccountRow() {
  return {
    mark: "",
    url: "",
    tab: "post",
    earliest: "",
    latest: "",
    enable: true,
    selected: false,
  };
}

function normalizeAccountRows(rows) {
  if (!Array.isArray(rows)) {
    return [defaultAccountRow()];
  }
  const normalized = rows
    .filter((item) => item && typeof item === "object")
    .map((item) => ({
      mark: String(item.mark || "").trim(),
      url: String(item.url || "").trim(),
      tab: String(item.tab || "post").trim() || "post",
      earliest: String(item.earliest || "").trim(),
      latest: String(item.latest || "").trim(),
      enable: Boolean(item.enable ?? true),
      selected: Boolean(item.selected ?? false),
    }));
  return normalized.length ? normalized : [defaultAccountRow()];
}

function defaultDeletedRow() {
  return {
    mark: "",
    url: "",
    tab: "post",
    earliest: "",
    latest: "",
    enable: false,
    deleted_at: "",
    reason: "",
    selected: false,
  };
}

function normalizeDeletedRows(rows) {
  if (!Array.isArray(rows)) {
    return [];
  }
  return rows
    .filter((item) => item && typeof item === "object")
    .map((item) => ({
      mark: String(item.mark || "").trim(),
      url: String(item.url || "").trim(),
      tab: String(item.tab || "post").trim() || "post",
      earliest: String(item.earliest || "").trim(),
      latest: String(item.latest || "").trim(),
      enable: Boolean(item.enable ?? false),
      deleted_at: String(item.deleted_at || "").trim(),
      reason: String(item.reason || "").trim(),
      selected: Boolean(item.selected ?? false),
    }))
    .filter((item) => item.url);
}

function accountRowsKey(platform) {
  return platform === "tiktok" ? "tiktok" : "douyin";
}

function accountBodyRef(platform) {
  return platform === "tiktok" ? refs.accountsTiktokBody : refs.accountsDouyinBody;
}

function deletedBodyRef(platform) {
  return platform === "tiktok" ? refs.deletedTikTokBody : refs.deletedDouyinBody;
}

function escapeAttr(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function renderAccountRows(platform) {
  const key = accountRowsKey(platform);
  const body = accountBodyRef(platform);
  if (!body) {
    return;
  }
  const keyword =
    (platform === "tiktok" ? refs.accountsTikTokSearch?.value : refs.accountsDouyinSearch?.value) ||
    "";
  const query = keyword.trim().toLowerCase();
  const rows = state.accountRows[key];
  body.innerHTML = "";
  const fragment = document.createDocumentFragment();
  rows.forEach((item, index) => {
    const text = `${item.mark} ${item.url} ${item.tab} ${item.earliest} ${item.latest}`.toLowerCase();
    if (query && !text.includes(query)) {
      return;
    }
    const tr = document.createElement("tr");
    tr.dataset.platform = key;
    tr.dataset.index = String(index);
    tr.dataset.section = "active";
    tr.innerHTML = `
      <td>
        <input data-field="selected" type="checkbox" ${item.selected ? "checked" : ""} />
      </td>
      <td>
        <label class="switch">
          <input data-field="enable" type="checkbox" ${item.enable ? "checked" : ""} />
          <span class="switch-slider"></span>
        </label>
      </td>
      <td>
        <input data-field="mark" type="text" value="${escapeAttr(item.mark)}" placeholder="可选标识" />
      </td>
      <td>
        <input data-field="url" type="text" value="${escapeAttr(item.url)}" placeholder="账号主页链接" />
      </td>
      <td>
        <input data-field="tab" type="text" value="${escapeAttr(item.tab)}" placeholder="post/favorite/collection" />
      </td>
      <td>
        <input data-field="earliest" type="text" value="${escapeAttr(item.earliest)}" placeholder="YYYY/MM/DD" />
      </td>
      <td>
        <input data-field="latest" type="text" value="${escapeAttr(item.latest)}" placeholder="YYYY/MM/DD" />
      </td>
      <td>
        <button data-action="open-row" class="btn ghost" type="button">跳转</button>
        <button data-action="remove-row" class="btn ghost danger" type="button">删除</button>
      </td>
    `;
    fragment.appendChild(tr);
  });
  if (!fragment.childNodes.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="8"><span class="empty-tip">无匹配结果</span></td>`;
    fragment.appendChild(tr);
  }
  body.appendChild(fragment);
}

function renderDeletedRows(platform) {
  const key = accountRowsKey(platform);
  const body = deletedBodyRef(platform);
  if (!body) {
    return;
  }
  const keyword =
    (platform === "tiktok" ? refs.accountsTikTokSearch?.value : refs.accountsDouyinSearch?.value) ||
    "";
  const query = keyword.trim().toLowerCase();
  const rows = state.deletedRows[key];
  body.innerHTML = "";
  const fragment = document.createDocumentFragment();
  rows.forEach((item, index) => {
    const text = `${item.mark} ${item.url} ${item.tab} ${item.deleted_at} ${item.reason}`.toLowerCase();
    if (query && !text.includes(query)) {
      return;
    }
    const tr = document.createElement("tr");
    tr.dataset.platform = key;
    tr.dataset.index = String(index);
    tr.dataset.section = "deleted";
    tr.innerHTML = `
      <td>
        <input data-field="selected" type="checkbox" ${item.selected ? "checked" : ""} />
      </td>
      <td>${escapeAttr(item.mark)}</td>
      <td class="url-cell">${escapeAttr(item.url)}</td>
      <td>${escapeAttr(item.tab)}</td>
      <td>${escapeAttr(item.deleted_at || "-")}</td>
      <td>${escapeAttr(item.reason || "-")}</td>
      <td>
        <button data-action="open-row" class="btn ghost" type="button">跳转</button>
        <button data-action="restore-row" class="btn ghost" type="button">撤销</button>
      </td>
    `;
    fragment.appendChild(tr);
  });
  if (!fragment.childNodes.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="7"><span class="empty-tip">无匹配结果</span></td>`;
    fragment.appendChild(tr);
  }
  body.appendChild(fragment);
}

function setAccountRows(platform, rows) {
  const key = accountRowsKey(platform);
  state.accountRows[key] = normalizeAccountRows(rows);
  renderAccountRows(platform);
}

function setDeletedRows(platform, rows) {
  const key = accountRowsKey(platform);
  state.deletedRows[key] = normalizeDeletedRows(rows);
  renderDeletedRows(platform);
}

function addAccountRow(platform) {
  const key = accountRowsKey(platform);
  state.accountRows[key].unshift(defaultAccountRow());
  renderAccountRows(platform);
}

function removeAccountRow(platform, index, reason = "手动删除") {
  const key = accountRowsKey(platform);
  const rows = state.accountRows[key];
  if (!rows.length) {
    return;
  }
  const [removed] = rows.splice(index, 1);
  if (removed?.url) {
    state.deletedRows[key].unshift(
      defaultDeletedRow(),
    );
    state.deletedRows[key][0] = {
      ...state.deletedRows[key][0],
      ...removed,
      enable: false,
      selected: false,
      deleted_at: new Date().toISOString().slice(0, 19).replace("T", " "),
      reason,
    };
  }
  if (!rows.length) {
    rows.push(defaultAccountRow());
  }
  renderAccountRows(platform);
  renderDeletedRows(platform);
}

function updateAccountRow(platform, index, field, value, section = "active") {
  const key = accountRowsKey(platform);
  const source = section === "deleted" ? state.deletedRows[key] : state.accountRows[key];
  const row = source?.[index];
  if (!row) {
    return;
  }
  row[field] = value;
}

function restoreDeletedRow(platform, index) {
  const key = accountRowsKey(platform);
  const rows = state.deletedRows[key];
  const [row] = rows.splice(index, 1);
  if (row?.url) {
    state.accountRows[key].unshift({
      mark: row.mark,
      url: row.url,
      tab: row.tab || "post",
      earliest: row.earliest || "",
      latest: row.latest || "",
      enable: true,
      selected: false,
    });
  }
  if (!state.accountRows[key].length) {
    state.accountRows[key].push(defaultAccountRow());
  }
  renderAccountRows(platform);
  renderDeletedRows(platform);
}

function normalizeUrl(url) {
  const value = String(url || "").trim();
  if (!value) {
    return "";
  }
  try {
    const parsed = new URL(value);
    parsed.search = "";
    parsed.hash = "";
    return parsed.toString().replace(/\/$/, "");
  } catch {
    return value.split("?")[0].split("#")[0].replace(/\/$/, "");
  }
}

function formatAccountUrls(platform) {
  const key = accountRowsKey(platform);
  state.accountRows[key] = state.accountRows[key].map((item) => ({
    ...item,
    url: normalizeUrl(item.url),
  }));
  renderAccountRows(platform);
}

function selectedIndexes(platform, section = "active") {
  const key = accountRowsKey(platform);
  const rows = section === "deleted" ? state.deletedRows[key] : state.accountRows[key];
  return rows
    .map((item, index) => ({ selected: Boolean(item.selected), index }))
    .filter((item) => item.selected)
    .map((item) => item.index);
}

function sectionName(section = "active") {
  return section === "deleted" ? "deleted" : "active";
}

function getSelectionAnchor(platform, section = "active") {
  const key = accountRowsKey(platform);
  const sectionKey = sectionName(section);
  const value = state.selectionAnchors[sectionKey]?.[key];
  return Number.isInteger(value) ? value : null;
}

function setSelectionAnchor(platform, section = "active", index = null) {
  const key = accountRowsKey(platform);
  const sectionKey = sectionName(section);
  if (!state.selectionAnchors[sectionKey]) {
    state.selectionAnchors[sectionKey] = {};
  }
  state.selectionAnchors[sectionKey][key] = Number.isInteger(index) ? index : null;
}

function applySelectionRange(platform, section = "active", fromIndex, toIndex, selected = true) {
  const key = accountRowsKey(platform);
  const rows = section === "deleted" ? state.deletedRows[key] : state.accountRows[key];
  if (!rows.length) {
    return;
  }
  const start = Math.max(0, Math.min(rows.length - 1, Math.min(fromIndex, toIndex)));
  const end = Math.max(0, Math.min(rows.length - 1, Math.max(fromIndex, toIndex)));
  for (let index = start; index <= end; index += 1) {
    rows[index].selected = selected;
  }
  if (section === "deleted") {
    renderDeletedRows(platform);
  } else {
    renderAccountRows(platform);
  }
}

function selectAllRows(platform, section = "active", selected = true) {
  const key = accountRowsKey(platform);
  const rows = section === "deleted" ? state.deletedRows[key] : state.accountRows[key];
  rows.forEach((item) => {
    item.selected = selected;
  });
  setSelectionAnchor(platform, section, null);
  if (section === "deleted") {
    renderDeletedRows(platform);
  } else {
    renderAccountRows(platform);
  }
}

function openUrls(urls) {
  urls.filter(Boolean).forEach((url) => window.open(url, "_blank", "noopener,noreferrer"));
}

function applyBatchEarliest(platform, value) {
  const key = accountRowsKey(platform);
  const indexes = selectedIndexes(platform, "active");
  indexes.forEach((index) => {
    state.accountRows[key][index].earliest = value;
  });
  renderAccountRows(platform);
}

function collectAccountRows(platform) {
  const key = accountRowsKey(platform);
  return state.accountRows[key].map((item) => ({
    mark: String(item.mark || "").trim(),
    url: String(item.url || "").trim(),
    tab: String(item.tab || "post").trim() || "post",
    earliest: String(item.earliest || "").trim(),
    latest: String(item.latest || "").trim(),
    enable: Boolean(item.enable),
  }));
}

function collectDeletedRows(platform) {
  const key = accountRowsKey(platform);
  return state.deletedRows[key].map((item) => ({
    mark: String(item.mark || "").trim(),
    url: String(item.url || "").trim(),
    tab: String(item.tab || "post").trim() || "post",
    earliest: String(item.earliest || "").trim(),
    latest: String(item.latest || "").trim(),
    enable: false,
    deleted_at: String(item.deleted_at || "").trim(),
    reason: String(item.reason || "").trim(),
  }));
}

function setAccountsIoStatus(text) {
  if (!refs.accountsIoStatus) {
    return;
  }
  refs.accountsIoStatus.textContent = text;
}

function toggleAccountsSettings(forceCollapsed = null) {
  const block = refs.accountsSettingsBlock;
  if (!block) {
    return;
  }
  const nextCollapsed =
    typeof forceCollapsed === "boolean"
      ? forceCollapsed
      : !block.classList.contains("collapsed");
  block.classList.toggle("collapsed", nextCollapsed);
  if (refs.accountsToggleBtn) {
    refs.accountsToggleBtn.textContent = nextCollapsed ? "展开配置" : "收起配置";
  }
  try {
    localStorage.setItem(
      ACCOUNTS_COLLAPSE_STORAGE_KEY,
      nextCollapsed ? "1" : "0",
    );
  } catch {}
}

function accountExportPayload() {
  return {
    version: 1,
    generated_at: new Date().toISOString(),
    accounts_urls: collectAccountRows("douyin"),
    accounts_urls_tiktok: collectAccountRows("tiktok"),
    deleted_accounts: collectDeletedRows("douyin"),
    deleted_accounts_tiktok: collectDeletedRows("tiktok"),
  };
}

function exportAccountsJson() {
  const payload = accountExportPayload();
  const now = new Date();
  const pad = (value) => String(value).padStart(2, "0");
  const suffix = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(
    now.getHours(),
  )}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
  const filename = `accounts_urls_${suffix}.json`;
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  setAccountsIoStatus(
    `已导出 JSON：抖音 ${payload.accounts_urls.length} 条，TikTok ${payload.accounts_urls_tiktok.length} 条，删除区 ${
      payload.deleted_accounts.length + payload.deleted_accounts_tiktok.length
    } 条`,
  );
}

function parseImportedAccountPayload(parsed) {
  if (Array.isArray(parsed)) {
    return {
      accounts_urls: parsed,
      accounts_urls_tiktok: [],
      deleted_accounts: [],
      deleted_accounts_tiktok: [],
    };
  }
  if (!parsed || typeof parsed !== "object") {
    throw new Error("JSON 根节点必须为对象或数组");
  }
  const accountsDouyin =
    parsed.accounts_urls ??
    parsed.douyin ??
    parsed.douyin_accounts ??
    parsed.douyin_accounts_urls ??
    [];
  const accountsTikTok =
    parsed.accounts_urls_tiktok ??
    parsed.tiktok ??
    parsed.tiktok_accounts ??
    parsed.tiktok_accounts_urls ??
    [];
  if (!Array.isArray(accountsDouyin) || !Array.isArray(accountsTikTok)) {
    throw new Error("accounts_urls / accounts_urls_tiktok 必须是数组");
  }
  return {
    accounts_urls: accountsDouyin,
    accounts_urls_tiktok: accountsTikTok,
    deleted_accounts: parsed.deleted_accounts ?? [],
    deleted_accounts_tiktok: parsed.deleted_accounts_tiktok ?? [],
  };
}

async function importAccountsJsonFile(file) {
  if (!file) {
    return;
  }
  setAccountsIoStatus(`正在导入：${file.name}`);
  try {
    const text = await file.text();
    const parsed = JSON.parse(text);
    const extracted = parseImportedAccountPayload(parsed);
    setAccountRows("douyin", extracted.accounts_urls);
    setAccountRows("tiktok", extracted.accounts_urls_tiktok);
    setDeletedRows("douyin", extracted.deleted_accounts);
    setDeletedRows("tiktok", extracted.deleted_accounts_tiktok);
    setAccountsIoStatus(
      `导入成功：抖音 ${collectAccountRows("douyin").length} 条，TikTok ${collectAccountRows("tiktok").length} 条，删除区 ${
        collectDeletedRows("douyin").length + collectDeletedRows("tiktok").length
      } 条（记得点“保存配置”）`,
    );
    setApiStatus("就绪", "ok");
  } catch (error) {
    setAccountsIoStatus(`导入失败: ${error.message}`);
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

function mapSettingsToForm(settings) {
  state.settingsData = settings && typeof settings === "object" ? settings : {};
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

  setAccountRows("douyin", settings?.accounts_urls || []);
  setAccountRows("tiktok", settings?.accounts_urls_tiktok || []);
  setDeletedRows("douyin", settings?.deleted_accounts || []);
  setDeletedRows("tiktok", settings?.deleted_accounts_tiktok || []);
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
    accounts_urls: collectAccountRows("douyin"),
    accounts_urls_tiktok: collectAccountRows("tiktok"),
    deleted_accounts: collectDeletedRows("douyin"),
    deleted_accounts_tiktok: collectDeletedRows("tiktok"),
    ui_schedules: state.settingsData?.ui_schedules || [],
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

function accountStatusRef(platform) {
  return platform === "tiktok" ? refs.accountsTikTokStatus : refs.accountsDouyinStatus;
}

function setAccountStatus(platform, text) {
  const element = accountStatusRef(platform);
  if (element) {
    element.textContent = text;
  }
}

async function persistAccountTables(reason = "accounts_batch_edit") {
  const payload = {
    accounts_urls: collectAccountRows("douyin"),
    accounts_urls_tiktok: collectAccountRows("tiktok"),
    deleted_accounts: collectDeletedRows("douyin"),
    deleted_accounts_tiktok: collectDeletedRows("tiktok"),
    backup: true,
    reason,
  };
  const result = await fetchJson("/ui/api/accounts", {
    method: "PUT",
    headers: headerOptions(true),
    body: JSON.stringify(payload),
  });
  setAccountRows("douyin", result.accounts_urls || payload.accounts_urls);
  setAccountRows("tiktok", result.accounts_urls_tiktok || payload.accounts_urls_tiktok);
  setDeletedRows("douyin", result.deleted_accounts || payload.deleted_accounts);
  setDeletedRows("tiktok", result.deleted_accounts_tiktok || payload.deleted_accounts_tiktok);
  return result;
}

async function verifyAccounts(platform) {
  setAccountStatus(platform, "正在检测账号有效性…");
  try {
    await persistAccountTables("pre_verify_sync");
    const payload = {
      platform,
      use_settings: true,
      move_deleted: true,
    };
    const result = await fetchJson("/ui/api/accounts/verify", {
      method: "POST",
      headers: headerOptions(true),
      body: JSON.stringify(payload),
    });
    if (platform === "tiktok") {
      setAccountRows("tiktok", result.accounts || []);
      setDeletedRows("tiktok", result.deleted_accounts || []);
    } else {
      setAccountRows("douyin", result.accounts || []);
      setDeletedRows("douyin", result.deleted_accounts || []);
    }
    setAccountStatus(
      platform,
      `检测完成：${result.checked} 条，存在 ${result.exists}，失效 ${result.missing}，转移 ${result.moved_to_deleted}`,
    );
    setApiStatus("就绪", "ok");
  } catch (error) {
    setAccountStatus(platform, `检测失败: ${error.message}`);
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

async function enqueueTaskRequest(endpoint, payload) {
  const result = await fetchJson("/ui/api/tasks", {
    method: "POST",
    headers: headerOptions(true),
    body: JSON.stringify({
      endpoint,
      payload,
    }),
  });
  return result?.task;
}

async function runTaskRequest() {
  const endpoint = refs.taskEndpoint.value;
  refs.taskStatus.textContent = "任务入队中…";
  refs.taskSummary.textContent = "";
  try {
    const payload = parseTaskPayload(refs.taskPayload.value);
    const task = await enqueueTaskRequest(endpoint, payload);
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

function workflowAccountEndpoint(platform) {
  return platform === "tiktok"
    ? "/workflow/tiktok/account_batch"
    : "/workflow/douyin/account_batch";
}

function workflowDetailEndpoint(platform) {
  return platform === "tiktok"
    ? "/workflow/tiktok/detail_links"
    : "/workflow/douyin/detail_links";
}

async function runWorkflowAccountTask() {
  const platform = refs.workflowAccountPlatform.value;
  const source = refs.workflowAccountSource.value;
  refs.workflowAccountStatus.textContent = "正在创建账号批量任务…";
  refs.workflowAccountSummary.textContent = "";
  try {
    const useSettings = source === "settings";
    const payload = {
      use_settings: useSettings,
      items: useSettings
        ? []
        : collectAccountRows(platform === "tiktok" ? "tiktok" : "douyin"),
      cookie: refs.workflowAccountCookie.value.trim(),
      proxy: refs.workflowAccountProxy.value.trim(),
    };
    const endpoint = workflowAccountEndpoint(platform);
    const task = await enqueueTaskRequest(endpoint, payload);
    state.selectedTaskId = task?.task_id || "";
    refs.workflowAccountStatus.textContent = `任务已入队: ${task?.task_id || endpoint}`;
    refs.workflowAccountSummary.textContent = `${task?.status || "pending"} · ${
      task?.endpoint || endpoint
    }`;
    if (task) {
      renderTaskResult(task);
    }
    await loadTaskList();
    setApiStatus("就绪", "ok");
  } catch (error) {
    refs.workflowAccountStatus.textContent = `创建失败: ${error.message}`;
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

function parseWorkflowLinks(text) {
  return String(text || "")
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

async function runWorkflowDetailTask() {
  const platform = refs.workflowDetailPlatform.value;
  const links = parseWorkflowLinks(refs.workflowDetailLinks.value);
  if (!links.length) {
    refs.workflowDetailStatus.textContent = "请至少输入一条链接";
    refs.workflowDetailSummary.textContent = "";
    return;
  }
  refs.workflowDetailStatus.textContent = "正在创建链接下载任务…";
  refs.workflowDetailSummary.textContent = "";
  try {
    const endpoint = workflowDetailEndpoint(platform);
    const payload = {
      links,
      cookie: refs.workflowDetailCookie.value.trim(),
      proxy: refs.workflowDetailProxy.value.trim(),
    };
    const task = await enqueueTaskRequest(endpoint, payload);
    state.selectedTaskId = task?.task_id || "";
    refs.workflowDetailStatus.textContent = `任务已入队: ${task?.task_id || endpoint}`;
    refs.workflowDetailSummary.textContent = `${task?.status || "pending"} · ${
      task?.endpoint || endpoint
    } · ${links.length} 条链接`;
    if (task) {
      renderTaskResult(task);
    }
    await loadTaskList();
    setApiStatus("就绪", "ok");
  } catch (error) {
    refs.workflowDetailStatus.textContent = `创建失败: ${error.message}`;
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

function schedulePayloadFromForm() {
  const platform = refs.schedulePlatform.value;
  const useSettings = refs.scheduleSource.value === "settings";
  return {
    name: refs.scheduleName.value.trim(),
    platform,
    use_settings: useSettings,
    items: useSettings
      ? []
      : collectAccountRows(platform === "tiktok" ? "tiktok" : "douyin"),
    hour: Number(refs.scheduleHour.value || 0),
    minute: Number(refs.scheduleMinute.value || 0),
    cookie: refs.scheduleCookie.value.trim(),
    proxy: refs.scheduleProxy.value.trim(),
    enabled: true,
  };
}

function renderScheduleList(items) {
  if (!refs.scheduleList) {
    return;
  }
  refs.scheduleList.innerHTML = "";
  if (!Array.isArray(items) || !items.length) {
    refs.scheduleList.innerHTML =
      '<div class="task-row"><div class="task-main"><span class="task-endpoint">暂无定时任务</span></div></div>';
    return;
  }
  const fragment = document.createDocumentFragment();
  items.forEach((item) => {
    const row = document.createElement("div");
    row.className = "task-row";
    row.innerHTML = `
      <span class="task-status ${item.enabled ? "success" : "canceled"}">${
      item.enabled ? "enabled" : "disabled"
    }</span>
      <div class="task-main">
        <span class="task-id">${item.schedule_id || "-"}</span>
        <span class="task-endpoint">${item.name || "-"} · ${item.platform || "-"}</span>
        <span class="task-time">每日 ${String(item.hour).padStart(2, "0")}:${String(
      item.minute,
    ).padStart(2, "0")} · 下次 ${item.next_run_at || "-"}</span>
      </div>
      <div class="task-actions">
        <button class="btn ghost" data-action="run">立即执行</button>
        <button class="btn ghost" data-action="toggle">${
          item.enabled ? "停用" : "启用"
        }</button>
        <button class="btn ghost danger" data-action="delete">删除</button>
      </div>
    `;
    row.querySelector('[data-action="run"]')?.addEventListener("click", () => {
      runScheduleNow(item.schedule_id);
    });
    row.querySelector('[data-action="toggle"]')?.addEventListener("click", () => {
      toggleSchedule(item.schedule_id, !item.enabled);
    });
    row.querySelector('[data-action="delete"]')?.addEventListener("click", () => {
      deleteSchedule(item.schedule_id);
    });
    fragment.appendChild(row);
  });
  refs.scheduleList.appendChild(fragment);
}

async function loadSchedules() {
  try {
    const payload = await fetchJson("/ui/api/schedules", {
      method: "GET",
      headers: headerOptions(false),
    });
    state.settingsData.ui_schedules = payload.items || [];
    renderScheduleList(payload.items || []);
  } catch (error) {
    refs.scheduleStatus.textContent = `加载定时任务失败: ${error.message}`;
  }
}

async function createSchedule() {
  refs.scheduleStatus.textContent = "正在创建定时任务…";
  try {
    const payload = schedulePayloadFromForm();
    await fetchJson("/ui/api/schedules", {
      method: "POST",
      headers: headerOptions(true),
      body: JSON.stringify(payload),
    });
    refs.scheduleStatus.textContent = "定时任务创建成功";
    await loadSchedules();
    setApiStatus("就绪", "ok");
  } catch (error) {
    refs.scheduleStatus.textContent = `创建失败: ${error.message}`;
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

async function toggleSchedule(scheduleId, enabled) {
  try {
    await fetchJson(`/ui/api/schedules/${encodeURIComponent(scheduleId)}/toggle`, {
      method: "POST",
      headers: headerOptions(true),
      body: JSON.stringify({ enabled }),
    });
    await loadSchedules();
    refs.scheduleStatus.textContent = "定时任务状态已更新";
  } catch (error) {
    refs.scheduleStatus.textContent = `更新失败: ${error.message}`;
  }
}

async function runScheduleNow(scheduleId) {
  try {
    const result = await fetchJson(`/ui/api/schedules/${encodeURIComponent(scheduleId)}/run`, {
      method: "POST",
      headers: headerOptions(false),
    });
    refs.scheduleStatus.textContent = `已触发执行: ${scheduleId}`;
    if (result?.task) {
      renderTaskResult(result.task);
      await loadTaskList();
    }
  } catch (error) {
    refs.scheduleStatus.textContent = `触发失败: ${error.message}`;
  }
}

async function deleteSchedule(scheduleId) {
  try {
    await fetchJson(`/ui/api/schedules/${encodeURIComponent(scheduleId)}`, {
      method: "DELETE",
      headers: headerOptions(false),
    });
    refs.scheduleStatus.textContent = "定时任务已删除";
    await loadSchedules();
  } catch (error) {
    refs.scheduleStatus.textContent = `删除失败: ${error.message}`;
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
  refs.tabButtons.forEach((button) => {
    button.addEventListener("click", () => {
      switchTab(button.dataset.tabTarget || "workbench");
    });
  });

  refs.applyTokenBtn.addEventListener("click", () => {
    state.token = refs.tokenInput.value.trim();
    setApiStatus("令牌已应用", "ok");
    loadSettings();
    loadRawSettings();
    loadFiles();
    loadTaskList();
    loadSchedules();
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

  refs.accountsDouyinAddBtn.addEventListener("click", () => {
    addAccountRow("douyin");
  });

  refs.accountsTiktokAddBtn.addEventListener("click", () => {
    addAccountRow("tiktok");
  });

  refs.accountsToggleBtn.addEventListener("click", () => {
    toggleAccountsSettings();
  });

  refs.accountsExportJsonBtn.addEventListener("click", () => {
    exportAccountsJson();
  });

  refs.accountsImportJsonBtn.addEventListener("click", () => {
    refs.accountsImportJsonFile.value = "";
    refs.accountsImportJsonFile.click();
  });

  refs.accountsImportJsonFile.addEventListener("change", (event) => {
    const file = event.target.files?.[0];
    importAccountsJsonFile(file);
  });

  const bindAccountBodies = (body, section = "active") => {
    body.addEventListener("input", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement)) {
        return;
      }
      const row = target.closest("tr");
      if (!row) {
        return;
      }
      const platform = row.dataset.platform || "douyin";
      const index = Number(row.dataset.index || "0");
      const field = target.dataset.field || "";
      if (!field) {
        return;
      }
      const checkedFields = new Set(["enable", "selected"]);
      updateAccountRow(
        platform,
        index,
        field,
        checkedFields.has(field) ? target.checked : target.value,
        section,
      );
    });

    body.addEventListener("click", async (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      if (
        target instanceof HTMLInputElement &&
        target.dataset.field === "selected"
      ) {
        const row = target.closest("tr");
        if (!row) {
          return;
        }
        const platform = row.dataset.platform || "douyin";
        const index = Number(row.dataset.index || "-1");
        if (!Number.isInteger(index) || index < 0) {
          return;
        }
        if (event.shiftKey) {
          const anchor = getSelectionAnchor(platform, section);
          if (Number.isInteger(anchor)) {
            applySelectionRange(platform, section, anchor, index, target.checked);
          }
        }
        setSelectionAnchor(platform, section, index);
        return;
      }
      const action = target.dataset.action;
      if (!action) {
        return;
      }
      const row = target.closest("tr");
      if (!row) {
        return;
      }
      const platform = row.dataset.platform || "douyin";
      const index = Number(row.dataset.index || "0");
      if (action === "open-row") {
        const rows =
          section === "deleted"
            ? state.deletedRows[accountRowsKey(platform)]
            : state.accountRows[accountRowsKey(platform)];
        openUrls([rows[index]?.url || ""]);
        return;
      }
      if (action === "remove-row" && section === "active") {
        removeAccountRow(platform, index);
        const result = await persistAccountTables("account_remove_row");
        setAccountStatus(platform, `已删除并备份: ${result.backup_path || "-"}`);
        return;
      }
      if (action === "restore-row" && section === "deleted") {
        restoreDeletedRow(platform, index);
        const result = await persistAccountTables("account_restore_row");
        setAccountStatus(platform, `已撤销并备份: ${result.backup_path || "-"}`);
      }
    });
  };

  bindAccountBodies(refs.accountsDouyinBody, "active");
  bindAccountBodies(refs.accountsTiktokBody, "active");
  bindAccountBodies(refs.deletedDouyinBody, "deleted");
  bindAccountBodies(refs.deletedTikTokBody, "deleted");

  const bindSearch = (input, platform) => {
    input.addEventListener("input", () => {
      renderAccountRows(platform);
      renderDeletedRows(platform);
    });
  };
  bindSearch(refs.accountsDouyinSearch, "douyin");
  bindSearch(refs.accountsTikTokSearch, "tiktok");

  refs.accountsDouyinFormatBtn.addEventListener("click", async () => {
    formatAccountUrls("douyin");
    const result = await persistAccountTables("account_format_url");
    setAccountStatus("douyin", `URL 已规则化并备份: ${result.backup_path || "-"}`);
  });
  refs.accountsTikTokFormatBtn.addEventListener("click", async () => {
    formatAccountUrls("tiktok");
    const result = await persistAccountTables("account_format_url");
    setAccountStatus("tiktok", `URL 已规则化并备份: ${result.backup_path || "-"}`);
  });

  refs.accountsDouyinCheckBtn.addEventListener("click", () => verifyAccounts("douyin"));
  refs.accountsTikTokCheckBtn.addEventListener("click", () => verifyAccounts("tiktok"));

  refs.accountsDouyinSelectAllBtn.addEventListener("click", () =>
    selectAllRows("douyin", "active", true),
  );
  refs.accountsDouyinClearSelectBtn.addEventListener("click", () =>
    selectAllRows("douyin", "active", false),
  );
  refs.accountsTikTokSelectAllBtn.addEventListener("click", () =>
    selectAllRows("tiktok", "active", true),
  );
  refs.accountsTikTokClearSelectBtn.addEventListener("click", () =>
    selectAllRows("tiktok", "active", false),
  );

  refs.deletedDouyinSelectAllBtn.addEventListener("click", () =>
    selectAllRows("douyin", "deleted", true),
  );
  refs.deletedDouyinClearSelectBtn.addEventListener("click", () =>
    selectAllRows("douyin", "deleted", false),
  );
  refs.deletedTikTokSelectAllBtn.addEventListener("click", () =>
    selectAllRows("tiktok", "deleted", true),
  );
  refs.deletedTikTokClearSelectBtn.addEventListener("click", () =>
    selectAllRows("tiktok", "deleted", false),
  );

  refs.accountsDouyinOpenSelectedBtn.addEventListener("click", () => {
    const key = accountRowsKey("douyin");
    openUrls(
      selectedIndexes("douyin", "active").map((index) => state.accountRows[key][index]?.url || ""),
    );
  });
  refs.accountsTikTokOpenSelectedBtn.addEventListener("click", () => {
    const key = accountRowsKey("tiktok");
    openUrls(
      selectedIndexes("tiktok", "active").map((index) => state.accountRows[key][index]?.url || ""),
    );
  });

  refs.deletedDouyinOpenSelectedBtn.addEventListener("click", () => {
    const key = accountRowsKey("douyin");
    openUrls(
      selectedIndexes("douyin", "deleted").map(
        (index) => state.deletedRows[key][index]?.url || "",
      ),
    );
  });
  refs.deletedTikTokOpenSelectedBtn.addEventListener("click", () => {
    const key = accountRowsKey("tiktok");
    openUrls(
      selectedIndexes("tiktok", "deleted").map(
        (index) => state.deletedRows[key][index]?.url || "",
      ),
    );
  });

  refs.accountsDouyinApplyEarliestBtn.addEventListener("click", async () => {
    applyBatchEarliest("douyin", refs.accountsDouyinBatchEarliest.value.trim());
    const result = await persistAccountTables("account_batch_earliest");
    setAccountStatus("douyin", `批量 earliest 已保存: ${result.backup_path || "-"}`);
  });
  refs.accountsTikTokApplyEarliestBtn.addEventListener("click", async () => {
    applyBatchEarliest("tiktok", refs.accountsTikTokBatchEarliest.value.trim());
    const result = await persistAccountTables("account_batch_earliest");
    setAccountStatus("tiktok", `批量 earliest 已保存: ${result.backup_path || "-"}`);
  });

  refs.accountsDouyinDeleteSelectedBtn.addEventListener("click", async () => {
    selectedIndexes("douyin", "active")
      .sort((a, b) => b - a)
      .forEach((index) => removeAccountRow("douyin", index, "批量删除"));
    const result = await persistAccountTables("account_batch_delete");
    setAccountStatus("douyin", `批量删除已保存: ${result.backup_path || "-"}`);
  });
  refs.accountsTikTokDeleteSelectedBtn.addEventListener("click", async () => {
    selectedIndexes("tiktok", "active")
      .sort((a, b) => b - a)
      .forEach((index) => removeAccountRow("tiktok", index, "批量删除"));
    const result = await persistAccountTables("account_batch_delete");
    setAccountStatus("tiktok", `批量删除已保存: ${result.backup_path || "-"}`);
  });

  refs.deletedDouyinRestoreSelectedBtn.addEventListener("click", async () => {
    selectedIndexes("douyin", "deleted")
      .sort((a, b) => b - a)
      .forEach((index) => restoreDeletedRow("douyin", index));
    const result = await persistAccountTables("account_batch_restore");
    setAccountStatus("douyin", `批量撤销已保存: ${result.backup_path || "-"}`);
  });
  refs.deletedTikTokRestoreSelectedBtn.addEventListener("click", async () => {
    selectedIndexes("tiktok", "deleted")
      .sort((a, b) => b - a)
      .forEach((index) => restoreDeletedRow("tiktok", index));
    const result = await persistAccountTables("account_batch_restore");
    setAccountStatus("tiktok", `批量撤销已保存: ${result.backup_path || "-"}`);
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

  refs.workflowAccountRunBtn.addEventListener("click", () => {
    runWorkflowAccountTask();
  });

  refs.workflowDetailRunBtn.addEventListener("click", () => {
    runWorkflowDetailTask();
  });

  refs.scheduleCreateBtn.addEventListener("click", () => {
    createSchedule();
  });

  refs.scheduleRefreshBtn.addEventListener("click", () => {
    loadSchedules();
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
  let activeTab = "workbench";
  try {
    activeTab = localStorage.getItem(ACTIVE_TAB_STORAGE_KEY) || "workbench";
  } catch {}
  switchTab(activeTab);
  let isCollapsed = false;
  try {
    isCollapsed = localStorage.getItem(ACCOUNTS_COLLAPSE_STORAGE_KEY) === "1";
  } catch {}
  toggleAccountsSettings(isCollapsed);
  setAccountRows("douyin", []);
  setAccountRows("tiktok", []);
  setDeletedRows("douyin", []);
  setDeletedRows("tiktok", []);
  loadTaskTemplate();
  connectLogSocket();
  startLogFallbackPolling();
  startTaskPolling();
  pollLogs();
  loadSettings();
  loadRawSettings();
  loadFiles();
  loadTaskList();
  loadSchedules();
}

bootstrap();
