import { useEffect, useState, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";

import { GridPattern } from "@/components/ui/grid-pattern";
import { NumberTicker } from "@/components/ui/number-ticker";
import "@/styles.css";

type MetricKey = "logs" | "tasks" | "accounts" | "files";

interface Metrics {
  logs: number;
  tasks: number;
  accounts: number;
  files: number;
}

declare global {
  interface Window {
    __doukMagicRoots?: Map<string, Root>;
  }
}

const INITIAL_METRICS: Metrics = {
  logs: 0,
  tasks: 0,
  accounts: 0,
  files: 0,
};

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
}

mountMagicUi();

void import("./legacy/app.js").catch((error: unknown) => {
  const status = document.getElementById("api-status");
  if (status) {
    status.textContent = "API: 界面初始化失败";
    status.classList.add("error");
  }
  console.error("Failed to initialize the WebUI", error);
});
