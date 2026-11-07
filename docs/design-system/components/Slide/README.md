# Slide

A slide is one 1920×1080 page of the pitch deck, built from five templates so every deck reads as one object.

Markup: `<section class="g-slide">` plus a ground: default `canvas`, `g-slide--surface` (white), or `g-slide--brand` (navy, for the cover, section breaks and the close). Inside: `.g-slide__kicker` (gold-ink, or `gold` on brand), then one of `.g-slide__hero` (serif, cover only), `.g-slide__title` (sans 96px), `.g-slide__statement` (serif 88px) or `.g-slide__metric` (sans 280px), with optional `.g-slide__body`, and `.g-slide__foot` (wordmark and page number). Margins: `space-16` top and bottom, 96px sides.

Templates:
1. **Cover**: brand ground, logo top-left, kicker, serif hero.
2. **Statement**: one sentence in the serif; the second clause in `label-tertiary`.
3. **Metric**: one number, a gold diamond (the needle), one line of meaning.
4. **Product**: a sans title and the real interface, scaled 2×, rising from the bottom edge.
5. **Split**: title and body left, product or chart right, on `surface`.

Rules: one idea per slide; at most 25 words of body; one gold mark per slide; no bullet lists over three items; charts follow the dataviz palette with `tint` as the first series. Export at 1920×1080; the same templates scale to 16:9 in Keynote or Google Slides with Instrument Sans and Newsreader installed.
