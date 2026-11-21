from api.core.errors import describe_validation_errors


def test_email_with_a_url_reads_plainly():
    errors = [
        {
            "type": "value_error",
            "loc": ("body", "email"),
            "msg": "value is not a valid email address: An email address must have an @-sign.",
        }
    ]
    assert (
        describe_validation_errors(errors)
        == "Email: Enter a valid email address like name@example.com."
    )


def test_required_and_length_and_dedupe():
    errors = [
        {"type": "missing", "loc": ("body", "full_name"), "msg": "Field required"},
        {"type": "string_too_long", "loc": ("body", "headline"), "msg": "x", "ctx": {"max_length": 200}},
        {"type": "missing", "loc": ("body", "full_name"), "msg": "Field required"},
    ]
    assert describe_validation_errors(errors) == (
        "Full name: This is required. Headline: Keep it to 200 characters or fewer."
    )
