// Row selection for bulk actions (spec §12): <form data-bulk> with [data-bulk-item] checkboxes, an optional
// [data-bulk-all] checkbox and a [data-bulk-bar] whose buttons need a selection. Without JS the form still
// posts whatever is checked.

function update(form: HTMLFormElement): void {
  const items = [...form.querySelectorAll<HTMLInputElement>("input[data-bulk-item]")];
  const selected = items.filter((item) => item.checked).length;
  const all = form.querySelector<HTMLInputElement>("input[data-bulk-all]");
  if (all) {
    all.checked = selected > 0 && selected === items.length;
    all.indeterminate = selected > 0 && selected < items.length;
  }
  const count = form.querySelector("[data-bulk-count]");
  if (count) count.textContent = selected === 0 ? "None selected" : `${selected} selected`;
  for (const button of form.querySelectorAll<HTMLButtonElement>("[data-bulk-bar] button")) {
    button.disabled = selected === 0;
  }
}

function updateAll(): void {
  for (const form of document.querySelectorAll<HTMLFormElement>("form[data-bulk]")) update(form);
}

export function initBulk(): void {
  updateAll();
  document.addEventListener("change", (event) => {
    const input = event.target;
    if (!(input instanceof HTMLInputElement)) return;
    const form = input.closest<HTMLFormElement>("form[data-bulk]");
    if (!form) return;
    if (input.matches("[data-bulk-all]")) {
      for (const item of form.querySelectorAll<HTMLInputElement>("input[data-bulk-item]")) {
        item.checked = input.checked;
      }
    }
    update(form);
  });
  document.addEventListener("htmx:afterSettle", updateAll);
}
