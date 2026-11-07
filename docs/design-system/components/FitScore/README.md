# FitScore

The fit score shows how closely a professor's publications match the applicant's interests, as a bar and a whole-number percentage.

In the app: `ScoreBar` in `components/ui/status.tsx`. Markup: `.g-fit` with `data-band="strong|moderate|weak"`, a `.g-fit__track` (48px, 4px) holding a `.g-fit__bar` whose `width` is the score, and a `.g-fit__value`. `size="lg"` adds `.g-fit--lg` (160px, 6px) and a `.g-fit__band` word ("Strong fit"). Every bar has a tooltip naming its band.

Bands use the cut-offs in `api/candidates/scoring.py`: strong 45% and up, moderate 30%, weak 15%, unrelated below (drawn as weak). Colours are `fit-strong` (`tint`), `fit-moderate` and `fit-weak`: one hue in three lightnesses, because fit is a measure. Weak scores drop the number to `label-tertiary`. No score, no bar.

Don't: colour fit green, amber and red.
