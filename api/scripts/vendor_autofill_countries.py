import json
from pathlib import Path
from urllib.request import urlopen

import pycountry

REVISION = "fa4f62182d19ff4f8b325cde6387c9cd9d80955a"
SOURCE = f"https://raw.githubusercontent.com/mledoze/countries/{REVISION}"
DESTINATION = Path(__file__).resolve().parents[1] / "api/autofill/data"


def main():
    with urlopen(f"{SOURCE}/countries.json", timeout=30) as response:
        countries = json.load(response)
    rows = []
    for item in countries:
        iso = pycountry.countries.get(alpha_2=item["cca2"])
        names = [item["name"]["common"], item["name"]["official"]]
        names.extend(item["altSpellings"])
        if iso:
            names.extend(
                getattr(iso, key, "")
                for key in ("name", "official_name", "common_name")
            )
        rows.append(
            {
                "alpha_2": item["cca2"],
                "alpha_3": item["cca3"],
                "numeric": item["ccn3"],
                "name": item["name"]["common"],
                "names": sorted(set(filter(None, names))),
                "demonyms": sorted(set(item["demonyms"]["eng"].values())),
            }
        )
    DESTINATION.mkdir(exist_ok=True)
    (DESTINATION / "countries.json").write_text(
        json.dumps(
            sorted(rows, key=lambda row: row["alpha_2"]), ensure_ascii=False, indent=2
        )
        + "\n"
    )
    with urlopen(f"{SOURCE}/LICENSE", timeout=30) as response:
        (DESTINATION / "countries-LICENSE").write_bytes(response.read())


if __name__ == "__main__":
    main()
