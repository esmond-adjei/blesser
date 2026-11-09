import type { ShareKit } from "./types"

/** Prefilled share links; each network gets the caption that suits it. */
export function quickLinks(kit: ShareKit, title: string) {
  const e = encodeURIComponent
  return [
    { label: "WhatsApp", href: `https://wa.me/?text=${e(kit.captions.standard)}` },
    { label: "X", href: `https://x.com/intent/tweet?text=${e(kit.captions.short)}` },
    { label: "LinkedIn", href: `https://www.linkedin.com/sharing/share-offsite/?url=${e(kit.share_url)}` },
    { label: "Facebook", href: `https://www.facebook.com/sharer/sharer.php?u=${e(kit.share_url)}` },
    { label: "Email", href: `mailto:?subject=${e(title)}&body=${e(kit.captions.standard)}` },
  ]
}

export function canShareFiles(): boolean {
  if (typeof navigator === "undefined" || typeof navigator.share !== "function" || typeof navigator.canShare !== "function") return false
  try {
    return navigator.canShare({ files: [new File([""], "probe.png", { type: "image/png" })] })
  } catch {
    return false
  }
}

export const imageFilename = (slug: string, format: string) => `blesser-${slug.replace(/[^\w-]/g, "").slice(0, 80) || "opportunity"}-${format}.png`
