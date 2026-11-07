# DocumentCard

A document card is one CV, statement or note in the Documents grid, shown as its page with the name underneath, like a file.

In the app: the document cards in `components/documents/DocumentList.tsx` with `DocumentThumb.tsx`.

Anatomy: a 4:5 thumbnail framed by a 1px `separator` border and `radius-md`, then under it the name (14px medium), the kind or the base it was tailored from (12px `label-secondary`), the edited time (12px, with a `caution` cloud-off icon while edits on this device are not synced), and a "More actions" button at the end.

Thumbnail: CVs and statements show the first page as it prints (`.doc-sheet`, the PDF's Helvetica layout, scaled), white with dark text in light and `surface` with `label` text in dark. Interest statements and notes are sticky notes: their heading over their text on `surface`, with a folded corner that grows on hover. A document over its limit shows a `caution` pill on the thumbnail ("2 pages over").

States: the card is one link; hover adds `elevation-1` to the frame; keyboard focus lifts it 1px with `elevation-2`. Renaming swaps the name for a 28px input.
