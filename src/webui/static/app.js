const state = {
  token: "",
  logAfterId: 0,
  logCount: 0,
  ws: null,
  wsActive: false,
  wsConnecting: false,
  autoScroll: true,
  showDebugLogs: false,
  logRecords: [],
  fileEntries: [],
  fileSearch: "",
  currentScope: "download",
  currentPath: "",
  selectedFilePath: "",
  fileAccountContext: {
    platform: "",
    url: "",
    mark: "",
  },
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
  accountBoard: {
    platform: "douyin",
    page: 1,
    pageSize: 24,
    pages: 1,
    total: 0,
    columns: 4,
    refreshKind: "auto",
    viewMode: "avatar",
  },
  accountBoardDirty: true,
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
  accountsDouyinBatchField: document.getElementById("accounts-douyin-batch-field"),
  accountsDouyinBatchValue: document.getElementById("accounts-douyin-batch-value"),
  accountsDouyinApplyBatchBtn: document.getElementById("accounts-douyin-apply-batch-btn"),
  accountsDouyinDeleteSelectedBtn: document.getElementById("accounts-douyin-delete-selected-btn"),
  accountsDouyinStatus: document.getElementById("accounts-douyin-status"),
  accountsDouyinDuplicateStatus: document.getElementById("accounts-douyin-duplicate-status"),
  accountsTikTokSelectAllBtn: document.getElementById("accounts-tiktok-select-all-btn"),
  accountsTikTokClearSelectBtn: document.getElementById("accounts-tiktok-clear-select-btn"),
  accountsTikTokOpenSelectedBtn: document.getElementById("accounts-tiktok-open-selected-btn"),
  accountsTikTokBatchField: document.getElementById("accounts-tiktok-batch-field"),
  accountsTikTokBatchValue: document.getElementById("accounts-tiktok-batch-value"),
  accountsTikTokApplyBatchBtn: document.getElementById("accounts-tiktok-apply-batch-btn"),
  accountsTikTokDeleteSelectedBtn: document.getElementById("accounts-tiktok-delete-selected-btn"),
  accountsTikTokStatus: document.getElementById("accounts-tiktok-status"),
  accountsTikTokDuplicateStatus: document.getElementById("accounts-tiktok-duplicate-status"),
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
  boardPlatform: document.getElementById("board-platform"),
  boardPageSize: document.getElementById("board-page-size"),
  boardRefreshKind: document.getElementById("board-refresh-kind"),
  boardViewMode: document.getElementById("board-view-mode"),
  boardDensity: document.getElementById("board-density"),
  boardDensityLabel: document.getElementById("board-density-label"),
  boardPrevBtn: document.getElementById("board-prev-btn"),
  boardNextBtn: document.getElementById("board-next-btn"),
  boardReloadBtn: document.getElementById("board-reload-btn"),
  boardPinAllBtn: document.getElementById("board-pin-all-btn"),
  boardMeta: document.getElementById("board-meta"),
  boardStatus: document.getElementById("board-status"),
  boardGrid: document.getElementById("board-grid"),

  logStream: document.getElementById("log-stream"),
  logsAutoscroll: document.getElementById("logs-autoscroll"),
  logsDebugToggle: document.getElementById("logs-debug-toggle"),
  logsClearBtn: document.getElementById("logs-clear-btn"),
  logCount: document.getElementById("log-count"),

  filesScope: document.getElementById("files-scope"),
  filesPath: document.getElementById("files-path"),
  filesSearch: document.getElementById("files-search"),
  filesOpenBtn: document.getElementById("files-open-btn"),
  filesUpBtn: document.getElementById("files-up-btn"),
  filesRefreshBtn: document.getElementById("files-refresh-btn"),
  filesStatsRefreshBtn: document.getElementById("files-stats-refresh-btn"),
  filesMeta: document.getElementById("files-meta"),
  filesStats: document.getElementById("files-stats"),
  filesAccountContext: document.getElementById("files-account-context"),
  filesBackToBoardBtn: document.getElementById("files-back-to-board-btn"),
  filesPinProfileBtn: document.getElementById("files-pin-profile-btn"),
  filesGenerateAvatarBtn: document.getElementById("files-generate-avatar-btn"),
  filesPinAvatarBtn: document.getElementById("files-pin-avatar-btn"),
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
const LOG_DEBUG_STORAGE_KEY = "webui.logs.debug";
const BOARD_COLUMNS_STORAGE_KEY = "webui.board.columns";
const BOARD_VIEW_MODE_STORAGE_KEY = "webui.board.view_mode";

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

function shouldRenderLog(item) {
  const level = String(item?.level || "INFO").toUpperCase();
  if (!state.showDebugLogs && level === "DEBUG") {
    return false;
  }
  const message = String(item?.message || "").trim();
  if (!message) {
    return false;
  }
  const noisyPrefixes = [
    "URL:",
    "Params:",
    "Data:",
    "Headers:",
    "Other:",
    "Response URL:",
    "Response Code:",
    "Response Headers:",
  ];
  if (state.showDebugLogs) {
    return true;
  }
  return !noisyPrefixes.some((prefix) => message.startsWith(prefix));
}

function buildLogRow(item) {
  if (!shouldRenderLog(item)) {
    return null;
  }
  const row = document.createElement("p");
  const level = String(item.level || "INFO").toUpperCase();
  row.className = "log-row";
  row.dataset.level = level;
  row.textContent = `[${item.timestamp || "--"}] [${level}] ${item.message || ""}`;
  state.logCount += 1;
  return row;
}

function rerenderLogs() {
  refs.logStream.innerHTML = "";
  state.logCount = 0;
  const fragment = document.createDocumentFragment();
  for (const item of state.logRecords) {
    const row = buildLogRow(item);
    if (row) {
      fragment.appendChild(row);
    }
  }
  refs.logStream.appendChild(fragment);
  updateLogCount();
  if (state.autoScroll) {
    refs.logStream.scrollTop = refs.logStream.scrollHeight;
  }
}

function appendLogs(logs) {
  if (!logs.length) {
    return;
  }
  const fragment = document.createDocumentFragment();
  for (const item of logs) {
    const id = Number(item.id || 0);
    if (id > state.logAfterId) {
      state.logAfterId = id;
    }
    state.logRecords.push(item);
    const row = buildLogRow(item);
    if (row) {
      fragment.appendChild(row);
    }
  }
  let trimmed = false;
  if (state.logRecords.length > 5000) {
    state.logRecords.splice(0, state.logRecords.length - 5000);
    trimmed = true;
  }
  if (trimmed) {
    rerenderLogs();
    return;
  }
  if (!fragment.childNodes.length) {
    return;
  }
  refs.logStream.appendChild(fragment);
  updateLogCount();
  if (state.autoScroll) {
    refs.logStream.scrollTop = refs.logStream.scrollHeight;
  }
}

function clearLogs() {
  state.logRecords = [];
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
  if (tab === "profiles" && state.accountBoardDirty) {
    loadAccountBoard(true);
  }
  if (tab === "files") {
    updateFilesAccountContext();
  }
}

function defaultAccountRow() {
  return {
    mark: "",
    url: "",
    tab: "post",
    earliest: "",
    latest: "",
    enable: true,
    auto_update_earliest: false,
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
      auto_update_earliest: Boolean(item.auto_update_earliest ?? false),
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
    auto_update_earliest: false,
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
      auto_update_earliest: Boolean(item.auto_update_earliest ?? false),
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

function duplicateUrlIndexes(platform) {
  const key = accountRowsKey(platform);
  const rows = state.accountRows[key] || [];
  const map = new Map();
  rows.forEach((item, index) => {
    const normalized = normalizeUrl(item.url || "");
    if (!normalized) {
      return;
    }
    const bucket = map.get(normalized) || [];
    bucket.push(index);
    map.set(normalized, bucket);
  });
  const duplicates = new Set();
  map.forEach((indexes) => {
    if (indexes.length > 1) {
      indexes.forEach((index) => duplicates.add(index));
    }
  });
  return {
    duplicates,
    duplicateUrls: Array.from(map.values()).filter((indexes) => indexes.length > 1).length,
  };
}

function setDuplicateStatus(platform, duplicateUrls = 0, duplicateRows = 0) {
  const ref =
    platform === "tiktok"
      ? refs.accountsTikTokDuplicateStatus
      : refs.accountsDouyinDuplicateStatus;
  if (!ref) {
    return;
  }
  if (!duplicateRows) {
    ref.textContent = "未检测到重复 URL";
    return;
  }
  ref.textContent = `检测到重复 URL: ${duplicateUrls} 组，共 ${duplicateRows} 行（建议先规则化 URL）`;
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
  const { duplicates, duplicateUrls } = duplicateUrlIndexes(platform);
  setDuplicateStatus(platform, duplicateUrls, duplicates.size);
  body.innerHTML = "";
  const fragment = document.createDocumentFragment();
  rows.forEach((item, index) => {
    const text = `${item.mark} ${item.url} ${item.tab} ${item.earliest} ${item.latest}`.toLowerCase();
    if (query && !text.includes(query)) {
      return;
    }
    const tr = document.createElement("tr");
    const duplicate = duplicates.has(index);
    tr.classList.toggle("duplicate-row", duplicate);
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
        <label class="switch">
          <input
            data-field="auto_update_earliest"
            type="checkbox"
            title="下载该账号成功后，自动回写 earliest=今天-回溯天数"
            ${
            item.auto_update_earliest ? "checked" : ""
          }
          />
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
        ${duplicate ? '<span class="badge warn duplicate-tag">重复 URL</span>' : ""}
      </td>
    `;
    fragment.appendChild(tr);
  });
  if (!fragment.childNodes.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="9"><span class="empty-tip">无匹配结果</span></td>`;
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
  state.accountBoardDirty = true;
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
      auto_update_earliest: Boolean(row.auto_update_earliest ?? false),
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

function parseBatchBoolValue(value) {
  const normalized = String(value || "")
    .trim()
    .toLowerCase();
  const trueValues = new Set(["1", "true", "yes", "on", "enable", "enabled", "启用", "开启"]);
  const falseValues = new Set(["0", "false", "no", "off", "disable", "disabled", "禁用", "关闭"]);
  if (trueValues.has(normalized)) {
    return true;
  }
  if (falseValues.has(normalized)) {
    return false;
  }
  return null;
}

function batchValuePlaceholder(field) {
  if (field === "enable" || field === "auto_update_earliest") {
    return "批量值：true / false / 启用 / 禁用";
  }
  if (field === "url") {
    return "批量值：账号主页链接";
  }
  if (field === "tab") {
    return "批量值：post / favorite / collection";
  }
  return `批量值：${field}`;
}

function syncBatchValuePlaceholder(platform) {
  const fieldRef =
    platform === "tiktok" ? refs.accountsTikTokBatchField : refs.accountsDouyinBatchField;
  const valueRef =
    platform === "tiktok" ? refs.accountsTikTokBatchValue : refs.accountsDouyinBatchValue;
  if (!fieldRef || !valueRef) {
    return;
  }
  valueRef.placeholder = batchValuePlaceholder(fieldRef.value || "earliest");
}

function applyBatchField(platform, field, rawValue) {
  const key = accountRowsKey(platform);
  const indexes = selectedIndexes(platform, "active");
  if (!indexes.length) {
    return { updated: 0, error: "请先勾选至少一行再批量替换" };
  }
  const editableFields = new Set([
    "mark",
    "url",
    "tab",
    "earliest",
    "latest",
    "enable",
    "auto_update_earliest",
  ]);
  if (!editableFields.has(field)) {
    return { updated: 0, error: `不支持字段: ${field}` };
  }
  let nextValue = rawValue;
  if (field === "enable" || field === "auto_update_earliest") {
    const parsed = parseBatchBoolValue(rawValue);
    if (parsed === null) {
      return {
        updated: 0,
        error: `${field} 只支持 true/false/1/0/启用/禁用`,
      };
    }
    nextValue = parsed;
  }
  indexes.forEach((index) => {
    const row = state.accountRows[key][index];
    if (!row) {
      return;
    }
    row[field] =
      field === "enable" || field === "auto_update_earliest"
        ? Boolean(nextValue)
        : String(nextValue ?? "");
  });
  renderAccountRows(platform);
  return { updated: indexes.length, field };
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
    auto_update_earliest: Boolean(item.auto_update_earliest),
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
    auto_update_earliest: Boolean(item.auto_update_earliest),
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
    "profile_avatar_folder",
    "earliest_update_days",
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

  const boolFields = [
    "download",
    "folder_mode",
    "music",
    "dynamic_cover",
    "static_cover",
    "auto_backfill_mark",
  ];
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
  const rawDays = Number(formData.get("earliest_update_days"));
  const earliestUpdateDays = Number.isFinite(rawDays) ? Math.max(0, Math.trunc(rawDays)) : 0;
  const payload = {
    root: String(formData.get("root") || "").trim(),
    folder_name: String(formData.get("folder_name") || "").trim(),
    profile_avatar_folder: String(formData.get("profile_avatar_folder") || "").trim(),
    earliest_update_days: earliestUpdateDays,
    storage_format: String(formData.get("storage_format") || "").trim(),
    proxy: String(formData.get("proxy") || "").trim(),
    proxy_tiktok: String(formData.get("proxy_tiktok") || "").trim(),
    run_command: String(formData.get("run_command") || "").trim(),
    download: refs.settingsForm.elements.namedItem("download").checked,
    folder_mode: refs.settingsForm.elements.namedItem("folder_mode").checked,
    music: refs.settingsForm.elements.namedItem("music").checked,
    dynamic_cover: refs.settingsForm.elements.namedItem("dynamic_cover").checked,
    static_cover: refs.settingsForm.elements.namedItem("static_cover").checked,
    auto_backfill_mark: refs.settingsForm.elements.namedItem("auto_backfill_mark").checked,
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

function filteredFileEntries() {
  const query = String(state.fileSearch || "")
    .trim()
    .toLowerCase();
  const entries = state.fileEntries || [];
  if (!query) {
    return entries;
  }
  return entries.filter((entry) => {
    const text = `${entry.name || ""} ${entry.path || ""}`.toLowerCase();
    return text.includes(query);
  });
}

function renderFiles() {
  const entries = filteredFileEntries();
  refs.filesList.innerHTML = "";
  if (!entries.length) {
    const tip = state.fileSearch.trim() ? "无匹配文件" : "目录为空";
    refs.filesList.innerHTML = `<div class="file-row"><span class="file-name">${tip}</span></div>`;
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
      updateFilesAccountContext();

      if (entry.is_dir || entry.kind === "dir") {
        state.currentPath = entry.path || "";
        refs.filesPath.value = state.currentPath;
        state.selectedFilePath = "";
        updateFilesAccountContext();
        loadFiles();
      } else {
        renderFilePreview(entry);
      }
    });

    fragment.appendChild(row);
  }
  refs.filesList.appendChild(fragment);
}

function updateFilesAccountContext() {
  const context = state.fileAccountContext || {};
  const hasAccount = Boolean(context.url);
  const selected = state.fileEntries.find((item) => item.path === state.selectedFilePath);
  const fileLabel = selected?.name || selected?.path || "";
  const selectedHint = fileLabel ? ` · 已选文件: ${fileLabel}` : " · 未选择文件";
  if (refs.filesAccountContext) {
    refs.filesAccountContext.textContent = hasAccount
      ? `账户上下文：${context.mark || "(未设置 mark)"} · ${context.url}${selectedHint}`
      : "账户上下文：未从看板选择账户";
  }
  const mediaSelected = Boolean(
    hasAccount &&
      selected &&
      !selected.is_dir &&
      (selected.kind === "image" || selected.kind === "video"),
  );
  const imageSelected = Boolean(
    hasAccount &&
      selected &&
      !selected.is_dir &&
      selected.kind === "image",
  );
  if (refs.filesPinProfileBtn) {
    refs.filesPinProfileBtn.disabled = !mediaSelected || state.currentScope !== "download";
  }
  if (refs.filesGenerateAvatarBtn) {
    refs.filesGenerateAvatarBtn.disabled = !mediaSelected;
  }
  if (refs.filesPinAvatarBtn) {
    refs.filesPinAvatarBtn.disabled = !imageSelected;
  }
}

function openBoardFolderInFiles(card) {
  const folderPath = card?.dataset?.folderPath || "";
  const url = card?.dataset?.url || "";
  if (!folderPath || !url) {
    setBoardStatus("当前卡片无目录或 URL，无法跳转文件浏览");
    return;
  }
  state.fileAccountContext = {
    platform: card.dataset.platform || state.accountBoard.platform,
    url,
    mark: card.dataset.mark || "",
  };
  state.currentScope = "download";
  state.currentPath = folderPath;
  state.selectedFilePath = "";
  if (refs.filesScope) {
    refs.filesScope.value = "download";
  }
  if (refs.filesPath) {
    refs.filesPath.value = folderPath;
  }
  switchTab("files");
  loadFiles();
  updateFilesAccountContext();
}

async function generateBoardCardAvatar(card) {
  const url = card?.dataset?.url || "";
  const path = card?.dataset?.mediaPath || "";
  const platform = card?.dataset?.platform || state.accountBoard.platform;
  if (!url || !path) {
    setBoardStatus("当前卡片没有可用于识别的人脸媒体");
    return;
  }
  setBoardStatus("正在生成人脸头像…");
  try {
    const payload = await fetchJson("/ui/api/accounts/board/avatar/generate", {
      method: "POST",
      headers: headerOptions(true),
      body: JSON.stringify({
        platform,
        url,
        scope: "download",
        path,
      }),
    });
    card.dataset.avatarPath = payload.avatar_path || "";
    card.dataset.avatarScope = payload.avatar_scope || "project";
    renderBoardCardPreview(card);
    const faces = payload?.details?.faces_detected || 0;
    setBoardStatus(`头像生成成功（识别 ${faces} 张人脸）`);
    setApiStatus("就绪", "ok");
  } catch (error) {
    setBoardStatus(`头像生成失败: ${error.message}`);
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

async function pinFromFileBrowser() {
  const context = state.fileAccountContext || {};
  const selected = state.fileEntries.find((item) => item.path === state.selectedFilePath);
  if (!context.url) {
    setBoardStatus("请先从账户看板进入文件浏览");
    return;
  }
  if (!selected || selected.is_dir || (selected.kind !== "image" && selected.kind !== "video")) {
    setBoardStatus("请选择图片或视频文件后再执行 Profile Pin");
    return;
  }
  try {
    await fetchJson("/ui/api/accounts/board/pin", {
      method: "POST",
      headers: headerOptions(true),
      body: JSON.stringify({
        platform: context.platform || "douyin",
        url: context.url,
        path: selected.path,
      }),
    });
    setBoardStatus("已将当前文件设为该账号 Profile Pin");
    setApiStatus("就绪", "ok");
  } catch (error) {
    setBoardStatus(`Profile Pin 失败: ${error.message}`);
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

async function generateAvatarFromFileBrowser() {
  const context = state.fileAccountContext || {};
  const selected = state.fileEntries.find((item) => item.path === state.selectedFilePath);
  if (!context.url) {
    setBoardStatus("请先从账户看板进入文件浏览");
    return;
  }
  if (!selected || selected.is_dir || (selected.kind !== "image" && selected.kind !== "video")) {
    setBoardStatus("请选择图片或视频文件后再执行头像生成");
    return;
  }
  setBoardStatus("正在基于当前文件生成人脸头像…");
  try {
    const payload = await fetchJson("/ui/api/accounts/board/avatar/generate", {
      method: "POST",
      headers: headerOptions(true),
      body: JSON.stringify({
        platform: context.platform || "douyin",
        url: context.url,
        scope: state.currentScope,
        path: selected.path,
      }),
    });
    const faces = payload?.details?.faces_detected || 0;
    setBoardStatus(`头像生成成功（识别 ${faces} 张人脸）`);
    setApiStatus("就绪", "ok");
  } catch (error) {
    setBoardStatus(`头像生成失败: ${error.message}`);
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

async function pinAvatarFromFileBrowser() {
  const context = state.fileAccountContext || {};
  const selected = state.fileEntries.find((item) => item.path === state.selectedFilePath);
  if (!context.url) {
    setBoardStatus("请先从账户看板进入文件浏览");
    return;
  }
  if (!selected || selected.is_dir || selected.kind !== "image") {
    setBoardStatus("手动设头像仅支持图片文件");
    return;
  }
  try {
    await fetchJson("/ui/api/accounts/board/avatar/pin", {
      method: "POST",
      headers: headerOptions(true),
      body: JSON.stringify({
        platform: context.platform || "douyin",
        url: context.url,
        scope: state.currentScope,
        path: selected.path,
      }),
    });
    setBoardStatus("已将当前图片手动设为账号头像");
    setApiStatus("就绪", "ok");
  } catch (error) {
    setBoardStatus(`手动设头像失败: ${error.message}`);
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

async function loadFileStats() {
  if (!refs.filesStats) {
    return;
  }
  refs.filesStats.textContent = "正在统计目录信息…";
  try {
    const query = new URLSearchParams({
      scope: state.currentScope,
      path: state.currentPath || "",
    });
    const payload = await fetchJson(`/ui/api/files/stats?${query.toString()}`, {
      method: "GET",
      headers: headerOptions(false),
    });
    refs.filesStats.textContent = `目录统计：文件 ${payload.files} · 图片 ${payload.images} · 视频 ${payload.videos} · 文件夹 ${payload.folders} · 占用 ${payload.size_human}`;
  } catch (error) {
    refs.filesStats.textContent = `统计失败: ${error.message}`;
  }
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
    state.fileEntries = normalized.entries || [];
    state.currentPath = normalized.currentPath || state.currentPath || "";
    refs.filesPath.value = state.currentPath;
    renderFiles();
    updateFilesAccountContext();
    const filteredCount = filteredFileEntries().length;
    refs.filesMeta.textContent = `scope=${state.currentScope} · path=/${state.currentPath || ""} · ${filteredCount}/${normalized.total} 项`;
    loadFileStats();
    setApiStatus("就绪", "ok");
  } catch (error) {
    state.fileEntries = [];
    state.selectedFilePath = "";
    refs.filesList.innerHTML = "";
    refs.filesMeta.textContent = `加载失败: ${error.message}`;
    if (refs.filesStats) {
      refs.filesStats.textContent = "统计信息待加载…";
    }
    updateFilesAccountContext();
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

function boardAssetUrl(path, scope = "download") {
  return `/ui/api/file?scope=${encodeURIComponent(scope)}&path=${encodeURIComponent(path || "")}`;
}

function boardColumnsCap() {
  const width = window.innerWidth || 1280;
  const compactMode = state.accountBoard.viewMode === "avatar";
  if (width <= 700) {
    return compactMode ? 2 : 1;
  }
  if (width <= 980) {
    return compactMode ? 4 : 2;
  }
  if (width <= 1200) {
    return compactMode ? 6 : 3;
  }
  if (compactMode) {
    return Math.max(6, Math.min(12, Math.floor(width / 170)));
  }
  return Math.max(4, Math.min(8, Math.floor(width / 260)));
}

function applyBoardColumns(persist = true) {
  const cap = boardColumnsCap();
  const inputColumns = Number(state.accountBoard.columns || 4);
  const next = Math.max(1, Math.min(inputColumns, cap));
  state.accountBoard.columns = next;
  if (refs.boardDensity) {
    refs.boardDensity.max = String(cap);
    refs.boardDensity.value = String(next);
  }
  if (refs.boardDensityLabel) {
    refs.boardDensityLabel.textContent = `${next} 列`;
  }
  if (refs.boardGrid) {
    refs.boardGrid.style.setProperty("--board-columns", String(next));
    refs.boardGrid.classList.toggle("profile-board-compact", state.accountBoard.viewMode === "avatar");
    refs.boardGrid.classList.toggle(
      "profile-board-ultra",
      state.accountBoard.viewMode === "avatar" && next >= 9,
    );
  }
  if (persist) {
    try {
      localStorage.setItem(BOARD_COLUMNS_STORAGE_KEY, String(next));
    } catch {}
  }
}

function updateBoardMeta() {
  refs.boardMeta.textContent = `第 ${state.accountBoard.page} / ${state.accountBoard.pages} 页 · 共 ${state.accountBoard.total} 账号`;
}

function setBoardStatus(text) {
  refs.boardStatus.textContent = text;
}

function selectedBoardPreview(card) {
  if (!card) {
    return {
      path: "",
      kind: "",
      scope: "download",
      pinned: false,
    };
  }
  if (state.accountBoard.viewMode === "avatar" && card.dataset.avatarPath) {
    return {
      path: card.dataset.avatarPath || "",
      kind: "image",
      scope: card.dataset.avatarScope || "project",
      pinned: true,
    };
  }
  return {
    path: card.dataset.mediaPath || "",
    kind: card.dataset.mediaKind || "",
    scope: "download",
    pinned: card.dataset.pinned === "1",
  };
}

function renderBoardCardPreview(card) {
  const mediaWrap = card.querySelector(".profile-media-wrap");
  const pinBtn = card.querySelector('[data-action="board-pin-media"]');
  const refreshBtn = card.querySelector('[data-action="board-refresh-media"]');
  const refreshVideoBtn = card.querySelector('[data-action="board-refresh-video"]');
  const pinBadge = card.querySelector(".profile-pin-badge");
  const avatarBadge = card.querySelector(".profile-avatar-badge");
  const avatarBtn = card.querySelector('[data-action="board-generate-avatar"]');
  const preview = selectedBoardPreview(card);

  if (pinBadge) {
    pinBadge.textContent = card.dataset.pinned === "1" ? "已 Pin" : "未 Pin";
    pinBadge.classList.toggle("ok", card.dataset.pinned === "1");
  }
  if (avatarBadge) {
    avatarBadge.textContent = card.dataset.avatarPath ? "有头像" : "无头像";
    avatarBadge.classList.toggle("ok", Boolean(card.dataset.avatarPath));
  }
  if (pinBtn) {
    pinBtn.textContent = card.dataset.pinned === "1" ? "已 Pin" : "Pin";
    pinBtn.disabled = !card.dataset.mediaPath;
  }
  if (refreshBtn) {
    refreshBtn.disabled = !card.dataset.folderPath;
  }
  if (refreshVideoBtn) {
    refreshVideoBtn.disabled = !card.dataset.folderPath;
  }
  if (avatarBtn) {
    avatarBtn.disabled = !card.dataset.mediaPath;
  }
  if (!mediaWrap) {
    return;
  }
  mediaWrap.innerHTML = "";
  if (!preview.path || !preview.kind) {
    const empty = document.createElement("div");
    empty.className = "profile-empty";
    empty.textContent = card.dataset.folderPath
      ? "目录存在，但未找到可预览媒体"
      : "未匹配到账户目录";
    mediaWrap.appendChild(empty);
    return;
  }
  const src = boardAssetUrl(preview.path, preview.scope || "download");
  if (preview.kind === "image") {
    const image = document.createElement("img");
    image.src = src;
    image.alt = card.dataset.mark || "profile";
    image.loading = "lazy";
    mediaWrap.appendChild(image);
    return;
  }
  if (preview.kind === "video") {
    const video = document.createElement("video");
    video.src = src;
    video.controls = true;
    video.preload = "metadata";
    video.muted = true;
    video.playsInline = true;
    mediaWrap.appendChild(video);
    return;
  }
  const empty = document.createElement("div");
  empty.className = "profile-empty";
  empty.textContent = "媒体类型暂不支持预览";
  mediaWrap.appendChild(empty);
}

function setBoardCardMedia(card, mediaPath, mediaKind, pinned = false) {
  card.dataset.mediaPath = mediaPath || "";
  card.dataset.mediaKind = mediaKind || "";
  card.dataset.pinned = pinned ? "1" : "0";
  renderBoardCardPreview(card);
}

function renderAccountBoard(items) {
  refs.boardGrid.innerHTML = "";
  if (!Array.isArray(items) || !items.length) {
    refs.boardGrid.innerHTML = '<div class="empty-tip">当前页没有可展示账号</div>';
    return;
  }
  const fragment = document.createDocumentFragment();
  for (const item of items) {
    const card = document.createElement("article");
    card.className = "profile-card";
    card.dataset.platform = item.platform || state.accountBoard.platform;
    card.dataset.url = item.url || "";
    card.dataset.mark = item.mark || "";
    card.dataset.folderPath = item.folder_path || "";
    card.dataset.mediaPath = item.media_path || "";
    card.dataset.mediaKind = item.media_kind || "";
    card.dataset.pinned = item.pinned ? "1" : "0";
    card.dataset.avatarPath = item.avatar_path || "";
    card.dataset.avatarScope = item.avatar_scope || "";

    const mediaWrap = document.createElement("div");
    mediaWrap.className = "profile-media-wrap";

    const body = document.createElement("div");
    body.className = "profile-body";

    const titleRow = document.createElement("div");
    titleRow.className = "profile-title";

    const name = document.createElement("div");
    name.className = "profile-name";
    name.textContent = item.mark || "未设置 mark";

    const badges = document.createElement("div");
    badges.className = "card-actions";
    const enableBadge = document.createElement("span");
    enableBadge.className = `badge ${item.enable ? "ok" : "warn"}`;
    enableBadge.textContent = item.enable ? "启用" : "停用";
    const pinBadge = document.createElement("span");
    pinBadge.className = `badge profile-pin-badge ${item.pinned ? "ok" : ""}`;
    pinBadge.textContent = item.pinned ? "已 Pin" : "未 Pin";
    const avatarBadge = document.createElement("span");
    avatarBadge.className = `badge profile-avatar-badge ${item.avatar_path ? "ok" : ""}`;
    avatarBadge.textContent = item.avatar_path ? "有头像" : "无头像";
    badges.appendChild(enableBadge);
    badges.appendChild(pinBadge);
    badges.appendChild(avatarBadge);

    titleRow.appendChild(name);
    titleRow.appendChild(badges);

    const url = document.createElement("div");
    url.className = "profile-url";
    url.textContent = item.url || "-";

    const folder = document.createElement("div");
    folder.className = "profile-folder";
    folder.textContent = item.folder_path
      ? `目录: ${item.folder_path}`
      : "目录: (未匹配)";

    const actions = document.createElement("div");
    actions.className = "profile-actions";
    actions.innerHTML = `
      <button class="btn ghost" type="button" data-action="board-open-account">打开主页</button>
      <button class="btn ghost" type="button" data-action="board-open-files">文件浏览</button>
      <button class="btn ghost" type="button" data-action="board-refresh-media">刷新媒体</button>
      <button class="btn ghost" type="button" data-action="board-refresh-video">刷视频</button>
      <button class="btn ghost" type="button" data-action="board-generate-avatar">AI 头像</button>
      <button class="btn ghost" type="button" data-action="board-pin-media">Pin</button>
    `;

    body.appendChild(titleRow);
    body.appendChild(url);
    body.appendChild(folder);
    body.appendChild(actions);

    card.appendChild(mediaWrap);
    card.appendChild(body);
    setBoardCardMedia(card, item.media_path || "", item.media_kind || "", Boolean(item.pinned));
    fragment.appendChild(card);
  }
  refs.boardGrid.appendChild(fragment);
}

async function loadAccountBoard(resetPage = false) {
  if (!refs.boardPlatform || !refs.boardPageSize) {
    return;
  }
  if (resetPage) {
    state.accountBoard.page = 1;
  }
  state.accountBoard.platform = refs.boardPlatform.value || "douyin";
  state.accountBoard.pageSize = Number(refs.boardPageSize.value || "24");
  setBoardStatus("正在加载账户媒体看板…");
  try {
    const query = new URLSearchParams({
      platform: state.accountBoard.platform,
      page: String(state.accountBoard.page),
      page_size: String(state.accountBoard.pageSize),
    });
    const payload = await fetchJson(`/ui/api/accounts/board?${query.toString()}`, {
      method: "GET",
      headers: headerOptions(false),
    });
    state.accountBoard.page = Number(payload.page || 1);
    state.accountBoard.pageSize = Number(payload.page_size || state.accountBoard.pageSize);
    state.accountBoard.pages = Number(payload.pages || 1);
    state.accountBoard.total = Number(payload.total || 0);
    refs.boardPrevBtn.disabled = state.accountBoard.page <= 1;
    refs.boardNextBtn.disabled = state.accountBoard.page >= state.accountBoard.pages;
    updateBoardMeta();
    renderAccountBoard(payload.items || []);
    setBoardStatus(
      `已加载 ${state.accountBoard.platform} · 第 ${state.accountBoard.page}/${state.accountBoard.pages} 页`,
    );
    state.accountBoardDirty = false;
    setApiStatus("就绪", "ok");
  } catch (error) {
    refs.boardGrid.innerHTML = "";
    setBoardStatus(`加载失败: ${error.message}`);
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

async function refreshBoardCard(card, preferKind = "auto") {
  const platform = card.dataset.platform || state.accountBoard.platform;
  const url = card.dataset.url || "";
  if (!url) {
    setBoardStatus("当前卡片缺少账号 URL，无法刷新");
    return;
  }
  setBoardStatus("正在刷新卡片媒体…");
  try {
    const payload = await fetchJson("/ui/api/accounts/board/random", {
      method: "POST",
      headers: headerOptions(true),
      body: JSON.stringify({
        platform,
        url,
        current_path: card.dataset.mediaPath || "",
        prefer_kind: preferKind,
      }),
    });
    setBoardCardMedia(
      card,
      payload.media_path || "",
      payload.media_kind || "",
      false,
    );
    const usedKind = String(payload.media_kind || "").trim();
    const preferText =
      preferKind === "video"
        ? "视频优先"
        : preferKind === "image"
          ? "图片优先"
          : "自动";
    setBoardStatus(`已刷新卡片媒体（${preferText}，当前: ${usedKind || "无"}）`);
    setApiStatus("就绪", "ok");
  } catch (error) {
    setBoardStatus(`刷新失败: ${error.message}`);
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

async function pinBoardCard(card) {
  const platform = card.dataset.platform || state.accountBoard.platform;
  const url = card.dataset.url || "";
  const path = card.dataset.mediaPath || "";
  if (!url || !path) {
    setBoardStatus("当前卡片无可 Pin 的媒体");
    return;
  }
  try {
    await fetchJson("/ui/api/accounts/board/pin", {
      method: "POST",
      headers: headerOptions(true),
      body: JSON.stringify({
        platform,
        url,
        path,
      }),
    });
    setBoardCardMedia(card, path, card.dataset.mediaKind || "", true);
    setBoardStatus("已固定该账号 Profile 媒体");
    setApiStatus("就绪", "ok");
  } catch (error) {
    setBoardStatus(`固定失败: ${error.message}`);
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

async function pinCurrentBoardPage() {
  const cards = Array.from(refs.boardGrid.querySelectorAll(".profile-card"));
  const items = cards
    .map((card) => ({
      url: card.dataset.url || "",
      path: card.dataset.mediaPath || "",
    }))
    .filter((item) => item.url && item.path);
  if (!items.length) {
    setBoardStatus("当前页没有可批量 Pin 的媒体");
    return;
  }
  try {
    const result = await fetchJson("/ui/api/accounts/board/pin-all", {
      method: "POST",
      headers: headerOptions(true),
      body: JSON.stringify({
        platform: state.accountBoard.platform,
        items,
      }),
    });
    for (const card of cards) {
      if (!card.dataset.mediaPath) {
        continue;
      }
      setBoardCardMedia(card, card.dataset.mediaPath, card.dataset.mediaKind || "", true);
    }
    setBoardStatus(`批量固定完成：${result.updated || 0} / ${result.requested || items.length}`);
    setApiStatus("就绪", "ok");
  } catch (error) {
    setBoardStatus(`批量固定失败: ${error.message}`);
    setApiStatus(`异常: ${error.message}`, "error");
  }
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

function formatWorkflowAccountSummary(task) {
  const endpoint = String(task?.endpoint || "");
  if (!endpoint.endsWith("/account_batch")) {
    return "";
  }
  const result = task?.result;
  const data = result && typeof result === "object" ? result.data : null;
  if (!data || typeof data !== "object") {
    return `${task?.status || "-"} · ${endpoint}`;
  }
  const parts = [task?.status || "-"];
  const numericFields = [
    ["total", "total"],
    ["queued", "queued"],
    ["success", "success"],
    ["failed", "failed"],
    ["skipped", "skipped"],
  ];
  for (const [key, label] of numericFields) {
    const value = Number(data[key]);
    if (Number.isFinite(value) && value >= 0) {
      parts.push(`${label} ${value}`);
    }
  }
  const markBackfilled = Number(data.mark_backfilled);
  if (Number.isFinite(markBackfilled) && markBackfilled > 0) {
    parts.push(`mark回填 ${markBackfilled}`);
  }
  const earliestUpdated = Number(data.earliest_updated);
  if (Number.isFinite(earliestUpdated) && earliestUpdated > 0) {
    parts.push(`earliest更新 ${earliestUpdated}`);
  }
  return parts.join(" · ");
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
  const workflowSummary = formatWorkflowAccountSummary(task);
  if (workflowSummary && refs.workflowAccountSummary) {
    refs.workflowAccountSummary.textContent = workflowSummary;
  }
  if (workflowSummary && refs.workflowAccountStatus && task.message) {
    refs.workflowAccountStatus.textContent = task.message;
  }
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

  refs.logsDebugToggle.addEventListener("change", (event) => {
    state.showDebugLogs = Boolean(event.target.checked);
    try {
      localStorage.setItem(
        LOG_DEBUG_STORAGE_KEY,
        state.showDebugLogs ? "1" : "0",
      );
    } catch {}
    rerenderLogs();
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
      const checkedFields = new Set(["enable", "auto_update_earliest", "selected"]);
      updateAccountRow(
        platform,
        index,
        field,
        checkedFields.has(field) ? target.checked : target.value,
        section,
      );
    });

    body.addEventListener("change", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement)) {
        return;
      }
      const row = target.closest("tr");
      if (!row) {
        return;
      }
      const platform = row.dataset.platform || "douyin";
      const field = target.dataset.field || "";
      if (section === "active" && field === "url") {
        renderAccountRows(platform);
      }
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

  refs.accountsDouyinBatchField.addEventListener("change", () => {
    syncBatchValuePlaceholder("douyin");
  });
  refs.accountsTikTokBatchField.addEventListener("change", () => {
    syncBatchValuePlaceholder("tiktok");
  });

  refs.accountsDouyinApplyBatchBtn.addEventListener("click", async () => {
    const field = refs.accountsDouyinBatchField.value;
    const value = refs.accountsDouyinBatchValue.value;
    const resultState = applyBatchField("douyin", field, value);
    if (resultState.error) {
      setAccountStatus("douyin", resultState.error);
      return;
    }
    const result = await persistAccountTables("account_batch_replace");
    setAccountStatus(
      "douyin",
      `已批量替换 ${resultState.updated} 行 ${field}: ${result.backup_path || "-"}`,
    );
  });
  refs.accountsTikTokApplyBatchBtn.addEventListener("click", async () => {
    const field = refs.accountsTikTokBatchField.value;
    const value = refs.accountsTikTokBatchValue.value;
    const resultState = applyBatchField("tiktok", field, value);
    if (resultState.error) {
      setAccountStatus("tiktok", resultState.error);
      return;
    }
    const result = await persistAccountTables("account_batch_replace");
    setAccountStatus(
      "tiktok",
      `已批量替换 ${resultState.updated} 行 ${field}: ${result.backup_path || "-"}`,
    );
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

  refs.boardPlatform.addEventListener("change", () => {
    state.accountBoard.platform = refs.boardPlatform.value || "douyin";
    state.accountBoard.page = 1;
    loadAccountBoard(true);
  });

  refs.boardRefreshKind.addEventListener("change", () => {
    state.accountBoard.refreshKind = refs.boardRefreshKind.value || "auto";
  });

  refs.boardViewMode.addEventListener("change", () => {
    state.accountBoard.viewMode = refs.boardViewMode.value || "avatar";
    try {
      localStorage.setItem(BOARD_VIEW_MODE_STORAGE_KEY, state.accountBoard.viewMode);
    } catch {}
    applyBoardColumns(true);
    for (const card of refs.boardGrid.querySelectorAll(".profile-card")) {
      renderBoardCardPreview(card);
    }
  });

  refs.boardDensity.addEventListener("input", () => {
    state.accountBoard.columns = Number(refs.boardDensity.value || "4");
    applyBoardColumns(true);
  });

  refs.boardPageSize.addEventListener("change", () => {
    state.accountBoard.pageSize = Number(refs.boardPageSize.value || "24");
    state.accountBoard.page = 1;
    loadAccountBoard(true);
  });

  refs.boardPrevBtn.addEventListener("click", () => {
    state.accountBoard.page = Math.max(1, state.accountBoard.page - 1);
    loadAccountBoard(false);
  });

  refs.boardNextBtn.addEventListener("click", () => {
    state.accountBoard.page = Math.min(state.accountBoard.pages, state.accountBoard.page + 1);
    loadAccountBoard(false);
  });

  refs.boardReloadBtn.addEventListener("click", () => {
    loadAccountBoard(false);
  });

  refs.boardPinAllBtn.addEventListener("click", () => {
    pinCurrentBoardPage();
  });

  refs.boardGrid.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }
    const actionButton = target.closest("button[data-action]");
    if (!(actionButton instanceof HTMLButtonElement)) {
      return;
    }
    const card = actionButton.closest(".profile-card");
    if (!(card instanceof HTMLElement)) {
      return;
    }
    const action = actionButton.dataset.action || "";
    if (action === "board-open-account") {
      openUrls([card.dataset.url || ""]);
      return;
    }
    if (action === "board-open-files") {
      openBoardFolderInFiles(card);
      return;
    }
    if (action === "board-refresh-media") {
      refreshBoardCard(card, state.accountBoard.refreshKind || "auto");
      return;
    }
    if (action === "board-refresh-video") {
      refreshBoardCard(card, "video");
      return;
    }
    if (action === "board-generate-avatar") {
      generateBoardCardAvatar(card);
      return;
    }
    if (action === "board-pin-media") {
      pinBoardCard(card);
    }
  });

  refs.filesBackToBoardBtn.addEventListener("click", () => {
    switchTab("profiles");
  });

  refs.filesPinProfileBtn.addEventListener("click", () => {
    pinFromFileBrowser();
  });

  refs.filesGenerateAvatarBtn.addEventListener("click", () => {
    generateAvatarFromFileBrowser();
  });

  refs.filesPinAvatarBtn.addEventListener("click", () => {
    pinAvatarFromFileBrowser();
  });

  refs.filesScope.addEventListener("change", () => {
    state.currentScope = refs.filesScope.value;
    state.currentPath = "";
    refs.filesPath.value = "";
    loadFiles();
  });

  refs.filesSearch.addEventListener("input", () => {
    state.fileSearch = refs.filesSearch.value || "";
    renderFiles();
    updateFilesAccountContext();
    refs.filesMeta.textContent = `scope=${state.currentScope} · path=/${state.currentPath || ""} · ${
      filteredFileEntries().length
    }/${state.fileEntries.length} 项`;
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

  refs.filesStatsRefreshBtn.addEventListener("click", () => {
    loadFileStats();
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

  window.addEventListener("resize", () => {
    applyBoardColumns(false);
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
  syncBatchValuePlaceholder("douyin");
  syncBatchValuePlaceholder("tiktok");
  state.accountBoard.platform = refs.boardPlatform.value || "douyin";
  state.accountBoard.pageSize = Number(refs.boardPageSize.value || "24");
  state.accountBoard.refreshKind = refs.boardRefreshKind.value || "auto";
  state.accountBoard.viewMode = refs.boardViewMode?.value || "avatar";
  try {
    state.accountBoard.columns = Number(localStorage.getItem(BOARD_COLUMNS_STORAGE_KEY) || "4");
  } catch {
    state.accountBoard.columns = 4;
  }
  try {
    state.accountBoard.viewMode =
      localStorage.getItem(BOARD_VIEW_MODE_STORAGE_KEY) ||
      state.accountBoard.viewMode ||
      "avatar";
  } catch {}
  if (refs.boardViewMode) {
    refs.boardViewMode.value = state.accountBoard.viewMode;
  }
  applyBoardColumns(false);
  state.currentScope = refs.filesScope.value;
  state.currentPath = refs.filesPath.value.trim();
  state.fileSearch = refs.filesSearch?.value || "";
  updateFilesAccountContext();
  try {
    state.showDebugLogs = localStorage.getItem(LOG_DEBUG_STORAGE_KEY) === "1";
  } catch {
    state.showDebugLogs = false;
  }
  if (refs.logsDebugToggle) {
    refs.logsDebugToggle.checked = state.showDebugLogs;
  }
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
