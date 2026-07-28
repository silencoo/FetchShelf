import { useEffect, useState, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";

import { AppSelect } from "@/components/ui/app-select";
import { GridPattern } from "@/components/ui/grid-pattern";
import { NumberTicker } from "@/components/ui/number-ticker";
import "@/styles.css";

type MetricKey = "logs" | "tasks" | "accounts" | "files";
type Theme = "light" | "dark";
type ThemePreference = Theme | "system";

interface Metrics {
  logs: number;
  tasks: number;
  accounts: number;
  files: number;
}

declare global {
  interface Window {
    __doukMagicRoots?: Map<string, Root>;
    __doukSelectRoots?: Map<HTMLSelectElement, { mount: HTMLElement; root: Root }>;
  }
}

const INITIAL_METRICS: Metrics = {
  logs: 0,
  tasks: 0,
  accounts: 0,
  files: 0,
};

const THEME_STORAGE_KEY = "webui.theme";
const THEME_OPTIONS: Array<{
  value: ThemePreference;
  label: string;
  title: string;
}> = [
  { value: "system", label: "自动", title: "跟随系统主题" },
  { value: "light", label: "浅色", title: "使用浅色主题" },
  { value: "dark", label: "深色", title: "使用深色主题" },
];

const METRIC_CONFIG: Array<{
  key: MetricKey;
  label: string;
  shortLabel: string;
}> = [
  { key: "tasks", label: "队列任务", shortLabel: "QUEUE" },
  { key: "accounts", label: "账户总数", shortLabel: "ACCOUNTS" },
  { key: "files", label: "目录项目", shortLabel: "FILES" },
  { key: "logs", label: "本次日志", shortLabel: "LOGS" },
];

function parseMetricText(key: MetricKey, text: string): number {
  const normalized = text.replaceAll(",", "");
  const patterns: Record<MetricKey, RegExp> = {
    logs: /(\d+)\s*条日志/,
    tasks: /任务:\s*(\d+)/,
    accounts: /共\s*(\d+)\s*账号/,
    files: /·\s*\d+\/(\d+)\s*项/,
  };
  const match = normalized.match(patterns[key]);
  return match ? Math.max(0, Number(match[1]) || 0) : 0;
}

function readMetrics(): Metrics {
  return {
    logs: parseMetricText("logs", document.getElementById("log-count")?.textContent || ""),
    tasks: parseMetricText(
      "tasks",
      document.getElementById("task-queue-meta")?.textContent || "",
    ),
    accounts: parseMetricText(
      "accounts",
      document.getElementById("board-meta")?.textContent || "",
    ),
    files: parseMetricText("files", document.getElementById("files-meta")?.textContent || ""),
  };
}

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  return reduced;
}

function isThemePreference(value: string | null | undefined): value is ThemePreference {
  return value === "system" || value === "light" || value === "dark";
}

function resolveTheme(preference: ThemePreference, systemPrefersDark: boolean): Theme {
  if (preference === "system") {
    return systemPrefersDark ? "dark" : "light";
  }
  return preference;
}

function readInitialThemePreference(): ThemePreference {
  const bootstrappedPreference = document.documentElement.dataset.themePreference;
  if (isThemePreference(bootstrappedPreference)) {
    return bootstrappedPreference;
  }

  try {
    const storedPreference = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (isThemePreference(storedPreference)) {
      return storedPreference;
    }
  } catch {
    // Storage can be unavailable in strict privacy modes.
  }

  return "system";
}

function applyTheme(preference: ThemePreference, systemPrefersDark: boolean) {
  const resolvedTheme = resolveTheme(preference, systemPrefersDark);
  const root = document.documentElement;
  root.dataset.theme = resolvedTheme;
  root.dataset.themePreference = preference;
  root.style.colorScheme = resolvedTheme;
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute("content", resolvedTheme === "light" ? "#eef3f7" : "#000000");
}

