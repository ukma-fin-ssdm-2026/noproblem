import {
  approveAccessRequest,
  createDocument,
  createParagraph,
  deleteParagraph,
  getDocument,
  getDocumentMembers,
  listAccessRequests,
  listMyAccessRequests,
  listParagraphs,
  moveDocumentToTrash,
  renameDocument,
  rejectAccessRequest,
  requestAccess,
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
  noAccessView: document.querySelector("#document-no-access"),
  noAccessTitle: document.querySelector("#no-access-title"),
  noAccessDescription: document.querySelector("#no-access-description"),
  noAccessStatus: document.querySelector("#no-access-status"),
  noAccessError: document.querySelector("#no-access-error"),
  accessPendingStatus: document.querySelector("#access-pending-status"),
  requestAccessButton: document.querySelector("#request-access-button"),
  retryAccessRequest: document.querySelector("#retry-access-request"),
  retryAccessState: document.querySelector("#retry-access-state"),
  openAccessDocument: document.querySelector("#open-access-document"),
  returnToDocuments: document.querySelector("#return-to-documents"),
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
  shareAddError: document.querySelector("#share-add-error"),
  shareAddErrorMessage: document.querySelector("#share-add-error-message"),
  retryShareAdd: document.querySelector("#retry-share-add"),
  shareMembersCount: document.querySelector("#share-members-count"),
  shareMembers: document.querySelector("#share-members"),
  revokeDialog: document.querySelector("#revoke-access-dialog"),
  revokeDescription: document.querySelector("#revoke-access-description"),
  revokeError: document.querySelector("#revoke-access-error"),
  revokeErrorMessage: document.querySelector("#revoke-access-error-message"),
  revokeConfirm: document.querySelector("#revoke-access-confirm"),
  shareAccessTitle: document.querySelector("#share-access-title"),
  shareAccessDescription: document.querySelector("#share-access-description"),
  shareAccessLink: document.querySelector("#share-access-link"),
  copyShareLink: document.querySelector("#copy-share-link"),
  shareTabs: document.querySelector(".share-tabs"),
  shareMembersTab: document.querySelector("#share-members-tab"),
  shareRequestsTab: document.querySelector("#share-requests-tab"),
  shareMembersPanel: document.querySelector("#share-members-panel"),
  shareRequestsPanel: document.querySelector("#share-requests-panel"),
  sharePendingCount: document.querySelector("#share-pending-count"),
  shareRequestsLoading: document.querySelector("#share-requests-loading"),
  shareRequestsError: document.querySelector("#share-requests-error"),
  shareRequestsErrorMessage: document.querySelector("#share-requests-error-message"),
  retryShareRequests: document.querySelector("#retry-share-requests"),
  shareRequestsEmpty: document.querySelector("#share-requests-empty"),
  shareRequestsList: document.querySelector("#share-requests-list"),
};

