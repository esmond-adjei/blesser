import * as React from "react"
import { cn } from "../../lib/utils"

/** Without an image the same shape shows initials, so layouts never jump. */
export function SchoolImage({
  src,
  name,
  variant,
  className,
}: {
  src?: string | null
  /** For the initials shown when there's no image. */
  name: string
  variant: "profile" | "thumb" | "thumb-xs" | "card" | "banner" | "banner-sm"
  className?: string
}) {
  const [failed, setFailed] = React.useState(false)
  // Crests and logos are near-square: show them whole on white instead of cropping.
  const [logo, setLogo] = React.useState(false)
  const shape = {
    profile: "h-10 w-10 rounded-full",
    thumb: "h-[34px] w-[52px] rounded-md",
    "thumb-xs": "h-[22px] w-[34px] rounded",
    card: "h-14 w-full rounded-lg",
    banner: "h-40 w-full rounded-xl sm:h-52",
    "banner-sm": "h-28 w-full rounded-xl",
  }[variant]
  if (!src || failed) {
    // Thumbs are too small for the crest's lens rings: plain brand navy.
    if (variant === "thumb" || variant === "thumb-xs")
      return (
        <span
          aria-hidden
          className={cn("flex shrink-0 items-center justify-center bg-brand text-xs font-semibold text-on-brand", shape, className)}
        >
          {schoolInitials(name)}
        </span>
      )
    const text = { profile: "text-sm", card: "text-lg", banner: "text-4xl sm:p-5", "banner-sm": "text-2xl" }[variant]
    return (
      <span aria-hidden className={cn("g-crest shrink-0", shape, text, className)}>
        <span>{schoolInitials(name)}</span>
      </span>
    )
  }
  return (
    <img
      src={src}
      alt=""
      loading="lazy"
      onError={() => setFailed(true)}
      onLoad={(e) => {
        const { naturalWidth: w, naturalHeight: h } = e.currentTarget
        if (h > 0 && w / h < 1.3) setLogo(true)
      }}
      className={cn("block shrink-0 bg-muted", logo ? "bg-inherit object-contain p-1" : "object-cover", shape, className)}
    />
  )
}

/** "UBC" for University of British Columbia, "MU" for McGill University. */
function schoolInitials(name: string): string {
  const words = name.split(/[\s-]+/).filter((w) => w && !/^(of|the|and|de|du|des|la|le|at|for|in)$/i.test(w))
  return words.slice(0, 3).map((w) => w[0]?.toUpperCase() ?? "").join("") || "?"
}
