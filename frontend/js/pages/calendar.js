import {
  addParticipant,
  createEvent,
  linkDocument,
  listEvents,
} from "../api/calendar.js";
import { listDocuments } from "../api/documents.js";
import { ApiError } from "../api/client.js";
import { requireAuthenticatedUser } from "../core/guard.js";
import { setProfile, setupLogout, showToast } from "../core/app-shell.js";

const elements = {
  announcement: document.querySelector("#calendar-announcement"),
  createButtons: [...document.querySelectorAll("[data-create-event]")],
  createCancel: document.querySelector("#calendar-create-cancel"),
  createDialog: document.querySelector("#calendar-create-dialog"),
  createError: document.querySelector("#calendar-create-error"),
  createFields: document.querySelector("#calendar-create-fields"),
  createForm: document.querySelector("#calendar-create-form"),
  createLoadingHint: document.querySelector("#calendar-create-loading-hint"),
  createSubmit: document.querySelector("#calendar-create-submit"),
  dialogCloseButtons: [...document.querySelectorAll("[data-calendar-dialog-close]")],
  document: document.querySelector("#calendar-event-document"),
  documentError: document.querySelector("#calendar-document-error"),
  documentsRetry: document.querySelector("#calendar-documents-retry"),
  empty: document.querySelector("#calendar-empty"),
  error: document.querySelector("#calendar-error"),
  end: document.querySelector("#calendar-event-end"),
  endError: document.querySelector("#calendar-end-error"),
  grid: document.querySelector("#calendar-grid"),
  loading: document.querySelector("#calendar-loading"),
  organizer: document.querySelector("#calendar-event-organizer"),
  participantEmail: document.querySelector("#calendar-participant-email"),
  participantError: document.querySelector("#calendar-participant-error"),
  participantList: document.querySelector("#calendar-participants"),
  participantsAdd: document.querySelector("#calendar-add-participant"),
  periodLabel: document.querySelector("#period-label"),
  retry: document.querySelector("#calendar-retry"),
  start: document.querySelector("#calendar-event-start"),
  startError: document.querySelector("#calendar-start-error"),
  today: document.querySelector("#today-button"),
  title: document.querySelector("#calendar-event-title"),
  titleError: document.querySelector("#calendar-title-error"),
  viewButtons: [...document.querySelectorAll("[data-view]")],
};

const VALID_VIEWS = new Set(["day", "week", "month"]);
const state = readLocationState();
let selectedDate = defaultSelectedDate(state.view, state.date);
let currentUser = null;
let requestVersion = 0;
let documentLoadVersion = 0;
let participants = [];
let isSubmitting = false;
let createFailed = false;

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
elements.createButtons.forEach((button) => {
  button.addEventListener("click", openCreateDialog);
});
elements.createForm.addEventListener("submit", (event) => {
  event.preventDefault();
  void submitCreateEvent();
});
elements.dialogCloseButtons.forEach((button) => {
  button.addEventListener("click", () => elements.createDialog.close());
});
elements.createDialog.addEventListener("cancel", (event) => {
  if (isSubmitting) {
    event.preventDefault();
  }
});
elements.createDialog.addEventListener("close", () => {
  documentLoadVersion += 1;
});
elements.participantsAdd.addEventListener("click", addParticipantFromInput);
elements.participantEmail.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    addParticipantFromInput();
  }
});
elements.participantEmail.addEventListener("input", () => {
  clearFieldError(elements.participantEmail, elements.participantError);
});
elements.documentsRetry.addEventListener("click", () => void loadEventDocuments());
elements.title.addEventListener("input", () => {
  clearFieldError(elements.title, elements.titleError);
});
elements.start.addEventListener("input", () => {
  clearFieldError(elements.start, elements.startError);
  if (elements.endError.textContent === "Завершення має бути пізніше за початок.") {
    clearFieldError(elements.end, elements.endError);
  }
});
elements.end.addEventListener("input", () => {
  clearFieldError(elements.end, elements.endError);
});
window.addEventListener("popstate", () => {
  Object.assign(state, readLocationState());
  selectedDate = defaultSelectedDate(state.view, state.date);
  void loadCurrentPeriod();
});

