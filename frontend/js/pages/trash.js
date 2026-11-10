import { listTrash, restoreDocument } from "../api/documents.js";
import { ApiError } from "../api/client.js";
import { createDocumentRow } from "../core/document-list.js";
import { requireAuthenticatedUser } from "../core/guard.js";
import { setProfile, setupLogout, showToast } from "../core/app-shell.js";

const elements = {
  count: document.querySelector("#document-count"),
  list: document.querySelector("#documents-list"),
  empty: document.querySelector("#documents-empty"),
  noOwner: document.querySelector("#trash-no-owner"),
  loading: document.querySelector("#documents-loading"),
  loadMore: document.querySelector("#load-more"),
  error: document.querySelector("#page-error"),
  errorMessage: document.querySelector("#page-error-message"),
  retry: document.querySelector("#page-retry"),
  dialog: document.querySelector("#restore-dialog"),
  dialogDescription: document.querySelector("#restore-dialog-description"),
  confirm: document.querySelector("#restore-confirm"),
};

let currentOffset = 0;
let hasMoreDocuments = false;
let selectedDocument = null;
let retryAction = loadFirstPage;

elements.retry.addEventListener("click", () => retryAction());
elements.loadMore.addEventListener("click", loadNextPage);
elements.confirm.addEventListener("click", confirmRestore);
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
  } catch (error) {
    showPageError(errorMessage(error, "Не вдалося завантажити кошик."));
    retryAction = initialize;
  }
}

async function loadFirstPage() {
  hidePageError();
  setLoading(true);
  elements.list.replaceChildren();
  elements.empty.hidden = true;
  elements.noOwner.hidden = true;
  elements.loadMore.hidden = true;
  try {
    const page = await listTrash({ offset: 0 });
    currentOffset = page.pagination.offset + page.documents.length;
    hasMoreDocuments = page.pagination.has_more;
    elements.count.textContent = countLabel(page.pagination.total);
    renderDocuments(page.documents, false);
    elements.empty.hidden = page.pagination.total !== 0;
    elements.loadMore.hidden = !hasMoreDocuments;
    retryAction = loadFirstPage;
  } catch (error) {
    if (error instanceof ApiError && error.status === 403) {
      elements.noOwner.hidden = false;
      elements.count.textContent = "";
    } else {
      showPageError(errorMessage(error, "Не вдалося завантажити кошик."));
      retryAction = loadFirstPage;
    }
  } finally {
    setLoading(false);
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
    const page = await listTrash({ offset: currentOffset });
    currentOffset = page.pagination.offset + page.documents.length;
    hasMoreDocuments = page.pagination.has_more;
    renderDocuments(page.documents, true);
    elements.count.textContent = countLabel(page.pagination.total);
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
      createDocumentRow(documentInfo, "trash", {
        onRestore: openRestoreDialog,
      }),
    );
  }
  if (append) {
    elements.list.append(fragment);
  } else {
    elements.list.replaceChildren(fragment);
  }
}

function openRestoreDialog(documentInfo) {
  selectedDocument = documentInfo;
  elements.dialogDescription.textContent =
    `«${documentInfo.title}» повернеться з кошика до документів.`;
  elements.dialog.showModal();
}

async function confirmRestore() {
  if (!selectedDocument) {
    return;
  }
  elements.confirm.disabled = true;
  elements.confirm.classList.add("button--loading");
  try {
    await restoreDocument(selectedDocument.id);
    elements.dialog.close();
    await loadFirstPage();
    showToast("Документ відновлено.");
  } catch (error) {
    elements.dialog.close();
    showToast(errorMessage(error, "Не вдалося відновити документ."), true);
  } finally {
    elements.confirm.disabled = false;
    elements.confirm.classList.remove("button--loading");
  }
}

function setLoading(isLoading) {
  elements.loading.hidden = !isLoading;
  elements.loading.setAttribute("aria-busy", String(isLoading));
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

/*p.s. File was created by Copilot and reviewed by Olha Bidochka*/
