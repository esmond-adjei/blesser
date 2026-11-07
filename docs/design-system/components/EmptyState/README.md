# EmptyState

An empty state explains why a view has nothing in it and offers the one action that fills it; load failures use the same layout.

In the app: `EmptyState` and `ErrorState` in `components/feedback/EmptyState.tsx`; stickers from `feedback/mascotStates.ts`.

Markup: `.g-empty` inside a `surface` panel (`radius-lg`, `elevation-1`), with a Gradis sticker `<img>` 112px tall (80px when `compact`), `.g-empty__title` (`title-3`; plain semibold when compact), `.g-empty__body` (one or two sentences, max 40ch) and an optional action 8px below. Without a sticker it shows a 48px `.g-icon-tile` with a 24px inbox icon.

Actions are usually `outline` `sm` ("Browse matches"). `ErrorState` uses the `offline` sticker by default, sits centred at up to 576px, and offers `outline` `sm` "Try again" with a refresh icon.

The consumer picks the sticker by situation: `search-empty` for no results, `empty-box` for nothing created yet, `offline` and `error-gear` for failures, `reading` while a run works, `happy` for done.

Inline "nothing here" lines inside lists (the sidebar's "No runs yet. Start one above.") are `caption` text, not an EmptyState.

Don't: use a dashed border or jokes in error copy.
