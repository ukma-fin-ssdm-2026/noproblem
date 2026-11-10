import { ApiError, request } from "./client.js";
import { clearSession, saveAccessToken } from "../core/session.js";

/**
 * Signs in and stores the returned token in the current tab's session.
 * @param {{email: string, password: string}} credentials
 * @returns {Promise<object>}
 */
export async function login(credentials) {
  const result = await request("/auth/login", {
    method: "POST",
    body: credentials,
  });
  requireAuthResponse(result);
  saveAccessToken(result.access_token);
  return result;
}

/**
 * Creates an account and stores the returned token in the current tab.
 * @param {{email: string, name: string, password: string}} details
 * @returns {Promise<object>}
 */
export async function register(details) {
  const result = await request("/auth/register", {
    method: "POST",
    body: details,
  });
  requireAuthResponse(result);
  saveAccessToken(result.access_token);
  return result;
}

/**
 * Returns the current user's public profile.
 * @param {{redirectOnUnauthorized?: boolean}} [options]
 * @returns {Promise<object>}
 */
export function getCurrentUser(options = {}) {
  return request("/auth/me", {
    authenticated: true,
    redirectOnUnauthorized: options.redirectOnUnauthorized,
  });
}

/**
 * Ends the current server session and clears its local token.
 * @returns {Promise<void>}
 */
export async function logout() {
  await request("/auth/logout", { method: "POST", authenticated: true });
  clearSession();
}

/**
 * Unlocks an account using the one-time token from the email link.
 * @param {string} token
 * @returns {Promise<void>}
 */
export async function unlockAccount(token) {
  await request("/auth/unlock", {
    method: "POST",
    body: { token },
  });
}

function requireAuthResponse(result) {
  if (
    !result ||
    typeof result !== "object" ||
    typeof result.access_token !== "string" ||
    result.token_type !== "bearer"
  ) {
    throw new ApiError({
      code: "INVALID_RESPONSE",
      message: "Не вдалося обробити відповідь сервера.",
    });
  }
}

/*p.s. File was created by Copilot and reviewed by Olha Bidochka*/