# SchoolCard

A school card stands for an institution the runs have found: its picture, name, country and what is known there.

In the app: `components/schools/SchoolCard.tsx` (Schools, grid view; built on `CoverCard`) and `entity/SchoolImage.tsx`; in list view a school is a ListRow with a thumbnail.

Anatomy, on `.g-ecard`: `.g-ecard__media` (campus photo with `object-fit: cover`; a crest with `contain` on white; otherwise `.g-crest`), the name (`.g-ecard__title`, up to two lines), the country (`.g-ecard__meta`, one line; "Country unknown" when missing), then a fact list in `caption`: programmes (book-open), faculty (users) and tier (layers). The whole card is one button.

Rules:
- `.g-crest` is the only fallback: brand navy, white initials and the lens rings. Never a grey box or a generic building icon.
- Tier is a fact ("Top tier"), never a coloured pill.
