const DB_NAME = 'hearttalk-competition-db';
const STORE_NAME = 'page-state';
const DB_VERSION = 1;

let openDbPromise = null;

const hasWindow = () => typeof window !== 'undefined';
const hasIndexedDb = () => hasWindow() && 'indexedDB' in window;

const openDb = () => {
  if (!hasIndexedDb()) {
    return Promise.resolve(null);
  }

  if (openDbPromise) {
    return openDbPromise;
  }

  openDbPromise = new Promise((resolve) => {
    try {
      const request = window.indexedDB.open(DB_NAME, DB_VERSION);

      request.onupgradeneeded = () => {
        const database = request.result;
        if (!database.objectStoreNames.contains(STORE_NAME)) {
          database.createObjectStore(STORE_NAME, { keyPath: 'key' });
        }
      };

      request.onsuccess = () => {
        const database = request.result;
        database.onversionchange = () => {
          database.close();
          openDbPromise = null;
        };
        resolve(database);
      };

      request.onerror = () => {
        console.warn('Failed to open IndexedDB:', request.error);
        resolve(null);
      };
    } catch (error) {
      console.warn('IndexedDB is unavailable:', error);
      resolve(null);
    }
  });

  return openDbPromise;
};

const withStore = async (mode, handler) => {
  const database = await openDb();
  if (!database) {
    return null;
  }

  return new Promise((resolve) => {
    try {
      const transaction = database.transaction(STORE_NAME, mode);
      const store = transaction.objectStore(STORE_NAME);
      const request = handler(store);

      transaction.oncomplete = () => {
        if (request?.result !== undefined) {
          resolve(request.result);
          return;
        }
        resolve(true);
      };

      transaction.onerror = () => {
        console.warn('IndexedDB transaction failed:', transaction.error);
        resolve(null);
      };

      if (request) {
        request.onerror = () => {
          console.warn('IndexedDB request failed:', request.error);
        };
      }
    } catch (error) {
      console.warn('IndexedDB store operation failed:', error);
      resolve(null);
    }
  });
};

export const loadPersistentJson = (key, fallback = null) => {
  if (!hasWindow()) {
    return fallback;
  }

  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) {
      return fallback;
    }
    return JSON.parse(raw);
  } catch (error) {
    console.warn(`Failed to load localStorage key "${key}":`, error);
    return fallback;
  }
};

export const savePersistentJson = (key, value) => {
  if (!hasWindow()) {
    return;
  }

  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch (error) {
    console.warn(`Failed to save localStorage key "${key}":`, error);
  }
};

export const removePersistentJson = (key) => {
  if (!hasWindow()) {
    return;
  }

  try {
    window.localStorage.removeItem(key);
  } catch (error) {
    console.warn(`Failed to remove localStorage key "${key}":`, error);
  }
};

export const loadPersistentValue = async (key) => {
  const result = await withStore('readonly', (store) => store.get(key));
  if (!result || typeof result !== 'object') {
    return null;
  }
  return result.value ?? null;
};

export const savePersistentValue = async (key, value) => {
  const stored = await withStore('readwrite', (store) =>
    store.put({
      key,
      value,
      updatedAt: Date.now(),
    })
  );

  return Boolean(stored);
};

export const removePersistentValue = async (key) => {
  await withStore('readwrite', (store) => store.delete(key));
};
