// Direct-to-storage uploads (spec §8) for the upload field (templates/components/file_input.html):
// an <input type=file data-upload-purpose> inside .file-input, with a hidden [data-upload-value]
// input, a [data-upload-live] status region and a [data-upload-replace] button.
//
// Per file: check type and size here (the server's own copy, no request when they fail), ask the
// server for a presigned PUT (intent), PUT the bytes straight to storage with progress, then
// confirm. On success the hidden input holds the file id and the field shows "{name} uploaded";
// any failure shows the error state and clears the hidden input. The live region announces only the
// start, the end and errors. Text is set with textContent, never innerHTML.

import { NETWORK_ERROR, SERVER_ERROR } from "./toast";

const MB = 1024 * 1024;
const PUT_FAILED = "The upload didn't finish. Try again.";
const SESSION_EXPIRED = "Your session may have expired. Reload the page and try again.";
const EMPTY = "This file is empty. Choose another file.";
const TYPE_LABELS: Readonly<Record<string, string>> = {
  "application/pdf": "PDF",
  "image/jpeg": "JPG",
  "image/png": "PNG",
};

class UploadError extends Error {}

interface Field {
  root: HTMLElement;
  control: HTMLInputElement;
  value: HTMLInputElement | null;
  live: HTMLElement | null;
  replace: HTMLButtonElement | null;
  label: string;
}

// The latest run per field, so a stale run (a file replaced mid-upload) changes nothing.
const runs = new WeakMap<HTMLElement, number>();
// The PUT in flight per field, aborted when a new file replaces it.
const puts = new WeakMap<HTMLElement, XMLHttpRequest>();

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function fieldOf(control: HTMLInputElement): Field | null {
  const root = control.closest<HTMLElement>(".file-input");
  if (!root) return null;
  return {
    root,
    control,
    value: root.querySelector<HTMLInputElement>("input[data-upload-value]"),
    live: root.querySelector<HTMLElement>("[data-upload-live]"),
    replace: root.querySelector<HTMLButtonElement>("[data-upload-replace]"),
    label: root.querySelector("label")?.textContent?.trim() ?? "",
  };
}

function typesPhrase(types: readonly string[]): string {
  const labels = types.map((type) => TYPE_LABELS[type] ?? type);
  if (labels.length === 1) return labels[0] ?? "";
  return `${labels.slice(0, -1).join(", ")} or ${labels.at(-1) ?? ""}`;
}

/** The server's checks, in its order, so a file it would refuse never leaves the browser. */
function check(file: File, control: HTMLInputElement): string | null {
  const types = control.accept
    .split(",")
    .map((type) => type.trim())
    .filter(Boolean);
  if (types.length > 0 && !types.includes(file.type)) {
    return `You can upload a ${typesPhrase(types)} file here.`;
  }
  if (file.size <= 0) return EMPTY;
  const max = Number(control.dataset.uploadMax);
  if (max > 0 && file.size > max) {
    return `This file is ${Math.ceil(file.size / MB)} MB. Upload a file of ${Math.floor(max / MB)} MB or less.`;
  }
  return null;
}

function csrfToken(): string {
  try {
    const headers: unknown = JSON.parse(document.body.getAttribute("hx-headers") ?? "{}");
    const token = isRecord(headers) ? headers["X-CSRFToken"] : undefined;
    return typeof token === "string" ? token : "";
  } catch {
    return "";
  }
}

/** POST to the app; the JSON body on success, else an UploadError with a sentence to show. */
async function post(url: string, body?: unknown): Promise<Record<string, unknown>> {
  const headers: Record<string, string> = { "X-CSRFToken": csrfToken() };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers,
      body: body === undefined ? null : JSON.stringify(body),
    });
  } catch {
    throw new UploadError(NETWORK_ERROR);
  }
  let data: unknown = null;
  try {
    data = await response.json();
  } catch {
    // Django's CSRF failure and proxy errors are HTML: fall through to the generic copy.
  }
  if (response.ok && isRecord(data)) return data;
  if (isRecord(data) && typeof data.error === "string") throw new UploadError(data.error);
  if (response.status === 401 || response.status === 403) throw new UploadError(SESSION_EXPIRED);
  throw new UploadError(SERVER_ERROR);
}

function put(
  root: HTMLElement,
  url: string,
  headers: Record<string, unknown>,
  file: File,
  onProgress: (percent: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    puts.set(root, xhr);
    xhr.addEventListener("loadend", () => {
      if (puts.get(root) === xhr) puts.delete(root);
    });
    xhr.open("PUT", url);
    for (const [name, value] of Object.entries(headers)) {
      if (typeof value === "string") xhr.setRequestHeader(name, value);
    }
    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable && event.total > 0) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    });
    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve();
      else reject(new UploadError(PUT_FAILED));
    });
    xhr.addEventListener("error", () => reject(new UploadError(PUT_FAILED)));
    xhr.addEventListener("abort", () => reject(new UploadError(PUT_FAILED)));
    xhr.addEventListener("timeout", () => reject(new UploadError(PUT_FAILED)));
    xhr.send(file);
  });
}

function setDescribedBy(control: HTMLInputElement, id: string, on: boolean): void {
  const ids = (control.getAttribute("aria-describedby") ?? "").split(/\s+/).filter(Boolean);
  const next = ids.filter((each) => each !== id);
  if (on) next.push(id);
  if (next.length > 0) control.setAttribute("aria-describedby", next.join(" "));
  else control.removeAttribute("aria-describedby");
}

function announce(field: Field, message: string): void {
  if (field.live) field.live.textContent = message;
}