let currentDocument = null;
let currentRole = null;
let currentUserEmail = null;
let currentMembers = null;
let currentAccessRequests = [];
let currentUser = null;
let pendingRevokeUserId = null;
let revocationPending = false;
let shareAddPending = false;
let openMemberRoleMenuId = null;
const memberRoleActions = new Map();
let accessRequestsLoading = false;
let accessRequestsLoadFailed = false;
let accessRequestActionId = null;
let noAccessStatus = "requestable";
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
elements.requestAccessButton.addEventListener("click", sendAccessRequest);
elements.retryAccessRequest.addEventListener("click", sendAccessRequest);
elements.retryAccessState.addEventListener("click", refreshMyAccessState);
elements.openAccessDocument.addEventListener("click", () => {
  if (currentUser) {
    void loadDocument(currentUser);
  }
});
elements.shareTabs.addEventListener("click", switchShareTab);
elements.shareRequestsList.addEventListener("click", handleShareRequestAction);
elements.retryShareRequests.addEventListener("click", () => {
  void loadShareRequests();
});
elements.shareButton.addEventListener("click", openShareDialog);
elements.shareAddForm.addEventListener("submit", addMember);
elements.retryShareAdd.addEventListener("click", () => {
  void submitMemberShare();
});
elements.shareEmail.addEventListener("input", () => {
  clearShareAddErrors();
  updateShareEmailState();
});
elements.shareRole.addEventListener("change", () => {
  clearShareAddErrors();
  updateShareEmailState();
});
elements.shareMembers.addEventListener("click", (event) => {
  const roleMenuTrigger = event.target.closest("[data-member-role-menu]");
  if (roleMenuTrigger) {
    toggleMemberRoleMenu(roleMenuTrigger);
    return;
  }
  const roleChoice = event.target.closest("[data-member-role-choice]");
  if (roleChoice) {
    void chooseMemberRole(roleChoice.dataset.memberRoleChoice, roleChoice.dataset.role);
    return;
  }
  if (event.target.closest("[data-revoke-member]")) {
    openRevokeDialog(event);
    return;
  }
  retryMemberRole(event);
});
elements.shareMembers.addEventListener("keydown", handleMemberRoleMenuKeydown);
document.addEventListener("click", (event) => {
  if (!event.target.closest("[data-member-role-menu], [data-member-role-choice]")) {
    const menu = openMemberRoleMenuId === null
      ? null
      : [...elements.shareMembers.querySelectorAll("[data-member-role-menu-container]")]
        .find((item) => item.dataset.memberRoleMenuContainer === openMemberRoleMenuId);
    closeMemberRoleMenu(Boolean(menu?.contains(document.activeElement)));
  }
});
elements.revokeConfirm.addEventListener("click", confirmRevokeAccess);
elements.revokeDialog.addEventListener("click", (event) => {
  if (event.target === elements.revokeDialog && !revocationPending) {
    elements.revokeDialog.close();
  }
});
elements.revokeDialog.addEventListener("cancel", (event) => {
  if (revocationPending) {
    event.preventDefault();
  }
});
elements.revokeDialog.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !revocationPending) {
    event.preventDefault();
    elements.revokeDialog.close();
  }
});
elements.revokeDialog.addEventListener("close", () => {
  if (!revocationPending) {
    pendingRevokeUserId = null;
    elements.revokeError.hidden = true;
    elements.revokeConfirm.textContent = "Відкликати доступ";
  }
});
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
    currentUser = user;
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
  elements.noAccessView.hidden = true;
  try {
    const documentInfo = await getDocument(documentId);
    const [paragraphResponse, access] = await Promise.all([
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
    if (error instanceof ApiError && error.status === 403) {
      await loadMyAccessState();
    } else {
      showLoadError(errorMessage(error, "Не вдалося завантажити документ."));
    }
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

async function loadMyAccessState() {
  try {
    const response = await listMyAccessRequests(documentId);
    const ownAccessRequests = response.requests.filter(
      (request) => request.request_type === "access",
    );
    const latestRequest = ownAccessRequests.reduce(
      (latest, request) =>
        !latest || request.created_at > latest.created_at ? request : latest,
      null,
    );
    if (!latestRequest) {
      renderNoAccessState("requestable");
    } else if (latestRequest.status === "pending") {
      renderNoAccessState("pending");
    } else if (latestRequest.status === "rejected") {
      renderNoAccessState("rejected");
    } else if (latestRequest.status === "approved") {
      renderNoAccessState("granted");
    } else {
      renderNoAccessState("status-error");
    }
    return noAccessStatus;
  } catch (error) {
    renderNoAccessState("status-error");
    showNoAccessError(noAccessStateErrorMessage(error));
    return noAccessStatus;
  }
}

function renderNoAccessState(state) {
  noAccessStatus = state;
  elements.loading.hidden = true;
  elements.editorView.hidden = true;
  elements.error.hidden = true;
  elements.noAccessView.hidden = false;
  elements.noAccessStatus.hidden = true;
  elements.noAccessError.hidden = true;
  elements.accessPendingStatus.hidden = true;
  elements.requestAccessButton.hidden = true;
  elements.retryAccessRequest.hidden = true;
  elements.retryAccessState.hidden = true;
  elements.openAccessDocument.hidden = true;
  elements.returnToDocuments.hidden = true;

  const states = {
    requestable: {
      title: "Немає доступу до документа",
      description: "Цей документ доступний лише користувачам із відповідним дозволом. Надішліть власнику запит на доступ.",
      action: elements.requestAccessButton,
    },
    pending: {
      title: "Запит очікує рішення",
      description: "Власник розгляне ваш запит на доступ до документа.",
      status: "Запит надіслано. Очікуємо рішення власника.",
      pending: true,
    },
    rejected: {
      title: "Запит відхилено",
      description: "Власник відхилив запит на доступ до документа. Зверніться до власника, щоб уточнити причину.",
      action: elements.returnToDocuments,
    },
    "send-error": {
      title: "Не вдалося надіслати запит",
      description: "Запит на доступ не надіслано. Спробуйте ще раз.",
      action: elements.retryAccessRequest,
    },
    "status-error": {
      title: "Не вдалося перевірити стан запиту",
      description: "Стан запиту тимчасово недоступний. Спробуйте ще раз.",
      action: elements.retryAccessState,
    },
    granted: {
      title: "Доступ уже надано",
      description: "Спробуйте відкрити документ ще раз.",
      action: elements.openAccessDocument,
    },
  };
  const viewState = states[state] ?? states["status-error"];
  elements.noAccessTitle.textContent = viewState.title;
  elements.noAccessDescription.textContent = viewState.description;
  if (viewState.status) {
    elements.noAccessStatus.textContent = viewState.status;
    elements.noAccessStatus.hidden = false;
  }
  if (viewState.pending) {
    elements.accessPendingStatus.hidden = false;
  }
  if (viewState.action) {
    viewState.action.hidden = false;
  }
}

async function refreshMyAccessState() {
  elements.retryAccessState.disabled = true;
  elements.retryAccessState.classList.add("button--loading");
  elements.noAccessView.setAttribute("aria-busy", "true");
  try {
    await loadMyAccessState();
  } finally {
    elements.noAccessView.removeAttribute("aria-busy");
    elements.retryAccessState.disabled = false;
    elements.retryAccessState.classList.remove("button--loading");
  }
}

async function sendAccessRequest() {
  if (!currentUser) {
    return;
  }
  const buttons = [elements.requestAccessButton, elements.retryAccessRequest];
  buttons.forEach((button) => {
    button.disabled = true;
    button.classList.add("button--loading");
  });
  elements.noAccessView.setAttribute("aria-busy", "true");
  elements.noAccessError.hidden = true;
  try {
    await requestAccess(documentId);
    renderNoAccessState("pending");
    showToast("Запит успішно надіслано. Очікуємо рішення власника.");
  } catch (error) {
    if (error instanceof ApiError && error.status === 409) {
      const state = await loadMyAccessState();
      if (state === "requestable" || state === "rejected") {
        renderNoAccessState("granted");
      }
      showNoAccessError("Запит уже очікує розгляду або доступ уже є");
    } else {
      renderNoAccessState("send-error");
      showNoAccessError(
        error instanceof ApiError && error.status === 403
          ? "Немає прав на надсилання запиту. Перевірте доступ до документа."
          : "Не вдалося надіслати запит. Спробуйте ще раз.",
      );
    }
  } finally {
    elements.noAccessView.removeAttribute("aria-busy");
    buttons.forEach((button) => {
      button.disabled = false;
      button.classList.remove("button--loading");
    });
  }
}

function showNoAccessError(message) {
  elements.noAccessError.textContent = message;
  elements.noAccessError.hidden = false;
}

function noAccessStateErrorMessage(error) {
  if (error instanceof ApiError && error.status === 404) {
    return "Документ не знайдено.";
  }
  return "Не вдалося перевірити стан запиту. Спробуйте ще раз.";
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
  clearShareAddErrors();
  updateShareEmailState();
  renderShareMembers(currentMembers);
  activateShareTab("members");
  const restricted = currentDocument.access_mode !== "link";
  elements.shareAccessTitle.textContent = restricted ? "Обмежений" : "За посиланням";
  elements.shareAccessDescription.textContent = restricted
    ? "Документ бачать лише додані учасники. Посилання саме по собі не надає доступу."
    : "За посиланням потрібна автентифікація. Після входу користувач отримує роль «Гість» — лише читання.";
  elements.shareAccessLink.textContent = location.href;
  elements.shareDialog.showModal();
  elements.shareEmail.focus();
  void loadShareRequests();
}

function switchShareTab(event) {
  const tab = event.target.closest("[data-share-tab]");
  if (!tab) {
    return;
  }
  activateShareTab(tab.dataset.shareTab);
}

function activateShareTab(selectedTab) {
  const isMembersSelected = selectedTab === "members";
  elements.shareMembersTab.setAttribute("aria-selected", String(isMembersSelected));
  elements.shareRequestsTab.setAttribute("aria-selected", String(!isMembersSelected));
  elements.shareMembersPanel.hidden = !isMembersSelected;
  elements.shareRequestsPanel.hidden = isMembersSelected;
}

async function loadShareRequests() {
  accessRequestsLoading = true;
  accessRequestsLoadFailed = false;
  elements.sharePendingCount.textContent = "…";
  elements.shareRequestsLoading.hidden = false;
  elements.shareRequestsLoading.setAttribute("aria-busy", "true");
  elements.shareRequestsError.hidden = true;
  try {
    await refreshShareRequests();
  } catch (error) {
    accessRequestsLoadFailed = true;
    elements.sharePendingCount.textContent = "—";
    showShareRequestsError(accessRequestsErrorMessage(error));
  } finally {
    accessRequestsLoading = false;
    elements.shareRequestsLoading.hidden = true;
    elements.shareRequestsLoading.setAttribute("aria-busy", "false");
    renderShareRequests(currentAccessRequests);
  }
}

async function refreshShareRequests() {
  const response = await listAccessRequests(documentId);
  currentAccessRequests = response.requests;
  accessRequestsLoadFailed = false;
  elements.shareRequestsError.hidden = true;
  renderShareRequests(currentAccessRequests);
}

function renderShareRequests(requests) {
  const pendingCount = requests.filter((request) => request.status === "pending").length;
  elements.sharePendingCount.textContent = accessRequestsLoadFailed ? "—" : String(pendingCount);
  elements.shareRequestsEmpty.hidden =
    requests.length !== 0 || accessRequestsLoadFailed || accessRequestsLoading;
  const fragment = document.createDocumentFragment();
  for (const request of requests) {
    fragment.append(createShareRequestElement(request));
  }
  elements.shareRequestsList.replaceChildren(fragment);
}

function createShareRequestElement(request) {
  const article = document.createElement("article");
  article.className = "share-request";
  article.setAttribute("aria-busy", String(accessRequestActionId === request.id));

  const content = document.createElement("div");
  content.className = "share-request__content";
  const title = document.createElement("h4");
  title.className = "share-request__title";
  title.textContent =
    request.request_type === "role"
      ? `Запит на роль ${roleLabel(request.requested_role)}`
      : "Запит на доступ до документа";
  const requester = document.createElement("p");
  requester.className = "share-request__requester";
  requester.textContent = `Ідентифікатор користувача: ${request.requester_id}`;
  const created = document.createElement("p");
  created.className = "share-request__date";
  created.textContent = `Надіслано: ${formatAccessRequestDate(request.created_at)}`;
  content.append(title, requester, created);

  const actions = document.createElement("div");
  actions.className = "share-request__actions";
  if (request.status === "pending") {
    actions.append(
      createAccessRequestAction(request.id, "approve", "Підтвердити", "button button--primary button--small"),
      createAccessRequestAction(request.id, "reject", "Відхилити", "button button--secondary button--small"),
    );
  } else {
    const status = document.createElement("span");
    status.className = "badge";
    status.textContent = requestStatusLabel(request.status);
    actions.append(status);
  }
  article.append(content, actions);
  return article;
}

function createAccessRequestAction(requestId, action, label, className) {
  const button = document.createElement("button");
  button.className = className;
  button.type = "button";
  button.dataset.shareRequestAction = action;
  button.dataset.requestId = requestId;
  button.textContent = label;
  button.disabled = accessRequestsLoading || accessRequestActionId !== null;
  if (accessRequestActionId === requestId) {
    button.classList.add("button--loading");
  }
  return button;
}

async function handleShareRequestAction(event) {
  const button = event.target.closest("[data-share-request-action]");
  if (!button || accessRequestActionId !== null) {
    return;
  }
  const { requestId, shareRequestAction: action } = button.dataset;
  const accessRequest = currentAccessRequests.find((request) => request.id === requestId);
  accessRequestActionId = requestId;
  elements.shareRequestsError.hidden = true;
  renderShareRequests(currentAccessRequests);
  try {
    if (action === "approve") {
      await approveAccessRequest(documentId, requestId);
      const [requestsResponse, membersResponse] = await Promise.all([
        listAccessRequests(documentId),
        getDocumentMembers(documentId),
      ]);
      currentAccessRequests = requestsResponse.requests;
      currentMembers = [...membersResponse.members];
      renderMembers(currentMembers);
      renderShareMembers(currentMembers);
      renderShareRequests(currentAccessRequests);
      showToast(
        accessRequest?.request_type === "role"
          ? "Запит підтверджено. Роль редактора надано."
          : "Запит підтверджено. Доступ надано.",
      );
    } else {
      await rejectAccessRequest(documentId, requestId);
      await refreshShareRequests();
      showToast("Запит відхилено.");
    }
  } catch (error) {
    if (error instanceof ApiError && error.status === 409) {
      try {
        await refreshShareRequests();
      } catch (refreshError) {
        showShareRequestsError(accessRequestsErrorMessage(refreshError));
        return;
      }
    }
    showShareRequestsError(accessRequestActionErrorMessage(error, action));
  } finally {
    accessRequestActionId = null;
    renderShareRequests(currentAccessRequests);
  }
}

function accessRequestsErrorMessage(error) {
  if (error instanceof ApiError && error.status === 403) {
    return "Керувати запитами може лише власник";
  }
  if (error instanceof ApiError && error.status === 404) {
    return "Документ або запити не знайдено.";
  }
  return "Не вдалося завантажити запити. Спробуйте ще раз.";
}

function accessRequestActionErrorMessage(error, action) {
  if (error instanceof ApiError && error.status === 403) {
    return "Керувати запитами може лише власник";
  }
  if (error instanceof ApiError && error.status === 409) {
    return "Запит уже розглянуто";
  }
  if (error instanceof ApiError && error.status === 404) {
    return "Запит не знайдено.";
  }
  return action === "approve"
    ? "Не вдалося підтвердити запит. Спробуйте ще раз."
    : "Не вдалося відхилити запит. Спробуйте ще раз.";
}

function showShareRequestsError(message) {
  elements.shareRequestsErrorMessage.textContent = message;
  elements.shareRequestsError.hidden = false;
}

function formatAccessRequestDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Дата невідома";
  }
  return new Intl.DateTimeFormat("uk-UA", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function requestStatusLabel(status) {
  const labels = new Map([
    ["pending", "Очікує рішення"],
    ["approved", "Підтверджено"],
    ["rejected", "Відхилено"],
  ]);
  return labels.get(status) ?? "Невідомий стан";
}

function updateShareEmailState() {
  const email = elements.shareEmail.value.trim();
  const valid = email.length > 0 && elements.shareEmail.checkValidity();
  elements.shareAddButton.disabled = !valid || shareAddPending;
  elements.shareEmail.setAttribute("aria-invalid", String(email.length > 0 && !valid));
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
  await submitMemberShare();
}

async function submitMemberShare() {
  const email = elements.shareEmail.value.trim();
  if (shareAddPending) {
    return;
  }
  if (!email || !elements.shareEmail.checkValidity()) {
    updateShareEmailState();
    elements.shareEmail.focus();
    return;
  }
  shareAddPending = true;
  clearShareAddErrors();
  elements.shareAddForm.setAttribute("aria-busy", "true");
  elements.shareEmail.disabled = true;
  elements.shareRole.disabled = true;
  elements.shareAddButton.disabled = true;
  elements.shareAddButton.classList.add("button--loading");
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
    clearShareAddErrors();
  } catch (error) {
    showShareEmailError(error);
  } finally {
    shareAddPending = false;
    elements.shareAddForm.removeAttribute("aria-busy");
    elements.shareEmail.disabled = false;
    elements.shareRole.disabled = false;
    elements.shareAddButton.classList.remove("button--loading");
    updateShareEmailState();
  }
}

function toggleMemberRoleMenu(trigger) {
  const memberId = trigger.dataset.memberRoleMenu;
  if (openMemberRoleMenuId === memberId) {
    closeMemberRoleMenu();
    return;
  }
  openMemberRoleMenu(memberId);
}

function openMemberRoleMenu(memberId, direction = 0) {
  const member = currentMembers.find((item) => item.user_id === memberId);
  const action = memberRoleActions.get(memberId);
  if (!member || action?.status === "loading") {
    return;
  }
  closeMemberRoleMenu();
  const trigger = [...elements.shareMembers.querySelectorAll("[data-member-role-menu]")]
    .find((item) => item.dataset.memberRoleMenu === memberId);
  const menu = [...elements.shareMembers.querySelectorAll("[data-member-role-menu-container]")]
    .find((item) => item.dataset.memberRoleMenuContainer === memberId);
  if (!trigger || !menu) {
    return;
  }
  openMemberRoleMenuId = memberId;
  trigger.setAttribute("aria-expanded", "true");
  menu.hidden = false;
  const options = [...menu.querySelectorAll("[data-member-role-choice]")];
  const currentIndex = options.findIndex((option) => option.dataset.role === member.role);
  const focusIndex = direction === 0
    ? Math.max(currentIndex, 0)
    : (Math.max(currentIndex, 0) + direction + options.length) % options.length;
  options[focusIndex]?.focus();
}

function closeMemberRoleMenu(restoreFocus = false) {
  if (openMemberRoleMenuId === null) {
    return;
  }
  const memberId = openMemberRoleMenuId;
  const trigger = [...elements.shareMembers.querySelectorAll("[data-member-role-menu]")]
    .find((item) => item.dataset.memberRoleMenu === memberId);
  const menu = [...elements.shareMembers.querySelectorAll("[data-member-role-menu-container]")]
    .find((item) => item.dataset.memberRoleMenuContainer === memberId);
  openMemberRoleMenuId = null;
  trigger?.setAttribute("aria-expanded", "false");
  if (menu) {
    menu.hidden = true;
  }
  if (restoreFocus && trigger && !trigger.disabled) {
    trigger.focus();
  }
}

function handleMemberRoleMenuKeydown(event) {
  const trigger = event.target.closest("[data-member-role-menu]");
  if (trigger) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      openMemberRoleMenu(
        trigger.dataset.memberRoleMenu,
        event.key === "ArrowDown" ? 1 : -1,
      );
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openMemberRoleMenu(trigger.dataset.memberRoleMenu);
    }
    return;
  }

  const option = event.target.closest("[data-member-role-choice]");
  if (!option) {
    return;
  }
  const memberId = option.dataset.memberRoleChoice;
  if (event.key === "Escape") {
    event.preventDefault();
    closeMemberRoleMenu(true);
  } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault();
    const options = [...option.parentElement.querySelectorAll("[data-member-role-choice]")];
    const currentIndex = options.indexOf(option);
    const direction = event.key === "ArrowDown" ? 1 : -1;
    options[(currentIndex + direction + options.length) % options.length]?.focus();
  } else if (event.key === "Home" || event.key === "End") {
    event.preventDefault();
    const options = [...option.parentElement.querySelectorAll("[data-member-role-choice]")];
    options[event.key === "Home" ? 0 : options.length - 1]?.focus();
  } else if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    void chooseMemberRole(memberId, option.dataset.role);
  } else if (event.key === "Tab") {
    event.preventDefault();
    const row = option.closest(".share-member");
    const nextFocus = event.shiftKey
      ? row?.querySelector("[data-member-role-menu]")
      : row?.querySelector("[data-revoke-member]");
    closeMemberRoleMenu();
    nextFocus?.focus();
  }
}

