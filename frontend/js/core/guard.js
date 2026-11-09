import { getCurrentUser } from "../api/auth.js";
import { ApiError } from "../api/client.js";
import { WORKSPACE_URL } from "./config.js";
import { getAccessToken } from "./session.js";

/**
 * Redirects an authenticated visitor away from a public auth page.
 * @returns {Promise<boolean>} True when a redirect was started.
 */
export async function redirectAuthenticatedUser() {
  if (!getAccessToken()) {
    return false;
  }
  try {
    await getCurrentUser({ redirectOnUnauthorized: false });
    location.replace(WORKSPACE_URL);
    return true;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      return false;
    }
    throw error;
  }
}

/*p.s. File was created by Copilot and reviewed by Olha Bidochka*/