# Tooltip

A tooltip names an icon-only control or adds one fact, on hover and on keyboard focus.

In the app: any element with a `data-tooltip` attribute gets one from `components/ui/tooltip.tsx` (`TooltipProvider`); there is no per-component wrapper. It renders `.app-tooltip` (index.css): fixed, above dialogs and menus (z 200), with an arrow toward the trigger, placed above it or below when there is no room.

Markup here: `.g-tooltip` with `role="tooltip"`; `data-side="bottom"` flips the arrow.

Look: `caption` (12px, 500) on `surface-raised` with `elevation-2`, radius 8px, 6px by 10px padding, at most 18rem wide. It rises 2px and fades over `duration-quick`.

Do: give every icon-only button both `aria-label` and `data-tooltip`. Don't: put links, buttons or anything essential in a tooltip; touch screens may never show it.
