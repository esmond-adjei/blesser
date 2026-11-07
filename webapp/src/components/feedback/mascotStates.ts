/** Cells of the Graduation Mascot Sticker Grid (3x3), each trimmed to alpha>8 plus 18px padding. */

export const MASCOT_STATES = {
  reading: { src: "/mascot-states/reading.png", alt: "Gradis reading a book" },
  "not-found": { src: "/mascot-states/not-found.png", alt: "Confused Gradis with a question mark" },
  "empty-box": { src: "/mascot-states/empty-box.png", alt: "Gradis popping out of an empty box" },
  offline: { src: "/mascot-states/offline.png", alt: "Gradis with a disconnected wifi signal" },
  "no-file": { src: "/mascot-states/no-file.png", alt: "Gradis peeking from behind a missing file" },
  "search-empty": { src: "/mascot-states/search-empty.png", alt: "Gradis searching with a magnifying glass" },
  loading: { src: "/mascot-states/loading.png", alt: "Gradis waiting with a loading spinner" },
  happy: { src: "/mascot-states/happy.png", alt: "Happy Gradis sparkling with joy" },
  "error-gear": { src: "/mascot-states/error-gear.png", alt: "Gradis fixing things with a gear and wrench" },
} as const

export type MascotStateName = keyof typeof MASCOT_STATES
