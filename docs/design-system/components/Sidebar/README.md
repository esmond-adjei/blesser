# Sidebar

The sidebar is the app's navigation: logo, New run, search, the destinations, then the Runs and Chats lists and the account menu.

In the app: `components/layout/Sidebar.tsx`, `SidebarListings.tsx`, `AccountMenu.tsx`. Hidden under 768px, where a top bar with icons replaces it.

Order, top to bottom:
1. Logo (28px) and "Graduator" (17/22, 600), with the hide-sidebar button at the end.
2. New run: a full-width primary capsule.
3. Search: a row with a search icon and a `Ctrl K` `.g-kbd`; it opens the workspace search dialog.
4. Gradis and Schools.
5. A "Workspace" section: Applications, Outbox, Matches, Documents (Documents opens in a new tab and shows an up-right arrow).
6. Collapsible Runs and Chats sections, each with a + button; their rows are SidebarRows and load more as they scroll (LoadMore).
7. The account menu at the foot: name and plan; it opens settings, a light, dark or system theme switch, and Sign out.

Look: on `canvas`; default width `sidebar-width` (264px), resizable from 200 to 440px by a 10px handle on its right edge (a `separator` hairline; a 4px `focus` bar shows while dragging or focused); arrow keys resize by 16px. Nav items are 34px, `radius-md`, 16px icon, 14px medium text in `label-secondary`; hover fills `fill-quiet`, the current page fills `fill` with `label` text: navigation is place, not action. Section labels are 12px semibold `label-tertiary` in capitals; this is the one place the app uses uppercase.

Don't: put settings in the nav list (they live in the account menu).
