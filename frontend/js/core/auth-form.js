import { ApiError } from "../api/client.js";
import { redirectAuthenticatedUser } from "./guard.js";

const EMAIL_MAX_LENGTH = 254;
const NAME_MAX_LENGTH = 100;
const PASSWORD_MAX_LENGTH = 128;
const PASSWORD_MIN_LENGTH = 8;
const DEFAULT_LOCK_SECONDS = 15 * 60;

/**
 * Checks an email using the same basic syntax accepted by the API domain.
 * @param {string} rawEmail
 * @returns {string|null}
 */
export function validateEmail(rawEmail) {
  const email = rawEmail.trim().toLowerCase();
  const [local, ...domainParts] = email.split("@");
  const domain = domainParts.join("@");
  if (
    email.length < 3 ||
    email.length > EMAIL_MAX_LENGTH ||
    !local ||
    !domain ||
    domain.includes("@") ||
    !domain.includes(".") ||
    domain.startsWith(".") ||
    domain.endsWith(".") ||
    domain.includes("..") ||
    /\s/.test(email)
  ) {
    return null;
  }
  return email;
}

/**
 * Attaches accessible field validation and error rendering to an auth form.
 * @param {{form: HTMLFormElement, email: HTMLInputElement, name?: HTMLInputElement, password: HTMLInputElement, globalError: HTMLElement, passwordToggle?: HTMLButtonElement, submitButton: HTMLButtonElement}} controls
 * @param {(data: {email: string, name?: string, password: string}) => Promise<unknown>} submitAction
 * @param {{register?: boolean}} [options]
 */
export function bindAuthForm(controls, submitAction, options = {}) {
  const { form, email, name, password, globalError, submitButton, passwordToggle } = controls;
  const fieldErrors = new Map();
  for (const input of [email, name, password].filter(Boolean)) {
    const error = input
      .closest(".field")
      ?.querySelector(".field__error");
    if (error) {
      fieldErrors.set(input, error);
      input.addEventListener("input", () => clearFieldError(input));
    }
  }

  passwordToggle?.addEventListener("click", () => {
    const reveal = password.type === "password";
    password.type = reveal ? "text" : "password";
    passwordToggle.textContent = reveal ? "Сховати пароль" : "Показати пароль";
    passwordToggle.setAttribute(
      "aria-label",
      reveal ? "Сховати пароль" : "Показати пароль",
    );
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (submitButton.disabled || form.getAttribute("aria-busy") === "true") {
      return;
    }
    clearGlobalError(globalError);
    clearAllFieldErrors(fieldErrors);
    const data = collectAndValidate({
      email,
      name,
      password,
      fieldErrors,
      isRegister: Boolean(options.register),
    });
    if (!data) {
      return;
    }

    setBusy(form, submitButton, true);
    try {
      await submitAction(data);
      location.assign("workspace.html");
    } catch (error) {
      renderAuthError(error, {
        email,
        name,
        password,
        fieldErrors,
        globalError,
        submitButton,
        form,
        isRegister: Boolean(options.register),
      });
    } finally {
      if (!submitButton.disabled || !submitButton.dataset.locked) {
        setBusy(form, submitButton, false);
      }
    }
  });
}

/**
 * Checks whether a stored session is valid before showing the auth form.
 * @param {HTMLElement} statusRegion
 * @returns {Promise<boolean>}
 */
export async function preparePublicAuthPage(statusRegion) {
  try {
    return !(await redirectAuthenticatedUser());
  } catch (error) {
    if (!(error instanceof ApiError)) {
      throw error;
    }
    statusRegion.textContent =
      "Не вдалося перевірити поточну сесію. Можете продовжити вхід або реєстрацію.";
    return true;
  }
}

function collectAndValidate({
  email,
  name,
  password,
  fieldErrors,
  isRegister,
}) {
  const normalizedEmail = validateEmail(email.value);
  if (!normalizedEmail) {
    setFieldError(
      email,
      fieldErrors,
      "Введіть коректну email-адресу.",
    );
  }

  const normalizedName = name?.value.trim();
  if (isRegister && (!normalizedName || normalizedName.length > NAME_MAX_LENGTH)) {
    setFieldError(
      name,
      fieldErrors,
      "Ім’я має містити від 1 до 100 символів.",
    );
  }

  const passwordValue = password.value;
  if (isRegister && passwordValue.length < PASSWORD_MIN_LENGTH) {
    setFieldError(
      password,
      fieldErrors,
      "Пароль має містити щонайменше 8 символів.",
    );
  } else if (passwordValue.length > PASSWORD_MAX_LENGTH) {
    setFieldError(
      password,
      fieldErrors,
      "Пароль має містити не більше ніж 128 символів.",
    );
  } else if (!passwordValue) {
    setFieldError(password, fieldErrors, "Введіть пароль.");
  }

  if (!normalizedEmail || (isRegister && !normalizedName) ||
      passwordValue.length < (isRegister ? PASSWORD_MIN_LENGTH : 1) ||
      passwordValue.length > PASSWORD_MAX_LENGTH ||
      (isRegister && normalizedName.length > NAME_MAX_LENGTH)) {
    const firstInvalid = [...fieldErrors.keys()].find(
      (input) => input.getAttribute("aria-invalid") === "true",
    );
    firstInvalid?.focus();
    return null;
  }

  return {
    email: normalizedEmail,
    ...(isRegister ? { name: normalizedName } : {}),
    password: passwordValue,
  };
}

