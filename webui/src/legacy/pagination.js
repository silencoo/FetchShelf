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
