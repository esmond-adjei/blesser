# NavBar

The landing page's header: logo and wordmark left, links and a capsule CTA right.

On the site: `website/src/components/SiteHeader.astro`. It sticks to the top, 64px tall within `site-max`, on `material` with a `blur-thin` backdrop and a `separator` hairline. Links are 14px medium `label-secondary` text with 12px by 8px padding that turn `label` on hover; Sign in is a link; the CTA is `g-btn--primary g-btn--capsule`. Under 768px the links move into a menu button (36px, bordered) that opens a list under the bar.

`.g-navbar` in the bundle (56px, `blur-regular`) is the older spec; the site builds the header in Tailwind.

Don't: add a scroll-progress line or a gradient under it.
