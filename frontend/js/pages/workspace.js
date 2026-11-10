import {
  createDocument,
  listDocuments,
  moveDocumentToTrash,
  renameDocument,
  searchDocuments,
} from "../api/documents.js";
import { ApiError } from "../api/client.js";
import { createDocumentRow } from "../core/document-list.js";
import { requireAuthenticatedUser } from "../core/guard.js";
import { setProfile, setupLogout, showToast } from "../core/app-shell.js";

const DEBOUNCE_MS = 300;
const SEARCH_MIN_LENGTH = 2;
const initialSearchQuery = new URLSearchParams(location.search).get("q");

const elements = {
  create: document.querySelector("#create-document"),
  count: document.querySelector("#document-count"),
  empty: document.querySelector("#documents-empty"),
  list: document.querySelector("#documents-list"),
  loading: document.querySelector("#documents-loading"),
  loadMore: document.querySelector("#load-more"),
  error: document.querySelector("#page-error"),
  errorMessage: document.querySelector("#page-error-message"),
  retry: document.querySelector("#page-retry"),
  search: document.querySelector("#document-search"),
  clearSearch: document.querySelector("#search-clear"),
  documentView: document.querySelector("#document-view"),
  searchView: document.querySelector("#search-view"),
  searchHint: document.querySelector("#search-hint"),
  searchResults: document.querySelector("#search-results"),
  searchEmpty: document.querySelector("#search-empty"),
  searchLoading: document.querySelector("#search-loading"),
  searchStart: document.querySelector("#search-start"),
  renameDialog: document.querySelector("#rename-dialog"),
  renameForm: document.querySelector("#rename-form"),
  renameInput: document.querySelector("#rename-title-input"),
  renameError: document.querySelector("#rename-error"),
  renameSubmit: document.querySelector("#rename-submit"),
  trashDialog: document.querySelector("#trash-dialog"),
  trashDescription: document.querySelector("#trash-dialog-description"),
  trashConfirm: document.querySelector("#trash-confirm"),
};

let currentOffset = 0;
let totalDocuments = 0;
let hasMoreDocuments = false;
let selectedDocument = null;
let pendingSearchTimer = null;
let currentSearchController = null;
let retryAction = loadFirstPage;

elements.create.addEventListener("click", handleCreate);
document.querySelector("#empty-create-document").addEventListener("click", handleCreate);
elements.loadMore.addEventListener("click", loadNextPage);
elements.retry.addEventListener("click", () => retryAction());
elements.clearSearch.addEventListener("click", clearSearch);
elements.search.addEventListener("input", onSearchInput);
elements.search.addEventListener("focus", onSearchInput);
elements.search.addEventListener("blur", onSearchBlur);
elements.renameForm.addEventListener("submit", handleRename);
elements.renameInput.addEventListener("input", clearRenameError);
elements.trashConfirm.addEventListener("click", confirmMoveToTrash);
document.querySelectorAll("[data-dialog-close]").forEach((button) => {
  button.addEventListener("click", () => {
    document.getElementById(button.dataset.dialogClose).close();
  });
});

initialize();

async function initialize() {
  hidePageError();
  try {
    const user = await requireAuthenticatedUser();
    if (!user) {
      return;
    }
    setProfile(user);
    setupLogout((message) => showToast(message, true));
    await loadFirstPage();
    if (initialSearchQuery) {
      elements.search.value = initialSearchQuery;
      onSearchInput();
    }
  } catch (error) {
    showPageError(errorMessage(error, "Не вдалося завантажити робочий простір."));
    retryAction = initialize;
  }
}

async function handleCreate() {
  resetSearchToDocuments();
  setCreateBusy(true);
  hidePageError();
  try {
    await createDocument("", crypto.randomUUID());
    await loadFirstPage();
    showToast("Документ створено.");
  } catch (error) {
    showToast(errorMessage(error, "Не вдалося створити документ."), true);
  } finally {
    setCreateBusy(false);
  }
}

async function loadFirstPage() {
  hidePageError();
  setListLoading(true);
  elements.list.replaceChildren();
  elements.empty.hidden = true;
  elements.loadMore.hidden = true;
  try {
    const page = await listDocuments({ offset: 0 });
    currentOffset = page.pagination.offset + page.documents.length;
    totalDocuments = page.pagination.total;
    hasMoreDocuments = page.pagination.has_more;
    renderDocuments(page.documents, false);
    elements.count.textContent = countLabel(totalDocuments);
    elements.empty.hidden = totalDocuments !== 0;
    elements.loadMore.hidden = !hasMoreDocuments;
    retryAction = loadFirstPage;
  } catch (error) {
    showPageError(errorMessage(error, "Не вдалося завантажити документи."));
    retryAction = loadFirstPage;
  } finally {
    setListLoading(false);
  }
}

