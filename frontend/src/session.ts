// Warn before a signed-in session ends (spec §10, M13; WCAG 2.2.1).
// The server enforces the limits (apps/accounts/session_policy.py); this only warns, using the
// seconds left that each page carries in <meta name="session-idle-seconds"> and
// <meta name="session-absolute-seconds">. "Stay signed in" posts the keep-alive form.

const IDLE_LEAD_SECONDS = 120;
const ABSOLUTE_LEAD_SECONDS = 300;
// The server records activity at most once a minute, so a request may count up to 60 s late.
const ACTIVITY_SLACK_SECONDS = 60;

function seconds(name: string): number | null {
  const meta = document.querySelector<HTMLMetaElement>(`meta[name="${name}"]`);
  if (!meta) return null;
  const value = Number(meta.content);
  return Number.isFinite(value) ? value : null;
}

function inWords(secondsLeft: number): string {
  if (secondsLeft >= 60) {
    const minutes = Math.round(secondsLeft / 60);
    return `${minutes} minute${minutes === 1 ? "" : "s"}`;
  }
  const whole = Math.max(1, Math.round(secondsLeft));
  return `${whole} second${whole === 1 ? "" : "s"}`;
}

export function initSessionWarning(): void {
  const idle = seconds("session-idle-seconds");
  const absolute = seconds("session-absolute-seconds");
  const dialog = document.querySelector<HTMLDialogElement>("[data-session-dialog]");
  const message = dialog?.querySelector<HTMLElement>("[data-session-message]");
  const form = dialog?.querySelector<HTMLFormElement>("[data-session-keep-alive]");
  if (idle === null || absolute === null || !dialog || !message || !form) return;

  let idleWarn = 0;
  let idleEnd = 0;

  const show = (text: string, canExtend: boolean): void => {
    message.textContent = text;
    form.hidden = !canExtend;
    if (!dialog.open) dialog.showModal();
  };

  const scheduleIdle = (secondsLeft: number): void => {
    window.clearTimeout(idleWarn);
    window.clearTimeout(idleEnd);
    const lead = Math.min(IDLE_LEAD_SECONDS, secondsLeft / 2);
    idleWarn = window.setTimeout(
      () => {
        show(`You'll be signed out in ${inWords(lead)} because you haven't done anything.`, true);
      },
      (secondsLeft - lead) * 1000,
    );
    // The next request after the limit lands on the sign-in page with the reason.
    idleEnd = window.setTimeout(() => window.location.reload(), (secondsLeft + 1) * 1000);
  };

  const absoluteLead = Math.min(ABSOLUTE_LEAD_SECONDS, absolute / 2);
  window.setTimeout(
    () => {
      window.clearTimeout(idleWarn);
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
          scheduleIdle(idle);
        } else {
          window.location.reload();
        }
      })
      .catch(() => window.location.reload());
  });

  document.body.addEventListener("htmx:afterRequest", () => {
    scheduleIdle(Math.max(1, idle - ACTIVITY_SLACK_SECONDS));
  });

  scheduleIdle(idle);
}
