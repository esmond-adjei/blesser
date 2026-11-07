# Progress

A progress bar shows how far something has got when the total is known; a skeleton holds the shape of content that is loading.

In the app: `Progress` and `Skeleton` in `components/ui/feedback.tsx`, plus `SkeletonStack` (a column of skeleton blocks from a list of sizes), `PageSkeleton` and `DetailSkeleton` there, and `ItemCardSkeleton`.

Markup: `<div class="g-progress"><span style="width:64%"></span></div>`, with a text line that says what it measures. Skeleton: `.g-skeleton` blocks sized like the rows they stand in for (avatars round, pills round, text lines 12 to 16px).

The bar is 4px, `tint` on `fill`, and grows over 600ms. Skeletons breathe on `fill-quiet` and stop under reduced motion. Small inline waits (a busy button, a list loading more, a tool call running) use a 14 or 16px spinning loader icon.

Don't: show a centred spinner for a page load; show the page's skeleton.
