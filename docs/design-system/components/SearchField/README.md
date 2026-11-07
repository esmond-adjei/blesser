# SearchField

The search field filters what is on screen; the sidebar's search row opens workspace search.

In app: `components/filters/SearchInput.tsx` (in-page) and `filters/GlobalSearch.tsx` (workspace).

Markup: `<label class="g-search">` holding a 16px search icon and an `<input>` (14px) with `aria-label`. It sits on a `fill-quiet` well without a border and becomes `surface` with a `focus` ring and `tint-soft` halo when active. The consumer supplies the placeholder, naming what is searched ("Search matches").

Workspace search: a sidebar row ("Search" with a `Ctrl K` `.g-kbd`) opens a dialog (576px, up to 640px tall) with a borderless 15px input, a row of scope buttons (All, Runs, Schools, Programmes, Professors, Matches, Applications, Drafts, CVs, Chats), results grouped under `.type-group-label` headings with a 16px kind icon, title and `caption` subtitle, and a preview card that floats beside the hovered result.

`.g-kbd` is 20px tall, 10px medium text on `surface`, no border. Show `⌘K` on Apple platforms and `Ctrl K` elsewhere.
