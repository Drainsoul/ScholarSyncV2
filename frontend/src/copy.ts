// Copy buttons: a [data-copy] button copies its value to the clipboard. The confirmation is a brief
// "Copied" bubble just above the pointer (above the button for a keyboard press), gone after a
// moment; a small action gets no toast. Screen readers hear it from a visually hidden live region.
// The buttons are hidden without JavaScript (the text beside them can still be selected).

const SHOWN_MS = 1200;
const GAP_PX = 10;

let live: HTMLElement | null = null;

function announce(text: string): void {
  if (!live) {
    live = document.createElement("div");
    live.className = "visually-hidden";
    live.setAttribute("aria-live", "polite");
    document.body.append(live);
  }
  live.textContent = "";
  // A fresh text node after a tick, so the same message is read again on the next copy.
  window.setTimeout(() => {
    if (live) live.textContent = text;
  }, 50);
}

function bubble(text: string, x: number, y: number, failed: boolean): void {
  for (const old of document.querySelectorAll(".copy-tip")) old.remove();
  const tip = document.createElement("div");
  tip.className = failed ? "copy-tip copy-tip--failed" : "copy-tip";
  tip.setAttribute("aria-hidden", "true");
  tip.textContent = text;
  // The open dialog is the top layer; anything outside it would sit behind its backdrop.
  (document.querySelector("dialog[open]") ?? document.body).append(tip);
  tip.style.left = `${x}px`;
  tip.style.top = `${y - GAP_PX}px`;
  window.setTimeout(() => tip.classList.add("copy-tip--leaving"), SHOWN_MS);
  window.setTimeout(() => tip.remove(), SHOWN_MS + 300);
}

export function initCopyButtons(): void {
  document.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target : null;
    const button = target?.closest<HTMLButtonElement>("button[data-copy]");
    if (!button) return;
    const box = button.getBoundingClientRect();
    // A mouse or touch click has a position; Enter or Space on the button (detail 0) has not.
    const byPointer = event.detail > 0;
    const x = byPointer ? event.clientX : box.left + box.width / 2;
    const y = byPointer ? event.clientY : box.top;
    navigator.clipboard.writeText(button.dataset.copy ?? "").then(
      () => {
        bubble("Copied", x, y, false);
        announce("Copied");
      },
      () => {
        bubble("Couldn't copy", x, y, true);
        announce("Couldn't copy. Select the text and copy it instead.");
      },
    );
  });
}
