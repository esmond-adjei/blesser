# Popover

A popover holds a picker: a short list of options anchored to the control that opened it.

In the app: `Popover` and `PopoverOption` in `components/ui/popover.tsx`, used by the run composer's options and statement pickers (`run/RunComposer.tsx`, `run/composer/`), the document limits and checks, and the ContextMeter.

Markup: `.g-popover` holding `.g-option` buttons (`role="checkbox"` or `role="radio"`, `aria-checked`) with a 16px `.g-option__box`, the label and an optional `.g-option__hint` (`caption`). Under a composer the trigger is a pill (`.g-controlpill`): 28px capsule, 1px `separator` border, a 14px icon and a `caption` label ("PhD, 3 regions, Robotics"); hover and open fill `fill-quiet`. The run options popover splits into a 224px list of sections and an options pane.

Look: 288px wide, up to 70% of the viewport tall, `surface-raised`, 1px `separator` border, `radius-xl`, 6px inset, `elevation-2`. Options are `radius-md` with 8px by 10px padding; hover and the keyboard's active option fill `fill-quiet`. A checked box fills `tint` with an `on-tint` mark (square for checkboxes, dot for radios). Under 640px it becomes a bottom sheet: full width, `radius-2xl` top corners, a header with the label in `title-3` and a close button, on `scrim`.

Keyboard: up and down walk the options; Enter picks inside the popover and never submits the form behind it; Escape closes.
