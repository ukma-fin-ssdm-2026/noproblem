import { logout } from "../api/auth.js";
import { ApiError } from "../api/client.js";

/**
 * Renders the authenticated user's real name and email in the shared shell.
 * @param {{name: string, email: string}} user
 */
export function setProfile(user) {
  document.querySelector("#profile-name").textContent = user.name;
  document.querySelector("#profile-email").textContent = user.email;
  document.querySelector("#profile-avatar").textContent = initials(user.name);
}

/**
 * Wires the sign-out control.
 * @param {(message: string) => void} showError
 */
export function setupLogout(showError) {
  document.querySelector("#logout").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    try {
      await logout();
      location.replace("login.html");
    } catch (error) {
      button.disabled = false;
      showError(
        error instanceof ApiError
          ? error.message
          : "Не вдалося вийти. Спробуйте ще раз.",
      );
    }
  });
}

/**
 * Displays one temporary toast message without inserting HTML.
 * @param {string} message
 * @param {boolean} [isError]
 */
export function showToast(message, isError = false) {
  const region = document.querySelector("#toast-region");
  const toast = document.createElement("p");
  toast.className = isError
    ? "toast-message toast-message--error"
    : "toast-message";
  toast.textContent = message;
  region.replaceChildren(toast);
  window.setTimeout(() => {
    if (toast.parentElement === region) {
      region.replaceChildren();
    }
  }, 4500);
}

function initials(name) {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0] ?? "")
    .join("")
    .toLocaleUpperCase("uk-UA");
}


/*p.s. File was created by Copilot and reviewed by Olha Bidochka*/