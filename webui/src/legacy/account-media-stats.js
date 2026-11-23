import { renderPageNumbers } from "./pagination.js";
import { fetchJson, headerOptions } from "./runtime.js";

export function bindAccountMediaStats({ formatSize, formatCount, formatDate, jumpToValidatedPage }) {
  const dialog = document.getElementById("account-media-stats");
  const search = dialog.querySelector("[data-media-stats-search]");
  const platform = dialog.querySelector("[data-media-stats-platform]");
  const table = dialog.querySelector("[data-media-stats-table]");
  const body = dialog.querySelector("[data-media-stats-rows]");
  const status = dialog.querySelector("[data-media-stats-status]");
  const refresh = dialog.querySelector("[data-media-stats-refresh]");
  const footer = dialog.querySelector("[data-media-stats-pages]");
  const pager = footer.querySelector("nav");
  const jump = footer.querySelector("[data-media-stats-jump]");
  const pageInput = jump.querySelector("input");
  const sortButtons = [...dialog.querySelectorAll("[data-media-stats-sort]")];
  let page = 1;
  let pages = 1;
  let sort = "size";
  let order = "desc";
  let opener;
  let request;
  let timer;

  const goToPage = (nextPage) => {
    page = nextPage;
    void load();
  };

  function render(payload) {
    page = payload.page;
    pages = payload.pages;
    const fragment = document.createDocumentFragment();
    for (const item of payload.items) {
      const row = document.createElement("tr");
      const account = document.createElement("th");
      account.scope = "row";
      account.textContent = item.name;
      row.append(account);
      const label = item.platform === "tiktok" ? "TikTok" : "抖音";
      for (const text of [label, formatSize(item.size), formatCount(item.images), formatCount(item.videos)]) {
        row.insertCell().textContent = text;
      }
      fragment.append(row);
    }
    body.replaceChildren(fragment);
    table.hidden = !payload.items.length;
    footer.hidden = pages < 2;
    pageInput.value = String(page);
    pageInput.max = String(pages);
    renderPageNumbers(pager, page, pages, goToPage);

    const details = [];
    if (payload.refreshed_at) {
      details.push(payload.total ? `${formatCount(payload.total)} 个账户 · 第 ${page} / ${pages} 页` : "没有符合条件的账户媒体");
      details.push(`统计时间 ${formatDate(payload.refreshed_at)}`);
    }
    if (payload.status === "scanning" || payload.status === "refreshing") details.push("正在后台统计本地媒体…");
    if (payload.error) details.push(payload.error);
    if (payload.partial) details.push("部分文件读取失败");
    status.textContent = details.join(" · ");
    if (payload.status === "scanning" || payload.status === "refreshing") {
      timer = window.setTimeout(() => void load(), 4000);
    }
  }

  function cancelLoad() {
    window.clearTimeout(timer);
    request?.abort();
    request = undefined;
  }

  async function load(forceRefresh = false) {
    cancelLoad();
    const controller = new AbortController();
    request = controller;
    const query = new URLSearchParams({
      search: search.value.trim(), platform: platform.value, sort, order,
      page: String(page), refresh: String(forceRefresh),
    });
    table.setAttribute("aria-busy", "true");
    try {
      const payload = await fetchJson(`/ui/api/accounts/media-stats?${query}`, {
        headers: headerOptions(false), signal: controller.signal,
      });
      if (request === controller && dialog.open) render(payload);
    } catch (error) {
      if (request === controller && dialog.open) status.textContent = `加载失败 · ${error.message}`;
    } finally {
      if (request === controller) table.removeAttribute("aria-busy");
    }
  }

  document.querySelectorAll("[data-open-account-media-stats]").forEach((button) => {
    button.addEventListener("click", () => {
      opener = button;
      dialog.showModal();
      if (table.hidden) status.textContent = "正在加载账户媒体统计…";
      void load();
    });
  });
  dialog.querySelector("[data-media-stats-close]").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => {
    cancelLoad();
    table.removeAttribute("aria-busy");
    opener?.focus({ preventScroll: true });
    opener = undefined;
  });
  search.addEventListener("input", () => {
    cancelLoad();
    page = 1;
    timer = window.setTimeout(() => void load(), 250);
  });
  platform.addEventListener("change", () => goToPage(1));
  refresh.addEventListener("click", () => void load(true));
  for (const button of sortButtons) {
    button.addEventListener("click", () => {
      const field = button.dataset.mediaStatsSort;
      order = sort === field && order === "desc" ? "asc" : "desc";
      sort = field;
      for (const candidate of sortButtons) {
        if (candidate === button) candidate.parentElement.setAttribute("aria-sort", order === "desc" ? "descending" : "ascending");
        else candidate.parentElement.removeAttribute("aria-sort");
        candidate.querySelector("span").textContent = candidate === button ? (order === "desc" ? "↓" : "↑") : "";
      }
      goToPage(1);
    });
  }
  jump.addEventListener("submit", (event) => {
    event.preventDefault();
    jumpToValidatedPage(pageInput, pages, goToPage, (message) => { status.textContent = message; });
  });
}
