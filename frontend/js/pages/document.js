import {
  createDocument,
  createParagraph,
  deleteParagraph,
  getDocument,
  getDocumentMembers,
  listParagraphs,
  moveDocumentToTrash,
  renameDocument,
  revokeAccess,
  shareDocument,
  updateParagraph,
} from "../api/documents.js";
import { ApiError } from "../api/client.js";
import { DocumentSaveQueue } from "../core/document-save-queue.js";
import { setProfile, setupLogout, showToast } from "../core/app-shell.js";
import { requireAuthenticatedUser } from "../core/guard.js";

const MAX_TITLE_LENGTH = 100;
const MAX_PARAGRAPH_LENGTH = 10_000;
const documentId = parseDocumentId();

const elements = {
  createDocument: document.querySelector("#create-document"),
  searchForm: document.querySelector("#workspace-search-form"),
  searchInput: document.querySelector("#workspace-search"),
  toolbarTitle: document.querySelector("#toolbar-title"),
  toolbarSubtitle: document.querySelector("#toolbar-subtitle"),
  members: document.querySelector("#document-members"),
  documentTitle: document.querySelector("#document-title"),
  titleError: document.querySelector("#title-error"),
  paragraphList: document.querySelector("#paragraph-list"),
  paragraphsEmpty: document.querySelector("#paragraphs-empty"),
  addParagraph: document.querySelector("#add-paragraph"),
  editorView: document.querySelector("#document-view"),
  loading: document.querySelector("#document-loading"),
  error: document.querySelector("#document-error"),
  errorMessage: document.querySelector("#document-error-message"),
  loadRetry: document.querySelector("#load-retry"),
  readonlyBanner: document.querySelector("#readonly-banner"),
  readonlyMessage: document.querySelector("#readonly-message"),
  accessDetails: document.querySelector("#document-access-details"),
  saveStatus: document.querySelector("#save-status"),
  saveStatusText: document.querySelector("#save-status-text"),
  retrySave: document.querySelector("#retry-save"),
  actions: document.querySelector("#document-actions"),
  trashDocument: document.querySelector("#trash-document"),
  trashDialog: document.querySelector("#trash-dialog"),
  trashDescription: document.querySelector("#trash-description"),
  trashConfirm: document.querySelector("#trash-confirm"),
  deleteDialog: document.querySelector("#delete-paragraph-dialog"),
  deleteParagraphConfirm: document.querySelector("#delete-paragraph-confirm"),
  shareButton: document.querySelector("#share-button"),
  shareDialog: document.querySelector("#share-dialog"),
  shareAddForm: document.querySelector("#share-add-form"),
  shareEmail: document.querySelector("#share-email"),
  shareEmailError: document.querySelector("#share-email-error"),
  shareRole: document.querySelector("#share-role"),
  shareAddButton: document.querySelector("#share-add-button"),
  shareMembersCount: document.querySelector("#share-members-count"),
  shareMembers: document.querySelector("#share-members"),
  shareAccessTitle: document.querySelector("#share-access-title"),
  shareAccessDescription: document.querySelector("#share-access-description"),
  shareAccessLink: document.querySelector("#share-access-link"),
  copyShareLink: document.querySelector("#copy-share-link"),
};

let currentDocument = null;
let currentRole = null;
let currentUserEmail = null;
let currentMembers = null;
let canEdit = false;
let selectedParagraph = null;
let retryLoad = loadDocument;
const saveQueue = new DocumentSaveQueue({ onState: showSaveState });

elements.searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const query = elements.searchInput.value.trim();
  const search = new URLSearchParams();
  if (query) {
    search.set("q", query);
  }
  location.assign(`workspace.html${search.size ? `?${search}` : ""}`);
});

