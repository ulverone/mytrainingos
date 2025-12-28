/**
 * Database Manager for MyTrainingOS
 * Uses IndexedDB for local storage
 */

class Database {
    constructor() {
        this.dbName = 'MyTrainingOS';
        this.dbVersion = 1;
        this.db = null;
    }

    async init() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(this.dbName, this.dbVersion);
            request.onerror = () => reject(request.error);
            request.onsuccess = () => { this.db = request.result; resolve(this); };
            request.onupgradeneeded = (event) => {
                const db = event.target.result;
                if (!db.objectStoreNames.contains('activities')) {
                    const store = db.createObjectStore('activities', { keyPath: 'id' });
                    store.createIndex('date', 'date', { unique: false });
                    store.createIndex('sport', 'sport', { unique: false });
                }
                if (!db.objectStoreNames.contains('dailyTSS')) {
                    db.createObjectStore('dailyTSS', { keyPath: 'date' });
                }
                if (!db.objectStoreNames.contains('settings')) {
                    db.createObjectStore('settings', { keyPath: 'key' });
                }
            };
        });
    }

    async addActivity(activity) {
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction(['activities'], 'readwrite');
            const request = tx.objectStore('activities').put(activity);
            request.onsuccess = () => resolve(activity.id);
            request.onerror = () => reject(request.error);
        });
    }

    async getAllActivities() {
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction(['activities'], 'readonly');
            const request = tx.objectStore('activities').getAll();
            request.onsuccess = () => {
                resolve(request.result.sort((a, b) => new Date(b.startTime) - new Date(a.startTime)));
            };
            request.onerror = () => reject(request.error);
        });
    }

    async getActivitiesByDate(date) {
        const dateStr = typeof date === 'string' ? date : date.toISOString().split('T')[0];
        const all = await this.getAllActivities();
        return all.filter(a => new Date(a.startTime).toISOString().split('T')[0] === dateStr);
    }

    async deleteActivity(id) {
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction(['activities'], 'readwrite');
            const request = tx.objectStore('activities').delete(id);
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    }

    async getActivityCount() {
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction(['activities'], 'readonly');
            const request = tx.objectStore('activities').count();
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    async updateActivity(activity) {
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction(['activities'], 'readwrite');
            const request = tx.objectStore('activities').put(activity);
            request.onsuccess = () => resolve(activity.id);
            request.onerror = () => reject(request.error);
        });
    }

    async saveSetting(key, value) {
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction(['settings'], 'readwrite');
            const request = tx.objectStore('settings').put({ key, value });
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    }

    async getSetting(key) {
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction(['settings'], 'readonly');
            const request = tx.objectStore('settings').get(key);
            request.onsuccess = () => resolve(request.result?.value);
            request.onerror = () => reject(request.error);
        });
    }

    async getAllSettings() {
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction(['settings'], 'readonly');
            const request = tx.objectStore('settings').getAll();
            request.onsuccess = () => {
                const settings = {};
                request.result.forEach(item => { settings[item.key] = item.value; });
                resolve(settings);
            };
            request.onerror = () => reject(request.error);
        });
    }

    async clearActivities() {
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction(['activities'], 'readwrite');
            const request = tx.objectStore('activities').clear();
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    }

    async clearAll() {
        for (const store of ['activities', 'dailyTSS']) {
            await new Promise((resolve, reject) => {
                const tx = this.db.transaction([store], 'readwrite');
                const request = tx.objectStore(store).clear();
                request.onsuccess = () => resolve();
                request.onerror = () => reject(request.error);
            });
        }
    }

    generateActivityId(activity) {
        const dateStr = activity.startTime ? new Date(activity.startTime).toISOString() : new Date().toISOString();
        return `${activity.sport}_${dateStr}_${Math.random().toString(36).substr(2, 9)}`;
    }
}

window.Database = Database;
