# Landing page guide

The landing page (`website/src/pages/index.astro`), section by section. Sections sit within `site-max` (1200px) with 16px gutters (24px from 640px) and 96px of vertical padding (128px from 640px), separated by space rather than rules, and use real product components as their imagery.

1. **Header**: logo, How it works, Features, Pricing, FAQ, Sign in, Get started (primary capsule). Sticky, 64px, `material` with `blur-thin` and a `separator` hairline. See NavBar.
2. **Hero**: gold eyebrow "For PhD and master's applicants"; `hero` serif headline with one italic turn; one `lead` sentence; Start your search (`xl` primary) and Try it without signing up (`xl` plain with an arrow); the product film. See Hero.
3. **Problem**: one centred `statement` sentence, the second clause in `label-tertiary`: "Applicants email forty professors. Most never reply, because most emails could be to anyone."
4. **How it works**: `display` headline "From interests to inbox."; Steps.
5. **Features**: `display` headline "Read every paper." and a `lead`; a grid of entity-card tiles with live fragments and one navy trust tile ("Nothing is ever sent for you."). See FeatureTile.
6. **Try it**: the no-sign-up demo in a `surface` panel with `radius-2xl` and `elevation-1`; its eyebrow is `tint`; on wide screens Gradis (112px) sits beside the heading, the only mascot on the page.
7. **Sources**: `title-1` "Grounded in the record." and a quiet row of source names in `label-secondary`, set as text, not logos.
8. **Questions**: `title-1`, the first five questions as expandable rows in a `.g-list`, and a plain link to all of them.
9. **Closing band**: full-bleed `brand` field, centred `display` headline in `on-brand` ("Start with the professors who fit."), a `lead` in `on-brand-secondary`, `g-btn--on-brand g-btn--xl`.
10. **Footer**: the logo with one line about the product, three columns of 14px links in `label-secondary`, then the legal line and contact address.

Pricing lives on its own page (`/pricing`) with PriceCards; the landing page no longer carries a pricing teaser.

Responsive: under 640px the hero drops to 56px (44px under 480px), `display` to 40px, `statement` to 34px; feature tiles go from three columns to two (768px) to one.

Motion: feature tiles and steps rise 12px and fade in once over 600ms (`data-reveal`); nothing moves on scroll after that, and nothing moves under reduced motion.

Not on the site: radial glows, blurred gradients, progressive frost, scroll-progress lines, parallax.
