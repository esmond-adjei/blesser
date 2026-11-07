# SidebarRow

A sidebar row is one run or chat in the sidebar's lists, with a "More actions" menu that appears on hover.

In the app: `RunsList` and `ChatsList` in `components/lists/`, with `RowMenu` (`components/ui/row-menu.tsx`, `variant="sidebar"`); a chat's Rename and Delete come from `ChatMenu` (`components/gradis/ChatMenu.tsx`, shared with the chat header) and the in-place title is `RenameInput` (`components/ui/RenameInput.tsx`).

Run row (`.g-siderow__link`): the run's title (14px medium) over a meta line (`caption`, `label-tertiary`): the state as a coloured word only when it is news ("Researching," positive; "Paused," caution; "Cancelled," critical), the candidate count, and the relative date at the end. A running run's title shimmers. Its tooltip is the run's interest statement.

Chat row (`.g-siderow__link--chat`): 36px, a 14px message icon and the title; a 6px `focus` dot at the end means a tool call waits for approval. Rename edits the title in place (a 36px input with a `focus` border; Enter saves, Escape cancels).

Look: `radius-md`, `label-secondary` text; hover fills `fill-quiet`; the current run fills `fill` and the current chat `fill-quiet`, both with `label` text. Titles never ellipsize: they fade out over their last 24px (`.g-fade`). Nothing is reserved for the menu, so titles use the full row width.

RowMenu (`.g-rowmenu`): a 28px "More actions" button (ellipsis, `radius-sm`, `label-secondary`) overlaid on the row's top-right corner, inside its edge, on a small `canvas` chip with `elevation-1`; it takes no layout space and covers the end of the title while shown. It is a sibling of the link so opening it never navigates. Hidden until the row is hovered or focused; it stays while its menu is open. Runs: Pause or Resume, Cancel, Retry failed, then Edit run and Delete. Chats: Rename, Delete. Cancel and Delete confirm in a Dialog. On cards it is `g-rowmenu--card` (bordered, on `surface`), on list rows vertically centred (`g-rowmenu--center`).

The lists load more as they scroll (LoadMore). Empty lists show one `caption` line ("No runs yet. Start one above.").
