import { request } from "./client.js";

/**
 * Lists events intersecting a timezone-aware interval.
 * @param {Date} startAt Inclusive local interval start.
 * @param {Date} endAt Exclusive local interval end.
 * @returns {Promise<Array<object>>}
 */
export function listEvents(startAt, endAt) {
  if (!(startAt instanceof Date) || !(endAt instanceof Date)) {
    throw new TypeError("Calendar range bounds must be Date objects.");
  }
  if (!Number.isFinite(startAt.getTime()) || !Number.isFinite(endAt.getTime())) {
    throw new RangeError("Calendar range bounds must be valid dates.");
  }
  if (endAt <= startAt) {
    throw new RangeError("Calendar range end must follow its start.");
  }
  const query = new URLSearchParams({
    start_at: startAt.toISOString(),
    end_at: endAt.toISOString(),
  });
  return request(`/calendar/events?${query}`, { authenticated: true });
}

/**
 * Loads one calendar event.
 * @param {number} eventId
 * @returns {Promise<object>}
 */
export function getEvent(eventId) {
  if (!Number.isInteger(eventId) || eventId < 1) {
    throw new TypeError("Calendar event id is invalid.");
  }
  return request(`/calendar/events/${eventId}`, { authenticated: true });
}

/**
 * Creates a calendar event.
 * @param {{title: string, startAt: Date, endAt: Date}} event
 * @returns {Promise<object>}
 */
export function createEvent({ title, startAt, endAt }) {
  if (typeof title !== "string" || !(startAt instanceof Date) || !(endAt instanceof Date)) {
    throw new TypeError("Calendar event details are invalid.");
  }
  if (!Number.isFinite(startAt.getTime()) || !Number.isFinite(endAt.getTime())) {
    throw new RangeError("Calendar event dates must be valid.");
  }
  return request("/calendar/events", {
    method: "POST",
    body: {
      title,
      start_at: startAt.toISOString(),
      end_at: endAt.toISOString(),
    },
    authenticated: true,
  });
}

/**
 * Updates only the supplied calendar event fields.
 * @param {number} eventId
 * @param {{title?: string, startAt?: Date, endAt?: Date}} changes
 * @returns {Promise<object>}
 */
export function updateEvent(eventId, changes) {
  if (!Number.isInteger(eventId) || eventId < 1 || !changes || typeof changes !== "object") {
    throw new TypeError("Calendar event details are invalid.");
  }
  const body = {};
  if (changes.title !== undefined) {
    body.title = changes.title;
  }
  if (changes.startAt !== undefined) {
    if (!(changes.startAt instanceof Date) || !Number.isFinite(changes.startAt.getTime())) {
      throw new TypeError("Calendar event start date is invalid.");
    }
    body.start_at = changes.startAt.toISOString();
  }
  if (changes.endAt !== undefined) {
    if (!(changes.endAt instanceof Date) || !Number.isFinite(changes.endAt.getTime())) {
      throw new TypeError("Calendar event end date is invalid.");
    }
    body.end_at = changes.endAt.toISOString();
  }
  if (Object.keys(body).length === 0) {
    throw new TypeError("Calendar event changes are empty.");
  }
  return request(`/calendar/events/${eventId}`, {
    method: "PATCH",
    body,
    authenticated: true,
  });
}

/**
 * Lists users participating in an event; the creator is not included.
 * @param {number} eventId
 * @returns {Promise<Array<{user_id: string, name: string, email: string}>>}
 */
export function listParticipants(eventId) {
  if (!Number.isInteger(eventId) || eventId < 1) {
    throw new TypeError("Calendar event id is invalid.");
  }
  return request(`/calendar/events/${eventId}/participants`, {
    authenticated: true,
  });
}

/**
 * Adds a registered user to an event by email.
 * @param {number} eventId
 * @param {string} email
 * @returns {Promise<null>}
 */
export function addParticipant(eventId, email) {
  if (!Number.isInteger(eventId) || eventId < 1 || typeof email !== "string") {
    throw new TypeError("Calendar participant details are invalid.");
  }
  return request(`/calendar/events/${eventId}/participants`, {
    method: "PUT",
    body: { email },
    authenticated: true,
  });
}

/**
 * Removes a participant from an event.
 * @param {number} eventId
 * @param {string} userId
 * @returns {Promise<null>}
 */
export function removeParticipant(eventId, userId) {
  if (!Number.isInteger(eventId) || eventId < 1 || typeof userId !== "string" || !userId) {
    throw new TypeError("Calendar participant details are invalid.");
  }
  return request(
    `/calendar/events/${eventId}/participants/${encodeURIComponent(userId)}`,
    {
      method: "DELETE",
      authenticated: true,
    },
  );
}

/**
 * Links a document to an event.
 * @param {number} eventId
 * @param {number} documentId
 * @returns {Promise<object>}
 */
export function linkDocument(eventId, documentId) {
  if (
    !Number.isInteger(eventId) ||
    eventId < 1 ||
    !Number.isInteger(documentId) ||
    documentId < 1
  ) {
    throw new TypeError("Calendar document details are invalid.");
  }
  return request(`/calendar/events/${eventId}/document`, {
    method: "PUT",
    body: { document_id: documentId },
    authenticated: true,
  });
}

/**
 * Unlinks the document from an event.
 * @param {number} eventId
 * @returns {Promise<object>}
 */
export function unlinkDocument(eventId) {
  if (!Number.isInteger(eventId) || eventId < 1) {
    throw new TypeError("Calendar event id is invalid.");
  }
  return request(`/calendar/events/${eventId}/document`, {
    method: "DELETE",
    authenticated: true,
  });
}

// p.s. File was created by Copilot and reviewed by Kozynska Anastasia