async function loadNextPage() {
  if (!hasMoreDocuments) {
    return;
  }
  elements.loadMore.disabled = true;
  elements.loadMore.classList.add("button--loading");
  hidePageError();
  try {
    const page = await listDocuments({ offset: currentOffset });
    currentOffset = page.pagination.offset + page.documents.length;
    totalDocuments = page.pagination.total;
    hasMoreDocuments = page.pagination.has_more;
    renderDocuments(page.documents, true);
    elements.count.textContent = countLabel(totalDocuments);
    elements.loadMore.hidden = !hasMoreDocuments;
  } catch (error) {
    showPageError(errorMessage(error, "Не вдалося завантажити наступну сторінку."));
    retryAction = loadNextPage;
  } finally {
    elements.loadMore.disabled = false;
    elements.loadMore.classList.remove("button--loading");
  }
}

function renderDocuments(documents, append) {
  const fragment = document.createDocumentFragment();
  for (const documentInfo of documents) {
    fragment.append(
      createDocumentRow(documentInfo, "active", {
        onRename: openRenameDialog,
        onTrash: openTrashDialog,
      }),
    );
  }
  if (append) {
    elements.list.append(fragment);
  } else {
    elements.list.replaceChildren(fragment);
  }
}

function openRenameDialog(documentInfo) {
  selectedDocument = documentInfo;
  elements.renameInput.value = documentInfo.title;
  clearRenameError();
  elements.renameDialog.showModal();
  elements.renameInput.focus();
  elements.renameInput.select();
}

async function handleRename(event) {
  event.preventDefault();
  const title = elements.renameInput.value.trim();
  if (!title || title.length > 100) {
    showRenameError("Назва має містити від 1 до 100 символів.");
    return;
  }
  if (!selectedDocument) {
    return;
  }
  setRenameBusy(true);
  try {
    await renameDocument(selectedDocument.id, title);
    elements.renameDialog.close();
    await loadFirstPage();
    showToast("Назву документа змінено.");
  } catch (error) {
    showRenameError(errorMessage(error, "Не вдалося перейменувати документ."));
  } finally {
    setRenameBusy(false);
  }
}

function openTrashDialog(documentInfo) {
  selectedDocument = documentInfo;
  elements.trashDescription.textContent =
    `«${documentInfo.title}» буде переміщено до кошика. Його можна буде відновити.`;
  elements.trashDialog.showModal();
}

async function confirmMoveToTrash() {
  if (!selectedDocument) {
    return;
  }
  elements.trashConfirm.disabled = true;
  elements.trashConfirm.classList.add("button--loading");
  try {
    await moveDocumentToTrash(selectedDocument.id);
    elements.trashDialog.close();
    await loadFirstPage();
    showToast("Документ переміщено до кошика.");
  } catch (error) {
    elements.trashDialog.close();
    showToast(errorMessage(error, "Не вдалося перемістити документ до кошика."), true);
  } finally {
    elements.trashConfirm.disabled = false;
    elements.trashConfirm.classList.remove("button--loading");
  }
}

function onSearchInput() {
  const query = elements.search.value.trim();
  elements.clearSearch.hidden = query.length === 0;
  const searchActive = query.length > 0 || document.activeElement === elements.search;
  elements.documentView.hidden = searchActive;
  elements.searchView.hidden = !searchActive;
  elements.searchEmpty.hidden = true;
  elements.searchResults.replaceChildren();
  elements.searchLoading.hidden = true;
  elements.searchStart.hidden = true;
  elements.searchHint.textContent = "";
  hidePageError();
  clearTimeout(pendingSearchTimer);
  currentSearchController?.abort();

  if (!searchActive) {
    return;
  }
  if (query.length === 0) {
    elements.searchStart.hidden = false;
    return;
  }
  if (query.length < SEARCH_MIN_LENGTH) {
    elements.searchHint.textContent = "Введіть щонайменше два символи для пошуку.";
    return;
  }
  if (query.length > 10_000) {
    elements.searchHint.textContent = "Запит задовгий.";
    return;
  }

  elements.searchHint.textContent = "Пошук за назвою та вмістом.";
  pendingSearchTimer = window.setTimeout(() => runSearch(query), DEBOUNCE_MS);
  retryAction = () => runSearch(query);
}

