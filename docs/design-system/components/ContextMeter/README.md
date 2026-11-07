# ContextMeter

The context meter shows how full the model's context window is, so the applicant knows when a chat is getting long.

In the app: `ChatControls` in `components/gradis/ChatControls.tsx`, inside the Composer.

Ring: `.g-ring`, a 28px round button with a 20px ring: the track is `label-secondary` at 20%, the value `tint`, turning `critical` at 90% and up (`data-full`). Its `aria-label` says the share and the counts ("34% of context used: 68,000 of 200,000 tokens").

Pressing it opens a Popover above: the model name, a `.g-meter` bar (6px, same colours, `role="meter"`), the counts ("68,000 / 200,000 tokens" and "34%") in 12px tabular `label-secondary`, and a `caption` note that counts between replies are estimates and measure context, not billing. When the model's window is not set, the bar stays empty, the count reads "?" and a link opens Settings, Models.
