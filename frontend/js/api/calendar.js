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

// p.s. File was created by Copilot and reviewed by Kozynska Anastasia
