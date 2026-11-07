# Dialog

A dialog asks for a decision or a few fields without leaving the page; it blocks everything behind it until answered.

In the app: `components/ui/dialog.tsx` (`Dialog`, `DialogContent`, `DialogHeader`, `DialogTitle`, `DialogDescription`, `DialogBody`, `DialogFooter`) and `dialogs/ConfirmDialog.tsx` for confirmations.

Markup: `.g-scrim` holding `.g-dialog` (`role="dialog"`, `aria-modal`, `aria-labelledby`) with a `.g-dialog__close` button, `.g-dialog__head` (title in `title-3`, description in `callout` `label-secondary`), `.g-dialog__body` (the only part that scrolls) and `.g-dialog__foot`.

Look: the scrim is black at 50% with no blur. The dialog sits 12% of the viewport from the top, not centred, so growing content extends downward. 512px wide by default (`max-w-lg`), wider for forms and search (`max-w-xl`, `max-w-2xl`); at most 88% of the viewport tall. `surface-raised`, `radius-xl`, `elevation-3`. The close button is a 28px `fill-quiet` circle 16px from the top right. It rises 8px and fades in over 320ms; the scrim fades over 200ms.

Footer: Cancel (`outline`) first, the action last (`primary`, or `destructive` for a delete), both default size and labelled with the verb ("Delete chat", never "OK"). On phones the footer stacks with the action on top.

Don't: open a dialog from a dialog; use one for information that could be a Banner.