async function chooseMemberRole(memberId, role) {
  closeMemberRoleMenu();
  const member = currentMembers.find((item) => item.user_id === memberId);
  if (member && member.role !== role) {
    await updateMemberRole(memberId, role);
  }
  const trigger = [...elements.shareMembers.querySelectorAll("[data-member-role-menu]")]
    .find((item) => item.dataset.memberRoleMenu === memberId);
  trigger?.focus();
}

async function updateMemberRole(memberId, role) {
  if (currentRole !== "owner" || memberRoleActions.get(memberId)?.status === "loading") {
    return;
  }
  const member = currentMembers.find((item) => item.user_id === memberId);
  if (!member) {
    return;
  }
  memberRoleActions.set(memberId, { role, status: "loading" });
  renderShareMembers(currentMembers);
  try {
    const updated = await shareDocument(documentId, member.email, role);
    const index = currentMembers.findIndex((item) => item.user_id === memberId);
    if (index !== -1) {
      currentMembers[index] = updated;
    }
    memberRoleActions.delete(memberId);
    renderShareMembers(currentMembers);
    showToast("Роль учасника змінено.");
  } catch (error) {
    memberRoleActions.set(memberId, {
      role,
      status: "error",
      message: memberRoleErrorMessage(error),
    });
    renderShareMembers(currentMembers);
  }
}

