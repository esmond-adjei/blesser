# FeatureTile

A feature tile presents one capability on the landing page: what it is, its benefit in one line, one sentence of proof, and sometimes a live piece of the product.

On the site: `website/src/components/sections/Features.astro`. Tiles are `.g-ecard` with `min-h-64`: `.g-ecard__kind` names the feature, `.g-ecard__title` the benefit, `.g-ecard__body` the proof, and `.g-ecard__signal` a real fragment (Best fit and a FitScore, a record). One tile is the navy trust tile: `brand` ground, `radius-lg`, 24px padding, `on-brand` text with `on-brand-secondary` support ("Nothing is ever sent for you.").

Grid: one column on phones, two from 768px, three from 1024px, 16px gaps; the first tile spans two columns.

`.g-tile` in the bundle (`radius-2xl`, 32px padding) is kept for the deck.

Don't: use icon-in-a-tinted-square headers or more than one brand tile per grid.
