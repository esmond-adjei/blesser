# LoadMore

LoadMore ends a list that pages in: when it comes within 200px of view, the next page loads.

In the app: `components/ui/LoadMore.tsx`, under the sidebar's runs and chats.

Markup: `.g-loadmore`, a 32px row centred under the list. While a page loads it shows a 14px spinning loader in `label-secondary` (`aria-label` "Loading more"); otherwise it is empty. It renders nothing when there are no more pages, so a list simply ends.

Don't: add a "Load more" button or a page count; scrolling is the action.