elements.createDocument.addEventListener("click", createNewDocument);
elements.documentTitle.addEventListener("input", onTitleInput);
elements.documentTitle.addEventListener("blur", () => {
  void saveQueue.flush("title");
});
elements.paragraphList.addEventListener("input", onParagraphInput);
elements.paragraphList.addEventListener("focusout", onParagraphFocusOut);
elements.paragraphList.addEventListener("click", onParagraphAction);
elements.addParagraph.addEventListener("click", addParagraph);
elements.loadRetry.addEventListener("click", () => retryLoad());
elements.retrySave.addEventListener("click", () => saveQueue.retry());
elements.trashDocument.addEventListener("click", openTrashDialog);
elements.trashConfirm.addEventListener("click", confirmMoveToTrash);
elements.deleteParagraphConfirm.addEventListener("click", confirmDeleteParagraph);
elements.shareButton.addEventListener("click", openShareDialog);
elements.shareAddForm.addEventListener("submit", addMember);
elements.shareEmail.addEventListener("input", updateShareEmailState);
elements.shareRole.addEventListener("change", updateShareEmailState);
elements.shareMembers.addEventListener("change", changeMemberRole);
elements.shareMembers.addEventListener("click", revokeMember);
elements.copyShareLink.addEventListener("click", copyDocumentLink);
elements.shareDialog.addEventListener("click", (event) => {
  if (event.target === elements.shareDialog) {
    elements.shareDialog.close();
  }
});
document.querySelectorAll("[data-dialog-close]").forEach((button) => {
  button.addEventListener("click", () => {
    document.getElementById(button.dataset.dialogClose).close();
  });
});
window.addEventListener("beforeunload", warnAboutUnsavedChanges);

void initialize();

async function initialize() {
  try {
    const user = await requireAuthenticatedUser();
    if (!user) {
      return;
    }
    currentUserEmail = user.email;
    setProfile(user);
    setupLogout((message) => showToast(message, true));
    if (documentId === null) {
      throw new ApiError({
        code: "INVALID_DOCUMENT_ID",
        message: "Посилання на документ недійсне.",
      });
    }
    await loadDocument(user);
  } catch (error) {
    showLoadError(errorMessage(error, "Не вдалося завантажити документ."));
  }
}

async function loadDocument(user) {
  retryLoad = () => loadDocument(user);
  setLoading(true);
  hideLoadError();
  try {
    const [documentInfo, paragraphResponse, access] = await Promise.all([
      getDocument(documentId),
      listParagraphs(documentId),
      loadAccess(user),
    ]);
    currentDocument = documentInfo;
    currentRole = access.role;
    canEdit = currentRole === "owner" || currentRole === "editor";
    renderDocument(documentInfo, paragraphResponse.paragraphs, access.members);
    if (!canEdit) {
      setReadOnly(
        "Режим читання: роль поточного користувача недоступна через API. Редагування вимкнене.",
      );
    } else {
      showSaveState("saved");
    }
    elements.editorView.hidden = false;
  } catch (error) {
    showLoadError(errorMessage(error, "Не вдалося завантажити документ."));
  } finally {
    setLoading(false);
  }
}

async function loadAccess(user) {
  try {
    const response = await getDocumentMembers(documentId);
    const member = response.members.find(
      (item) => item.email.toLocaleLowerCase("uk-UA") === user.email.toLocaleLowerCase("uk-UA"),
    );
    return {
      role: member?.role?.toLocaleLowerCase("uk-UA") ?? null,
      members: response.members,
    };
  } catch (error) {
    if (error instanceof ApiError && error.status === 403) {
      return { role: null, members: null };
    }
    throw error;
  }
}

