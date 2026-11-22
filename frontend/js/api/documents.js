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
 * Grants a registered user access or changes their role.
 * @param {number} documentId
 * @param {string} email
 * @param {"editor"|"guest"} role
 * @returns {Promise<object>}
 */
export function shareDocument(documentId, email, role) {
  return request(`/documents/${documentId}/access`, {
    method: "PUT",
    body: { email, role },
    authenticated: true,
  });
}

/**
 * Revokes a member's access.
 * @param {number} documentId
 * @param {string} userId
 * @returns {Promise<void>}
 */
export async function revokeAccess(documentId, userId) {
  await request(`/documents/${documentId}/access/${encodeURIComponent(userId)}`, {
    method: "DELETE",
    authenticated: true,
  });
}

/**
 * @typedef {object} AccessRequest
 * @property {string} id
 * @property {number} document_id
 * @property {string} requester_id
 * @property {"access"|"role"} request_type
 * @property {"editor"|null} requested_role
 * @property {"pending"|"approved"|"rejected"} status
 * @property {string} created_at
 * @property {string|null} resolved_at
 */

/**
 * Lists pending access requests for a document; only the owner can view them.
 * @param {number} documentId
 * @returns {Promise<{requests: AccessRequest[]}>}
 */
export function listAccessRequests(documentId) {
  return request(`/documents/${documentId}/access/requests`, {
    authenticated: true,
  });
}

/**
 * Approves an access request.
 * @param {number} documentId
 * @param {string} requestId
 * @returns {Promise<AccessRequest>}
 */
export function approveAccessRequest(documentId, requestId) {
  return request(
    `/documents/${documentId}/access/requests/${encodeURIComponent(requestId)}/approve`,
    {
      method: "POST",
      authenticated: true,
    },
  );
}

/**
 * Rejects an access request.
 * @param {number} documentId
 * @param {string} requestId
 * @returns {Promise<AccessRequest>}
 */
export function rejectAccessRequest(documentId, requestId) {
  return request(
    `/documents/${documentId}/access/requests/${encodeURIComponent(requestId)}/reject`,
    {
      method: "POST",
      authenticated: true,
    },
  );
}

/**
 * Requests access to a document.
 * @param {number} documentId
 * @returns {Promise<AccessRequest>}
 */
export function requestAccess(documentId) {
  return request(`/documents/${documentId}/access/requests`, {
    method: "POST",
    authenticated: true,
  });
}

/**
 * Lists the current user's requests for a document.
 * @param {number} documentId
 * @returns {Promise<{requests: AccessRequest[]}>}
 */
export function listMyAccessRequests(documentId) {
  return request(`/documents/${documentId}/access/requests/mine`, {
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