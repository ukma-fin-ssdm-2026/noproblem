import { register } from "../api/auth.js";
import { bindAuthForm, preparePublicAuthPage } from "../core/auth-form.js";

const form = document.querySelector("#register-form");
const statusRegion = document.querySelector("#session-status");
const email = document.querySelector("#email");
const name = document.querySelector("#name");
const password = document.querySelector("#password");
const globalError = document.querySelector("#form-error");
const submitButton = document.querySelector("#submit-button");
const passwordToggle = document.querySelector("#password-toggle");

const shouldShowPage = await preparePublicAuthPage(statusRegion);
if (shouldShowPage) {
  bindAuthForm(
    { form, email, name, password, globalError, submitButton, passwordToggle },
    register,
    { register: true },
  );
}

/*p.s. File was created by Copilot and reviewed by Olha Bidochka*/