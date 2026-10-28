// Toasts (spec §12): the server sends HX-Trigger {"toast": {message, tone}} after an HTMX request,
// or a Django message after a normal POST (rendered into #toasts by base.html).
// Messages are set with textContent, never innerHTML. Success and info hide after 8 s unless
// hovered or focused; warnings and errors stay until dismissed.

export type Tone = "info" | "success" | "warning" | "danger";

export interface ToastDetail {
  message: string;
  tone?: Tone;
}

const TONES: ReadonlySet<string> = new Set(["info", "success", "warning", "danger"]);
const AUTO_HIDE_MS = 8000;

function isToastDetail(value: unknown): value is ToastDetail {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as { message?: unknown }).message === "string"
  );
}

function arm(toast: HTMLElement): void {
  const tone = toast.dataset.tone;
  if (tone !== "info" && tone !== "success") return;
  const tick = (): void => {
    if (toast.matches(":hover, :focus-within")) {
      window.setTimeout(tick, AUTO_HIDE_MS);
    } else {
      toast.remove();
    }
  };
  window.setTimeout(tick, AUTO_HIDE_MS);
}

export function showToast(detail: ToastDetail): HTMLElement | null {
  const region = document.getElementById("toasts");
  const template = document.getElementById("toast-template");
  if (!(region && template instanceof HTMLTemplateElement)) return null;
  const toast = template.content.firstElementChild?.cloneNode(true);
  if (!(toast instanceof HTMLElement)) return null;
  const tone = detail.tone && TONES.has(detail.tone) ? detail.tone : "info";
  toast.className = `toast toast--${tone}`;
  toast.dataset.tone = tone;
  const text = toast.querySelector(".toast__text");
  if (text) text.textContent = detail.message;
  region.append(toast);
  arm(toast);
  return toast;
}

export function initToasts(): void {
  for (const toast of document.querySelectorAll<HTMLElement>("#toasts [data-toast]")) arm(toast);
  document.addEventListener("click", (event) => {
    const button =
      event.target instanceof Element ? event.target.closest("[data-toast-close]") : null;
    button?.closest("[data-toast]")?.remove();
  });
  document.addEventListener("toast", (event) => {
    const detail: unknown = (event as CustomEvent<unknown>).detail;
    if (isToastDetail(detail)) showToast(detail);
  });
}
