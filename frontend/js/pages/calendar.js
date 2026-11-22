import { listEvents } from "../api/calendar.js";
import { requireAuthenticatedUser } from "../core/guard.js";
import { setProfile, setupLogout, showToast } from "../core/app-shell.js";

const elements = {
  announcement: document.querySelector("#calendar-announcement"),
  empty: document.querySelector("#calendar-empty"),
  error: document.querySelector("#calendar-error"),
  grid: document.querySelector("#calendar-grid"),
  loading: document.querySelector("#calendar-loading"),
  periodLabel: document.querySelector("#period-label"),
  retry: document.querySelector("#calendar-retry"),
  today: document.querySelector("#today-button"),
  viewButtons: [...document.querySelectorAll("[data-view]")],
};

const VALID_VIEWS = new Set(["day", "week", "month"]);
const state = readLocationState();
let requestVersion = 0;

elements.viewButtons.forEach((button) => {
  button.addEventListener("click", () => {
    updateState({ view: button.dataset.view });
  });
});
document.querySelectorAll("[data-period-step]").forEach((button) => {
  button.addEventListener("click", () => {
    updateState({ date: movePeriod(state.date, Number(button.dataset.periodStep)) });
  });
});
elements.today.addEventListener("click", () => updateState({ date: new Date() }));
elements.retry.addEventListener("click", () => void loadCurrentPeriod());
window.addEventListener("popstate", () => {
  Object.assign(state, readLocationState());
  void loadCurrentPeriod();
});

void initialize();

async function initialize() {
  try {
    const user = await requireAuthenticatedUser();
    if (!user) {
      return;
    }
    setProfile(user);
    setupLogout((message) => showToast(message, true));
    writeLocationState(false);
    await loadCurrentPeriod();
  } catch {
    renderCalendar([]);
    showCalendarError();
  }
}

function readLocationState() {
  const params = new URLSearchParams(location.search);
  const view = VALID_VIEWS.has(params.get("view")) ? params.get("view") : "week";
  return {
    view,
    date: normalizeDate(parseDate(params.get("date")) ?? new Date(), view),
  };
}

function parseDate(value) {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return null;
  }
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(0);
  date.setFullYear(year, month - 1, day);
  date.setHours(0, 0, 0, 0);
  if (
    date.getFullYear() !== year ||
    date.getMonth() !== month - 1 ||
    date.getDate() !== day
  ) {
    return null;
  }
  return date;
}

function updateState(changes) {
  const view = changes.view ?? state.view;
  Object.assign(state, {
    view,
    date: normalizeDate(changes.date ?? state.date, view),
  });
  writeLocationState(true);
  void loadCurrentPeriod();
}

function writeLocationState(push) {
  const url = new URL(location.href);
  url.search = "";
  url.searchParams.set("view", state.view);
  url.searchParams.set("date", dateParameter(state.date));
  if (push) {
    history.pushState(null, "", url);
  } else {
    history.replaceState(null, "", url);
  }
}

function dateParameter(date) {
  return [
    date.getFullYear().toString().padStart(4, "0"),
    (date.getMonth() + 1).toString().padStart(2, "0"),
    date.getDate().toString().padStart(2, "0"),
  ].join("-");
}

function normalizeDate(date, view) {
  const normalized = startOfDay(date);
  if (view === "week") {
    const mondayOffset = (normalized.getDay() + 6) % 7;
    normalized.setDate(normalized.getDate() - mondayOffset);
  } else if (view === "month") {
    normalized.setDate(1);
  }
  return normalized;
}

function movePeriod(date, amount) {
  const next = new Date(date);
  if (state.view === "day") {
    next.setDate(next.getDate() + amount);
  } else if (state.view === "week") {
    next.setDate(next.getDate() + amount * 7);
  } else {
    next.setDate(1);
    next.setMonth(next.getMonth() + amount);
  }
  return next;
}