void initialize();

async function initialize() {
  try {
    const user = await requireAuthenticatedUser();
    if (!user) {
      return;
    }
    currentUser = user;
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
    date: normalizeDate(
      changes.date ?? (view === "day" ? selectedDate : state.date),
      view,
    ),
  });
  selectedDate = defaultSelectedDate(state.view, state.date);
  writeLocationState(true);
  void loadCurrentPeriod();
}

function defaultSelectedDate(view, date) {
  const today = startOfDay(new Date());
  if (view === "day") {
    return startOfDay(date);
  }
  if (view === "month") {
    return today.getFullYear() === date.getFullYear() &&
      today.getMonth() === date.getMonth()
      ? today
      : startOfDay(date);
  }
  const range = getPeriodRange(view, date);
  return today >= range.start && today < range.end ? today : startOfDay(date);
}

function setSelectedDate(date) {
  selectedDate = startOfDay(date);
  document.querySelectorAll("[data-calendar-date]").forEach((button) => {
    button.setAttribute(
      "aria-pressed",
      String(button.dataset.calendarDate === dateParameter(selectedDate)),
    );
  });
  elements.announcement.textContent =
    `Обрано ${formatLongDate(selectedDate)} для створення події.`;
}

function openCreateDialog() {
  if (isSubmitting) {
    return;
  }
  elements.createForm.reset();
  elements.title.value = "";
  elements.participantEmail.value = "";
  participants = [];
  renderParticipants();
  clearAllCreateErrors();
  createFailed = false;
  setSubmitting(false);
  elements.document.value = "";
  elements.documentError.hidden = true;
  elements.documentsRetry.hidden = true;
  elements.organizer.textContent = currentUser?.name
    ? `Організатор · ${currentUser.name} (ви)`
    : "Організатор (ви)";
  const start = createDefaultStartDate();
  const end = new Date(start);
  end.setHours(end.getHours() + 1);
  elements.start.value = formatLocalDateTime(start);
  elements.end.value = formatLocalDateTime(end);
  elements.createDialog.showModal();
  elements.title.focus();
  void loadEventDocuments();
}

function createDefaultStartDate() {
  const now = new Date();
  const start = startOfDay(selectedDate);
  const hour = now.getHours() + (now.getMinutes() || now.getSeconds() || now.getMilliseconds() ? 1 : 0);
  start.setHours(hour, 0, 0, 0);
  return start;
}

function formatLocalDateTime(date) {
  const localDate = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return localDate.toISOString().slice(0, 16);
}

async function loadEventDocuments() {
  const version = ++documentLoadVersion;
  elements.documentsRetry.hidden = true;
  elements.documentError.hidden = true;
  elements.documentError.textContent = "";
  elements.document.disabled = true;
  const noDocument = document.createElement("option");
  noDocument.value = "";
  noDocument.textContent = "Без документа";
  elements.document.replaceChildren(noDocument);

  try {
    const documents = [];
    let offset = 0;
    let hasMore = true;
    while (hasMore) {
      const page = await listDocuments({ offset });
      if (
        !page ||
        !Array.isArray(page.documents) ||
        !page.pagination ||
        !Number.isInteger(page.pagination.offset) ||
        typeof page.pagination.has_more !== "boolean"
      ) {
        throw new TypeError("Document list response is invalid.");
      }
      documents.push(...page.documents);
      const nextOffset = page.pagination.offset + page.documents.length;
      hasMore = page.pagination.has_more;
      if (hasMore && nextOffset <= offset) {
        throw new TypeError("Document list pagination did not advance.");
      }
      offset = nextOffset;
    }

    if (version !== documentLoadVersion || !elements.createDialog.open) {
      return;
    }
    const options = document.createDocumentFragment();
    for (const documentInfo of documents) {
      if (!Number.isInteger(documentInfo?.id) || typeof documentInfo.title !== "string") {
        throw new TypeError("Document list contains an invalid document.");
      }
      const option = document.createElement("option");
      option.value = String(documentInfo.id);
      option.textContent = documentInfo.title;
      options.append(option);
    }
    elements.document.append(options);
  } catch {
    if (version !== documentLoadVersion || !elements.createDialog.open) {
      return;
    }
    elements.documentError.textContent =
      "Не вдалося завантажити список документів. Спробуйте ще раз.";
    elements.documentError.hidden = false;
    elements.documentsRetry.hidden = false;
  } finally {
    if (version === documentLoadVersion && elements.createDialog.open) {
      elements.document.disabled = false;
    }
  }
}

