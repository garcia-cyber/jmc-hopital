// -- le service worker laisse le navigateur installer l'app --
self.addEventListener('fetch', function(event) {
  event.respondWith(fetch(event.request));
});