function renderDocument(documentInfo, paragraphs, members) {
  currentDocument.paragraphs = paragraphs;
  currentMembers = members ? [...members] : [];
  const owner = members?.find((member) => member.role === "owner");
  elements.toolbarTitle.textContent = documentInfo.title;
  document.title = `${documentInfo.title} — NoteLy`;
  elements.documentTitle.value = documentInfo.title;
  elements.documentTitle.readOnly = !canEdit;
  elements.toolbarSubtitle.textContent = currentRole
    ? `${roleLabel(currentRole)}${owner ? ` · ${owner.name}` : ""}`
    : "Лише читання";
  elements.accessDetails.textContent = currentRole
    ? `Власник: ${owner?.name ?? "невідомий"} · ${accessModeLabel(documentInfo.access_mode)}.`
    : "Роль поточного користувача не повертається API.";
  elements.actions.hidden = currentRole !== "owner";
  elements.trashDocument.disabled = currentRole !== "owner";
  elements.shareButton.disabled = currentRole !== "owner";
  renderMembers(members);
  renderParagraphs(paragraphs);
}

function renderMembers(members) {
  const fragment = document.createDocumentFragment();
  if (members) {
    for (const member of members) {
      const avatar = document.createElement("span");
      const role = ["owner", "editor", "guest"].includes(member.role)
        ? member.role
        : "unknown";
      avatar.className = `document-member${role === "unknown" ? "" : ` document-member--${role}`}`;
      avatar.textContent = initials(member.name);
      avatar.title = `${member.name} — ${roleLabel(member.role)}`;
      fragment.append(avatar);
    }
  }
  elements.members.replaceChildren(fragment);
}

function renderParagraphs(paragraphs) {
  const fragment = document.createDocumentFragment();
  paragraphs.forEach((paragraph, index) => {
    fragment.append(createParagraphElement(paragraph, index, paragraphs.length));
  });
  elements.paragraphList.replaceChildren(fragment);
  elements.paragraphsEmpty.hidden = paragraphs.length !== 0;
  const emptyDescription = elements.paragraphsEmpty.querySelector(".empty-state__description");
  emptyDescription.textContent = canEdit
    ? "Додайте перший абзац, щоб почати записувати думки."
    : "У цього документа поки немає абзаців.";
  elements.addParagraph.disabled = !canEdit;
}

function createParagraphElement(paragraph, index, count) {
  const article = document.createElement("article");
  article.className = "document-paragraph";
  article.dataset.paragraphId = String(paragraph.id);

  const label = document.createElement("label");
  label.className = "visually-hidden";
  label.htmlFor = `paragraph-${paragraph.id}`;
  label.textContent = `Абзац ${index + 1}`;
  const textarea = document.createElement("textarea");
  textarea.className = "document-paragraph__textarea";
  textarea.id = `paragraph-${paragraph.id}`;
  textarea.dataset.paragraphId = String(paragraph.id);
  textarea.value = paragraph.content;
  textarea.readOnly = !canEdit;
  textarea.setAttribute("aria-label", `Абзац ${index + 1}`);
  textarea.setAttribute("aria-describedby", "format-help");
  article.append(label, textarea);

  if (canEdit) {
    const controls = document.createElement("div");
    controls.className = "document-paragraph__controls";

    const moveUp = createParagraphAction(
      "↑",
      `Перемістити абзац ${index + 1} вище`,
      "move-up",
      paragraph.id,
    );
    moveUp.disabled = index === 0;
    const moveDown = createParagraphAction(
      "↓",
      `Перемістити абзац ${index + 1} нижче`,
      "move-down",
      paragraph.id,
    );
    moveDown.disabled = index === count - 1;
    const remove = createParagraphAction(
      "Видалити",
      `Видалити абзац ${index + 1}`,
      "delete",
      paragraph.id,
      "button button--quiet button--small",
    );
    controls.append(moveUp, moveDown, remove);
    article.append(controls);
  }
  return article;
}

function createParagraphAction(text, label, action, paragraphId, className = "button button--secondary button--small") {
  const button = document.createElement("button");
  button.className = className;
  button.type = "button";
  button.textContent = text;
  button.setAttribute("aria-label", label);
  button.dataset.action = action;
  button.dataset.paragraphId = String(paragraphId);
  return button;
}

