# Country data

`countries.json` contains country names, ISO codes, alternate names and English
demonyms derived from [mledoze/countries](https://github.com/mledoze/countries),
revision `fa4f62182d19ff4f8b325cde6387c9cd9d80955a`. The 250 entries include
territories and Kosovo. ISO official and common names are supplemented from
`pycountry`. Ambiguous demonyms, such as Congolese, are retained as ambiguous.

This derived database is available under the Open Database License 1.0 in
`countries-LICENSE`. Its individual contents use the Database Contents License
linked there. This data license applies to this database, separately from code.

Regenerate from `api/` with `uv run python -m scripts.vendor_autofill_countries`.
The script records the upstream revision so refreshes produce a reviewable diff.
Language codes and Ghana's 16 region names and codes use the installed
`pycountry` ISO datasets.
