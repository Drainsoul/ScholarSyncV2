// One-click form filler for the demo's test accounts (spec §11 rev 36). A button with
// data-fill-email and data-fill-password fills the login form's "login" and "password" inputs and
// moves focus to the submit button. If a [data-fill-status] element exists, it also gets a short
// announcement ("Filled in the … account. Press Log in.") for screen readers, so each button's
// text must read alone. The buttons render hidden and are revealed here, and each
// [data-fill-fallback] list (names and emails, for pages without JS) is hidden instead.
// No-op when none exist.

export function initFill(): void {
  const buttons = document.querySelectorAll<HTMLButtonElement>("[data-fill-email]");
  if (buttons.length === 0) return;
  for (const fallback of document.querySelectorAll<HTMLElement>("[data-fill-fallback]")) {
    fallback.hidden = true;
  }
  for (const button of buttons) {
    button.hidden = false;
    button.addEventListener("click", () => {
      const form = document.getElementById("login-form");
      if (!(form instanceof HTMLFormElement)) return;
      const login = form.querySelector<HTMLInputElement>("[name=login]");
      const password = form.querySelector<HTMLInputElement>("[name=password]");
      if (login) login.value = button.dataset.fillEmail ?? "";
      if (password) password.value = button.dataset.fillPassword ?? "";
      for (const other of buttons) delete other.dataset.filled;
      button.dataset.filled = "";
      const status = document.querySelector<HTMLElement>("[data-fill-status]");
      if (status)
        status.textContent = `Filled in the ${button.textContent?.trim() ?? ""} account. Press Log in.`;
      form.querySelector<HTMLElement>("[type=submit], button:not([type])")?.focus();
    });
  }
}
