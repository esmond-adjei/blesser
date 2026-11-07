# TextField

A text field collects one value with a visible label above it; the label never lives only in the placeholder.

In the app: `Input`, `Textarea`, `Label`, `Field` in `components/ui/input.tsx`, `Select` in `ui/select.tsx` (native, with a chevron), `Combobox` in `ui/combobox.tsx` (searchable, single or multiple), and `FormField` in `ui/form.tsx`.

Markup: `.g-field` wraps `.g-label`, `.g-input`, `.g-textarea` or `.g-select`, and an optional `.g-hint`. Errors set `aria-invalid="true"`, which draws a `critical` inset ring; the note under the field turns `critical` and says how to fix it.

Look: 36px, `radius-md`, a 1px `control-border` inset ring (a `separator` hairline now), `body` value text; hover darkens the ring to `label-secondary`; focus adds a `focus` ring and a 3px `tint-soft` halo. Disabled is 50%. In forms (`FormField`) the label is 13px medium, "Optional" follows it in 12px `label-secondary`, and the note under the field is 12px.

Don't: grey out a field to show it is optional.
