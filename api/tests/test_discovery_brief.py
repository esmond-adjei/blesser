from api.prospects.tasks import _field_line, _region_line


def test_region_line():
    for value in ("Anywhere", "anywhere", "", None):
        assert _region_line(value).startswith("Anywhere (no regional preference")
    assert _region_line("Canada, United States") == "Canada, United States"


def test_field_line():
    for value in ("", "  ", None):
        assert _field_line(value) == "(not given: read it from the interest statement)"
    assert _field_line(" Robotics ") == "Robotics"
