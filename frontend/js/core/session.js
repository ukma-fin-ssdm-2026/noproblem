const ACCESS_TOKEN_KEY = "notely.accessToken";

/**
 * Returns the current tab's access token, if one is stored.
 * @returns {string|null}
 */
export function getAccessToken() {
  return sessionStorage.getItem(ACCESS_TOKEN_KEY);
}

/**
 * Stores an access token for this browser tab.
 * @param {string} token
 */
export function saveAccessToken(token) {
  if (!token) {
    throw new TypeError("An access token is required.");
  }
  sessionStorage.setItem(ACCESS_TOKEN_KEY, token);
}

/**
 * Removes the current tab's access token.
 */
export function clearSession() {
  sessionStorage.removeItem(ACCESS_TOKEN_KEY);
}

/*p.s. File was created by Copilot and reviewed by Olha Bidochka*/