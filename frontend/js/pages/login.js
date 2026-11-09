import { login } from "../api/auth.js";
import { bindAuthForm, preparePublicAuthPage } from "../core/auth-form.js";

const form = document.querySelector("#login-form");
const statusRegion = document.querySelector("#session-status");
const email = document.querySelector("#email");
const password = document.querySelector("#password");
const globalError = document.querySelector("#form-error");
const submitButton = document.querySelector("#submit-button");
const passwordToggle = document.querySelector("#password-toggle");

const shouldShowPage = await preparePublicAuthPage(statusRegion);
if (shouldShowPage) {
  bindAuthForm(
    { form, email, password, globalError, submitButton, passwordToggle },
    login,
  );
}

/*p.s. File was created by Copilot and reviewed by Olha Bidochka*/