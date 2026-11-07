from api.core import mailer
from api.core.mail_layout import Footer, Item, compose


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