async function loadCurrentPeriod() {
  const version = ++requestVersion;
  const range = getPeriodRange(state.view, state.date);
  updateControls(range);
  setLoading(true);
  try {
    const events = await listEvents(range.start, range.end);
    if (version !== requestVersion) {
      return;
    }
    const validEvents = validateEvents(events);
    renderCalendar(validEvents, range);
    elements.grid.hidden = false;
    elements.loading.hidden = true;
    elements.loading.setAttribute("aria-busy", "false");
    elements.error.hidden = true;
    elements.empty.hidden = validEvents.length !== 0;
    elements.announcement.textContent = validEvents.length
      ? `Завантажено подій: ${validEvents.length}.`
      : "У цьому періоді немає подій.";
  } catch {
    if (version !== requestVersion) {
      return;
    }
    renderCalendar([]);
    showCalendarError();
  }
}

function validateEvents(events) {
  if (!Array.isArray(events)) {
    throw new TypeError("Calendar response must be a list.");
  }
  return events.map((event) => {
    if (
      !event ||
      typeof event.title !== "string" ||
      !Number.isFinite(Date.parse(event.start_at)) ||
      !Number.isFinite(Date.parse(event.end_at)) ||
      Date.parse(event.end_at) <= Date.parse(event.start_at)
    ) {
      throw new TypeError("Calendar response contains an invalid event.");
    }
    return {
      ...event,
      start: new Date(event.start_at),
      end: new Date(event.end_at),
    };
  });
}

function setLoading(loading) {
  elements.loading.hidden = !loading;
  elements.grid.hidden = loading;
  elements.empty.hidden = true;
  elements.error.hidden = true;
  elements.loading.setAttribute("aria-busy", String(loading));
  elements.announcement.textContent = loading ? "Завантажуємо календар." : "";
}

function showCalendarError() {
  elements.loading.hidden = true;
  elements.loading.setAttribute("aria-busy", "false");
  elements.grid.hidden = false;
  elements.empty.hidden = true;
  elements.error.hidden = false;
  elements.announcement.textContent = "Не вдалося завантажити календар.";
}

function updateControls(range) {
  elements.periodLabel.textContent = formatPeriodLabel(state.view, range);
  elements.viewButtons.forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.view === state.view));
  });
}

function getPeriodRange(view, date) {
  const start = startOfDay(date);
  if (view === "day") {
    return { start, end: addDays(start, 1) };
  }
  if (view === "week") {
    const weekStart = normalizeDate(start, "week");
    return { start: weekStart, end: addDays(weekStart, 7) };
  }
  const monthStart = new Date(start.getFullYear(), start.getMonth(), 1);
  const gridStart = startOfWeek(monthStart);
  const daysInMonth = new Date(
    monthStart.getFullYear(),
    monthStart.getMonth() + 1,
    0,
  ).getDate();
  const precedingDays = Math.round((monthStart - gridStart) / 86_400_000);
  const weekCount = Math.ceil((precedingDays + daysInMonth) / 7);
  return { start: gridStart, end: addDays(gridStart, weekCount * 7) };
}

function renderCalendar(events, suppliedRange = getPeriodRange(state.view, state.date)) {
  elements.grid.replaceChildren();
  if (state.view === "month") {
    renderMonth(events, suppliedRange);
  } else {
    const days =
      state.view === "day"
        ? [startOfDay(state.date)]
        : Array.from({ length: 7 }, (_unused, index) => addDays(suppliedRange.start, index));
    renderAgenda(events, days);
  }
}

function renderAgenda(events, days) {
  const agenda = document.createElement("section");
  agenda.className = "calendar-agenda";
  agenda.setAttribute(
    "aria-label",
    state.view === "day" ? "Розклад дня" : "Розклад тижня",
  );

  const header = document.createElement("div");
  header.className = "calendar-agenda__header";
  header.style.setProperty("--calendar-day-count", String(days.length));
  const corner = document.createElement("span");
  corner.className = "calendar-agenda__corner";
  corner.textContent = "Час";
  header.append(corner);
  days.forEach((day) => header.append(createDayHeading(day, state.view)));

  const body = document.createElement("div");
  body.className = "calendar-agenda__body";
  body.style.setProperty("--calendar-day-count", String(days.length));
  body.setAttribute("role", "list");
  const timeRail = document.createElement("div");
  timeRail.className = "calendar-agenda__times";
  timeRail.setAttribute("aria-hidden", "true");
  for (let hour = 0; hour < 24; hour += 1) {
    const timeLabel = document.createElement("span");
    timeLabel.className = "calendar-agenda__time";
    timeLabel.style.setProperty("--calendar-hour-index", String(hour));
    const time = new Date(days[0]);
    time.setHours(hour, 0, 0, 0);
    timeLabel.textContent = formatTime(time);
    timeRail.append(timeLabel);
  }
  body.append(timeRail);
  days.forEach((day) => {
    const column = document.createElement("div");
    column.className = "calendar-agenda__day";
    if (sameDate(day, new Date())) {
      column.classList.add("calendar-agenda__day--today");
    }
    column.setAttribute("role", "listitem");
    column.setAttribute("aria-label", formatLongDate(day));
    renderDayEvents(column, events, day);
    body.append(column);
  });

  agenda.append(header, body);
  elements.grid.append(agenda);
  body.scrollTop = body.scrollHeight / 3;
}

