import { renderPageNumbers } from "./pagination.js";
import { fetchJson, headerOptions } from "./runtime.js";

const labels = {
  success: "正常",
  legacy_success: "历史检查成功",
  no_updates: "没有符合范围的新作品",
  empty: "暂无作品",
  visibility: "私密或不可见",
  failed: "采集失败",
  skipped: "已跳过",
  never: "从未检查",
};

const outcomeLabels = {
  empty: "已确认 0 件",
  private_not_visible: "私密 · 当前采集身份不可见",
  private_followed_empty: "私密 · 已关注但未返回作品",
  works_not_visible: "作品列表对当前身份不可见",
};

const relativeDate = new Intl.RelativeTimeFormat("zh-CN", { numeric: "auto" });

function addTime(cell, value, formatDate, relative = false) {
  if (!value) {
    cell.textContent = "—";
    return;
  }
  const time = document.createElement("time");
  time.dateTime = value;
  time.textContent = formatDate(value);
  const days = Math.max(0, Math.floor((Date.now() - Date.parse(value)) / 86400000));
  if (relative && Number.isFinite(days)) {
    const unit = days >= 365 ? "year" : days >= 30 ? "month" : "day";
    const age = days / (unit === "year" ? 365 : unit === "month" ? 30 : 1);
    cell.append(relativeDate.format(-Math.floor(age), unit));
    time.className = "board-activity-secondary";
  }
  cell.append(time);
}

