import type { ShareKit } from "./types"

export type ShareNetwork = "whatsapp" | "x" | "linkedin" | "facebook" | "email"

export interface ShareLink {
  label: string
  href: string
  icon: ShareNetwork
}

/** Prefilled share links; each network gets the caption that suits it. */
export function quickLinks(kit: ShareKit, title: string): ShareLink[] {
  const e = encodeURIComponent
  return [
    { label: "WhatsApp", href: `https://wa.me/?text=${e(kit.captions.standard)}`, icon: "whatsapp" },
    { label: "X", href: `https://x.com/intent/tweet?text=${e(kit.captions.short)}`, icon: "x" },
    { label: "LinkedIn", href: `https://www.linkedin.com/sharing/share-offsite/?url=${e(kit.share_url)}`, icon: "linkedin" },
    { label: "Facebook", href: `https://www.facebook.com/sharer/sharer.php?u=${e(kit.share_url)}`, icon: "facebook" },
    { label: "Email", href: `mailto:?subject=${e(title)}&body=${e(kit.captions.standard)}`, icon: "email" },
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
