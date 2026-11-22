const TIME_STEP_MINUTES = 15;
const VALUE_PATTERN = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})$/;
const ISO_DATE_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/;
const POPUP_GAP_PX = 4;
const WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"];
const WEEKDAY_NAMES = ["понеділок", "вівторок", "середа", "четвер", "пʼятниця", "субота", "неділя"];

const monthTitleFormat = new Intl.DateTimeFormat("uk-UA", { month: "long", year: "numeric" });
const fullDateFormat = new Intl.DateTimeFormat("uk-UA", { day: "numeric", month: "long", year: "numeric" });
const dayMonthFormat = new Intl.DateTimeFormat("uk-UA", { day: "numeric", month: "long" });

/** Genitive month names as used in "23 листопада": index 0 = січня. */
const GENITIVE_MONTHS = Array.from({ length: 12 }, (_, month) =>
  dayMonthFormat
    .format(new Date(2026, month, 15))
    .replace(/[\d\s]/g, "")
    .toLocaleLowerCase("uk-UA"),
);

let popupCounter = 0;

/**
 * Date + time control in the spirit of Google Calendar.
 *
 * - Date: a text field (shown as "23.11.2026") with a NoteLy-styled month
 *   picker. You can pick a day or type "23.11.2026", "23.11.26", "23.11",
 *   "23 листопада 2026".
 * - Time: a text field you can type into ("9", "930", "9:30", "21.15") with a
 *   compact list of times every 15 minutes, scrolled to the current value.
 *   For an end field the list shows the duration from the start.
 *
 * For the rest of the page it behaves like an input: `value` uses the
 * datetime-local format "YYYY-MM-DDTHH:MM" ("" when incomplete or invalid),
 * and an "input" event fires on every change. A "datetimechange" event with
 * `detail.previous` fires on committed changes, so the page can shift the end
 * time when the start moves.
 */
export class DateTimeField {
  /**
   * @param {HTMLElement} root Element with `[data-date]`, `[data-date-picker]`,
   *   `[data-time]` and `[data-time-list]`.
   */
  constructor(root) {
    this.root = root;
    this.date = root.querySelector("[data-date]");
    this.picker = root.querySelector("[data-date-picker]");
    this.time = root.querySelector("[data-time]");
    this.list = root.querySelector("[data-time-list]");
    this.isoDate = "";
    this.durationBase = null;
    this.committed = "";
    this.timeActiveIndex = -1;
    this.timeTyped = false;
    this.dateTyped = false;
    this.viewMonth = startOfMonth(new Date());
    this.activeDate = "";

    this.#setupTimeList();
    this.#setupDatePicker();

    const controls = [this.date, this.time];
    this.classList = {
      add: (...names) => controls.forEach((control) => control.classList.add(...names)),
      remove: (...names) => controls.forEach((control) => control.classList.remove(...names)),
    };

    const reposition = () => {
      if (!this.list.hidden) {
        positionPopup(this.time, this.list);
      }
      if (!this.picker.hidden) {
        positionPopup(this.date, this.picker);
      }
    };
    window.addEventListener("resize", reposition);
    document.addEventListener("scroll", reposition, true);
  }

  /** @returns {string} "YYYY-MM-DDTHH:MM" or "". */
  get value() {
    const time = parseTime(this.time.value);
    return this.isoDate && time ? `${this.isoDate}T${time}` : "";
  }

  /** @param {string} value "YYYY-MM-DDTHH:MM" or "". */
  set value(value) {
    const match = VALUE_PATTERN.exec(value ?? "");
    this.#setIsoDate(match && isValidIsoDate(match[1]) ? match[1] : "");
    this.time.value = match ? match[2] : "";
    this.committed = this.value;
  }

  /**
   * Shows durations from another field in this field's time list.
   * @param {DateTimeField} field
   */
  setDurationBase(field) {
    this.durationBase = field;
  }

  addEventListener(type, listener) {
    this.date.addEventListener(type, listener);
    this.time.addEventListener(type, listener);
  }

  setAttribute(name, value) {
    this.date.setAttribute(name, value);
    this.time.setAttribute(name, value);
  }

  removeAttribute(name) {
    this.date.removeAttribute(name);
    this.time.removeAttribute(name);
  }

