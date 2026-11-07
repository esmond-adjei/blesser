# Switch

A switch turns a setting on or off immediately, with no Save button.

In the app: `Switch` in `components/settings/controls.tsx`, at the end of a `SettingRow` (title 14px medium, description 12px `label-secondary`) inside a bordered settings section (see Card).

Markup: `<button class="g-switch" role="switch" aria-checked="true|false|mixed" aria-label="…">`. The consumer supplies the state, the handler and an optional tooltip; `mixed` shows a group whose children differ (Flows) and switches all on when pressed.

Look: 36×20px capsule. Off is `label-secondary` at 30%; on is `tint`; mixed is `tint` at 45% with the thumb centred and a short tint dash on it. The 16px thumb is the ground colour (`canvas`) with `elevation-1`. Focus is a 2px ring with a 2px gap. Disabled (while saving) is 50% with a wait cursor.

Don't: use a switch for something that only applies after a Save (use a checkbox), or put the label after the switch.
