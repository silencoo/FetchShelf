const pageDirection = new Map([
  ["ArrowLeft", -1], ["PageUp", -1],
  ["ArrowRight", 1], ["PageDown", 1],
]);

export function handlePageShortcut(event) {
  const direction = pageDirection.get(event.key);
  const target = event.target;
  if (!direction || event.defaultPrevented || event.isComposing || event.repeat ||
      event.altKey || event.ctrlKey || event.metaKey || event.shiftKey ||
      !(target instanceof HTMLElement) || target.isContentEditable ||
      target.closest('input, textarea, select, video, audio, [role="slider"], [role="combobox"], [role="menu"]')) {
    return;
  }

  const dialog = target.closest("dialog[open]");
  if (!dialog && document.querySelector("dialog[open]")) return;
  const scope = dialog || document;
  const pagers = [...scope.querySelectorAll("nav.page-numbers")].filter(nav =>
    nav.getClientRects().length && nav.querySelector('[aria-current="page"]')
  );
  // When two tables are visible, only page the one that owns keyboard focus.
  for (let owner = target; owner; owner = owner.parentElement) {
    const local = pagers.filter(nav => owner.contains(nav));
    if (local.length > 1) return;
    if (local.length === 1) {
      const current = local[0].querySelector('[aria-current="page"]');
      const next = direction < 0 ? current.previousElementSibling : current.nextElementSibling;
      if (next instanceof HTMLButtonElement && !next.disabled) {
        event.preventDefault();
        next.click();
      }
      return;
    }
    if (owner === dialog) return;
  }
}

export function renderPageNumbers(nav, current, total, select, busy = false) {
  const pages = new Set([1, total]);
  const start = current <= 3 ? 1 : Math.min(current - 1, Math.max(1, total - 3));
  const end = current >= total - 2 ? total : Math.min(total, Math.max(4, current + 1));
  for (let page = start; page <= end; page++) {
    pages.add(page);
  }

  const fragment = document.createDocumentFragment();
  function addButton(page) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn ghost";
    button.textContent = String(page);
    button.setAttribute("aria-label", `第 ${page} 页`);
    if (Math.abs(page - current) === 1) {
      const keys = page < current ? ["ArrowLeft", "PageUp"] : ["ArrowRight", "PageDown"];
      button.setAttribute("aria-keyshortcuts", keys.join(" "));
      button.title = keys.join(" / ");
    }
    button.disabled = busy;
    if (page === current) button.setAttribute("aria-current", "page");
    else button.addEventListener("click", () => select(page));
    fragment.appendChild(button);
  }

  let previous = 0;
  for (const page of [...pages].sort((a, b) => a - b)) {
    if (page - previous === 2) addButton(previous + 1);
    if (page - previous > 2) {
      const gap = document.createElement("span");
      gap.textContent = "…";
      gap.setAttribute("aria-hidden", "true");
      fragment.appendChild(gap);
    }
    addButton(page);
    previous = page;
  }
  const hadFocus = nav.contains(document.activeElement);
  nav.replaceChildren(fragment);
  if (hadFocus) nav.querySelector('[aria-current="page"]')?.focus({ preventScroll: true });
}
