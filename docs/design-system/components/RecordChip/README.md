# RecordChip

A record card shows something Gradis or a run's agent created, changed or chose to show (a professor, a paper, a document, an application...) and links to it. Chat answers and run traces use the same card.

In the app: `RecordCard` in `components/cards/RecordCard.tsx`. Gradis shows cards for what a turn wrote and for what it showed with `show_record`; reads and lists never add one. Several cards sit in one or two columns.

Card: a 32px icon tile, the kind in words (`caption`), the name (14px, 600), an optional sublabel (`caption`, `label-tertiary`) and a chevron that nudges right on hover. Each kind has a tone: a light wash for the card, a tile ground and an ink for the icon and kind word. People and runs get round tiles; paper records keep squarer ones.

| Kind | Icon | Tone |
|---|---|---|
| Professor | user-round | teal |
| Match | user-round-search | rose |
| Programme | book-open | blue |
| School | school | indigo |
| Application | clipboard-list | emerald |
| Draft | mail | sky |
| Run | play | violet |
| Document | file-text | amber |
| Suggestions (to a document) | file-pen-line | amber |
| Paper | library | fuchsia |

The tones are Tailwind's 50 and 700 steps in light, 950 and 300 in dark. The word always names the kind, so colour is a second cue, never the only one. Cards rest on `elevation-1`; hover drops the shadow and dims slightly; the record open in the detail panel gets a 2px `tint` ring.

The gold `.g-record` chip that run traces used is retired; it stays in the CSS for the website.
