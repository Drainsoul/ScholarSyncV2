// Modal dialogs (spec §12). An opener is a link to the full page (no-JS) with hx-get to a fragment and
// hx-target="#app-dialog-body"; after the swap the dialog opens. [data-dialog-close] closes the dialog it
// sits in, and the server can close it with HX-Trigger "closeDialog". Focus returns to the opener.

function openDialog(dialog: HTMLDialogElement): void {
  if (dialog.open) return;
  const previous = document.activeElement;
  dialog.addEventListener(
    "close",
    () => {
      if (dialog.id === "app-dialog") document.getElementById("app-dialog-body")?.replaceChildren();
      if (previous instanceof HTMLElement && previous.isConnected) previous.focus();
    },
    { once: true },
  );
  dialog.showModal();
}

export function initDialogs(): void {
  document.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target : null;
    const dialog = target?.closest("[data-dialog-close]")?.closest("dialog");
    if (dialog) {
      event.preventDefault();
      dialog.close();
    }
  });
  document.addEventListener("htmx:afterSwap", (event) => {
    const { target } = (event as CustomEvent<{ target: Element }>).detail;
    const dialog = target.closest("dialog");
    if (dialog) openDialog(dialog);
  });
  document.addEventListener("closeDialog", () => {
    for (const dialog of document.querySelectorAll<HTMLDialogElement>("dialog[open]"))
      dialog.close();
  });
}
