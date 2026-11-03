// One-click form filler. A button with data-fill-email and data-fill-password fills the login form's
// "login" and "password" inputs and moves focus to the submit button. If a [data-fill-status] element exists, it also gets a short
// announcement ("Filled in the … account. Press Log in.") for screen readers. The buttons render
// hidden and are revealed here, so without JS the page shows plain text instead. No-op when none
// exist.

export function initFill(): void {
  const buttons = document.querySelectorAll<HTMLButtonElement>("[data-fill-email]");
  for (const button of buttons) {
    button.hidden = false;
    button.addEventListener("click", () => {
      const form = document.getElementById("login-form");
      if (!(form instanceof HTMLFormElement)) return;
      const login = form.querySelector<HTMLInputElement>("[name=login]");
      const password = form.querySelector<HTMLInputElement>("[name=password]");
      if (login) login.value = button.dataset.fillEmail ?? "";
      if (password) password.value = button.dataset.fillPassword ?? "";
      const status = document.querySelector<HTMLElement>("[data-fill-status]");
      if (status)
        status.textContent = `Filled in the ${button.textContent?.trim() ?? ""} account. Press Log in.`;
      form.querySelector<HTMLElement>("[type=submit], button:not([type])")?.focus();
    });
  }
}
