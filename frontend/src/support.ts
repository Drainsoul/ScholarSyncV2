// Reply templates (spec §12 rev 35). A <select data-template-picker="<form id>"> sits in a small GET
// form; without JS its "Use template" button reloads the page with the form filled. With JS the
// button and its hint are hidden and picking a template fills the reply form at once: the option's
// data-body into [name=body], data-subject into [name=subject] (email only), its id into
// [name=template]. Text the user typed is replaced only after a confirm.

const CONFIRM = "Replace what you've typed with this template?";

function hideFallbacks(root: ParentNode): void {
  for (const element of root.querySelectorAll<HTMLElement>("[data-template-use]")) {
    element.hidden = true;
  }
}

function targetForm(select: HTMLSelectElement): HTMLFormElement | null {
  const form = document.getElementById(select.dataset.templatePicker ?? "");
  return form instanceof HTMLFormElement ? form : null;
}

// A page the server filled from ?template= (the no-JS button) starts as if the template had been
// picked here: the picker shows it, and its untouched text is replaced without a confirm.
function adoptServerFill(root: ParentNode): void {
  for (const select of root.querySelectorAll<HTMLSelectElement>("select[data-template-picker]")) {
    const form = targetForm(select);
    const body = form?.querySelector<HTMLTextAreaElement>("[name=body]");
    const picked = form?.querySelector<HTMLInputElement>("[name=template]")?.value ?? "";
    if (!body || picked === "") continue;
    const option = Array.from(select.options).find((candidate) => candidate.value === picked);
    if (!option || body.value !== (option.dataset.body ?? "")) continue;
    select.value = picked;
    select.dataset.previous = picked;
    body.dataset.filled = body.value;
  }
}

function fill(select: HTMLSelectElement): void {
  const form = targetForm(select);
  if (!form) return;
  const body = form.querySelector<HTMLTextAreaElement>("[name=body]");
  const subject = form.querySelector<HTMLInputElement>("[name=subject]");
  const template = form.querySelector<HTMLInputElement>("[name=template]");
  const option = select.selectedOptions[0];
  if (!body || !option) return;
  const typed = body.value.trim() !== "" && body.value !== (body.dataset.filled ?? "");
  if (typed && !window.confirm(CONFIRM)) {
    select.value = select.dataset.previous ?? "";
    return;
  }
  select.dataset.previous = select.value;
  const text = option.dataset.body ?? "";
  body.value = text;
  body.dataset.filled = text;
  if (subject && option.dataset.subject) subject.value = option.dataset.subject;
  if (template) template.value = select.value;
  body.focus();
}

export function initTemplatePicker(): void {
  hideFallbacks(document);
  adoptServerFill(document);
  document.addEventListener("htmx:afterSwap", (event) => {
    if (event.target instanceof Element) {
      hideFallbacks(event.target);
      adoptServerFill(event.target);
    }
  });
  document.addEventListener("change", (event) => {
    const target = event.target;
    if (target instanceof HTMLSelectElement && target.dataset.templatePicker !== undefined) {
      fill(target);
    }
  });
}
