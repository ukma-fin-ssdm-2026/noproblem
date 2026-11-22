import { LOGIN_URL, WORKSPACE_URL } from "./config.js";

const NEXT_PARAM = "next";
const AUTH_PAGES = new Set(["login.html", "register.html"]);

/**
 * Returns the login page URL that remembers the current page,
 * so the user comes back here after signing in or registering.
 * @returns {string}
 */
export function buildLoginUrl() {
  const current = currentPagePath();
  if (!current) {
    return LOGIN_URL;
  }
  const params = new URLSearchParams({ [NEXT_PARAM]: current });
  return `${LOGIN_URL}?${params}`;
}

/**
 * Where to send the user after a successful sign-in or registration:
 * the remembered internal page, otherwise the workspace.
 * @returns {string}
 */
export function getPostAuthUrl() {
  return readSafeNext() ?? WORKSPACE_URL;
}

/**
 * Keeps the remembered page when switching between login and register.
 * @param {ParentNode} [root]
 */
export function carryNextToAuthLinks(root = document) {
  const next = readSafeNext();
  if (!next) {
    return;
  }
  const params = new URLSearchParams({ [NEXT_PARAM]: next });
  for (const link of root.querySelectorAll('a[href="login.html"], a[href="register.html"]')) {
    link.setAttribute("href", `${link.getAttribute("href")}?${params}`);
  }
}

/**
 * Current page as a relative path with query string, or null on auth pages.
 * @returns {string|null}
 */
function currentPagePath() {
  const page = location.pathname.split("/").pop() || "";
  if (!page || AUTH_PAGES.has(page)) {
    return null;
  }
  return `${page}${location.search}`;
}

/**
 * Pages allowed as a return target. Each builder returns a URL assembled only
 * from constant strings and a validated integer, so a value from the query
 * string never reaches location.assign/replace directly (no open redirect).
 * @type {Readonly<Record<string, (params: URLSearchParams) => string|null>>}
 */
const RETURN_TARGETS = Object.freeze({
  "workspace.html": () => "workspace.html",
  "trash.html": () => "trash.html",
  "document.html": (params) => {
    const rawId = params.get("id") ?? "";
    if (!/^[1-9]\d{0,15}$/.test(rawId)) {
      return null;
    }
    const id = Number(rawId);
    return Number.isSafeInteger(id) ? `document.html?id=${id}` : null;
  },
});

/**
 * Reads the `next` parameter and maps it to an allowed page of this site.
 * Anything else (other origins, absolute paths, unknown pages) is ignored.
 * @returns {string|null}
 */
function readSafeNext() {
  const raw = new URLSearchParams(location.search).get(NEXT_PARAM);
  if (!raw) {
    return null;
  }
  let url;
  try {
    url = new URL(raw, location.href);
  } catch {
    return null;
  }
  if (url.origin !== location.origin) {
    return null;
  }
  const page = url.pathname.split("/").pop() || "";
  if (!Object.hasOwn(RETURN_TARGETS, page)) {
    return null;
  }
  return RETURN_TARGETS[page](url.searchParams);
}

/*p.s. File was created by Claude and reviewed by Kozynska Anastasia*/