function onSearchBlur() {
  window.setTimeout(() => {
    if (document.activeElement !== elements.search && !elements.search.value.trim()) {
      onSearchInput();
    }
  }, 0);
}

async function runSearch(query) {
  currentSearchController?.abort();
  const controller = new AbortController();
  currentSearchController = controller;
  elements.searchLoading.hidden = false;
  elements.searchEmpty.hidden = true;
  elements.searchResults.replaceChildren();
  try {
    const results = await searchDocuments(query, { signal: controller.signal });
    if (controller.signal.aborted || elements.search.value.trim() !== query) {
      return;
    }
    elements.searchLoading.hidden = true;
    renderSearchResults(results, query);
    elements.searchEmpty.hidden = results.length !== 0;
    elements.searchHint.textContent = results.length
      ? `Знайдено результатів: ${countLabel(results.length)}.`
      : "";
    hidePageError();
  } catch (error) {
    if (controller.signal.aborted) {
      return;
    }
    elements.searchLoading.hidden = true;
    showPageError(errorMessage(error, "Не вдалося виконати пошук."));
    retryAction = () => runSearch(query);
  }
}

function renderSearchResults(results, query) {
  const fragment = document.createDocumentFragment();
  for (const result of results) {
    const article = document.createElement("article");
    article.className = "search-result";
    const title = document.createElement("a");
    title.className = "search-result__title";
    title.href = `document.html?id=${encodeURIComponent(result.doc_id)}`;
    appendHighlightedText(title, result.title, query);
    const snippet = document.createElement("p");
    snippet.className = "search-result__snippet";
    appendHighlightedText(snippet, result.snippet, query);
    article.append(title, snippet);
    fragment.append(article);
  }
  elements.searchResults.replaceChildren(fragment);
}

function appendHighlightedText(container, text, query) {
  const pattern = new RegExp(escapeRegExp(query), "giu");
  let lastIndex = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > lastIndex) {
      container.append(document.createTextNode(text.slice(lastIndex, match.index)));
    }
    const mark = document.createElement("mark");
    mark.textContent = match[0];
    container.append(mark);
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length) {
    container.append(document.createTextNode(text.slice(lastIndex)));
  }
}

function clearSearch() {
  elements.search.value = "";
  elements.search.focus();
  onSearchInput();
}

function resetSearchToDocuments() {
  clearTimeout(pendingSearchTimer);
  currentSearchController?.abort();
  elements.search.value = "";
  elements.clearSearch.hidden = true;
  elements.searchView.hidden = true;
  elements.documentView.hidden = false;
  elements.searchHint.textContent = "";
  elements.searchResults.replaceChildren();
  elements.searchEmpty.hidden = true;
  elements.searchLoading.hidden = true;
}

function setListLoading(isLoading) {
  elements.loading.hidden = !isLoading;
  elements.loading.setAttribute("aria-busy", String(isLoading));
}

function setCreateBusy(isBusy) {
  for (const button of [elements.create, document.querySelector("#empty-create-document")]) {
    button.disabled = isBusy;
    button.classList.toggle("button--loading", isBusy);
  }
}

function setRenameBusy(isBusy) {
  elements.renameSubmit.disabled = isBusy;
  elements.renameSubmit.classList.toggle("button--loading", isBusy);
  elements.renameInput.disabled = isBusy;
}

function showRenameError(message) {
  elements.renameError.textContent = message;
  elements.renameError.hidden = false;
  elements.renameInput.classList.add("field__control--invalid");
  elements.renameInput.setAttribute("aria-invalid", "true");
  elements.renameInput.setAttribute("aria-describedby", "rename-error");
}

function clearRenameError() {
  elements.renameError.textContent = "";
  elements.renameError.hidden = true;
  elements.renameInput.classList.remove("field__control--invalid");
  elements.renameInput.removeAttribute("aria-invalid");
  elements.renameInput.removeAttribute("aria-describedby");
}

function showPageError(message) {
  elements.errorMessage.textContent = message;
  elements.error.hidden = false;
}

function hidePageError() {
  elements.error.hidden = true;
  elements.errorMessage.textContent = "";
}

function errorMessage(error, fallback) {
  return error instanceof ApiError ? error.message : fallback;
}

function countLabel(count) {
  return new Intl.NumberFormat("uk-UA").format(count);
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}


/*p.s. File was created by Copilot and reviewed by Olha Bidochka*/