function createDayHeading(day, view) {
  const heading = document.createElement("div");
  heading.className = "calendar-agenda__heading";
  if (sameDate(day, new Date())) {
    heading.classList.add("calendar-agenda__heading--today");
  }
  const weekday = document.createElement("span");
  weekday.textContent = capitalize(formatWeekday(day, view === "day" ? "long" : "short"));
  const dayNumber = document.createElement("span");
  dayNumber.className = "calendar-agenda__day-number";
  dayNumber.textContent = String(day.getDate());
  heading.append(weekday, dayNumber);
  return heading;
}

function renderDayEvents(column, events, day) {
  const dayStart = startOfDay(day);
  const dayEnd = addDays(dayStart, 1);
  const segments = events
    .map((event) => makeDaySegment(event, dayStart, dayEnd))
    .filter(Boolean)
    .sort((left, right) => left.startMinute - right.startMinute || left.endMinute - right.endMinute);
  const laneEnds = [];
  segments.forEach((segment) => {
    let lane = laneEnds.findIndex((end) => end <= segment.startMinute);
    if (lane === -1) {
      lane = laneEnds.length;
    }
    laneEnds[lane] = segment.endMinute;
    segment.lane = lane;
  });
  const laneCount = Math.max(1, laneEnds.length);
  segments.forEach((segment) => {
    const eventElement = document.createElement("article");
    eventElement.className = "calendar-event";
    eventElement.style.setProperty("--event-top", `${(segment.startMinute / 1440) * 100}%`);
    eventElement.style.setProperty(
      "--event-height",
      `${((segment.endMinute - segment.startMinute) / 1440) * 100}%`,
    );
    eventElement.style.setProperty("--event-left", `${(segment.lane / laneCount) * 100}%`);
    eventElement.style.setProperty("--event-width", `${100 / laneCount}%`);
    eventElement.setAttribute("role", "listitem");
    eventElement.setAttribute(
      "aria-label",
      `${segment.label}, ${segment.event.title}`,
    );
    const time = document.createElement("span");
    time.className = "calendar-event__time";
    time.textContent = segment.label;
    const title = document.createElement("span");
    title.className = "calendar-event__title";
    title.textContent = segment.event.title;
    eventElement.append(time, title);
    column.append(eventElement);
  });
}

function makeDaySegment(event, dayStart, dayEnd) {
  if (event.end <= dayStart || event.start >= dayEnd) {
    return null;
  }
  const startMinute =
    event.start <= dayStart ? 0 : event.start.getHours() * 60 + event.start.getMinutes();
  const endMinute =
    event.end >= dayEnd ? 1440 : event.end.getHours() * 60 + event.end.getMinutes();
  const displayEnd = endMinute === 1440 ? "24:00" : formatTime(event.end);
  return {
    event,
    startMinute,
    endMinute: Math.max(endMinute, startMinute + 1),
    label: `${formatTime(event.start <= dayStart ? dayStart : event.start)}–${displayEnd}`,
  };
}