function onTitleInput() {
  if (!canEdit) {
    return;
  }
  const value = elements.documentTitle.value;
  const normalized = value.trim();
  const length = Array.from(normalized).length;
  const key = "title";
  const save = async (title) => {
    try {
      const updated = await renameDocument(documentId, String(title).trim());
      currentDocument = {
        ...updated,
        paragraphs: currentDocument.paragraphs ?? [],
      };
      elements.toolbarTitle.textContent = updated.title;
      document.title = `${updated.title} — NoteLy`;
      if (elements.documentTitle.value.trim() === String(title).trim()) {
        elements.documentTitle.value = updated.title;
      }
    } catch (error) {
      handleWriteError(error);
      throw error;
    }
  };
  if (length < 1 || length > MAX_TITLE_LENGTH) {
    showFieldError(
      elements.documentTitle,
      elements.titleError,
      `Назва має містити від 1 до ${MAX_TITLE_LENGTH} символів.`,
    );
    saveQueue.setValidationError(key, value, save, "Некоректна назва документа.");
    return;
  }
  clearFieldError(elements.documentTitle, elements.titleError);
  saveQueue.set(key, normalized, save);
}

function onParagraphInput(event) {
  const textarea = event.target.closest("textarea[data-paragraph-id]");
  if (!textarea || !canEdit) {
    return;
  }
  const paragraphId = Number(textarea.dataset.paragraphId);
  const key = paragraphKey(paragraphId);
  const value = textarea.value;
  const save = async (content) => {
    try {
      await updateParagraph(documentId, paragraphId, { content: String(content) });
      const paragraph = currentDocument.paragraphs?.find((item) => item.id === paragraphId);
      if (paragraph) {
        paragraph.content = String(content);
      }
    } catch (error) {
      handleWriteError(error);
      throw error;
    }
  };
  if (Array.from(value).length > MAX_PARAGRAPH_LENGTH) {
    textarea.setAttribute("aria-invalid", "true");
    textarea.setAttribute("aria-describedby", "format-help paragraph-length-error");
    showParagraphLengthError(textarea);
    saveQueue.setValidationError(
      key,
      value,
      save,
      `Абзац не може перевищувати ${MAX_PARAGRAPH_LENGTH} символів.`,
    );
    return;
  }
  clearParagraphLengthError(textarea);
  saveQueue.set(key, value, save);
}

function onParagraphFocusOut(event) {
  const textarea = event.target.closest("textarea[data-paragraph-id]");
  if (textarea && canEdit) {
    void saveQueue.flush(paragraphKey(Number(textarea.dataset.paragraphId)));
  }
}

function onParagraphAction(event) {
  const button = event.target.closest("button[data-action]");
  if (!button || !canEdit) {
    return;
  }
  const paragraphId = Number(button.dataset.paragraphId);
  if (button.dataset.action === "delete") {
    selectedParagraph = paragraphId;
    elements.deleteDialog.showModal();
  } else {
    void moveParagraph(paragraphId, button.dataset.action === "move-up" ? -1 : 1);
  }
}

async function addParagraph() {
  if (!canEdit) {
    return;
  }
  if (!(await saveQueue.flushAll())) {
    showToast("Спершу виправте або збережіть незбережені зміни.", true);
    return;
  }
  setStructuralActionsBusy(true);
  try {
    const paragraph = await createParagraph(documentId, "");
    await reloadParagraphs();
    const textarea = elements.paragraphList.querySelector(
      `textarea[data-paragraph-id="${paragraph.id}"]`,
    );
    textarea?.focus();
    showToast("Абзац додано.");
  } catch (error) {
    handleWriteError(error);
    showToast(errorMessage(error, "Не вдалося додати абзац."), true);
  } finally {
    setStructuralActionsBusy(false);
  }
}