function retryMemberRole(event) {
  const button = event.target.closest("[data-retry-member-role]");
  if (!button) {
    return;
  }
  void chooseMemberRole(button.dataset.retryMemberRole, button.dataset.role);
}

function openRevokeDialog(event) {
  const button = event.target.closest("[data-revoke-member]");
  if (!button || currentRole !== "owner") {
    return;
  }
  const memberId = button.dataset.revokeMember;
  const member = currentMembers.find((item) => item.user_id === memberId);
  if (!member || member.role === "owner") {
    return;
  }
  pendingRevokeUserId = memberId;
  elements.revokeDescription.textContent =
    `Доступ до документа для «${member.name}» буде відкликано.`;
  elements.revokeError.hidden = true;
  elements.revokeErrorMessage.textContent = "";
  elements.revokeConfirm.textContent = "Відкликати доступ";
  elements.revokeConfirm.disabled = false;
  elements.revokeDialog.showModal();
  elements.revokeDialog
    .querySelector("[data-dialog-close='revoke-access-dialog']")
    .focus();
}

async function confirmRevokeAccess() {
  const memberId = pendingRevokeUserId;
  if (!memberId || currentRole !== "owner" || revocationPending) {
    return;
  }
  revocationPending = true;
  elements.revokeDialog.setAttribute("aria-busy", "true");
  elements.revokeError.hidden = true;
  elements.revokeConfirm.disabled = true;
  elements.revokeConfirm.classList.add("button--loading");
  elements.revokeConfirm.textContent = "Відкликаємо…";
  elements.revokeDialog
    .querySelector("[data-dialog-close='revoke-access-dialog']")
    .disabled = true;
  try {
    await revokeAccess(documentId, memberId);
    currentMembers = currentMembers.filter(
      (item) => item.user_id !== memberId,
    );
    memberRoleActions.delete(memberId);
    renderShareMembers(currentMembers);
    pendingRevokeUserId = null;
    elements.revokeDialog.close();
    showToast("Доступ учасника відкликано.");
  } catch (error) {
    elements.revokeErrorMessage.textContent = revokeErrorMessage(error);
    elements.revokeError.hidden = false;
    elements.revokeConfirm.textContent = "Повторити";
  } finally {
    revocationPending = false;
    elements.revokeDialog.removeAttribute("aria-busy");
    elements.revokeConfirm.disabled = false;
    elements.revokeConfirm.classList.remove("button--loading");
    elements.revokeDialog
      .querySelector("[data-dialog-close='revoke-access-dialog']")
      .disabled = false;
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
  closeMemberRoleMenu();
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
      const roleAction = memberRoleActions.get(member.user_id);
      actions.setAttribute("aria-busy", String(roleAction?.status === "loading"));
      const roleMenuId = `share-role-menu-${member.user_id}`;
      const roleControl = document.createElement("div");
      roleControl.className = "share-member__role-control";
      const trigger = document.createElement("button");
      trigger.className = "share-member__role";
      trigger.type = "button";
      trigger.dataset.memberRoleMenu = member.user_id;
      trigger.setAttribute("aria-haspopup", "menu");
      trigger.setAttribute("aria-expanded", "false");
      trigger.setAttribute("aria-controls", roleMenuId);
      trigger.setAttribute("aria-label", `Змінити роль учасника ${member.name}`);
      trigger.disabled = roleAction?.status === "loading";
      const roleLabelText = document.createElement("span");
      roleLabelText.textContent = roleLabel(member.role);
      const chevron = document.createElement("img");
      chevron.src = "assets/icon-chevron-down.svg";
      chevron.width = 16;
      chevron.height = 16;
      chevron.alt = "";
      trigger.append(roleLabelText, chevron);

      const menu = document.createElement("div");
      menu.className = "share-member__role-menu";
      menu.id = roleMenuId;
      menu.dataset.memberRoleMenuContainer = member.user_id;
      menu.setAttribute("role", "menu");
      menu.setAttribute("aria-label", `Роль учасника ${member.name}`);
      menu.hidden = true;
      for (const [value, label] of [["editor", "Редактор"], ["guest", "Гість"]]) {
        const option = document.createElement("button");
        option.className = "share-member__role-option";
        option.type = "button";
        option.setAttribute("role", "menuitemradio");
        option.setAttribute("aria-checked", String(member.role === value));
        option.dataset.memberRoleChoice = member.user_id;
        option.dataset.role = value;
        option.textContent = label;
        menu.append(option);
      }
      const revoke = document.createElement("button");
      revoke.className = "button button--quiet button--small share-member__revoke";
      revoke.type = "button";
      revoke.dataset.revokeMember = member.user_id;
      revoke.textContent = "Відкликати";
      revoke.disabled = roleAction?.status === "loading";
      roleControl.append(trigger, menu);
      actions.append(roleControl, revoke);
      if (roleAction?.status === "loading") {
        const status = document.createElement("span");
        status.className = "share-member__status";
        status.setAttribute("role", "status");
        const spinner = document.createElement("span");
        spinner.className = "spinner";
        spinner.setAttribute("aria-hidden", "true");
        status.append(spinner, document.createTextNode("Зберігаємо роль…"));
        actions.append(status);
      } else if (roleAction?.status === "error") {
        const error = document.createElement("span");
        error.className = "share-member__error";
        error.setAttribute("role", "alert");
        error.textContent = roleAction.message;
        const retry = document.createElement("button");
        retry.className = "button button--secondary button--small";
        retry.type = "button";
        retry.dataset.retryMemberRole = member.user_id;
        retry.dataset.role = roleAction.role;
        retry.textContent = "Повторити";
        actions.append(error, retry);
      }
      row.append(actions);
    }
    fragment.append(row);
  }
  elements.shareMembers.replaceChildren(fragment);
}