function renderAuthError(error, controls) {
  const {
    email,
    name,
    password,
    fieldErrors,
    globalError,
    submitButton,
    form,
    isRegister,
  } = controls;
  if (!(error instanceof ApiError)) {
    showGlobalError(globalError, "Не вдалося виконати запит. Спробуйте ще раз.");
    return;
  }
  if (isRegister && error.status === 409) {
    setFieldError(email, fieldErrors, "Цей email уже зареєстрований.");
    email.focus();
    return;
  }
  if (isRegister && error.code === "PASSWORD_TOO_SHORT") {
    setFieldError(password, fieldErrors, error.message);
    password.focus();
    return;
  }
  if (isRegister && error.code === "PASSWORD_TOO_LONG") {
    setFieldError(password, fieldErrors, error.message);
    password.focus();
    return;
  }
  if (isRegister && error.code === "INVALID_EMAIL") {
    setFieldError(email, fieldErrors, error.message);
    email.focus();
    return;
  }
  if (isRegister && error.code === "INVALID_NAME") {
    setFieldError(name, fieldErrors, error.message);
    name?.focus();
    return;
  }
  if (error.status === 423) {
    const waitSeconds = Math.min(
      error.retryAfterSeconds ?? DEFAULT_LOCK_SECONDS,
      24 * 60 * 60,
    );
    startLockout(form, submitButton, globalError, waitSeconds);
    return;
  }
  showGlobalError(globalError, error.message);
}

function setFieldError(input, fieldErrors, message) {
  if (!input) {
    return;
  }
  const error = fieldErrors.get(input);
  if (!error) {
    return;
  }
  input.setAttribute("aria-invalid", "true");
  error.textContent = message;
  error.hidden = false;
}

function clearFieldError(input) {
  const error = input.closest(".field")?.querySelector(".field__error");
  input.removeAttribute("aria-invalid");
  if (error) {
    error.textContent = "";
    error.hidden = true;
  }
}

function clearAllFieldErrors(fieldErrors) {
  for (const input of fieldErrors.keys()) {
    clearFieldError(input);
  }
}

function showGlobalError(region, message) {
  region.classList.remove("alert--warning");
  region.classList.add("alert--error");
  region.setAttribute("aria-live", "assertive");
  region.textContent = message;
  region.hidden = false;
}

function clearGlobalError(region) {
  region.textContent = "";
  region.hidden = true;
  region.classList.remove("alert--warning");
  region.classList.add("alert--error");
  region.setAttribute("aria-live", "assertive");
}

function setBusy(form, button, busy) {
  form.setAttribute("aria-busy", String(busy));
  button.disabled = busy;
  button.classList.toggle("button--loading", busy);
  if (busy) {
    button.dataset.idleLabel ??= button.textContent.trim();
    button.textContent = button.dataset.loadingLabel ?? "Обробляємо…";
  } else if (button.dataset.idleLabel) {
    button.textContent = button.dataset.idleLabel;
  }
}

function startLockout(form, button, region, seconds) {
  button.dataset.locked = "true";
  button.disabled = true;
  button.classList.remove("button--loading");
  if (button.dataset.idleLabel) {
    button.textContent = button.dataset.idleLabel;
  }
  form.setAttribute("aria-busy", "false");
  region.classList.remove("alert--error");
  region.classList.add("alert--warning");
  let timer;
  const updateMessage = () => {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    const remaining = `${minutes}:${String(remainingSeconds).padStart(2, "0")}`;
    region.textContent =
      `Вхід тимчасово заблоковано. Спробуйте знову через ${remaining}.`;
    region.hidden = false;
    if (seconds <= 0) {
      if (timer) {
        clearInterval(timer);
      }
      delete button.dataset.locked;
      button.disabled = false;
      form.removeAttribute("aria-busy");
      region.textContent =
        "Час блокування минув. Можете спробувати увійти знову.";
      return;
    }
    seconds -= 1;
  };
  const shouldStartTimer = seconds > 0;
  updateMessage();
  region.setAttribute("aria-live", "off");
  if (shouldStartTimer) {
    timer = setInterval(updateMessage, 1000);
  }
}

/*p.s. File was created by Copilot and reviewed by Olha Bidochka*/