import { refs } from "./dom-refs.js";
import { refreshIcons } from "./icons.js";
import { state } from "./state.js";
import {
  SIDEBAR_COLLAPSE_STORAGE_KEY,
  TOKEN_STORAGE_KEY,
} from "./task-templates.js";

function readStoredBoolean(key, defaultValue = false) {
  try {
    const value = localStorage.getItem(key);
    if (value === null) {
      return defaultValue;
    }
    return value === "true";
  } catch {
    return defaultValue;
  }
}

function applySidebarCollapsed(collapsed, persist = true) {
  const appShell = document.querySelector(".app-shell");
  appShell?.classList.toggle("sidebar-collapsed", collapsed);
  if (!refs.sidebarToggleBtn) {
    return;
  }
  const label = collapsed ? "展开导航" : "收起导航";
  refs.sidebarToggleBtn.setAttribute("aria-expanded", String(!collapsed));
  refs.sidebarToggleBtn.title = label;
  refs.sidebarToggleBtn.querySelector(".sr-only").textContent = label;
  const icon = refs.sidebarToggleBtn.querySelector("svg, [data-lucide]");
  if (icon) {
    icon.setAttribute("data-lucide", collapsed ? "panel-left-open" : "panel-left-close");
  }
  refreshIcons(refs.sidebarToggleBtn);
  refs.tabButtons.forEach((button) => {
    button.title = button.querySelector(".nav-label")?.textContent?.trim() || "";
  });
  if (persist) {
    try {
      localStorage.setItem(SIDEBAR_COLLAPSE_STORAGE_KEY, String(collapsed));
    } catch {
      // The current session can still use the collapsed layout.
    }
  }
}

function setBadge(element, text, kind = "") {
  if (!element) {
    return;
  }
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

function syncTabOrientation() {
  const tabList = document.querySelector(".top-tabs");
  if (!tabList) {
    return;
  }
  tabList.setAttribute(
    "aria-orientation",
    window.matchMedia("(max-width: 1180px)").matches ? "horizontal" : "vertical",
  );
}

async function withBusyButton(button, busyText, action) {
  if (!button || button.disabled) {
    return;
  }
  const previousMarkup = button.innerHTML;
  button.disabled = true;
  button.classList.add("busy");
  button.setAttribute("aria-busy", "true");
  if (busyText) {
    button.textContent = busyText;
  }
  try {
    await action();
  } finally {
    button.classList.remove("busy");
    button.removeAttribute("aria-busy");
    button.disabled = false;
    button.innerHTML = previousMarkup;
    refreshIcons(button);
  }
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

function readStoredToken() {
  try {
    return localStorage.getItem(TOKEN_STORAGE_KEY)?.trim() || "";
  } catch {
    return "";
  }
}

function persistToken(token) {
  try {
    if (token) {
      localStorage.setItem(TOKEN_STORAGE_KEY, token);
    } else {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
    }
    return true;
  } catch {
    return false;
  }
}

async function establishWebUiSession() {
  if (!state.token) {
    return;
  }
  await fetchJson("/token", {
    method: "GET",
    headers: headerOptions(false),
  });
}

async function clearWebUiSession() {
  await fetchJson("/ui/api/session", {
    method: "DELETE",
    headers: headerOptions(false),
  });
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

export {
  applySidebarCollapsed,
  clearWebUiSession,
  establishWebUiSession,
  fetchJson,
  headerOptions,
  persistToken,
  readStoredBoolean,
  readStoredToken,
  setApiStatus,
  setBadge,
  setWsStatus,
  syncTabOrientation,
  withBusyButton,
};