function ThemeControl() {
  const [preference, setPreference] = useState<ThemePreference>(readInitialThemePreference);

  useEffect(() => {
    const colorScheme = window.matchMedia("(prefers-color-scheme: dark)");
    const updateTheme = () => applyTheme(preference, colorScheme.matches);
    updateTheme();

    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, preference);
    } catch {
      // Theme selection still applies for the current page when storage is blocked.
    }

    if (preference !== "system") {
      return;
    }

    colorScheme.addEventListener("change", updateTheme);
    return () => colorScheme.removeEventListener("change", updateTheme);
  }, [preference]);

  useEffect(() => {
    const syncPreference = (event: StorageEvent) => {
      if (event.key !== THEME_STORAGE_KEY) {
        return;
      }

      if (event.newValue === null) {
        setPreference("system");
      } else if (isThemePreference(event.newValue)) {
        setPreference(event.newValue);
      }
    };
    window.addEventListener("storage", syncPreference);
    return () => window.removeEventListener("storage", syncPreference);
  }, []);

  const selectTheme = (nextPreference: ThemePreference) => {
    applyTheme(
      nextPreference,
      window.matchMedia("(prefers-color-scheme: dark)").matches,
    );
    setPreference(nextPreference);
  };

  return (
    <div className="theme-control" role="group" aria-label="界面主题">
      <span className="theme-control-label" aria-hidden="true">
        主题
      </span>
      <div className="theme-options">
        {THEME_OPTIONS.map(({ value, label, title }) => (
          <button
            className="theme-option"
            data-theme-option={value}
            key={value}
            type="button"
            aria-pressed={preference === value}
            title={title}
            onClick={() => selectTheme(value)}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}

function AccessibleTicker({ value, label }: { value: number; label: string }) {
  const reducedMotion = usePrefersReducedMotion();

  return (
    <>
      <span className="sr-only">{`${label}：${value}`}</span>
      {reducedMotion ? (
        <span aria-hidden="true" className="metric-value tabular-nums">
          {value.toLocaleString("zh-CN")}
        </span>
      ) : (
        <NumberTicker
          aria-hidden="true"
          className="metric-value"
          value={value}
        />
      )}
    </>
  );
}

function OperationsMetrics() {
  const [metrics, setMetrics] = useState<Metrics>(() => readMetrics());

  useEffect(() => {
    const targets = ["log-count", "task-queue-meta", "board-meta", "files-meta"]
      .map((id) => document.getElementById(id))
      .filter((element): element is HTMLElement => Boolean(element));
    const update = () => setMetrics(readMetrics());
    const observer = new MutationObserver(update);
    targets.forEach((target) =>
      observer.observe(target, { childList: true, characterData: true, subtree: true }),
    );
    update();
    return () => observer.disconnect();
  }, []);

  return (
    <div className="metric-grid" aria-label="运行概览">
      {METRIC_CONFIG.map(({ key, label, shortLabel }) => (
        <div className="metric-card" data-metric key={key}>
          <AccessibleTicker label={label} value={metrics[key]} />
          <span className="metric-label" aria-hidden="true">
            {shortLabel}
          </span>
        </div>
      ))}
    </div>
  );
}

function mountMagicUi() {
  const roots = (window.__doukMagicRoots ??= new Map<string, Root>());
  const renderRoot = (id: string, content: ReactNode) => {
    const container = document.getElementById(id);
    if (!container) {
      return;
    }
    let root = roots.get(id);
    if (!root) {
      root = createRoot(container);
      roots.set(id, root);
    }
    root.render(content);
  };

  renderRoot(
    "magic-grid-root",
    <GridPattern
      className="magic-grid-pattern"
      height={54}
      squares={[
        [1, 1],
        [4, 2],
        [7, 1],
        [10, 3],
        [13, 2],
      ]}
      strokeDasharray="2 5"
      width={54}
    />,
  );
  renderRoot("magic-metrics-root", <OperationsMetrics />);
  renderRoot("theme-control-root", <ThemeControl />);
}

function getSelectLabel(nativeSelect: HTMLSelectElement) {
  const explicitLabel =
    nativeSelect.getAttribute("aria-label") ||
    nativeSelect.getAttribute("title");
  if (explicitLabel) {
    return explicitLabel;
  }

  const label = nativeSelect.labels?.[0];
  const fieldLabel = label?.querySelector(":scope > span")?.textContent?.trim();
  if (fieldLabel) {
    return fieldLabel;
  }

  return nativeSelect.name || nativeSelect.id || "选择选项";
}

function mountEnhancedSelects() {
  const roots = (window.__doukSelectRoots ??= new Map());

  const enhance = (nativeSelect: HTMLSelectElement) => {
    if (
      roots.has(nativeSelect) ||
      nativeSelect.dataset.uiSelect === "false" ||
      nativeSelect.closest(".app-select-mount")
    ) {
      return;
    }

    const mount = document.createElement("span");
    mount.className = "app-select-mount";
    nativeSelect.insertAdjacentElement("afterend", mount);
    nativeSelect.classList.add("native-select-enhanced");
    nativeSelect.tabIndex = -1;
    nativeSelect.setAttribute("aria-hidden", "true");

    const root = createRoot(mount);
    roots.set(nativeSelect, { mount, root });
    root.render(
      <AppSelect
        ariaLabel={getSelectLabel(nativeSelect)}
        nativeSelect={nativeSelect}
      />,
    );
  };

  const remove = (nativeSelect: HTMLSelectElement) => {
    const entry = roots.get(nativeSelect);
    if (!entry) {
      return;
    }
    entry.root.unmount();
    entry.mount.remove();
    roots.delete(nativeSelect);
  };

  document.querySelectorAll("select").forEach((element) => {
    enhance(element as HTMLSelectElement);
  });

  const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      mutation.addedNodes.forEach((node) => {
        if (!(node instanceof Element)) {
          return;
        }
        if (node instanceof HTMLSelectElement) {
          enhance(node);
        }
        node.querySelectorAll("select").forEach((element) => {
          enhance(element as HTMLSelectElement);
        });
      });

      mutation.removedNodes.forEach((node) => {
        if (!(node instanceof Element)) {
          return;
        }
        if (node instanceof HTMLSelectElement) {
          remove(node);
        }
        node.querySelectorAll("select").forEach((element) => {
          remove(element as HTMLSelectElement);
        });
      });
    });
  });
  observer.observe(document.body, { childList: true, subtree: true });
}

mountMagicUi();
mountEnhancedSelects();

void import("./legacy/app.js").catch((error: unknown) => {
  const status = document.getElementById("api-status");
  if (status) {
    status.textContent = "API: 界面初始化失败";
    status.classList.add("error");
  }
  console.error("Failed to initialize the WebUI", error);
});