/** Back to the idle look: no status, no error, control visible, Replace hidden. */
function reset(field: Field): void {
  const { root, control } = field;
  for (const old of root.querySelectorAll(":scope > .file-input__status, :scope > .field__error")) {
    old.remove();
  }
  root.classList.remove("field--invalid", "file-input--done");
  control.removeAttribute("aria-invalid");
  setDescribedBy(control, `${control.id}-error`, false);
  if (field.replace) field.replace.hidden = true;
}

/** Put a status block where the template puts it: after the control's siblings, before Replace. */
function placeStatus(field: Field, status: HTMLElement): void {
  if (field.replace) field.root.insertBefore(status, field.replace);
  else field.root.append(status);
}

function showProgress(field: Field, name: string): (percent: number) => void {
  const status = document.createElement("div");
  status.className = "file-input__status";
  const progress = document.createElement("progress");
  progress.max = 100;
  progress.value = 0;
  progress.setAttribute("aria-label", `Upload progress for ${field.label}`);
  const text = document.createElement("span");
  status.append(progress, text);
  placeStatus(field, status);
  const update = (percent: number): void => {
    progress.value = percent;
    progress.textContent = `${percent}%`;
    text.textContent = `Uploading ${name}: ${percent}%`;
  };
  update(0);
  return update;
}

function doneIcon(field: Field): Node | null {
  // The template renders the icon (with the sprite's hashed URL) in an inert <template>.
  const template = field.root.querySelector<HTMLTemplateElement>("template[data-upload-done-icon]");
  return template?.content.firstElementChild?.cloneNode(true) ?? null;
}

function showDone(field: Field, id: string, name: string): void {
  reset(field);
  // Cleared so choosing the same file again (Replace, or a retry after an error) fires "change".
  field.control.value = "";
  const { root, control } = field;
  const status = document.createElement("p");
  status.className = "file-input__status file-input__status--done";
  const text = document.createElement("span");
  text.textContent = `${name} uploaded`;
  const icon = doneIcon(field);
  if (icon) status.append(icon);
  status.append(text);
  placeStatus(field, status);
  if (field.value) field.value.value = id;
  const hadFocus = document.activeElement === control;
  root.classList.add("file-input--done");
  if (field.replace) {
    field.replace.hidden = false;
    if (hadFocus) field.replace.focus();
  }
  announce(field, `${name} uploaded`);
  root.dispatchEvent(new CustomEvent("upload:done", { bubbles: true, detail: { id, name } }));
}

function showError(field: Field, message: string): void {
  reset(field);
  field.control.value = "";
  const { root, control } = field;
  const errorId = `${control.id}-error`;
  const error = document.createElement("p");
  error.className = "field__error";
  error.id = errorId;
  const text = document.createElement("span");
  text.textContent = message;
  error.append(text);
  // Above the control, after the help text (the static error state's order).
  const anchor =
    root.querySelector(":scope > .field__help") ?? root.querySelector(":scope > label");
  if (anchor) anchor.after(error);
  else root.prepend(error);
  root.classList.add("field--invalid");
  control.setAttribute("aria-invalid", "true");
  setDescribedBy(control, errorId, true);
  if (field.value) field.value.value = "";
  announce(field, message);
}

async function upload(field: Field, file: File): Promise<void> {
  const run = (runs.get(field.root) ?? 0) + 1;
  runs.set(field.root, run);
  puts.get(field.root)?.abort();
  puts.delete(field.root);
  const current = (): boolean => runs.get(field.root) === run;
  // Replace hides itself; keep keyboard focus in the field on the control it reveals.
  const replaceHadFocus = field.replace !== null && document.activeElement === field.replace;
  reset(field);
  if (replaceHadFocus) field.control.focus();
  if (field.value) field.value.value = "";

  const problem = check(file, field.control);
  if (problem) {
    showError(field, problem);
    return;
  }

  announce(field, `Uploading ${file.name}`);
  const progress = showProgress(field, file.name);
  try {
    const intent = await post(field.control.dataset.uploadUrl ?? "", {
      purpose: field.control.dataset.uploadPurpose ?? "",
      name: file.name,
      type: file.type,
      size: file.size,
    });
    if (!current()) return;
    const { url, confirm_url: confirmUrl } = intent;
    if (typeof url !== "string" || typeof confirmUrl !== "string") {
      throw new UploadError(SERVER_ERROR);
    }
    const headers = isRecord(intent.headers) ? intent.headers : {};
    await put(field.root, url, headers, file, (percent) => {
      if (current()) progress(percent);
    });
    if (!current()) return;
    const confirmed = await post(confirmUrl);
    if (!current()) return;
    const id = typeof confirmed.id === "string" ? confirmed.id : "";
    const name = typeof confirmed.name === "string" ? confirmed.name : file.name;
    if (!id) throw new UploadError(SERVER_ERROR);
    showDone(field, id, name);
  } catch (error) {
    if (!current()) return;
    showError(field, error instanceof UploadError ? error.message : SERVER_ERROR);
  }
}

export function initUploads(): void {
  document.addEventListener("change", (event) => {
    const control = event.target;
    if (
      !(
        control instanceof HTMLInputElement &&
        control.matches("input[type=file][data-upload-purpose]")
      )
    )
      return;
    const file = control.files?.[0];
    const field = fieldOf(control);
    if (!(file && field)) return;
    void upload(field, file);
  });
  document.addEventListener("click", (event) => {
    const button =
      event.target instanceof Element ? event.target.closest("[data-upload-replace]") : null;
    button
      ?.closest(".file-input")
      ?.querySelector<HTMLInputElement>("input[type=file][data-upload-purpose]")
      ?.click();
  });
}
