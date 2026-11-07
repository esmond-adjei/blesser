# Composer

The composer is where the applicant writes to Gradis: what Gradis is looking at, queued prompts, attachments, the text, and the controls that shape the reply.

In the app: the composer in `components/gradis/GradisChat.tsx`, with `ChatAttachments.tsx`, `ModeDropup.tsx`, `ChatControls.tsx` and `ui/ModelDropup.tsx`.

Markup, top to bottom inside `.g-composer`:
1. `.g-composer__chips` of context chips: `.g-chip` (22px capsule, `separator` border on `canvas`, a 12px kind icon, `caption` text, an x). Pressing one removes it; its border hints `critical` on hover.
2. Queued prompts as `.g-chip--queued`: a clock (or a `focus`-coloured zap when it will interrupt), the text, Send now and Remove.
3. Attachments as `.g-attach`: `radius-lg`, a 32px thumbnail or file tile, the name, an x.
4. The textarea (`.g-composer__input`, 14px, grows to 128px then scrolls). Placeholder "Ask Gradis"; while a reply streams, "Add a prompt for after this one".
5. `.g-composer__bar`: Attach, the mode menu (`.g-composer__mode`), then at the end reasoning effort, the ContextMeter, the model menu and the send button (`.g-send`, a 28px `tint` circle; while streaming it becomes a `critical` stop button).

Look: `radius-lg`, 1px `separator` border, `fill-quiet` at 60%; the border turns `focus` while typing. Dropping files makes the border dashed `tint`. Editing a sent prompt adds a strip at the top ("Editing a sent prompt, later replies will be removed") with a cancel x. In a narrow composer the mode and model menus drop their labels and keep their icons.

Keys: Enter sends; Shift+Enter is a new line; Ctrl or Cmd+Enter hands the prompt to the running turn; Escape cancels an edit. Pasting a file attaches it.

Chips a prompt went out with show again above its bubble (see ChatMessage).
