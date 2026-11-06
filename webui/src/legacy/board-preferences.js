import { fetchJson, headerOptions, setApiStatus } from "./runtime.js";
import { state } from "./state.js";

const endpoint = "/ui/api/preferences/account-board";
export const boardPreferenceKeys = [
  "viewMode", "columns", "pageSize", "refreshKind", "platform", "status", "sort",
];

// Patch only explicit edits so a stale phone cannot overwrite desktop settings.
export function createBoardPreferences(apply, legacyPreferences) {
  let pending = {};
  let writing = null;
  let loading = null;
  let revision = 0;
  let generation = 0;

  async function flush() {
    if (writing) return writing;
    if (!Object.keys(pending).length) return;
    const owner = generation;
    writing = (async () => {
      while (owner === generation && Object.keys(pending).length) {
        const patch = pending;
        pending = {};
        try {
          await fetchJson(endpoint, {
            method: "PATCH", headers: headerOptions(true),
            body: JSON.stringify(patch), keepalive: true,
            signal: AbortSignal.timeout(8000),
          });
        } catch {
          if (owner === generation) {
            pending = { ...patch, ...pending };
            setApiStatus("看板偏好尚未同步，将在返回看板时重试", "error");
          }
          break;
        }
      }
    })();
    try { await writing; } finally { if (owner === generation) writing = null; }
  }

  async function load() {
    if (loading) return loading;
    const owner = generation;
    loading = (async () => {
      await flush();
      if (owner !== generation || Object.keys(pending).length) return;
      const version = revision;
      try {
        let payload = await fetchJson(endpoint, {
          headers: headerOptions(false), signal: AbortSignal.timeout(8000),
        });
        if (owner !== generation || version !== revision) return;
        if (!Object.keys(payload.preferences || {}).length && Object.keys(legacyPreferences).length) {
          payload = await fetchJson(`${endpoint}?initialize=true`, {
            method: "PATCH", headers: headerOptions(true),
            body: JSON.stringify(legacyPreferences), signal: AbortSignal.timeout(8000),
          });
        }
        if (owner === generation && version === revision) apply(payload.preferences || {});
      } catch {
        if (owner === generation) setApiStatus("看板偏好同步失败，暂用本机设置", "error");
      }
    })();
    try { await loading; } finally { if (owner === generation) loading = null; }
  }

  return {
    load,
    save(key) {
      revision += 1;
      pending[key] = state.accountBoard[key];
      void flush();
    },
    reset() {
      generation += 1;
      pending = {};
      writing = null;
      loading = null;
      legacyPreferences = {};
    },
  };
}
