import { API_BASE_URL, LOGIN_URL } from "../core/config.js";
import { clearSession, getAccessToken } from "../core/session.js";

const DEFAULT_TIMEOUT_MS = 10_000;

const STATUS_MESSAGES = new Map([
  [400, "Посилання недійсне або застаріле."],
  [401, "Невірний email або пароль"],
  [403, "Недостатньо прав"],
  [404, "Запитаний ресурс не знайдено."],
  [409, "Ця email-адреса вже використовується."],
  [422, "Перевірте введені дані."],
  [423, "Вхід тимчасово заблоковано."],
  [503, "Сервіс тимчасово недоступний, спробуйте пізніше"],
]);

const VALIDATION_CODES = new Map([
  ["Пароль має містити щонайменше 8 символів.", "PASSWORD_TOO_SHORT"],
  ["Пароль має містити не більше ніж 128 символів.", "PASSWORD_TOO_LONG"],
  ["Некоректний формат email.", "INVALID_EMAIL"],
  ["Ім'я має містити від 1 до 100 символів.", "INVALID_NAME"],
]);

/**
 * A safe, normalized API error; raw server responses are never exposed.
 */
export class ApiError extends Error {
  /**
   * @param {{status?: number, code?: string, message: string, isTimeout?: boolean, isNetwork?: boolean, retryAfterSeconds?: number|null}} options
   */
  constructor({
    status = 0,
    code = "UNKNOWN",
    message,
    isTimeout = false,
    isNetwork = false,
    retryAfterSeconds = null,
  }) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.message = message;
    this.isTimeout = isTimeout;
    this.isNetwork = isNetwork;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

/**
 * Sends one request to the configured API and normalizes its failures.
 * @param {string} path API path relative to the configured version prefix.
 * @param {{method?: string, body?: unknown, authenticated?: boolean, timeoutMs?: number, signal?: AbortSignal, redirectOnUnauthorized?: boolean, headers?: HeadersInit}} [options]
 * @returns {Promise<unknown>}
 */
export async function request(path, options = {}) {
  const {
    method = "GET",
    body,
    authenticated = false,
    timeoutMs = DEFAULT_TIMEOUT_MS,
    signal,
    redirectOnUnauthorized = true,
    headers: extraHeaders,
  } = options;
  if (!path.startsWith("/")) {
    throw new TypeError("API paths must start with '/'.");
  }

  const controller = new AbortController();
  let timedOut = false;
  const timeoutId = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const abortFromCaller = () => controller.abort();
  signal?.addEventListener("abort", abortFromCaller, { once: true });

  const headers = new Headers({ Accept: "application/json" });
  new Headers(extraHeaders).forEach((value, name) => headers.set(name, value));
  if (body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  if (authenticated) {
    const token = getAccessToken();
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
  }

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    const responseBody = await readResponseBody(response);
    if (!response.ok) {
      const error = createApiError(response.status, response.headers, responseBody);
      if (response.status === 401 && authenticated) {
        clearSession();
        if (redirectOnUnauthorized && location.pathname !== `/${LOGIN_URL}`) {
          location.assign(LOGIN_URL);
        }
        error.message = "Сесія завершилась, увійдіть знову";
      }
      throw error;
    }
    return response.status === 204 ? null : responseBody;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    if (signal?.aborted) {
      throw error;
    }
    if (timedOut) {
      throw new ApiError({
        code: "TIMEOUT",
        message: "Сервер не відповів вчасно",
        isTimeout: true,
      });
    }
    throw new ApiError({
      code: "NETWORK_ERROR",
      message: "Немає з'єднання",
      isNetwork: true,
    });
  } finally {
    clearTimeout(timeoutId);
    signal?.removeEventListener("abort", abortFromCaller);
  }
}

async function readResponseBody(response) {
  if (response.status === 204) {
    return null;
  }
  try {
    return await response.json();
  } catch (error) {
    if (error instanceof SyntaxError) {
      return null;
    }
    throw error;
  }
}

function createApiError(status, headers, body) {
  const serverDetail = typeof body?.detail === "string" ? body.detail : "";
  const validationCode = VALIDATION_CODES.get(serverDetail);
  const knownDetail = new Map([
    [
      "Idempotency-Key вже використаний з іншою назвою документа.",
      "Цей запит на створення вже використав інший ключ.",
    ],
  ]).get(serverDetail);
  return new ApiError({
    status,
    code: validationCode ?? (knownDetail ? "KNOWN_DETAIL" : `HTTP_${status}`),
    message: validationCode
      ? validationMessage(validationCode)
      : knownDetail
        ? knownDetail
      : STATUS_MESSAGES.get(status) ?? "Не вдалося виконати запит.",
    retryAfterSeconds: parseRetryAfter(headers.get("Retry-After")),
  });
}

function validationMessage(code) {
  const messages = new Map([
    ["PASSWORD_TOO_SHORT", "Пароль має містити щонайменше 8 символів."],
    ["PASSWORD_TOO_LONG", "Пароль має містити не більше ніж 128 символів."],
    ["INVALID_EMAIL", "Некоректний формат email."],
    ["INVALID_NAME", "Ім'я має містити від 1 до 100 символів."],
  ]);
  return messages.get(code) ?? "Перевірте введені дані.";
}

function parseRetryAfter(value) {
  if (!value || !/^\d+$/.test(value)) {
    return null;
  }
  return Number(value);
}

/*p.s. File was created by Copilot and reviewed by Olha Bidochka*/