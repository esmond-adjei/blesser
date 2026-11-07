# ChatMessage

A chat message is one turn: the applicant's prompt as a bubble on the right, Gradis's answer as plain text on the left, each with actions that appear on hover.

In the app: `UserRow` and `AssistantRow` in `components/gradis/GradisChat.tsx`.

Prompt: right-aligned, up to 85% wide. Above the bubble, the context chips it was sent with (`.g-chip`, read-only) and any attachments. The bubble (`.g-bubble`) is `fill-quiet`, `radius-xl` with a `radius-sm` bottom-right tail, 8px by 12px padding.

Answer: full width, no bubble. The AgentActivity group comes first when Gradis used tools, then the answer as Markdown (`.rich-text`, with numbered citations), then any RecordChip cards for records it created or showed.

Actions (`.g-msg__actions`): a row of 28px icon buttons in `label-secondary` (`.g-iconbtn`), shown on hover or focus of the message on desktop and always on touch. Prompt: time, Copy prompt, Edit prompt. Answer: Copy (as Markdown with sources), Regenerate, then the model name and the time in 12px text. Times are relative and their tooltip gives the full date. Copy swaps to a `positive` check for a moment.

While the reply is being written, three dots hop (`.g-typing`); a failed turn shows a `critical` alert icon, what failed, and an outline "Retry" button. A round "jump to latest" button floats above the composer when the reader has scrolled up.
