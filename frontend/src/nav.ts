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
    // Escape closes the open menu and puts focus back on its toggle (WCAG 2.1.2 pattern).
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape" || toggle.hidden) return;
      // An open popover menu takes this Escape (the browser closes it); the navigation stays open.
      if (CSS.supports("selector(:popover-open)") && document.querySelector(":popover-open")) return;
      if (toggle.getAttribute("aria-expanded") !== "true") return;
      toggle.setAttribute("aria-expanded", "false");
      nav.classList.remove("is-open");
      toggle.focus();
    });
  }
}
