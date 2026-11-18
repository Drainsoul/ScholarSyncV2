// Warn before a signed-in session ends (spec §10, M13; WCAG 2.2.1).
// The server enforces the limits (apps/accounts/session_policy.py); this only warns. It starts
// from the seconds each page carries in <meta name="session-idle-seconds"> and
// <meta name="session-absolute-seconds">, then follows the server's clock: every signed-in
// response says the idle seconds left in X-Session-Idle. When the timer runs out it asks the
// status endpoint, which doesn't count as activity, and reloads only if the session has ended,
// so an unattended tab can't keep itself signed in and a running upload isn't cut off.

const IDLE_LEAD_SECONDS = 120;
const ABSOLUTE_LEAD_SECONDS = 300;
const IDLE_HEADER = "X-Session-Idle";

function seconds(name: string): number | null {
  const meta = document.querySelector<HTMLMetaElement>(`meta[name="${name}"]`);
  if (!meta) return null;
  const value = Number(meta.content);
  return Number.isFinite(value) ? value : null;
}

function headerSeconds(value: string | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function inWords(secondsLeft: number): string {
  if (secondsLeft >= 60) {
    const minutes = Math.round(secondsLeft / 60);
    return `${minutes} minute${minutes === 1 ? "" : "s"}`;
  }
  const whole = Math.max(1, Math.round(secondsLeft));
  return `${whole} second${whole === 1 ? "" : "s"}`;
}

/** Tell the warning that the server just answered a request of ours (e.g. an upload step). */
export function reportSessionResponse(response: Response): void {
  const idle = headerSeconds(response.headers.get(IDLE_HEADER));
  if (idle !== null) {
    document.dispatchEvent(new CustomEvent("session:activity", { detail: { idle } }));
  }
}

export function initSessionWarning(): void {
  const idle = seconds("session-idle-seconds");
  const absolute = seconds("session-absolute-seconds");
  const dialog = document.querySelector<HTMLDialogElement>("[data-session-dialog]");
  const message = dialog?.querySelector<HTMLElement>("[data-session-message]");
  const form = dialog?.querySelector<HTMLFormElement>("[data-session-keep-alive]");
  const statusUrl = dialog?.dataset.sessionStatus;
  if (idle === null || absolute === null || !dialog || !message || !form || !statusUrl) return;

  let idleWarn = 0;
  let idleEnd = 0;
  let ending = false;

  const show = (text: string, canExtend: boolean): void => {
    message.textContent = text;
    form.hidden = !canExtend;
    if (!dialog.open) dialog.showModal();
  };

  // Ask the server, without counting as activity; reload only when the session has ended (the
  // reload then lands on the sign-in page with the reason).
  const check = (): void => {
    // "manual": following the sign-out redirect would render the sign-in page here and use up
    // its "signed out" message before the reload can show it.
    void fetch(statusUrl, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
      redirect: "manual",
    })
      .then((response) => response.json() as Promise<{ idle?: unknown }>)
      .then((data) => {
        if (typeof data.idle === "number" && data.idle > 0) {
          scheduleIdle(data.idle);
        } else {
          window.location.reload();
        }
      })
      .catch(() => window.location.reload());
  };

  const scheduleIdle = (secondsLeft: number): void => {
    if (ending) return;
    window.clearTimeout(idleWarn);
    window.clearTimeout(idleEnd);
    if (dialog.open && !form.hidden && secondsLeft > IDLE_LEAD_SECONDS) dialog.close();
    const lead = Math.min(IDLE_LEAD_SECONDS, secondsLeft / 2);
    idleWarn = window.setTimeout(
      () => {
        show(`You'll be signed out in ${inWords(lead)} because you haven't done anything.`, true);
      },
      (secondsLeft - lead) * 1000,
    );
    idleEnd = window.setTimeout(check, (secondsLeft + 1) * 1000);
  };

  const absoluteLead = Math.min(ABSOLUTE_LEAD_SECONDS, absolute / 2);
  window.setTimeout(
    () => {
      ending = true;
      window.clearTimeout(idleWarn);
      window.clearTimeout(idleEnd);
      show(
        `Your session ends in ${inWords(absoluteLead)}. Save your work, then sign in again.`,
        false,
      );
    },
    (absolute - absoluteLead) * 1000,
  );
  window.setTimeout(() => window.location.reload(), (absolute + 1) * 1000);

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    void fetch(form.action, {
      method: "POST",
      body: new FormData(form),
      credentials: "same-origin",
    })
      .then((response) => {
        if (response.status === 204) {
          dialog.close();
          scheduleIdle(headerSeconds(response.headers.get(IDLE_HEADER)) ?? idle);
        } else {
          window.location.reload();
        }
      })
      .catch(() => window.location.reload());
  });

  document.body.addEventListener("htmx:afterRequest", (event) => {
    const xhr = (event as CustomEvent<{ xhr?: XMLHttpRequest }>).detail.xhr;
    const left = headerSeconds(xhr?.getResponseHeader(IDLE_HEADER));
    if (left !== null) scheduleIdle(left);
  });

  document.addEventListener("session:activity", (event) => {
    const left = (event as CustomEvent<{ idle?: unknown }>).detail.idle;
    if (typeof left === "number") scheduleIdle(left);
  });

  scheduleIdle(idle);
}