  focus() {
    this.date.focus();
  }

  // -- Shared -------------------------------------------------------------

  #setIsoDate(iso) {
    this.isoDate = iso;
    this.date.value = iso ? formatDisplayDate(iso) : "";
  }

  #commit() {
    const value = this.value;
    if (value === this.committed) {
      return;
    }
    const previous = this.committed;
    this.committed = value;
    this.root.dispatchEvent(
      new CustomEvent("datetimechange", { bubbles: true, detail: { previous, value } }),
    );
  }

  // -- Date picker --------------------------------------------------------

  #setupDatePicker() {
    const id = `date-picker-${++popupCounter}`;
    this.picker.id ||= id;
    this.picker.hidden = true;
    this.picker.setAttribute("role", "dialog");
    this.picker.setAttribute("aria-label", "Вибір дати");
    this.date.setAttribute("role", "combobox");
    this.date.setAttribute("aria-haspopup", "dialog");
    this.date.setAttribute("aria-expanded", "false");
    this.date.setAttribute("aria-controls", this.picker.id);

    const header = document.createElement("div");
    header.className = "date-picker__header";
    this.prevMonthButton = createIconButton("date-picker__nav date-picker__nav--prev", "Попередній місяць");
    this.nextMonthButton = createIconButton("date-picker__nav date-picker__nav--next", "Наступний місяць");
    this.monthTitle = document.createElement("span");
    this.monthTitle.className = "date-picker__title";
    this.monthTitle.setAttribute("aria-live", "polite");
    header.append(this.prevMonthButton, this.monthTitle, this.nextMonthButton);

    this.grid = document.createElement("table");
    this.grid.className = "date-picker__grid";
    this.grid.setAttribute("role", "grid");
    const head = document.createElement("thead");
    const headRow = document.createElement("tr");
    WEEKDAYS.forEach((short, index) => {
      const cell = document.createElement("th");
      cell.scope = "col";
      cell.abbr = WEEKDAY_NAMES[index];
      cell.textContent = short;
      headRow.append(cell);
    });
    head.append(headRow);
    this.gridBody = document.createElement("tbody");
    this.grid.append(head, this.gridBody);

    const footer = document.createElement("div");
    footer.className = "date-picker__footer";
    this.todayButton = document.createElement("button");
    this.todayButton.type = "button";
    this.todayButton.className = "button button--quiet button--small";
    this.todayButton.textContent = "Сьогодні";
    footer.append(this.todayButton);

    this.picker.replaceChildren(header, this.grid, footer);

    // Keep focus in the text field while using the picker with a mouse.
    this.picker.addEventListener("pointerdown", (event) => event.preventDefault());
    this.prevMonthButton.addEventListener("click", () => this.#shiftViewMonth(-1));
    this.nextMonthButton.addEventListener("click", () => this.#shiftViewMonth(1));
    this.todayButton.addEventListener("click", () => this.#pickDate(toIsoDate(new Date())));
    this.gridBody.addEventListener("click", (event) => {
      const day = event.target.closest("[data-iso]");
      if (day) {
        this.#pickDate(day.dataset.iso);
      }
    });

    this.date.addEventListener("focus", () => this.#openPicker());
    this.date.addEventListener("click", () => this.#openPicker());
    this.date.addEventListener("input", (event) => {
      if (event.isTrusted) {
        this.#onDateTyped();
      }
    });
    this.date.addEventListener("blur", () => {
      this.#closePicker();
      this.#normalizeTypedDate();
    });
    this.date.addEventListener("keydown", (event) => this.#onDateKeydown(event));
  }

  #openPicker() {
    if (!this.picker.hidden) {
      return;
    }
    this.dateTyped = false;
    const base = this.isoDate || toIsoDate(new Date());
    this.activeDate = base;
    this.viewMonth = startOfMonth(fromIsoDate(base));
    this.#renderPicker();
    this.picker.hidden = false;
    this.date.setAttribute("aria-expanded", "true");
    positionPopup(this.date, this.picker);
  }

  #closePicker() {
    if (this.picker.hidden) {
      return;
    }
    this.picker.hidden = true;
    this.date.setAttribute("aria-expanded", "false");
    this.date.removeAttribute("aria-activedescendant");
  }

  #shiftViewMonth(delta) {
    this.viewMonth = addMonths(this.viewMonth, delta);
    const active = fromIsoDate(this.activeDate || toIsoDate(new Date()));
    const day = Math.min(active.getDate(), daysInMonth(this.viewMonth));
    this.activeDate = toIsoDate(
      new Date(this.viewMonth.getFullYear(), this.viewMonth.getMonth(), day),
    );
    this.#renderPicker();
  }

  #moveActiveDate(days) {
    const next = fromIsoDate(this.activeDate || this.isoDate || toIsoDate(new Date()));
    next.setDate(next.getDate() + days);
    this.activeDate = toIsoDate(next);
    this.viewMonth = startOfMonth(next);
    this.#renderPicker();
  }

  #pickDate(iso) {
    if (!iso) {
      return;
    }
    this.#setIsoDate(iso);
    this.#closePicker();
    this.date.dispatchEvent(new Event("input", { bubbles: true }));
    this.#commit();
  }

  #onDateTyped() {
    this.dateTyped = true;
    if (this.picker.hidden) {
      this.#openPicker();
      this.dateTyped = true;
    }
    const iso = parseDate(this.date.value);
    if (iso) {
      this.isoDate = iso;
      this.activeDate = iso;
      this.viewMonth = startOfMonth(fromIsoDate(iso));
      this.#renderPicker();
    }
  }

  #normalizeTypedDate() {
    const text = this.date.value.trim();
    const iso = text ? parseDate(text) : null;
    const changedText = iso ? formatDisplayDate(iso) !== this.date.value : false;
    this.isoDate = iso ?? "";
    if (iso && changedText) {
      this.date.value = formatDisplayDate(iso);
      this.date.dispatchEvent(new Event("input", { bubbles: true }));
    }
    this.#commit();
  }

  #onDateKeydown(event) {
    const open = !this.picker.hidden;
    const arrowsMoveDays = open && !this.dateTyped;
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        if (!open) {
          this.#openPicker();
        } else {
          this.#moveActiveDate(7);
        }
        break;
      case "ArrowUp":
        if (open) {
          event.preventDefault();
          this.#moveActiveDate(-7);
        }
        break;
      case "ArrowLeft":
      case "ArrowRight":
        if (arrowsMoveDays) {
          event.preventDefault();
          this.#moveActiveDate(event.key === "ArrowRight" ? 1 : -1);
        }
        break;
      case "PageUp":
      case "PageDown":
        if (open) {
          event.preventDefault();
          this.#shiftViewMonth(event.key === "PageDown" ? 1 : -1);
        }
        break;
      case "Enter":
        if (open) {
          event.preventDefault();
          const typed = parseDate(this.date.value);
          this.#pickDate(this.dateTyped && typed ? typed : this.activeDate || typed);
        }
        break;
      case "Escape":
        if (open) {
          event.preventDefault();
          event.stopPropagation();
          this.#closePicker();
        }
        break;
      case "Tab":
        this.#closePicker();
        break;
      default:
        break;
    }
  }

  #renderPicker() {
    const title = monthTitleFormat.format(this.viewMonth).replace(/\s*р\.$/, "");
    this.monthTitle.textContent = title.charAt(0).toLocaleUpperCase("uk-UA") + title.slice(1);

    const today = toIsoDate(new Date());
    const first = new Date(this.viewMonth);
    const offset = (first.getDay() + 6) % 7; // Monday-first
    const cursor = new Date(first);
    cursor.setDate(cursor.getDate() - offset);

    const rows = document.createDocumentFragment();
    for (let week = 0; week < 6; week += 1) {
      const row = document.createElement("tr");
      for (let weekday = 0; weekday < 7; weekday += 1) {
        const iso = toIsoDate(cursor);
        const cell = document.createElement("td");
        cell.setAttribute("role", "gridcell");
        const day = document.createElement("button");
        day.type = "button";
        day.tabIndex = -1;
        day.id = `${this.picker.id}-${iso}`;
        day.className = "date-picker__day";
        day.dataset.iso = iso;
        day.textContent = String(cursor.getDate());
        day.setAttribute("aria-label", fullDateFormat.format(cursor).replace(/\s*р\.$/, ""));
        if (cursor.getMonth() !== this.viewMonth.getMonth()) {
          day.classList.add("date-picker__day--outside");
        }
        if (iso === today) {
          day.classList.add("date-picker__day--today");
          day.setAttribute("aria-current", "date");
        }
        if (iso === this.isoDate) {
          day.classList.add("date-picker__day--selected");
          cell.setAttribute("aria-selected", "true");
        }
        if (iso === this.activeDate) {
          day.classList.add("date-picker__day--active");
          this.date.setAttribute("aria-activedescendant", day.id);
        }
        cell.append(day);
        row.append(cell);
        cursor.setDate(cursor.getDate() + 1);
      }
      rows.append(row);
    }
    this.gridBody.replaceChildren(rows);
  }

  // -- Time list ----------------------------------------------------------

  #setupTimeList() {
    this.list.id ||= `time-list-${++popupCounter}`;
    this.time.setAttribute("role", "combobox");
    this.time.setAttribute("aria-autocomplete", "list");
    this.time.setAttribute("aria-expanded", "false");
    this.time.setAttribute("aria-controls", this.list.id);
    this.list.setAttribute("role", "listbox");
    this.list.hidden = true;

    this.time.addEventListener("focus", () => this.#openTimeList());
    this.time.addEventListener("click", () => this.#openTimeList());
    this.time.addEventListener("input", (event) => {
      if (!event.isTrusted) {
        return;
      }
      if (this.list.hidden) {
        this.#openTimeList();
      }
      this.#highlightTypedTime();
    });
    this.time.addEventListener("blur", () => {
      this.#closeTimeList();
      this.#normalizeTypedTime();
    });
    this.time.addEventListener("keydown", (event) => this.#onTimeKeydown(event));

    this.list.addEventListener("pointerdown", (event) => event.preventDefault());
    this.list.addEventListener("click", (event) => {
      const option = event.target.closest("[role='option']");
      if (option) {
        this.#chooseTime(option.dataset.value);
      }
    });
  }

  #onTimeKeydown(event) {
    const options = this.#timeOptions();
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (this.list.hidden) {
        this.#openTimeList();
        return;
      }
      const step = event.key === "ArrowDown" ? 1 : -1;
      const start = this.timeActiveIndex < 0 ? this.#selectedTimeIndex() : this.timeActiveIndex;
      this.#setActiveTime(Math.min(options.length - 1, Math.max(0, start + step)));
    } else if (event.key === "Enter") {
      if (!this.list.hidden) {
        event.preventDefault();
        const typed = parseTime(this.time.value);
        const active = options[this.timeActiveIndex]?.dataset.value;
        this.#chooseTime(this.timeTyped && typed ? typed : active ?? typed);
      }
    } else if (event.key === "Escape") {
      if (!this.list.hidden) {
        event.preventDefault();
        event.stopPropagation();
        this.#closeTimeList();
      }
    } else if (event.key === "Tab") {
      this.#closeTimeList();
    }
  }

  #openTimeList() {
    if (!this.list.hidden) {
      return;
    }
    this.timeTyped = false;
    this.#renderTimeOptions();
    this.list.hidden = false;
    this.time.setAttribute("aria-expanded", "true");
    positionPopup(this.time, this.list);
    this.#setActiveTime(this.#selectedTimeIndex(), "center");
  }

  #closeTimeList() {
    if (this.list.hidden) {
      return;
    }
    this.list.hidden = true;
    this.time.setAttribute("aria-expanded", "false");
    this.time.removeAttribute("aria-activedescendant");
    this.timeActiveIndex = -1;
  }

  #chooseTime(time) {
    if (!time) {
      return;
    }
    this.time.value = time;
    this.#closeTimeList();
    this.time.dispatchEvent(new Event("input", { bubbles: true }));
    this.#commit();
  }

  #normalizeTypedTime() {
    const time = parseTime(this.time.value);
    if (time && time !== this.time.value) {
      this.time.value = time;
      this.time.dispatchEvent(new Event("input", { bubbles: true }));
    }
    this.#commit();
  }

  #renderTimeOptions() {
    const base = this.#durationBaseMinutes();
    const items = [];
    for (let minutes = 0; minutes < 24 * 60; minutes += TIME_STEP_MINUTES) {
      items.push(minutes);
    }
    const current = parseTime(this.time.value);
    const currentMinutes = current ? toMinutes(current) : null;
    if (currentMinutes !== null && currentMinutes % TIME_STEP_MINUTES !== 0) {
      items.push(currentMinutes);
      items.sort((a, b) => a - b);
    }

    const fragment = document.createDocumentFragment();
    items.forEach((minutes, index) => {
      const value = fromMinutes(minutes);
      const option = document.createElement("li");
      option.id = `${this.list.id}-${index}`;
      option.className = "time-listbox__option";
      option.setAttribute("role", "option");
      option.dataset.value = value;
      option.setAttribute("aria-selected", String(value === current));

      const label = document.createElement("span");
      label.textContent = value;
      option.append(label);
      if (base !== null && minutes > base) {
        const duration = document.createElement("span");
        duration.className = "time-listbox__duration";
        duration.textContent = `(${formatDuration(minutes - base)})`;
        option.append(duration);
      }
      fragment.append(option);
    });
    this.list.replaceChildren(fragment);
  }

  /** Start time in minutes when the base field is on the same date, else null. */
  #durationBaseMinutes() {
    const match = VALUE_PATTERN.exec(this.durationBase?.value ?? "");
    if (!match || match[1] !== this.isoDate) {
      return null;
    }
    return toMinutes(match[2]);
  }

  #highlightTypedTime() {
    this.timeTyped = true;
    const typed = parseTime(this.time.value);
    if (!typed) {
      return;
    }
    const options = this.#timeOptions();
    const target = toMinutes(typed);
    let index = options.findIndex((option) => toMinutes(option.dataset.value) >= target);
    if (index < 0) {
      index = options.length - 1;
    }
    this.#setActiveTime(index, "center");
  }

  #timeOptions() {
    return [...this.list.querySelectorAll("[role='option']")];
  }

  #selectedTimeIndex() {
    const options = this.#timeOptions();
    const current = parseTime(this.time.value);
    if (!current) {
      return options.findIndex((option) => option.dataset.value === "09:00");
    }
    const target = toMinutes(current);
    const index = options.findIndex((option) => toMinutes(option.dataset.value) >= target);
    return index < 0 ? options.length - 1 : index;
  }

  #setActiveTime(index, align = "nearest") {
    const options = this.#timeOptions();
    options.forEach((option, optionIndex) => {
      option.classList.toggle("time-listbox__option--active", optionIndex === index);
    });
    this.timeActiveIndex = index;
    const active = options[index];
    if (active) {
      this.time.setAttribute("aria-activedescendant", active.id);
      scrollListTo(this.list, active, align);
    }
  }
}

