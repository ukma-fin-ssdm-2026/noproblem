import { getCurrentUser } from "../api/auth.js";
import { ApiError } from "../api/client.js";
import { buildLoginUrl, getPostAuthUrl } from "./return-url.js";
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
    location.replace(getPostAuthUrl());
    return true;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      return false;
    }
    throw error;
  }
}

/**
 * Requires a valid user session on a protected page.
 * @returns {Promise<object|null>}
 */
export async function requireAuthenticatedUser() {
  if (!getAccessToken()) {
    location.replace(buildLoginUrl());
    return null;
  }
  try {
    return await getCurrentUser();
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      return null;
    }
    throw error;
  }
}

/*p.s. File was created by Copilot and reviewed by Olha Bidochka*/