async function moveParagraph(paragraphId, direction) {
  if (!(await saveQueue.flushAll())) {
    showToast("Спершу виправте або збережіть незбережені зміни.", true);
    return;
  }
  const paragraphs = currentDocument.paragraphs ?? [];
  const currentIndex = paragraphs.findIndex((item) => item.id === paragraphId);
  const position = currentIndex + direction;
  if (currentIndex < 0 || position < 0 || position >= paragraphs.length) {
    return;
  }
  setStructuralActionsBusy(true);
  try {
    await updateParagraph(documentId, paragraphId, { position });
    await reloadParagraphs();
  } catch (error) {
    handleWriteError(error);
    showToast(errorMessage(error, "Не вдалося змінити порядок абзаців."), true);
  } finally {
    setStructuralActionsBusy(false);
  }
}

async function confirmDeleteParagraph() {
  if (selectedParagraph === null) {
    return;
  }
  if (!(await saveQueue.flushAll())) {
    elements.deleteDialog.close();
    showToast("Спершу виправте або збережіть незбережені зміни.", true);
    return;
  }
  setStructuralActionsBusy(true);
  try {
    await deleteParagraph(documentId, selectedParagraph);
    saveQueue.cancel(paragraphKey(selectedParagraph));
    elements.deleteDialog.close();
    selectedParagraph = null;
    await reloadParagraphs();
    showToast("Абзац видалено.");
  } catch (error) {
    handleWriteError(error);
    showToast(errorMessage(error, "Не вдалося видалити абзац."), true);
  } finally {
    setStructuralActionsBusy(false);
  }
}

async function reloadParagraphs() {
  const result = await listParagraphs(documentId);
  currentDocument.paragraphs = result.paragraphs;
  renderParagraphs(result.paragraphs);
}

function openShareDialog() {
  if (currentRole !== "owner") {
    return;
  }
  elements.shareEmail.value = "";
  elements.shareRole.value = "editor";
  elements.shareEmailError.hidden = true;
  elements.shareEmailError.textContent = "";
  updateShareEmailState();
  renderShareMembers(currentMembers);
  const restricted = currentDocument.access_mode !== "link";
  elements.shareAccessTitle.textContent = restricted ? "Обмежений" : "За посиланням";
  elements.shareAccessDescription.textContent = restricted
    ? "Документ бачать лише додані учасники. Посилання саме по собі не надає доступу."
    : "За посиланням потрібна автентифікація. Після входу користувач отримує роль «Гість» — лише читання.";
  elements.shareAccessLink.textContent = location.href;
  elements.shareDialog.showModal();
  elements.shareEmail.focus();
}

function updateShareEmailState() {
  const email = elements.shareEmail.value.trim();
  const valid = email.length > 0 && elements.shareEmail.checkValidity();
  elements.shareAddButton.disabled = !valid;
  if (!valid && email.length > 0) {
    elements.shareEmailError.textContent = "Некоректна електронна пошта.";
    elements.shareEmailError.hidden = false;
  } else {
    elements.shareEmailError.hidden = true;
    elements.shareEmailError.textContent = "";
  }
}

async function addMember(event) {
  event.preventDefault();
  const email = elements.shareEmail.value.trim();
  if (!email || !elements.shareEmail.checkValidity()) {
    updateShareEmailState();
    return;
  }
  elements.shareAddButton.disabled = true;
  elements.shareAddButton.classList.add("button--loading");
  elements.shareEmailError.hidden = true;
  try {
    const member = await shareDocument(documentId, email, elements.shareRole.value);
    const index = currentMembers.findIndex((item) => item.user_id === member.user_id);
    if (index === -1) {
      currentMembers.push(member);
    } else {
      currentMembers[index] = member;
    }
    renderShareMembers(currentMembers);
    elements.shareEmail.value = "";
    updateShareEmailState();
  } catch (error) {
    showShareEmailError(error);
  } finally {
    elements.shareAddButton.classList.remove("button--loading");
    updateShareEmailState();
  }
}

