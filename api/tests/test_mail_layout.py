from api.core import mailer
from api.core.mail_layout import TAGLINE, Footer, Item, compose


def test_branded_mail_has_text_html_and_inline_logo():
    mail = compose(
        to="a@example.com",
        subject="Hi",
        heading="Run <b>done</b>",
        paragraphs=["Body & more"],
        items=[Item("Row", "detail", "https://x.test/row")],
        action=("Open", "https://x.test/open?token=abc"),
        footer=Footer("Why you got this.", [("Unsubscribe", "https://x.test/unsubscribe?token=t1")]),
    )
    assert "Open: https://x.test/open?token=abc" in mail.text
    assert "Unsubscribe: https://x.test/unsubscribe?token=t1" in mail.text
    assert mail.html and "Run &lt;b&gt;done&lt;/b&gt;" in mail.html and "Body &amp; more" in mail.html

    msg = mailer.build_message(mail)
    types = [part.get_content_type() for part in msg.walk()]
    assert {"text/plain", "text/html", "image/png"} <= set(types)
    logo = next(part for part in msg.walk() if part.get_content_type() == "image/png")
    assert logo["Content-ID"] == f"<{mailer.LOGO_CID}>"


def test_mail_follows_the_copy_rules_and_brand_tokens():
    from api.core import mail_tokens

    mail = compose(
        to="a@example.com",
        subject="Digest",
        eyebrow="Daily digest",
        heading="You have 2 unread notifications",
        paragraphs=["Here is what happened in the last day."],
        items=[Item("One", "first"), Item("Two", "second", "https://x.test/2")],
        footer=Footer("Why you got this.", [("Stop", "https://x.test/s"), ("Settings", "https://x.test/p")]),
    )
    assert mail.html
    # No middle dots or em dashes anywhere, footer links included.
    assert "·" not in mail.html and "—" not in mail.html and "&middot;" not in mail.html
    assert mail_tokens.SUN_SOFT in mail.html and mail_tokens.SURFACE_SUNK in mail.html
    assert 'alt="Blesser"' in mail.html


def test_mail_without_footer_signs_off_with_the_tagline():
    mail = compose(to="a@example.com", subject="Hi", heading="Hello", paragraphs=["Body"])
    assert mail.text.endswith(TAGLINE + "\n")
    assert mail.html and TAGLINE in mail.html
