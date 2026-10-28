// Toasts (spec §12): the server sends HX-Trigger {"toast": {message, tone}} after an HTMX request,
// or a Django message after a normal POST (rendered into #toasts by base.html). A failed htmx request
// (4xx/5xx or no connection) shows a danger toast here, since htmx swaps nothing and the click would
// look ignored. Messages are set with textContent, never innerHTML. Success and info hide after 8 s
// unless hovered or focused; warnings and errors stay until dismissed.
//
// An open modal dialog makes the rest of the page inert, so while one is open toasts go into the
// dialog's own [data-toast-region] (base.html); when it closes, any left there move to #toasts.

export type Tone = "info" | "success" | "warning" | "danger";

export interface ToastDetail {
  message: string;
  tone?: Tone;
}

const TONES: ReadonlySet<string> = new Set(["info", "success", "warning", "danger"]);
const AUTO_HIDE_MS = 8000;
const SERVER_ERROR = "Something went wrong on our side. Try again.";
const NETWORK_ERROR = "We couldn't reach the server. Check your connection and try again.";

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

function currentRegion(): HTMLElement | null {
  const modals = [...document.querySelectorAll<HTMLDialogElement>("dialog[open]")].filter(
    (dialog) => dialog.matches(":modal"),
  );
  const inDialog = modals.at(-1)?.querySelector<HTMLElement>(":scope > [data-toast-region]");
  return inDialog ?? document.getElementById("toasts");
}

export function showToast(detail: ToastDetail): HTMLElement | null {
  const region = currentRegion();
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
    button?.closest("[data-toast-region] [data-toast]")?.remove();
  });
  document.addEventListener("toast", (event) => {
    const detail: unknown = (event as CustomEvent<unknown>).detail;
    if (isToastDetail(detail)) showToast(detail);
  });
  document.addEventListener("htmx:responseError", () => {
    showToast({ message: SERVER_ERROR, tone: "danger" });
  });
  document.addEventListener("htmx:sendError", () => {
    showToast({ message: NETWORK_ERROR, tone: "danger" });
  });
  // "close" does not bubble, so listen in the capture phase.
  document.addEventListener(
    "close",
    (event) => {
      const page = document.getElementById("toasts");
      if (!(page && event.target instanceof HTMLDialogElement)) return;
      page.append(...event.target.querySelectorAll(":scope > [data-toast-region] [data-toast]"));
    },
    true,
  );
}
