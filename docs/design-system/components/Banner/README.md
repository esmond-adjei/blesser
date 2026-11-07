# Banner

A banner states a condition that affects the page the person is on and, when it can, offers the fix.

In the app: `Alert`, `AlertTitle`, `AlertDescription` in `components/ui/feedback.tsx` (`variant` default, `info`, `caution`, `destructive`), also the email-verification and health banners.

Markup: `.g-banner` with a tone (`--info`, `--caution`, `--critical`), a 16px icon, a body whose first sentence is `<strong>` and says what happened, and an optional `g-btn--plain g-btn--sm` action (`.g-banner__action`). Tone grounds are the `*-soft` colours; text stays `label`, only the icon takes the tone colour.

Don't: stack more than one banner, or use one for something that just succeeded (use a Toast).