function renderMonth(events, range) {
  const monthStart = new Date(state.date.getFullYear(), state.date.getMonth(), 1);
  const dayCount = Math.round((range.end - range.start) / 86_400_000);
  const weekCount = dayCount / 7;
  const month = document.createElement("section");
  month.className = "calendar-month";
  month.style.setProperty("--calendar-week-count", String(weekCount));
  month.setAttribute("aria-label", "Місячний календар");

  const weekdays = document.createElement("div");
  weekdays.className = "calendar-month__weekdays";
  for (let day = 0; day < 7; day += 1) {
    const weekday = document.createElement("span");
    weekday.textContent = capitalize(formatWeekday(addDays(range.start, day), "long"));
    weekdays.append(weekday);
  }
  const cells = document.createElement("div");
  cells.className = "calendar-month__days";
  cells.style.setProperty("--calendar-week-count", String(weekCount));
  for (let index = 0; index < dayCount; index += 1) {
    const day = addDays(range.start, index);
    const cell = document.createElement("div");
    cell.className = "calendar-month__day";
    if (day.getMonth() !== monthStart.getMonth()) {
      cell.classList.add("calendar-month__day--outside");
    }
    if (sameDate(day, new Date())) {
      cell.classList.add("calendar-month__day--today");
    }
    const dateLabel = document.createElement("span");
    dateLabel.className = "calendar-month__date";
    dateLabel.textContent = String(day.getDate());
    cell.append(dateLabel);
    const dayStart = startOfDay(day);
    const dayEnd = addDays(dayStart, 1);
    const dayEvents = events.filter((event) => makeDaySegment(event, dayStart, dayEnd));
    const eventList = document.createElement("div");
    eventList.className = "calendar-month__events";
    dayEvents.slice(0, 3).forEach((event) => eventList.append(createMonthEvent(event, day)));
    if (dayEvents.length > 3) {
      const more = document.createElement("span");
      more.className = "calendar-month__more";
      more.textContent = `+${dayEvents.length - 3} ще`;
      eventList.append(more);
    }
    cell.append(eventList);
    cells.append(cell);
  }
  month.append(weekdays, cells);
  elements.grid.append(month);
}

function createMonthEvent(event, day) {
  const item = document.createElement("div");
  item.className = "calendar-month__event";
  const segment = makeDaySegment(event, startOfDay(day), addDays(startOfDay(day), 1));
  const time = document.createElement("span");
  time.textContent = segment.label;
  const title = document.createElement("span");
  title.textContent = event.title;
  item.append(time, title);
  item.setAttribute("aria-label", `${segment.label}, ${event.title}`);
  return item;
}

function formatPeriodLabel(view, range) {
  if (view === "month") {
    return capitalize(
      new Intl.DateTimeFormat("uk-UA", {
        month: "long",
        year: "numeric",
      }).format(state.date),
    );
  }
  const lastDay = addDays(range.end, -1);
  if (view === "day") {
    return formatLongDate(range.start);
  }
  if (
    range.start.getMonth() === lastDay.getMonth() &&
    range.start.getFullYear() === lastDay.getFullYear()
  ) {
    const monthYear = new Intl.DateTimeFormat("uk-UA", {
      month: "long",
      year: "numeric",
    }).format(lastDay);
    return `${range.start.getDate()}–${lastDay.getDate()} ${monthYear}`;
  }
  return `${formatLongDate(range.start)} – ${formatLongDate(lastDay)}`;
}

function formatLongDate(date) {
  return new Intl.DateTimeFormat("uk-UA", {
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(date);
}

function formatWeekday(date, weekday) {
  return new Intl.DateTimeFormat("uk-UA", { weekday }).format(date);
}

function formatTime(date) {
  return new Intl.DateTimeFormat("uk-UA", {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(date);
}

function capitalize(value) {
  return value.charAt(0).toLocaleUpperCase("uk-UA") + value.slice(1);
}

function startOfWeek(date) {
  const monday = startOfDay(date);
  monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7));
  return monday;
}

function startOfDay(date) {
  const result = new Date(date);
  result.setHours(0, 0, 0, 0);
  return result;
}

function addDays(date, amount) {
  const result = new Date(date);
  result.setDate(result.getDate() + amount);
  return result;
}

function sameDate(left, right) {
  return (
    left.getFullYear() === right.getFullYear() &&
    left.getMonth() === right.getMonth() &&
    left.getDate() === right.getDate()
  );
}

// p.s. File was created by Copilot and reviewed by Kozynska Anastasia
