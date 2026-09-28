// Service worker mínimo: hace la app instalable. No guarda nada en caché para no servir versiones viejas.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', () => {});
