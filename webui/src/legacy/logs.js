import { refs } from "./dom-refs.js";
import { state } from "./state.js";
import {
  fetchJson,
  headerOptions,
  setApiStatus,
  setWsStatus,
} from "./runtime.js";

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

export {
  clearLogs,
  connectLogSocket,
  pollLogs,
  rerenderLogs,
};
