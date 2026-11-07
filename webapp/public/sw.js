/* Graduator service worker: browser push notifications only (#196).
 *
 * No offline cache: the app is online-only, and a fetch handler would
 * only add a stale-asset failure mode. A push payload carries
 * {id, kind, title, body, link}: what happened and where to open it,
 * never CV text, draft content or professor details.
 */

self.addEventListener("install", () => self.skipWaiting())
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()))

self.addEventListener("push", (event) => {
  let data = {}
  try {
    data = event.data ? event.data.json() : {}
  } catch {
    data = { title: "Graduator", body: event.data ? event.data.text() : "" }
  }
  const title = data.title || "Graduator"
  event.waitUntil(
    Promise.all([
      self.registration.showNotification(title, {
        body: data.body || "",
        icon: "/logo-light.svg",
        badge: "/logo-light.svg",
        tag: data.id || undefined,
        data: { link: data.link || "/" },
      }),
      // Open tabs refresh the inbox bell straight away.
      self.clients.matchAll({ type: "window" }).then((clients) =>
        clients.forEach((client) => client.postMessage({ type: "notification", id: data.id })),
      ),
    ]),
  )
})

self.addEventListener("notificationclick", (event) => {
  event.notification.close()
  const link = (event.notification.data && event.notification.data.link) || "/"
  const url = new URL(link, self.location.origin)
  // Only ever open this app's own pages.
  if (url.origin !== self.location.origin) return
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if (new URL(client.url).origin === url.origin && "focus" in client) {
          return client.navigate(url.href).then((c) => (c || client).focus())
        }
      }
      return self.clients.openWindow(url.href)
    }),
  )
})
