# PriceCard

A price card shows one plan: its name, its price with the period in words, what it includes, and one action.

Markup: `.g-price` (add `--featured` to the recommended plan: a 2px `tint` ring and `elevation-2`) with `.g-price__name`, `.g-price__amount` (tabular figures, period in a `<small>`), a `<ul>` of three to five inclusions each with a check icon in `tint`, and a capsule `lg` button pinned to the bottom. The consumer supplies plan data from `api/billing/plans.py`; the amounts shown here are placeholders.

Don't: strike through prices, add "Most popular" ribbons, or list what a plan lacks.