// -- Helpers --------------------------------------------------------------

/**
 * Fixed positioning so a popup is not clipped by a scrolling dialog;
 * opens upwards when there is no room below.
 */
function positionPopup(anchor, popup) {
  const rect = anchor.getBoundingClientRect();
  const height = popup.offsetHeight;
  const width = popup.offsetWidth;
  const spaceBelow = window.innerHeight - rect.bottom;
  const openUp = spaceBelow < height + POPUP_GAP_PX && rect.top > spaceBelow;
  const top = openUp ? rect.top - height - POPUP_GAP_PX : rect.bottom + POPUP_GAP_PX;
  const left = Math.min(rect.left, window.innerWidth - width - POPUP_GAP_PX);
  popup.style.setProperty("--popup-top", `${Math.max(POPUP_GAP_PX, top)}px`);
  popup.style.setProperty("--popup-left", `${Math.max(POPUP_GAP_PX, left)}px`);
  popup.style.setProperty("--popup-min-width", `${rect.width}px`);
}

/** Scrolls only the list itself (scrollIntoView would also move the dialog). */
function scrollListTo(list, option, align) {
  const top = option.offsetTop;
  const bottom = top + option.offsetHeight;
  if (align === "center") {
    list.scrollTop = top - (list.clientHeight - option.offsetHeight) / 2;
  } else if (top < list.scrollTop) {
    list.scrollTop = top;
  } else if (bottom > list.scrollTop + list.clientHeight) {
    list.scrollTop = bottom - list.clientHeight;
  }
}

