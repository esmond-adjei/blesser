# Card

A card (a panel, in the app) groups related settings or facts under one heading: a settings section, this month's usage, a flow.

In the app the resting panel is `rounded-xl border border-border bg-card`: `surface`, a 1px `separator` border, `radius-xl`, 16 or 20px padding, no shadow (`SettingSection` in `settings/controls.tsx`, `UsagePanel`, `FlowsPanel`, `Plans`). Rows inside are divided by `separator` hairlines. Here it is `.g-panel` (in `app-patterns.css`).

`.g-card` in the bundle (eyebrow, `title-3` title, body, on `elevation-1`) is the landing page's version and stays for it.

Headings inside a panel are 14px semibold with a 12px `label-secondary` description; numbers use tabular figures.

Don't: nest panels, add coloured left borders, or use a panel where a list row would do.
