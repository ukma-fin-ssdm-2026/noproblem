import { request } from "./client.js";

const PAGE_SIZE = 100;

/**
 * Loads one page of active documents.
 * @param {{offset?: number, signal?: AbortSignal}} [options]
 * @returns {Promise<{documents: object[], pagination: object}>}
 */
export async function listDocuments({ offset = 0, signal } = {}) {
  return request(`/documents?limit=${PAGE_SIZE}&offset=${offset}`, {
    authenticated: true,
    signal,
  });
}

/**
 * Loads one page of the current user's trash.
 * @param {{offset?: number, signal?: AbortSignal}} [options]
 * @returns {Promise<{documents: object[], pagination: object}>}
 */
export async function listTrash({ offset = 0, signal } = {}) {
  return request(`/documents/trash?limit=${PAGE_SIZE}&offset=${offset}`, {
    authenticated: true,
    signal,
  });
}

/**
 * Creates a document using an idempotency key unique to the user action.
 * @param {string} title
 * @param {string} idempotencyKey
 * @returns {Promise<object>}
 */
export function createDocument(title, idempotencyKey) {
  if (!idempotencyKey) {
    throw new TypeError("An idempotency key is required.");
  }
  return request("/documents", {
    method: "POST",
    body: title ? { title } : undefined,
    authenticated: true,
    headers: { "Idempotency-Key": idempotencyKey },
  });
}

/**
 * Renames an active document.
 * @param {number} documentId
 * @param {string} title
 * @returns {Promise<object>}
 */
export function renameDocument(documentId, title) {
  return request(`/documents/${documentId}`, {
    method: "PUT",
    body: { title },
    authenticated: true,
  });
}

/**
 * Loads one active document by its identifier.
 * @param {number} documentId
 * @returns {Promise<object>}
 */
export function getDocument(documentId) {
  return request(`/documents/${documentId}`, { authenticated: true });
}

/**
 * Loads all paragraphs in display order.
 * @param {number} documentId
 * @returns {Promise<{paragraphs: object[]}>}
 */
export function listParagraphs(documentId) {
  return request(`/documents/${documentId}/paragraphs`, {
    authenticated: true,
  });
}

/**
 * Adds a paragraph at the end or at the provided zero-based position.
 * @param {number} documentId
 * @param {string} content
 * @param {number} [position]
 * @returns {Promise<object>}
 */
export function createParagraph(documentId, content, position) {
  const body = { content };
  if (position !== undefined) {
    body.position = position;
  }
  return request(`/documents/${documentId}/paragraphs`, {
    method: "POST",
    body,
    authenticated: true,
  });
}

/**
 * Updates a paragraph's content and/or zero-based position.
 * @param {number} documentId
 * @param {number} paragraphId
 * @param {{content?: string, position?: number}} changes
 * @returns {Promise<object>}
 */
export function updateParagraph(documentId, paragraphId, changes) {
  return request(`/documents/${documentId}/paragraphs/${paragraphId}`, {
    method: "PATCH",
    body: changes,
    authenticated: true,
  });
}

/**
 * Deletes a paragraph.
 * @param {number} documentId
 * @param {number} paragraphId
 * @returns {Promise<void>}
 */
export async function deleteParagraph(documentId, paragraphId) {
  await request(`/documents/${documentId}/paragraphs/${paragraphId}`, {
    method: "DELETE",
    authenticated: true,
  });
}

/**
 * Returns document members and roles; only the backend owner can see them.
 * @param {number} documentId
 * @returns {Promise<{members: Array<{user_id: string, email: string, name: string, role: string}>}>}
 */
export function getDocumentMembers(documentId) {
  return request(`/documents/${documentId}/access`, {
    authenticated: true,
  });
}

/**
 * Moves an active document to the trash.
 * @param {number} documentId
 * @returns {Promise<void>}
 */
export async function moveDocumentToTrash(documentId) {
  await request(`/documents/${documentId}`, {
    method: "DELETE",
    authenticated: true,
  });
}

/**
 * Restores a document from the trash.
 * @param {number} documentId
 * @returns {Promise<object>}
 */
export function restoreDocument(documentId) {
  return request(`/documents/${documentId}/restore`, {
    method: "POST",
    authenticated: true,
  });
}

/**
 * Searches accessible active documents.
 * @param {string} query
 * @param {{signal?: AbortSignal}} [options]
 * @returns {Promise<Array<{doc_id: number, title: string, snippet: string}>>}
 */
export function searchDocuments(query, { signal } = {}) {
  const params = new URLSearchParams({ q: query });
  return request(`/search?${params.toString()}`, {
    authenticated: true,
    signal,
  });
}


/*p.s. File was created by Copilot and reviewed by Olha Bidochka*/