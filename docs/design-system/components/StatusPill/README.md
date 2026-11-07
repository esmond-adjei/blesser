# StatusPill

A status pill names the state of one record with a dot and a sentence-case word.

In the app: `StatusPill`, `RunStatusBadge`, `CandidateStatusBadge` and `ApplicationStatusBadge` in `components/ui/status.tsx`. Markup: `<span class="g-pill g-pill--positive">Approved</span>`; add `g-pill--live` to pulse the dot while something runs.

| Record | Neutral | Info | Positive | Caution | Critical |
|---|---|---|---|---|---|
| Run | Cancelled | Researching (live) | Done | Paused | |
| Match | | Drafted | Approved, Sent | | Rejected |
| Application | Wishlist | Submitted, Interview | Offer | Applying | Rejected |

Matches are `quiet`: scored and earlier states show no pill. In sidebar run rows the state is a coloured word in the meta line instead ("Researching", positive; "Paused", caution; "Cancelled", critical).

`caption` text on the tone's `*-soft` ground, 22px tall, `radius-sm`. The word carries the meaning; colour only helps scanning.

Related: `.g-best` is the gold "Best fit" marker, one per list. Counts are plain text or a small `tint` badge, never a pill.
