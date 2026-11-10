/**
 * Creates a document list row using DOM APIs only.
 * @param {object} documentInfo
 * @param {"active"|"trash"} mode
 * @param {{onRename?: (documentInfo: object) => void, onTrash?: (documentInfo: object) => void, onRestore?: (documentInfo: object) => void}} handlers
 * @returns {HTMLElement}
 */
export function createDocumentRow(documentInfo, mode, handlers = {}) {
  const row = document.createElement("article");
  row.className = "document-row";

  const main = document.createElement("div");
  main.className = "document-row__main";
  const icon = document.createElement("img");
  icon.className = "document-row__icon";
  icon.src = "assets/icon-files.svg";
  icon.alt = "";
  main.append(icon);

  const title = document.createElement("a");
  title.className = "document-row__title";
  title.href = `document.html?id=${encodeURIComponent(documentInfo.id)}`;
  title.textContent = documentInfo.title;
  main.append(title);
  row.append(main);

  if (mode === "active") {
    row.append(
      createMeta(
        "Змінено",
        formatDate(documentInfo.updated_at),
      ),
    );
    const access = document.createElement("span");
    access.className = "badge document-access";
    access.textContent =
      documentInfo.access_mode === "link" ? "За посиланням" : "Обмежений доступ";
    row.append(access);
    row.append(createActiveActions(documentInfo, handlers));
  } else {
    row.append(createMeta("Переміщено до кошика", formatDate(documentInfo.deleted_at)));
    row.append(createMeta("Створено", formatDate(documentInfo.created_at)));
    row.append(createTrashActions(documentInfo, handlers));
  }
  return row;
}

function createMeta(label, value) {
  const meta = document.createElement("div");
  meta.className = "document-row__meta";
  const metaLabel = document.createElement("span");
  metaLabel.className = "document-row__label";
  metaLabel.textContent = label;
  const metaValue = document.createElement("span");
  metaValue.className = "document-row__value";
  metaValue.textContent = value;
  meta.append(metaLabel, metaValue);
  return meta;
}

function createActiveActions(documentInfo, handlers) {
  const actions = document.createElement("div");
  actions.className = "document-row__actions";
  const rename = document.createElement("button");
  rename.className = "button button--secondary button--small";
  rename.type = "button";
  rename.textContent = "Перейменувати";
  rename.setAttribute("aria-label", `Перейменувати: ${documentInfo.title}`);
  rename.addEventListener("click", () => handlers.onRename?.(documentInfo));

  const trash = document.createElement("button");
  trash.className = "button button--quiet button--small";
  trash.type = "button";
  trash.textContent = "До кошика";
  trash.setAttribute("aria-label", `Перемістити до кошика: ${documentInfo.title}`);
  trash.addEventListener("click", () => handlers.onTrash?.(documentInfo));
  actions.append(rename, trash);
  return actions;
}

function createTrashActions(documentInfo, handlers) {
  const actions = document.createElement("div");
  actions.className = "document-row__actions";
  const restore = document.createElement("button");
  restore.className = "button button--secondary button--small document-row__restore";
  restore.type = "button";
  restore.textContent = "Відновити";
  restore.setAttribute("aria-label", `Відновити: ${documentInfo.title}`);
  restore.addEventListener("click", () => handlers.onRestore?.(documentInfo));

  const permanentDelete = document.createElement("button");
  permanentDelete.className = "button button--danger button--small document-row__delete";
  permanentDelete.type = "button";
  permanentDelete.textContent = "Видалити назавжди";
  permanentDelete.disabled = true;
  permanentDelete.title = "Остаточне видалення недоступне в API.";
  actions.append(restore, permanentDelete);
  return actions;
}

function formatDate(value) {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }
  return new Intl.DateTimeFormat("uk-UA", {
    day: "numeric",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

/*p.s. File was created by Copilot and reviewed by Olha Bidochka*/