// Popover menus (spec §12 rev 29): the account menu and the switchers are a <button popovertarget>
// and a popover list, so the browser opens and closes them (outside click, Esc, focus return) with no
// script. CSS anchor positioning sets them against their button; where that is missing, this places
// them from the button's box just before they open, so nothing is measured and nothing flashes.

const GAP_PX = 4;

function place(panel: HTMLElement): void {
  const button = document.querySelector<HTMLElement>(`[popovertarget="${panel.id}"]`);
  if (!button) return;
  const box = button.getBoundingClientRect();
  const style = panel.style;
  style.inset = "auto";
  style.margin = "0";
  style.minWidth = `${box.width}px`;
  if (panel.classList.contains("account-menu__panel")) {
    // At the foot of the sidebar: open upward, as wide as the card.
    style.width = `${box.width}px`;
    style.bottom = `${window.innerHeight - box.top + GAP_PX}px`;
    style.left = `${box.left}px`;
    return;
  }
  style.top = `${box.bottom + GAP_PX}px`;
  if (panel.closest(".switcher--end")) {
    style.right = `${document.documentElement.clientWidth - box.right}px`;
  } else {
    style.left = `${box.left}px`;
  }
}

export function initMenus(): void {
  if (CSS.supports("position-area", "block-end")) return;
  // beforetoggle does not bubble, so listen in the capture phase.
  document.addEventListener(
    "beforetoggle",
    (event) => {
      const panel = event.target;
      if (!(panel instanceof HTMLElement && panel.classList.contains("menu-panel"))) return;
      if ((event as ToggleEvent).newState === "open") place(panel);
    },
    true,
  );
}