async function changeMemberRole(event) {
  const select = event.target.closest("[data-member-role]");
  if (!select) {
    return;
  }
  const memberId = select.dataset.memberRole;
  const member = currentMembers.find((item) => item.user_id === memberId);
  if (!member) {
    return;
  }
  select.disabled = true;
  try {
    const updated = await shareDocument(documentId, member.email, select.value);
    const index = currentMembers.findIndex((item) => item.user_id === memberId);
    if (index !== -1) {
      currentMembers[index] = updated;
    }
    renderShareMembers(currentMembers);
    showToast("Роль учасника змінено.");
  } catch (error) {
    select.value = member.role;
    if (error instanceof ApiError) {
      showToast(accessErrorMessage(error), true);
    } else {
      showToast("Не вдалося змінити роль учасника.", true);
    }
  } finally {
    select.disabled = false;
  }
}

async function revokeMember(event) {
  const button = event.target.closest("[data-revoke-member]");
  if (!button) {
    return;
  }
  button.disabled = true;
  try {
    await revokeAccess(documentId, button.dataset.revokeMember);
    currentMembers = currentMembers.filter(
      (item) => item.user_id !== button.dataset.revokeMember,
    );
    renderShareMembers(currentMembers);
    showToast("Доступ учасника відкликано.");
  } catch (error) {
    if (error instanceof ApiError) {
      showToast(accessErrorMessage(error), true);
    } else {
      showToast("Не вдалося відкликати доступ.", true);
    }
  } finally {
    button.disabled = false;
  }
}

async function copyDocumentLink() {
  try {
    await navigator.clipboard.writeText(location.href);
    showToast("Посилання скопійовано.");
  } catch {
    showToast("Не вдалося скопіювати посилання.", true);
  }
}

function renderShareMembers(members) {
  elements.shareMembersCount.textContent = String(members?.length ?? 0);
  const fragment = document.createDocumentFragment();
  for (const member of members ?? []) {
    const row = document.createElement("div");
    row.className = "share-member";

    const avatar = document.createElement("span");
    const role = ["owner", "editor", "guest"].includes(member.role)
      ? member.role
      : "unknown";
    avatar.className = `avatar${role === "unknown" ? "" : ` avatar--${role}`}`;
    avatar.textContent = initials(member.name);
    avatar.setAttribute("aria-hidden", "true");

    const details = document.createElement("div");
    details.className = "share-member__details";
    const nameRow = document.createElement("div");
    nameRow.className = "share-member__name-row";
    const name = document.createElement("span");
    name.className = "share-member__name";
    name.textContent = member.name;
    nameRow.append(name);
    const isCurrentUser =
      member.email.toLocaleLowerCase("uk-UA") ===
      currentUserEmail?.toLocaleLowerCase("uk-UA");
    if (member.role === "owner") {
      const badge = document.createElement("span");
      badge.className = "badge badge--owner";
      badge.textContent = "Власник";
      nameRow.append(badge);
      if (isCurrentUser) {
        const you = document.createElement("span");
        you.className = "share-member__you";
        you.textContent = "· ви";
        nameRow.append(you);
      }
    }
    const email = document.createElement("span");
    email.className = "share-member__email";
    email.textContent = member.email;
    details.append(nameRow, email);

    row.append(avatar, details);
    if (member.role !== "owner") {
      const actions = document.createElement("div");
      actions.className = "share-member__actions";
      const select = document.createElement("select");
      select.className = "share-member__role";
      select.dataset.memberRole = member.user_id;
      select.setAttribute("aria-label", `Роль учасника ${member.name}`);
      for (const [value, label] of [["editor", "Редактор"], ["guest", "Гість"]]) {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = label;
        option.selected = member.role === value;
        select.append(option);
      }
      const revoke = document.createElement("button");
      revoke.className = "button button--quiet button--small share-member__revoke";
      revoke.type = "button";
      revoke.dataset.revokeMember = member.user_id;
      revoke.textContent = "Відкликати";
      actions.append(select, revoke);
      row.append(actions);
    }
    fragment.append(row);
  }
  elements.shareMembers.replaceChildren(fragment);
}