function showShareEmailError(error) {
  if (error instanceof ApiError && [404, 409].includes(error.status)) {
    elements.shareEmailError.textContent = accessErrorMessage(error);
    elements.shareEmailError.hidden = false;
    return;
  }
  elements.shareAddErrorMessage.textContent = accessErrorMessage(error);
  elements.shareAddError.hidden = false;
}

function clearShareAddErrors() {
  elements.shareEmailError.hidden = true;
  elements.shareEmailError.textContent = "";
  elements.shareAddError.hidden = true;
  elements.shareAddErrorMessage.textContent = "";
}

function accessErrorMessage(error) {
  if (error.status === 404) {
    return "Користувача з таким email не знайдено";
  }
  if (error.status === 409) {
    return "Роль власника змінити не можна";
  }
  if (error.status === 403) {
    return "Керувати доступом може лише власник";
  }
  return "Не вдалося виконати дію з доступом.";
}

function memberRoleErrorMessage(error) {
  if (error instanceof ApiError && error.status === 404) {
    return "Учасника не знайдено або його доступ уже змінено.";
  }
  if (error instanceof ApiError && error.status === 409) {
    return "Роль власника змінити не можна";
  }
  if (error instanceof ApiError && error.status === 403) {
    return "Керувати доступом може лише власник";
  }
  return "Не вдалося змінити роль. Спробуйте ще раз.";
}

function revokeErrorMessage(error) {
  if (error instanceof ApiError && error.status === 403) {
    return "Керувати доступом може лише власник";
  }
  if (error instanceof ApiError && error.status === 404) {
    return "Учасника не знайдено або його доступ уже відкликано.";
  }
  if (error instanceof ApiError && error.status === 409) {
    return "Відкликати доступ власника не можна";
  }
  return "Не вдалося відкликати доступ. Спробуйте ще раз.";
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
  elements.noAccessView.hidden = true;
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
