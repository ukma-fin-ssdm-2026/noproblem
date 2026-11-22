import {
  addParticipant,
  createEvent,
  getEvent,
  linkDocument,
  listEvents,
  listParticipants,
  removeParticipant,
  unlinkDocument,
  updateEvent,
} from "../api/calendar.js";
import { getDocument, listDocuments } from "../api/documents.js";
import { ApiError } from "../api/client.js";
import { requireAuthenticatedUser } from "../core/guard.js";
import { DateTimeField } from "../core/date-time-field.js";
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
  createTitle: document.querySelector("#calendar-create-title"),
  dialogCloseButtons: [...document.querySelectorAll("[data-calendar-dialog-close]")],
  detailBody: document.querySelector("#calendar-detail-body"),
  detailDate: document.querySelector("#calendar-detail-date"),
  detailDelete: document.querySelector("#calendar-detail-delete"),
  detailDialog: document.querySelector("#calendar-detail-dialog"),
  detailDocument: document.querySelector("#calendar-detail-document"),
  detailDocumentSection: document.querySelector("#calendar-detail-document-section"),
  detailEdit: document.querySelector("#calendar-detail-edit"),
  detailError: document.querySelector("#calendar-detail-error"),
  detailLeave: document.querySelector("#calendar-detail-leave"),
  detailLoading: document.querySelector("#calendar-detail-loading"),
  detailNote: document.querySelector("#calendar-detail-note"),
  detailParticipants: document.querySelector("#calendar-detail-participants"),
  detailParticipantsTitle: document.querySelector("#calendar-detail-participants-title"),
  detailRetry: document.querySelector("#calendar-detail-retry"),
  detailTime: document.querySelector("#calendar-detail-time"),
  detailTitle: document.querySelector("#calendar-detail-title"),
  document: document.querySelector("#calendar-event-document"),
  documentError: document.querySelector("#calendar-document-error"),
  documentsRetry: document.querySelector("#calendar-documents-retry"),
  empty: document.querySelector("#calendar-empty"),
  error: document.querySelector("#calendar-error"),
  end: new DateTimeField(document.querySelector("#calendar-event-end")),
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
  start: new DateTimeField(document.querySelector("#calendar-event-start")),
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
let documentsLoading = false;
let participants = [];
let isSubmitting = false;
let createFailed = false;
let dialogMode = "create";
let editingEvent = null;
let editingParticipants = [];
let removedParticipantIds = new Set();
let participantsNeedRefresh = false;
let selectedEvent = null;
let selectedParticipants = [];
let detailRequestVersion = 0;

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
  if (dialogMode === "edit") {
    void submitEditEvent();
  } else {
    void submitCreateEvent();
  }
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
  documentsLoading = false;
  if (!isSubmitting) {
    elements.createSubmit.disabled = false;
  }
  if (dialogMode === "edit" && editingEvent) {
    const eventId = editingEvent.id;
    clearEditState();
    void openEventDetails(eventId);
  }
});
document.querySelectorAll("[data-calendar-detail-close]").forEach((button) => {
  button.addEventListener("click", () => elements.detailDialog.close());
});
elements.detailDialog.addEventListener("close", () => {
  detailRequestVersion += 1;
});
elements.detailEdit.addEventListener("click", openEditDialog);
elements.detailRetry.addEventListener("click", () => {
  if (selectedEvent) {
    void openEventDetails(selectedEvent.id);
  }
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
// Як у Google Календарі: у списку часу завершення видно тривалість, а при
// зміні початку завершення зсувається разом із ним, зберігаючи тривалість.
elements.end.setDurationBase(elements.start);
elements.start.root.addEventListener("datetimechange", (event) => {
  const previousStart = parseLocalDateTime(event.detail.previous);
  const nextStart = parseLocalDateTime(event.detail.value);
  const end = parseLocalDateTime(elements.end.value);
  if (!previousStart || !nextStart || !end || end <= previousStart) {
    return;
  }
  elements.end.value = formatLocalDateTime(
    new Date(end.getTime() + (nextStart.getTime() - previousStart.getTime())),
  );
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
  dialogMode = "create";
  clearEditState();
  elements.createForm.reset();
  elements.createTitle.textContent = "Нова подія";
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
  documentsLoading = true;
  elements.documentsRetry.hidden = true;
  elements.documentError.hidden = true;
  elements.documentError.textContent = "";
  elements.document.disabled = true;
  elements.createSubmit.disabled = true;
  const noDocument = document.createElement("option");
  noDocument.value = "";
  noDocument.textContent = "Без документа";
  elements.document.replaceChildren(noDocument);

  try {
    const documents = await fetchAllDocuments();
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
    const currentDocumentId = dialogMode === "edit" ? editingEvent?.document_id : null;
    if (
      Number.isInteger(currentDocumentId) &&
      !documents.some((documentInfo) => documentInfo.id === currentDocumentId)
    ) {
      const unavailable = document.createElement("option");
      unavailable.value = String(currentDocumentId);
      unavailable.textContent = "Документ недоступний";
      options.append(unavailable);
    }
    elements.document.append(options);
    elements.document.value = Number.isInteger(currentDocumentId)
      ? String(currentDocumentId)
      : "";
  } catch {
    if (version !== documentLoadVersion || !elements.createDialog.open) {
      return;
    }
    if (dialogMode === "edit" && Number.isInteger(editingEvent?.document_id)) {
      const currentDocument = document.createElement("option");
      currentDocument.value = String(editingEvent.document_id);
      currentDocument.textContent = "Документ недоступний";
      elements.document.append(currentDocument);
      elements.document.value = String(editingEvent.document_id);
    }
    elements.documentError.textContent =
      "Не вдалося завантажити список документів. Спробуйте ще раз.";
    elements.documentError.hidden = false;
    elements.documentsRetry.hidden = false;
  } finally {
    if (version === documentLoadVersion) {
      documentsLoading = false;
      if (elements.createDialog.open) {
        elements.document.disabled = false;
      }
      if (!isSubmitting) {
        elements.createSubmit.disabled = false;
      }
    }
  }
}

async function fetchAllDocuments() {
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
  return documents;
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
  const existing = dialogMode === "edit"
    ? editingParticipants.find((participant) => sameEmail(participant.email, email))
    : null;
  if (existing && removedParticipantIds.has(existing.user_id)) {
    removedParticipantIds.delete(existing.user_id);
    elements.participantEmail.value = "";
    clearFieldError(elements.participantEmail, elements.participantError);
    renderParticipants();
    return;
  }
  if (
    participants.some((participant) => sameEmail(participant, email)) ||
    (existing && !removedParticipantIds.has(existing.user_id))
  ) {
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
  if (dialogMode === "edit") {
    editingParticipants
      .filter((participant) => !removedParticipantIds.has(participant.user_id))
      .forEach((participant) => {
        appendEditableParticipant(participant.name || participant.email, () => {
            removedParticipantIds.add(participant.user_id);
            renderParticipants();
          });
      });
  }
  participants.forEach((email) => {
    appendEditableParticipant(email, () => {
      participants = participants.filter((entry) => entry !== email);
      renderParticipants();
    });
  });
  elements.participantList.hidden = elements.participantList.childElementCount === 0;
}

function appendEditableParticipant(label, onRemove) {
  const row = document.createElement("li");
  row.className = "calendar-dialog__participant";
  const address = document.createElement("span");
  address.className = "calendar-dialog__participant-email";
  address.textContent = label;
  const remove = document.createElement("button");
  remove.className = "button button--quiet button--small calendar-dialog__participant-remove";
  remove.type = "button";
  remove.textContent = "Вилучити";
  remove.setAttribute("aria-label", `Вилучити учасника ${label}`);
  remove.addEventListener("click", onRemove);
  row.append(address, remove);
  elements.participantList.append(row);
}

function sameEmail(left, right) {
  return left.toLocaleLowerCase("uk-UA") === right.toLocaleLowerCase("uk-UA");
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
  elements.createSubmit.disabled = submitting || documentsLoading;
  elements.createSubmit.classList.toggle("button--loading", submitting);
  elements.createSubmit.textContent = submitting
    ? dialogMode === "edit"
      ? "Зберігаємо зміни…"
      : "Створюємо подію…"
    : createFailed
      ? "Спробувати ще раз"
      : dialogMode === "edit"
        ? "Зберегти зміни"
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
    const alreadyParticipant = dialogMode === "edit" && editingParticipants.some(
      (participant) =>
        sameEmail(participant.email, draftEmail) &&
        !removedParticipantIds.has(participant.user_id),
    );
    if (elements.participantEmail.validity.typeMismatch) {
      setFieldError(elements.participantEmail, elements.participantError, "Введіть коректну email-адресу.");
      valid = false;
    } else if (alreadyParticipant || emails.some((email) => sameEmail(email, draftEmail))) {
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
  if (isSubmitting || documentsLoading) {
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

async function openEventDetails(eventId, showDialog = true) {
  const version = ++detailRequestVersion;
  selectedEvent = { id: eventId };
  if (showDialog && !elements.detailDialog.open) {
    elements.detailDialog.showModal();
  }
  elements.detailTitle.textContent = "Деталі події";
  elements.detailLoading.hidden = false;
  elements.detailError.hidden = true;
  elements.detailError.textContent = "";
  elements.detailRetry.hidden = true;
  elements.detailBody.hidden = true;

  try {
    const [event, eventParticipants] = await Promise.all([
      getEvent(eventId),
      listParticipants(eventId),
    ]);
    const validEvent = validateDetailedEvent(event);
    const validParticipants = validateParticipants(eventParticipants);
    const eventDocument = Number.isInteger(validEvent.document_id)
      ? await resolveEventDocument(validEvent.document_id)
      : null;
    if (version !== detailRequestVersion || (showDialog && !elements.detailDialog.open)) {
      return;
    }
    selectedEvent = validEvent;
    selectedParticipants = validParticipants;
    renderEventDetails(validEvent, validParticipants, eventDocument);
    elements.detailLoading.hidden = true;
    elements.detailBody.hidden = false;
  } catch (error) {
    if (version !== detailRequestVersion || (showDialog && !elements.detailDialog.open)) {
      return;
    }
    if (error instanceof ApiError && error.status === 404) {
      handleEventNotFound();
      return;
    }
    elements.detailLoading.hidden = true;
    elements.detailError.textContent =
      error instanceof ApiError && error.status === 403
        ? "Переглядати деталі події може лише її учасник."
        : "Не вдалося завантажити деталі події. Спробуйте ще раз.";
    elements.detailError.hidden = false;
    elements.detailRetry.hidden = false;
  }
}

function validateDetailedEvent(event) {
  if (
    !event ||
    !Number.isInteger(event.id) ||
    event.id < 1 ||
    typeof event.title !== "string" ||
    !Number.isFinite(Date.parse(event.start_at)) ||
    !Number.isFinite(Date.parse(event.end_at)) ||
    Date.parse(event.end_at) <= Date.parse(event.start_at) ||
    (event.document_id !== null && !Number.isInteger(event.document_id))
  ) {
    throw new TypeError("Calendar event response is invalid.");
  }
  return {
    ...event,
    start: new Date(event.start_at),
    end: new Date(event.end_at),
  };
}

function validateParticipants(eventParticipants) {
  if (!Array.isArray(eventParticipants)) {
    throw new TypeError("Calendar participants response is invalid.");
  }
  return eventParticipants.map((participant) => {
    if (
      !participant ||
      typeof participant.user_id !== "string" ||
      typeof participant.name !== "string" ||
      typeof participant.email !== "string"
    ) {
      throw new TypeError("Calendar participants response is invalid.");
    }
    return participant;
  });
}

async function resolveEventDocument(documentId) {
  try {
    const documents = await fetchAllDocuments();
    const found = documents.find((documentInfo) => documentInfo.id === documentId);
    if (found && typeof found.title === "string") {
      return { title: found.title, unavailable: false };
    }
  } catch (error) {
    if (!(error instanceof ApiError) || error.status === 401) {
      throw error;
    }
  }

  try {
    const documentInfo = await getDocument(documentId);
    if (!documentInfo || typeof documentInfo.title !== "string") {
      throw new TypeError("Document response is invalid.");
    }
    return { title: documentInfo.title, unavailable: false };
  } catch (error) {
    if (error instanceof ApiError && (error.status === 403 || error.status === 404)) {
      return { title: "Документ недоступний", unavailable: true };
    }
    throw error;
  }
}

function renderEventDetails(event, eventParticipants, eventDocument) {
  const isCreator = event.creator_id === currentUser?.id;
  const organizerName =
    (typeof event.creator_name === "string" && event.creator_name.trim()) ||
    (typeof event.creator_email === "string" && event.creator_email.trim()) ||
    "Невідомий користувач";
  elements.detailTitle.textContent = event.title;
  elements.detailDate.textContent = formatEventDate(event.start, event.end);
  elements.detailTime.textContent = `${formatTime(event.start)}–${formatTime(event.end)}`;
  elements.detailParticipantsTitle.textContent = `Учасники · ${eventParticipants.length + 1}`;
  elements.detailParticipants.replaceChildren();
  elements.detailParticipants.append(
    createDetailParticipant(organizerName, event.creator_email, true, isCreator),
  );
  eventParticipants.forEach((participant) => {
    elements.detailParticipants.append(
      createDetailParticipant(
        participant.name || participant.email,
        participant.email,
        false,
        participant.user_id === currentUser?.id,
      ),
    );
  });
  elements.detailDocument.replaceChildren();
  if (event.document_id === null) {
    elements.detailDocument.textContent = "Документ не прив’язаний.";
  } else if (eventDocument?.unavailable) {
    elements.detailDocument.textContent = "Документ недоступний";
  } else {
    const link = document.createElement("a");
    link.className = "calendar-detail-dialog__document-link";
    link.href = `document.html?id=${encodeURIComponent(String(event.document_id))}`;
    const icon = document.createElement("img");
    icon.src = "assets/icon-files.svg";
    icon.width = 18;
    icon.height = 18;
    icon.alt = "";
    const title = document.createElement("span");
    title.textContent = eventDocument.title;
    link.append(icon, title);
    elements.detailDocument.append(link);
  }
  elements.detailDocumentSection.hidden = false;
  elements.detailDelete.hidden = !isCreator;
  elements.detailEdit.hidden = !isCreator;
  elements.detailLeave.hidden = isCreator;
  elements.detailNote.hidden = isCreator;
  elements.detailNote.textContent =
    "Ви берете участь у цій події. Змінювати подію та склад учасників може лише її автор.";
}

function createDetailParticipant(name, email, isOrganizer, isCurrentUser) {
  const row = document.createElement("li");
  row.className = "calendar-detail-dialog__participant";
  const avatar = document.createElement("span");
  avatar.className = "calendar-detail-dialog__avatar";
  avatar.setAttribute("aria-hidden", "true");
  avatar.textContent = initials(name || email || "?");
  const participantName = document.createElement("span");
  participantName.className = "calendar-detail-dialog__participant-name";
  participantName.textContent = `${name}${isCurrentUser ? " · ви" : ""}`;
  row.append(avatar, participantName);
  if (isOrganizer) {
    const organizer = document.createElement("span");
    organizer.className = "calendar-detail-dialog__organizer-label";
    organizer.textContent = "Організатор";
    row.append(organizer);
  }
  return row;
}

function initials(name) {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0] ?? "")
    .join("")
    .toLocaleUpperCase("uk-UA");
}

function formatEventDate(start, end) {
  const dateOptions = {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  };
  const startLabel = capitalize(new Intl.DateTimeFormat("uk-UA", dateOptions).format(start));
  if (sameDate(start, end)) {
    return startLabel;
  }
  return `${startLabel} – ${capitalize(new Intl.DateTimeFormat("uk-UA", dateOptions).format(end))}`;
}

function openEditDialog() {
  if (!selectedEvent || selectedEvent.creator_id !== currentUser?.id || isSubmitting) {
    return;
  }
  elements.detailDialog.close();
  dialogMode = "edit";
  editingEvent = selectedEvent;
  editingParticipants = [...selectedParticipants];
  removedParticipantIds = new Set();
  participantsNeedRefresh = false;
  participants = [];
  elements.createForm.reset();
  elements.createTitle.textContent = "Редагувати подію";
  elements.title.value = editingEvent.title;
  elements.start.value = formatLocalDateTime(editingEvent.start);
  elements.end.value = formatLocalDateTime(editingEvent.end);
  elements.participantEmail.value = "";
  elements.organizer.textContent = `Організатор · ${
    editingEvent.creator_name || editingEvent.creator_email || "Невідомий користувач"
  }${editingEvent.creator_id === currentUser?.id ? " (ви)" : ""}`;
  renderParticipants();
  clearAllCreateErrors();
  createFailed = false;
  setSubmitting(false);
  elements.document.value = "";
  elements.documentError.hidden = true;
  elements.documentsRetry.hidden = true;
  elements.createDialog.showModal();
  elements.title.focus();
  void loadEventDocuments();
}

function clearEditState() {
  dialogMode = "create";
  editingEvent = null;
  editingParticipants = [];
  removedParticipantIds = new Set();
  participantsNeedRefresh = false;
  participants = [];
}

async function submitEditEvent() {
  if (isSubmitting || documentsLoading || !editingEvent) {
    return;
  }
  const formValues = validateCreateForm();
  if (!formValues) {
    createFailed = false;
    setSubmitting(false);
    return;
  }

  const eventId = editingEvent.id;
  const failures = [];
  let forbidden = false;
  let savedChangeCount = 0;
  createFailed = false;
  setSubmitting(true);
  elements.createError.hidden = true;
  elements.createError.textContent = "";

  const changes = {};
  if (formValues.title !== editingEvent.title) {
    changes.title = formValues.title;
  }
  if (formValues.startAt.getTime() !== editingEvent.start.getTime()) {
    changes.startAt = formValues.startAt;
  }
  if (formValues.endAt.getTime() !== editingEvent.end.getTime()) {
    changes.endAt = formValues.endAt;
  }
  if (Object.keys(changes).length) {
    try {
      editingEvent = validateDetailedEvent(await updateEvent(eventId, changes));
      savedChangeCount += Object.keys(changes).length;
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        handleEventNotFound();
        return;
      }
      if (error instanceof ApiError && error.status === 403) {
        forbidden = true;
      }
      failures.push(
        `не вдалося зберегти ${[
          changes.title !== undefined ? "назву події" : null,
          changes.startAt !== undefined ? "початок" : null,
          changes.endAt !== undefined ? "завершення" : null,
        ].filter(Boolean).join(", ")}`,
      );
    }
  }

  if (!forbidden) {
    for (const participantId of [...removedParticipantIds]) {
      const participant = editingParticipants.find((entry) => entry.user_id === participantId);
      if (!participant) {
        removedParticipantIds.delete(participantId);
        continue;
      }
      try {
        await removeParticipant(eventId, participantId);
        editingParticipants = editingParticipants.filter(
          (entry) => entry.user_id !== participantId,
        );
        removedParticipantIds.delete(participantId);
        participantsNeedRefresh = true;
        savedChangeCount += 1;
      } catch (error) {
        if (error instanceof ApiError && error.status === 403) {
          forbidden = true;
          failures.push(`учасника «${participant.name || participant.email}» не вдалося вилучити`);
          break;
        }
        failures.push(
          `учасника «${participant.name || participant.email}» не вдалося вилучити`,
        );
      }
    }
  }

  if (!forbidden) {
    for (const email of formValues.emails) {
      try {
        await addParticipant(eventId, email);
        participants = participants.filter((entry) => !sameEmail(entry, email));
        if (sameEmail(elements.participantEmail.value.trim(), email)) {
          elements.participantEmail.value = "";
          clearFieldError(elements.participantEmail, elements.participantError);
        }
        participantsNeedRefresh = true;
        savedChangeCount += 1;
      } catch (error) {
        if (error instanceof ApiError && error.status === 403) {
          forbidden = true;
          failures.push(`учасника з email ${email} не вдалося додати`);
          break;
        }
        failures.push(participantEditFailureMessage(email, error));
      }
    }
  }

  if (participantsNeedRefresh && !forbidden) {
    try {
      editingParticipants = validateParticipants(await listParticipants(eventId));
      participantsNeedRefresh = false;
      renderParticipants();
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        handleEventNotFound();
        return;
      }
      if (error instanceof ApiError && error.status === 403) {
        forbidden = true;
      } else {
        failures.push("не вдалося оновити список учасників");
      }
    }
  }

  if (!forbidden) {
    const nextDocumentId = elements.document.value ? Number(elements.document.value) : null;
    if (nextDocumentId !== editingEvent.document_id) {
      try {
        if (nextDocumentId === null) {
          await unlinkDocument(eventId);
        } else {
          await linkDocument(eventId, nextDocumentId);
        }
        editingEvent = { ...editingEvent, document_id: nextDocumentId };
        savedChangeCount += 1;
      } catch (error) {
        if (error instanceof ApiError && error.status === 403) {
          forbidden = true;
          failures.push(
            nextDocumentId === null
              ? "не вдалося відв’язати документ"
              : `документ «${elements.document.selectedOptions[0]?.textContent ?? "вибраний документ"}» не вдалося прив’язати`,
          );
        } else {
          const documentName =
            elements.document.selectedOptions[0]?.textContent ?? "вибраний документ";
          failures.push(
            nextDocumentId === null
              ? "не вдалося відв’язати документ"
              : `документ «${documentName}» не вдалося прив’язати`,
          );
        }
      }
    }
  }

  if (failures.length || forbidden) {
    createFailed = true;
    elements.createError.textContent = [
      forbidden ? "Змінювати подію може лише її автор." : "",
      failures.length
        ? `Не вдалося зберегти: ${failures.join("; ")}. ${
            savedChangeCount
              ? "Інші зміни збережено; дані форми залишилися."
              : "Дані форми залишилися. Спробуйте ще раз."
          }`
        : "",
    ].filter(Boolean).join(" ");
    elements.createError.hidden = false;
    setSubmitting(false);
    return;
  }

  dialogMode = "create";
  clearEditState();
  setSubmitting(false);
  elements.createDialog.close();
  await loadCurrentPeriod();
  await openEventDetails(eventId, false);
  showToast("Зміни збережено");
}

function participantEditFailureMessage(email, error) {
  if (error instanceof ApiError && error.status === 404) {
    return `Користувача з таким email не знайдено (${email})`;
  }
  return `учасника з email ${email} не вдалося додати`;
}

function handleEventNotFound() {
  if (isSubmitting) {
    setSubmitting(false);
  }
  createFailed = false;
  if (elements.detailDialog.open) {
    elements.detailDialog.close();
  }
  if (elements.createDialog.open) {
    dialogMode = "create";
    clearEditState();
    elements.createDialog.close();
  }
  selectedEvent = null;
  selectedParticipants = [];
  void loadCurrentPeriod();
  showToast("Подію не знайдено, можливо, її видалили", true);
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
      !Number.isInteger(event.id) ||
      event.id < 1 ||
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
    const eventElement = document.createElement("button");
    eventElement.type = "button";
    eventElement.className = "calendar-event";
    eventElement.style.setProperty("--event-top", `${(segment.startMinute / 1440) * 100}%`);
    eventElement.style.setProperty(
      "--event-height",
      `${((segment.endMinute - segment.startMinute) / 1440) * 100}%`,
    );
    eventElement.style.setProperty("--event-left", `${(segment.lane / laneCount) * 100}%`);
    eventElement.style.setProperty("--event-width", `${100 / laneCount}%`);
    eventElement.setAttribute(
      "aria-label",
      `${segment.label}, ${segment.event.title}`,
    );
    eventElement.addEventListener("click", () => {
      void openEventDetails(segment.event.id);
    });
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
  const item = document.createElement("button");
  item.type = "button";
  item.className = "calendar-month__event";
  const segment = makeDaySegment(event, startOfDay(day), addDays(startOfDay(day), 1));
  const time = document.createElement("span");
  time.textContent = segment.label;
  const title = document.createElement("span");
  title.textContent = event.title;
  item.append(time, title);
  item.setAttribute("aria-label", `${segment.label}, ${event.title}`);
  item.addEventListener("click", () => {
    void openEventDetails(event.id);
  });
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