function addParticipantFromInput() {
  const email = elements.participantEmail.value.trim();
  elements.participantEmail.value = email;
  if (!email) {
    setFieldError(elements.participantEmail, elements.participantError, "Введіть email учасника.");
    return;
  }
  if (elements.participantEmail.validity.typeMismatch) {
    setFieldError(elements.participantEmail, elements.participantError, "Введіть коректну email-адресу.");
    return;
  }
  if (participants.some((participant) => participant.toLocaleLowerCase("uk-UA") === email.toLocaleLowerCase("uk-UA"))) {
    setFieldError(elements.participantEmail, elements.participantError, "Цю email-адресу вже додано.");
    return;
  }
  participants.push(email);
  elements.participantEmail.value = "";
  clearFieldError(elements.participantEmail, elements.participantError);
  renderParticipants();
}

function renderParticipants() {
  elements.participantList.replaceChildren();
  elements.participantList.hidden = participants.length === 0;
  participants.forEach((email, index) => {
    const row = document.createElement("li");
    row.className = "calendar-dialog__participant";
    const address = document.createElement("span");
    address.className = "calendar-dialog__participant-email";
    address.textContent = email;
    const remove = document.createElement("button");
    remove.className = "button button--quiet button--small calendar-dialog__participant-remove";
    remove.type = "button";
    remove.textContent = "Вилучити";
    remove.setAttribute("aria-label", `Вилучити учасника ${email}`);
    remove.addEventListener("click", () => {
      participants.splice(index, 1);
      renderParticipants();
    });
    row.append(address, remove);
    elements.participantList.append(row);
  });
}

function clearFieldError(input, errorElement) {
  input.classList.remove("field__control--invalid");
  input.removeAttribute("aria-invalid");
  errorElement.textContent = "";
  errorElement.hidden = true;
}

function setFieldError(input, errorElement, message) {
  input.classList.add("field__control--invalid");
  input.setAttribute("aria-invalid", "true");
  errorElement.textContent = message;
  errorElement.hidden = false;
}

function clearAllCreateErrors() {
  clearFieldError(elements.title, elements.titleError);
  clearFieldError(elements.start, elements.startError);
  clearFieldError(elements.end, elements.endError);
  clearFieldError(elements.participantEmail, elements.participantError);
  elements.createError.hidden = true;
  elements.createError.textContent = "";
}

function setSubmitting(submitting) {
  isSubmitting = submitting;
  elements.createFields.disabled = submitting;
  elements.dialogCloseButtons.forEach((button) => {
    button.disabled = submitting;
  });
  elements.createCancel.disabled = submitting;
  elements.createSubmit.disabled = submitting;
  elements.createSubmit.classList.toggle("button--loading", submitting);
  elements.createSubmit.textContent = submitting
    ? "Створюємо подію…"
    : createFailed
      ? "Спробувати ще раз"
      : "Створити подію";
  elements.createLoadingHint.hidden = !submitting;
}

