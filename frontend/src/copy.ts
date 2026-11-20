// Copy buttons: a [data-copy] button copies its value to the clipboard and says so in a toast.
// The buttons are hidden without JavaScript (the text beside them can still be selected).

import { showToast } from "./toast";

export function initCopyButtons(): void {
  document.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target : null;
    const button = target?.closest<HTMLButtonElement>("button[data-copy]");
    if (!button) return;
    const value = button.dataset.copy ?? "";
    const done = button.dataset.copyDone ?? "Copied.";
    navigator.clipboard.writeText(value).then(
      () => showToast({ message: done, tone: "success" }),
      () =>
        showToast({
          message: "We couldn't copy that. Select it and copy it instead.",
          tone: "warning",
        }),
    );
  });
}
