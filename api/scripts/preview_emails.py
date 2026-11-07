"""Write every email template to HTML files for review in a browser; nothing is sent.

    uv run python -m scripts.preview_emails [out_dir]
"""

import shutil
import sys
from pathlib import Path

from api.core import mailer
from api.core.mail_layout import Footer, Item, compose

LINK = "https://blesser.example/scans/example"
FOOTER = Footer(
    reason="You're getting this because email is on for Run finished in your notification settings.",
    links=[("Stop emails like this one", LINK), ("Notification settings", LINK)],
)

SAMPLES = {
    "verify": compose(
        to="you@example.com", subject="Confirm your email for Blesser", heading="Confirm your email",
        paragraphs=["Confirm this address to unlock account features like data export and email notifications."],
        action=("Confirm email", LINK), note="The link expires in 48 hours. If you didn't create a Blesser account, ignore this email.",
    ),
    "reset": compose(
        to="you@example.com", subject="Reset your Blesser password", heading="Reset your password",
        paragraphs=["Someone (hopefully you) asked to reset the password for this Blesser account."],
        action=("Choose a new password", LINK), note="The link works once and expires in 30 minutes.",
    ),
    "notification": compose(
        to="you@example.com", subject="Your run finished", eyebrow="Run finished", heading="Your run finished",
        paragraphs=["Your run Machine Learning in Canada finished: 12 candidates."],
        action=("Open in Blesser", LINK), footer=FOOTER,
    ),
    "digest": compose(
        to="you@example.com", subject="Blesser: 3 unread notifications", eyebrow="Daily digest",
        heading="You have 3 unread notifications", paragraphs=["Here is what happened in the last day."],
        items=[
            Item("Your run finished", "Machine Learning in Canada finished: 12 candidates.", LINK),
            Item("First candidate saved", "A run saved its first matching professor.", LINK),
            Item("Deadline in 7 days", "University of Toronto, MSc Computer Science closes on Nov 8.", LINK),
        ],
        action=("Open your inbox", LINK),
        footer=Footer("You're getting this because the daily digest is on in your notification settings.", [("Stop the daily digest", LINK)]),
    ),
}


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "email-previews")
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy(mailer._LOGO, out / "logo.png")
    for name, mail in SAMPLES.items():
        assert mail.html
        (out / f"{name}.html").write_text(mail.html.replace(f"cid:{mailer.LOGO_CID}", "logo.png"))
        (out / f"{name}.txt").write_text(mail.text)
    print(f"Wrote {len(SAMPLES)} previews to {out.resolve()}")


if __name__ == "__main__":
    main()
