import { Backpack, Bell, CalendarDays, ClipboardList, MessageCircle, Radar, Sparkles } from "lucide-react"

export const NAV_GROUPS = [
  {
    label: "Discover",
    items: [
      { to: "/opportunities", label: "Opportunities", icon: Sparkles },
      { to: "/scans", label: "Scans", icon: Radar },
      { to: "/assistant", label: "Assistant", icon: MessageCircle },
    ],
  },
  {
    label: "Your work",
    items: [
      { to: "/applications", label: "Applications", icon: ClipboardList },
      { to: "/calendar", label: "Calendar", icon: CalendarDays },
      { to: "/kit", label: "Apply kit", icon: Backpack },
    ],
  },
  {
    label: "Inbox",
    items: [{ to: "/notifications", label: "Notifications", icon: Bell }],
  },
]
