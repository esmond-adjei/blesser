import type { ShareKit } from "../api"

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
