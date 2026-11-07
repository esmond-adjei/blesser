# Button

A button starts one action; its label says the action as a verb ("Delete chat", not "OK").

In the app: `components/ui/button.tsx` (`Button`, `buttonVariants`), which renders the `g-btn` classes. Markup: `<button class="g-btn g-btn--primary">` plus an optional leading 16px Lucide icon. The consumer supplies the label, the icon and the handler.

| Variant | Class (app `variant`) | When |
|---|---|---|
| Primary | `g-btn--primary` (`default`) | The one action a view exists for: New run, Approve draft, the confirm in a dialog. |
| Secondary | `g-btn--secondary` (`secondary`) | A strong second action beside primary. Tinted, not bordered. |
| Outline | `g-btn--outline` (`outline`) | Cancel in dialogs, toolbar controls (Sort, Filters), Try again, empty-state actions. The app's most used variant. |
| Plain | `g-btn--plain` (`ghost`, and `link` with an underline on hover) | Inline actions in rows and headers. Text in `tint`. |
| Destructive | `g-btn--destructive` (`destructive`) | The confirm button of a destructive dialog. Delete in menus is a destructive menu item, not a button. |
| On brand | `g-btn--on-brand` | White button on a `brand` field (landing closing band, deck). |

`g-btn--gray` and `g-btn--destructive-plain` stay in the bundle for the landing page and deck; the app does not use them.

Sizes: `g-btn--sm` (28px) for toolbars, row actions and empty states (the app's most used size); default (36px); `g-btn--lg` (44px) on phones and onboarding; `g-btn--xl` (52px, capsule) for marketing CTAs only. The sidebar's New run is a full-width default button with `g-btn--capsule`. `g-btn--icon` makes it square and needs `aria-label` and a tooltip.

States: hover darkens (`tint-hover`) or fills `fill-quiet`; press scales to 0.98; disabled is 40% opacity. In the app, keyboard focus is a flush 2px `focus` ring (`ring-2`), not the outline with a gap.

Don't: place two primary buttons side by side, or use `xl` inside the app.