export function bindAccountActivity({
  formatDate, formatCount, jumpToValidatedPage, onShowCards, onOpenAccount,
}) {
  const cards = document.getElementById("board-cards-panel");
  const cardActions = document.getElementById("board-card-actions");
  const panel = document.getElementById("board-activity-panel");
  const showCards = document.getElementById("board-show-cards");
  const showActivity = document.getElementById("board-show-activity");
  const filters = [...panel.querySelectorAll("[name]")];
  const search = panel.querySelector("[name=search]");
  const table = panel.querySelector(".board-activity-table");
  const rows = table.querySelector("tbody");
  const feedback = panel.querySelector("[data-activity-feedback]");
  const pagesRegion = panel.querySelector(".board-pagination");
  const pager = pagesRegion.querySelector("nav");
  const pageForm = pagesRegion.querySelector("form");
  const pageInput = pageForm.querySelector("input");
  const dialog = document.getElementById("board-activity-details");
  const detailFeedback = dialog.querySelector("[data-activity-detail-feedback]");
  const detailFields = dialog.querySelector("dl");
  let page = 1;
  let pages = 1;
  let request;
  let detailRequest;
  let detailTrigger;
  let searchTimer;

  async function openDetails(item, trigger) {
    detailRequest?.abort();
    const controller = new AbortController();
    detailRequest = controller;
    detailTrigger = trigger;
    detailFeedback.textContent = "正在加载最近检查详情…";
    detailFields.hidden = true;
    dialog.showModal();
    const query = new URLSearchParams({ platform: item.platform, url: item.url });
    try {
      const details = await fetchJson(`/ui/api/accounts/activity/details?${query}`, {
        headers: headerOptions(false), signal: controller.signal,
      });
      if (detailRequest !== controller || !dialog.open) return;
      const fields = [
        ["账户", item.mark],
        ["采集状态", labels[details.status]],
        ["最近检查", formatDate(details.last_checked_at)],
        ["最近成功", formatDate(details.last_success_at)],
        ["采集身份", details.identity || "暂无记录"],
      ];
      if (details.task_id) fields.push(["采集任务", details.task_id]);
      if (details.reason) fields.push(["结果说明", details.reason]);
      const fragment = document.createDocumentFragment();
      for (const [label, value] of fields) {
        const term = document.createElement("dt");
        const description = document.createElement("dd");
        term.textContent = label;
        description.textContent = value;
        fragment.append(term, description);
      }
      detailFields.replaceChildren(fragment);
      detailFields.hidden = false;
      detailFeedback.textContent = "";
    } catch (error) {
      if (detailRequest === controller && dialog.open) {
        detailFeedback.textContent = `详情加载失败 · ${error.message}`;
      }
    }
  }

  dialog.querySelector("[data-activity-close]").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => {
    if (dialog.open) return;
    detailRequest?.abort();
    if (detailTrigger?.isConnected) detailTrigger.focus({ preventScroll: true });
    detailTrigger = undefined;
  });

  function button(text, action) {
    const element = document.createElement("button");
    element.type = "button";
    element.className = "board-activity-link";
    element.textContent = text;
    element.addEventListener("click", () => action(element));
    return element;
  }

  function render(payload) {
    page = payload.page;
    pages = payload.pages;
    const fragment = document.createDocumentFragment();
    for (const item of payload.items) {
      const row = document.createElement("tr");
      const account = document.createElement("th");
      account.scope = "row";
      const platform = item.platform === "douyin" ? "抖音" : "TikTok";
      const accountMeta = document.createElement("span");
      accountMeta.className = "board-activity-secondary";
      accountMeta.textContent = item.enabled ? platform : `${platform} · 已停用`;
      account.append(button(item.mark, (trigger) => onOpenAccount(item, trigger)), accountMeta);
      row.append(account);
      const result = row.insertCell();
      const label = outcomeLabels[item.outcome_code] && item.status === "visibility"
        ? outcomeLabels[item.outcome_code] : labels[item.status];
      if (item.status === "never") {
        result.textContent = label;
      } else {
        const detailsButton = button(label, (trigger) => void openDetails(item, trigger));
        detailsButton.setAttribute("aria-label", `${item.mark} · ${label} · 最近检查详情`);
        result.append(detailsButton);
      }
      if (item.status === "empty") {
        const confirmation = document.createElement("span");
        confirmation.className = "board-activity-secondary";
        confirmation.textContent = outcomeLabels.empty;
        result.append(confirmation);
      }
      addTime(row.insertCell(), item.latest_work_at, formatDate, true);
      addTime(row.insertCell(), item.last_checked_at, formatDate);
      fragment.append(row);
    }
    rows.replaceChildren(fragment);
    table.hidden = !payload.items.length;
    pagesRegion.hidden = pages < 2;
    pageInput.value = String(page);
    pageInput.max = String(pages);
    renderPageNumbers(pager, page, pages, goToPage);
    feedback.textContent = payload.total
      ? `${formatCount(payload.total)} 个账户 · 第 ${page} / ${pages} 页`
      : "没有符合条件的账户";
  }

  function goToPage(nextPage) {
    page = nextPage;
    void load();
  }

  async function load() {
    window.clearTimeout(searchTimer);
    request?.abort();
    const controller = new AbortController();
    request = controller;
    const query = new URLSearchParams(filters.map(({ name, value }) => [name, value.trim()]));
    query.set("page", String(page));
    table.setAttribute("aria-busy", "true");
    feedback.textContent = "正在加载采集状态…";
    try {
      const payload = await fetchJson(`/ui/api/accounts/activity?${query}`, {
        headers: headerOptions(false), signal: controller.signal,
      });
      if (request === controller && !panel.hidden) render(payload);
    } catch (error) {
      if (request === controller && !panel.hidden) {
        const focused = pagesRegion.contains(document.activeElement);
        table.hidden = true;
        pagesRegion.hidden = true;
        feedback.textContent = `加载失败 · ${error.message}`;
        if (focused) panel.querySelector("[data-activity-refresh]").focus();
      }
    } finally {
      if (request === controller) table.removeAttribute("aria-busy");
    }
  }

  function switchView(active) {
    if (active === !panel.hidden) return;
    cards.hidden = cardActions.hidden = active;
    panel.hidden = !active;
    showCards.setAttribute("aria-pressed", String(!active));
    showActivity.setAttribute("aria-pressed", String(active));
    if (active) {
      void load();
    } else {
      window.clearTimeout(searchTimer);
      request?.abort();
      void onShowCards();
    }
  }

  showCards.addEventListener("click", () => switchView(false));
  showActivity.addEventListener("click", () => switchView(true));
  search.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    request?.abort();
    searchTimer = window.setTimeout(() => goToPage(1), 250);
  });
  for (const select of panel.querySelectorAll("select")) {
    select.addEventListener("change", () => goToPage(1));
  }
  panel.querySelector("[data-activity-refresh]").addEventListener("click", () => void load());
  panel.querySelector("[data-activity-reset]").addEventListener("click", () => {
    search.value = "";
    for (const select of panel.querySelectorAll("select")) select.selectedIndex = 0;
    goToPage(1);
  });
  pageForm.addEventListener("submit", (event) => {
    event.preventDefault();
    jumpToValidatedPage(pageInput, pages, goToPage, (message) => { feedback.textContent = message; });
  });
  return { active: () => !panel.hidden, load };
}
