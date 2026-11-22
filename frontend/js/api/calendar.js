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

// p.s. File was created by Copilot and reviewed by Kozynska Anastasia
