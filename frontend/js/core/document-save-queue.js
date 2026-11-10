/**
 * Debounces document writes, serializes writes per field, and retries failures.
 */
export class DocumentSaveQueue {
  /**
   * @param {{onState: (state: string, error?: Error) => void, debounceMs?: number, retryMs?: number}} options
   */
  constructor({ onState, debounceMs = 800, retryMs = 5000 }) {
    this.onState = onState;
    this.debounceMs = debounceMs;
    this.retryMs = retryMs;
    this.entries = new Map();
    this.disabled = false;
  }

  get hasPendingChanges() {
    return this.entries.size > 0;
  }

  /**
   * Queues the latest value for persistence.
   * @param {string} key
   * @param {unknown} value
   * @param {(value: unknown) => Promise<unknown>} save
   */
  set(key, value, save) {
    if (this.disabled) {
      return;
    }
    const entry = this.getOrCreate(key, save);
    entry.value = value;
    entry.save = save;
    entry.version += 1;
    entry.validationMessage = "";
    entry.status = "pending";
    this.clearTimer(entry);
    this.notify();
    this.schedule(key, entry, this.debounceMs);
  }

  /**
   * Keeps a locally invalid value in the dirty buffer without sending it.
   * @param {string} key
   * @param {unknown} value
   * @param {(value: unknown) => Promise<unknown>} save
   * @param {string} message
   */
  setValidationError(key, value, save, message) {
    if (this.disabled) {
      return;
    }
    const entry = this.getOrCreate(key, save);
    entry.value = value;
    entry.save = save;
    entry.version += 1;
    entry.validationMessage = message;
    entry.status = "validation";
    this.clearTimer(entry);
    this.notify(new Error(message));
  }

  /**
   * Flushes one field immediately.
   * @param {string} key
   * @returns {Promise<boolean>}
   */
  async flush(key) {
    return this.flushEntry(key);
  }

  /**
   * Flushes every currently valid field before a structural edit.
   * @returns {Promise<boolean>}
   */
  async flushAll() {
    const keys = [...this.entries.keys()];
    const results = await Promise.all(keys.map((key) => this.flushEntry(key)));
    return results.every(Boolean) && !this.hasPendingChanges;
  }

  /**
   * Retries valid pending changes immediately.
   */
  retry() {
    if (this.disabled) {
      return;
    }
    for (const [key, entry] of this.entries) {
      if (!entry.validationMessage && !entry.inFlight) {
        this.clearTimer(entry);
        this.schedule(key, entry, 0);
      }
    }
  }

  /**
   * Cancels and removes one pending field.
   * @param {string} key
   */
  cancel(key) {
    const entry = this.entries.get(key);
    if (!entry) {
      return;
    }
    this.clearTimer(entry);
    this.entries.delete(key);
    this.notify();
  }

  /**
   * Stops network retries without dropping unsaved local values.
   */
  disable() {
    this.disabled = true;
    for (const entry of this.entries.values()) {
      this.clearTimer(entry);
    }
    this.notify();
  }

  getOrCreate(key, save) {
    let entry = this.entries.get(key);
    if (!entry) {
      entry = {
        value: undefined,
        save,
        version: 0,
        timer: null,
        inFlight: false,
        promise: null,
        validationMessage: "",
        status: "pending",
      };
      this.entries.set(key, entry);
    }
    return entry;
  }

  schedule(key, entry, delay) {
    entry.timer = window.setTimeout(() => {
      entry.timer = null;
      void this.flushEntry(key);
    }, delay);
  }

  clearTimer(entry) {
    if (entry.timer !== null) {
      window.clearTimeout(entry.timer);
      entry.timer = null;
    }
  }

  async flushEntry(key) {
    const entry = this.entries.get(key);
    if (!entry) {
      return true;
    }
    this.clearTimer(entry);
    if (this.disabled || entry.validationMessage) {
      return false;
    }
    if (entry.inFlight) {
      await entry.promise;
      return !this.entries.has(key);
    }

    const version = entry.version;
    const value = entry.value;
    entry.inFlight = true;
    entry.status = "saving";
    this.notify();
    entry.promise = (async () => {
      try {
        await entry.save(value);
        if (this.entries.get(key) !== entry) {
          return;
        }
        entry.inFlight = false;
        entry.promise = null;
        if (entry.version === version) {
          this.entries.delete(key);
          this.notify();
          return;
        }
        entry.status = "pending";
        this.notify();
        this.schedule(key, entry, 0);
      } catch (error) {
        if (this.entries.get(key) !== entry) {
          return;
        }
        entry.inFlight = false;
        entry.promise = null;
        if (entry.version !== version) {
          entry.status = "pending";
          this.notify();
          this.schedule(key, entry, 0);
          return;
        }
        entry.status = "error";
        this.notify(error);
        if (!this.disabled) {
          this.schedule(key, entry, this.retryMs);
        }
      }
    })();
    await entry.promise;
    return !this.entries.has(key);
  }

  notify(error) {
    let state = "saved";
    if (this.disabled) {
      state = "readonly";
    } else if ([...this.entries.values()].some((entry) => entry.status === "validation")) {
      state = "validation";
    } else if ([...this.entries.values()].some((entry) => entry.status === "error")) {
      state = "error";
    } else if ([...this.entries.values()].some((entry) => entry.status === "saving")) {
      state = "saving";
    } else if (this.hasPendingChanges) {
      state = "pending";
    }
    this.onState(state, error);
  }
}


/*p.s. File was created by Copilot and reviewed by Olha Bidochka*/