function showShareEmailError(error) {
  elements.shareEmailError.textContent =
    error instanceof ApiError
      ? accessErrorMessage(error)
      : "Не вдалося додати учасника.";
  elements.shareEmailError.hidden = false;
}

function accessErrorMessage(error) {
  if (error.status === 404) {
    return "Користувача з таким email не знайдено";
  }
  if (error.status === 409) {
    return "Роль власника змінити не можна";
  }
  return "Не вдалося виконати дію з доступом.";
}

function openTrashDialog() {
  if (currentRole !== "owner") {
    return;
  }
  elements.trashDescription.textContent =
    `«${currentDocument.title}» буде переміщено до кошика. Документ можна буде відновити.`;
  elements.actions.open = false;
  elements.trashDialog.showModal();
}

async function confirmMoveToTrash() {
  if (!(await saveQueue.flushAll())) {
    elements.trashDialog.close();
    showToast("Спершу виправте або збережіть незбережені зміни.", true);
    return;
  }
  elements.trashConfirm.disabled = true;
  elements.trashConfirm.classList.add("button--loading");
  try {
    await moveDocumentToTrash(documentId);
    location.assign("trash.html");
  } catch (error) {
    handleWriteError(error);
    elements.trashDialog.close();
    showToast(errorMessage(error, "Не вдалося перемістити документ до кошика."), true);
  } finally {
    elements.trashConfirm.disabled = false;
    elements.trashConfirm.classList.remove("button--loading");
  }
}

async function createNewDocument() {
  if (!(await saveQueue.flushAll())) {
    showToast("Спершу виправте або збережіть незбережені зміни.", true);
    return;
  }
  elements.createDocument.disabled = true;
  elements.createDocument.classList.add("button--loading");
  try {
    const created = await createDocument("", crypto.randomUUID());
    location.assign(`document.html?id=${encodeURIComponent(created.id)}`);
  } catch (error) {
    showToast(errorMessage(error, "Не вдалося створити документ."), true);
  } finally {
    elements.createDocument.disabled = false;
    elements.createDocument.classList.remove("button--loading");
  }
}

function setReadOnly(message) {
  canEdit = false;
  saveQueue.disable();
  elements.documentTitle.readOnly = true;
  elements.addParagraph.disabled = true;
  elements.trashDocument.disabled = true;
  elements.paragraphList.querySelectorAll("textarea").forEach((textarea) => {
    textarea.readOnly = true;
  });
  elements.paragraphList.querySelectorAll(".document-paragraph__controls").forEach((controls) => {
    controls.remove();
  });
  elements.readonlyMessage.textContent = message;
  elements.readonlyBanner.hidden = false;
  elements.actions.hidden = true;
  if (currentRole === "guest" || currentRole === null) {
    elements.accessDetails.textContent = "Режим читання.";
  }
}

function handleWriteError(error) {
  if (error instanceof ApiError && error.status === 403) {
    setReadOnly("Недостатньо прав для редагування. Документ відкрито лише для читання.");
  }
}