function validateCreateForm() {
  clearAllCreateErrors();
  const title = elements.title.value.trim();
  let valid = true;
  if (!title) {
    setFieldError(elements.title, elements.titleError, "Вкажіть назву події.");
    valid = false;
  } else if (title.length > 100) {
    setFieldError(elements.title, elements.titleError, "Назва має містити не більше ніж 100 символів.");
    valid = false;
  }

  const startAt = parseLocalDateTime(elements.start.value);
  const endAt = parseLocalDateTime(elements.end.value);
  if (!startAt) {
    setFieldError(elements.start, elements.startError, "Вкажіть коректну дату й час початку.");
    valid = false;
  }
  if (!endAt) {
    setFieldError(elements.end, elements.endError, "Вкажіть коректну дату й час завершення.");
    valid = false;
  } else if (startAt && endAt <= startAt) {
    setFieldError(elements.end, elements.endError, "Завершення має бути пізніше за початок.");
    valid = false;
  }

  const emails = [...participants];
  const draftEmail = elements.participantEmail.value.trim();
  if (draftEmail) {
    elements.participantEmail.value = draftEmail;
    if (elements.participantEmail.validity.typeMismatch) {
      setFieldError(elements.participantEmail, elements.participantError, "Введіть коректну email-адресу.");
      valid = false;
    } else if (emails.some((email) => email.toLocaleLowerCase("uk-UA") === draftEmail.toLocaleLowerCase("uk-UA"))) {
      setFieldError(elements.participantEmail, elements.participantError, "Цю email-адресу вже додано.");
      valid = false;
    } else {
      emails.push(draftEmail);
    }
  }

  return valid
    ? {
        title,
        startAt,
        endAt,
        emails,
        documentId: elements.document.value ? Number(elements.document.value) : null,
      }
    : null;
}

function parseLocalDateTime(value) {
  if (!value) {
    return null;
  }
  const date = new Date(value);
  return Number.isFinite(date.getTime()) && formatLocalDateTime(date) === value
    ? date
    : null;
}

async function submitCreateEvent() {
  if (isSubmitting) {
    return;
  }
  const formValues = validateCreateForm();
  if (!formValues) {
    createFailed = false;
    setSubmitting(false);
    return;
  }

  createFailed = false;
  setSubmitting(true);
  elements.createError.hidden = true;
  elements.createError.textContent = "";

  let createdEvent;
  try {
    elements.title.value = formValues.title;
    createdEvent = await createEvent(formValues);
  } catch {
    createFailed = true;
    elements.createError.textContent =
      "Не вдалося створити подію. Усі введені дані збережено. Перевірте з’єднання й спробуйте ще раз.";
    elements.createError.hidden = false;
    setSubmitting(false);
    return;
  }

  const failures = [];
  const eventId = createdEvent?.id;
  for (const email of formValues.emails) {
    if (!Number.isInteger(eventId) || eventId < 1) {
      failures.push(`учасника з email ${email} не вдалося додати`);
      continue;
    }
    try {
      await addParticipant(eventId, email);
    } catch (error) {
      failures.push(participantFailureMessage(email, error));
    }
  }

  if (formValues.documentId !== null) {
    if (!Number.isInteger(eventId) || eventId < 1) {
      failures.push("документ не вдалося прив’язати");
    } else {
      try {
        await linkDocument(eventId, formValues.documentId);
      } catch {
        const documentName =
          elements.document.selectedOptions[0]?.textContent ?? "вибраний документ";
        failures.push(`документ «${documentName}» не вдалося прив’язати`);
      }
    }
  }

  elements.createDialog.close();
  await loadCurrentPeriod();
  if (failures.length) {
    showToast(`Подію створено, але ${failures.join("; ")}.`, true);
  } else {
    showToast("Подію створено");
  }
  setSubmitting(false);
}

function participantFailureMessage(email, error) {
  if (error instanceof ApiError && error.status === 404) {
    return `користувача з email ${email} не знайдено`;
  }
  return `учасника з email ${email} не вдалося додати`;
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
  const heading = document.createElement("button");
  heading.type = "button";
  heading.className = "calendar-agenda__heading";
  heading.dataset.calendarDate = dateParameter(day);
  heading.setAttribute("aria-pressed", String(sameDate(day, selectedDate)));
  heading.setAttribute("aria-label", `Обрати ${formatLongDate(day)} для нової події`);
  heading.addEventListener("click", () => setSelectedDate(day));
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
    const dateLabel = document.createElement("button");
    dateLabel.type = "button";
    dateLabel.className = "calendar-month__date";
    dateLabel.dataset.calendarDate = dateParameter(day);
    dateLabel.setAttribute("aria-pressed", String(sameDate(day, selectedDate)));
    dateLabel.setAttribute("aria-label", `Обрати ${formatLongDate(day)} для нової події`);
    dateLabel.addEventListener("click", () => setSelectedDate(day));
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