function createIconButton(className, label) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.setAttribute("aria-label", label);
  button.tabIndex = -1;
  return button;
}

/**
 * Accepts "23.11.2026", "23/11/26", "23-11", "23 11 2026", "2026-11-23",
 * "23 листопада 2026", "23 листопада" → "YYYY-MM-DD". A missing year means
 * the current year.
 * @param {string} raw
 * @returns {string|null}
 */
export function parseDate(raw) {
  const text = String(raw ?? "").trim().toLocaleLowerCase("uk-UA").replace(/\s*р\.?$/, "");
  let day;
  let month;
  let year;
  let match;
  if ((match = ISO_DATE_PATTERN.exec(text))) {
    [, year, month, day] = match.map(Number);
  } else if ((match = /^(\d{1,2})[.\/\-\s](\d{1,2})(?:[.\/\-\s](\d{2}|\d{4}))?$/.exec(text))) {
    day = Number(match[1]);
    month = Number(match[2]);
    year = match[3] === undefined ? new Date().getFullYear() : Number(match[3]);
  } else if ((match = /^(\d{1,2})\s+([^\d\s]+)(?:\s+(\d{4}))?$/.exec(text))) {
    day = Number(match[1]);
    month = GENITIVE_MONTHS.indexOf(match[2]) + 1;
    year = match[3] === undefined ? new Date().getFullYear() : Number(match[3]);
    if (month === 0) {
      return null;
    }
  } else {
    return null;
  }
  if (year < 100) {
    year += 2000;
  }
  const iso = `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
  return isValidIsoDate(iso) ? iso : null;
}

/**
 * Accepts "9", "09", "930", "0930", "9:30", "9.30", "21 15" → "HH:MM".
 * @param {string} raw
 * @returns {string|null}
 */
export function parseTime(raw) {
  const text = String(raw ?? "").trim().replace(/[.,\s]/g, ":");
  let hours;
  let minutes;
  let match;
  if ((match = /^(\d{1,2})$/.exec(text))) {
    hours = Number(match[1]);
    minutes = 0;
  } else if ((match = /^(\d{1,2}):(\d{2})$/.exec(text))) {
    hours = Number(match[1]);
    minutes = Number(match[2]);
  } else if ((match = /^(\d{1,2})(\d{2})$/.exec(text))) {
    hours = Number(match[1]);
    minutes = Number(match[2]);
  } else {
    return null;
  }
  return hours < 24 && minutes < 60 ? fromMinutes(hours * 60 + minutes) : null;
}

function isValidIsoDate(iso) {
  const match = ISO_DATE_PATTERN.exec(iso);
  if (!match) {
    return false;
  }
  const [, year, month, day] = match.map(Number);
  const date = new Date(year, month - 1, day);
  return (
    year >= 1900 &&
    date.getFullYear() === year &&
    date.getMonth() === month - 1 &&
    date.getDate() === day
  );
}

/** "2026-11-23" → "23.11.2026" — компактно, щоб дата вміщалася в поле. */
function formatDisplayDate(iso) {
  const [year, month, day] = iso.split("-");
  return `${day}.${month}.${year}`;
}

function toIsoDate(date) {
  return [
    String(date.getFullYear()).padStart(4, "0"),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-");
}

function fromIsoDate(iso) {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function startOfMonth(date) {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function addMonths(date, delta) {
  return new Date(date.getFullYear(), date.getMonth() + delta, 1);
}

function daysInMonth(date) {
  return new Date(date.getFullYear(), date.getMonth() + 1, 0).getDate();
}

function toMinutes(time) {
  const [hours, minutes] = time.split(":").map(Number);
  return hours * 60 + minutes;
}

function fromMinutes(total) {
  const hours = Math.floor(total / 60);
  const minutes = total % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

function formatDuration(totalMinutes) {
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours === 0) {
    return `${minutes} хв`;
  }
  if (minutes === 0) {
    return `${hours} год`;
  }
  if (minutes === 30) {
    return `${hours},5 год`;
  }
  return `${hours} год ${minutes} хв`;
}

/*p.s. File was created by Claude and reviewed by Kozynska Anastasia*/
