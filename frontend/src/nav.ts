// Collapsible navigation below 64rem (spec §12). Without JS the navigation stays open and the toggle
// stays hidden (it carries the hidden attribute until this runs).

export function initNav(): void {
  for (const toggle of document.querySelectorAll<HTMLButtonElement>("[data-nav-toggle]")) {
    const nav = document.getElementById(toggle.getAttribute("aria-controls") ?? "");
    if (!nav) continue;
    nav.classList.add("is-collapsible");
    toggle.hidden = false;
    toggle.addEventListener("click", () => {
      const open = toggle.getAttribute("aria-expanded") !== "true";
      toggle.setAttribute("aria-expanded", String(open));
      nav.classList.toggle("is-open", open);
    });
  }
}