function showSaveState(state, error) {
  elements.saveStatus.classList.remove(
    "document-save-status--saved",
    "document-save-status--saving",
    "document-save-status--error",
  );
  elements.retrySave.hidden = true;
  elements.saveStatus.setAttribute("aria-busy", String(state === "saving" || state === "pending"));

  if (state === "saving") {
    elements.saveStatus.classList.add("document-save-status--saving");
    elements.saveStatusText.textContent = "Зберігаємо…";
  } else if (state === "pending") {
    elements.saveStatusText.textContent = "Зміни очікують збереження…";
  } else if (state === "error") {
    elements.saveStatus.classList.add("document-save-status--error");
    elements.saveStatusText.textContent = error instanceof ApiError
      ? `${error.message}. Повторимо через 5 секунд.`
      : "Помилка збереження. Повторимо через 5 секунд.";
    elements.retrySave.hidden = false;
  } else if (state === "validation") {
    elements.saveStatus.classList.add("document-save-status--error");
    elements.saveStatusText.textContent = "Виправте позначене поле. Зміни не збережені.";
  } else if (state === "readonly") {
    elements.saveStatusText.textContent = "Лише читання";
  } else {
    elements.saveStatus.classList.add("document-save-status--saved");
    elements.saveStatusText.textContent = "Збережено";
  }
}

function showLoadError(message) {
  elements.loading.hidden = true;
  elements.editorView.hidden = true;
  elements.errorMessage.textContent = message;
  elements.error.hidden = false;
}

function hideLoadError() {
  elements.error.hidden = true;
  elements.errorMessage.textContent = "";
}

function setLoading(isLoading) {
  elements.loading.hidden = !isLoading;
  elements.loading.setAttribute("aria-busy", String(isLoading));
}

function setStructuralActionsBusy(isBusy) {
  elements.addParagraph.disabled = isBusy || !canEdit;
  elements.paragraphList.querySelectorAll(".document-paragraph__controls button").forEach((button) => {
    button.disabled = isBusy;
  });
  elements.deleteParagraphConfirm.disabled = isBusy;
}

function showFieldError(input, errorElement, message) {
  input.classList.add("document-title-input--invalid");
  input.setAttribute("aria-invalid", "true");
  input.setAttribute("aria-describedby", "title-error");
  errorElement.textContent = message;
  errorElement.hidden = false;
}

function clearFieldError(input, errorElement) {
  input.classList.remove("document-title-input--invalid");
  input.removeAttribute("aria-invalid");
  input.removeAttribute("aria-describedby");
  errorElement.textContent = "";
  errorElement.hidden = true;
}

function showParagraphLengthError(textarea) {
  let error = textarea.parentElement.querySelector(".document-paragraph__error");
  if (!error) {
    error = document.createElement("span");
    error.id = `paragraph-length-error-${textarea.dataset.paragraphId}`;
    error.className = "document-field-error document-paragraph__error";
  }
  textarea.setAttribute("aria-describedby", `format-help ${error.id}`);
  error.textContent = `Максимум ${MAX_PARAGRAPH_LENGTH} символів.`;
  textarea.after(error);
}

function clearParagraphLengthError(textarea) {
  textarea.removeAttribute("aria-invalid");
  textarea.setAttribute("aria-describedby", "format-help");
  const error = textarea.parentElement.querySelector(".document-paragraph__error");
  error?.remove();
}

function warnAboutUnsavedChanges(event) {
  if (!saveQueue.hasPendingChanges) {
    return;
  }
  event.preventDefault();
  event.returnValue = "";
}

function parseDocumentId() {
  const value = new URLSearchParams(location.search).get("id");
  if (!value || !/^[1-9]\d*$/.test(value)) {
    return null;
  }
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) ? parsed : null;
}

function paragraphKey(id) {
  return `paragraph:${id}`;
}

function roleLabel(role) {
  const labels = new Map([
    ["owner", "Власник"],
    ["editor", "Редактор"],
    ["guest", "Гість"],
  ]);
  return labels.get(role) ?? "Невідома роль";
}

function accessModeLabel(mode) {
  const labels = new Map([
    ["restricted", "Доступ лише для запрошених учасників"],
    ["link", "Доступ за посиланням"],
  ]);
  return labels.get(mode) ?? "Режим доступу недоступний";
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

function errorMessage(error, fallback) {
  return error instanceof ApiError ? error.message : fallback;
}

/*p.s. File was created by Copilot and reviewed by Olha Bidochka*/
