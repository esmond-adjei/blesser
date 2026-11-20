"""Country names for eligibility checks.

A listing's `countries` holds free text: "Ghana", "Africa", "Global", "ECOWAS
member states". Only entries that are clearly a single country can exclude a
member; anything else (a region, "Global", a typo) keeps the listing in.
"""

import re
import unicodedata

COUNTRIES = (
    "Afghanistan", "Albania", "Algeria", "Andorra", "Angola", "Antigua and Barbuda",
    "Argentina", "Armenia", "Australia", "Austria", "Azerbaijan", "Bahamas", "Bahrain",
    "Bangladesh", "Barbados", "Belarus", "Belgium", "Belize", "Benin", "Bhutan", "Bolivia",
    "Bosnia and Herzegovina", "Botswana", "Brazil", "Brunei", "Bulgaria", "Burkina Faso",
    "Burundi", "Cabo Verde", "Cambodia", "Cameroon", "Canada", "Central African Republic",
    "Chad", "Chile", "China", "Colombia", "Comoros", "Congo", "Costa Rica", "Côte d'Ivoire",
    "Croatia", "Cuba", "Cyprus", "Czechia", "Democratic Republic of the Congo", "Denmark",
    "Djibouti", "Dominica", "Dominican Republic", "Ecuador", "Egypt", "El Salvador",
    "Equatorial Guinea", "Eritrea", "Estonia", "Eswatini", "Ethiopia", "Fiji", "Finland",
    "France", "Gabon", "Gambia", "Georgia", "Germany", "Ghana", "Greece", "Grenada",
    "Guatemala", "Guinea", "Guinea-Bissau", "Guyana", "Haiti", "Honduras", "Hungary",
    "Iceland", "India", "Indonesia", "Iran", "Iraq", "Ireland", "Israel", "Italy", "Jamaica",
    "Japan", "Jordan", "Kazakhstan", "Kenya", "Kiribati", "Kuwait", "Kyrgyzstan", "Laos",
    "Latvia", "Lebanon", "Lesotho", "Liberia", "Libya", "Liechtenstein", "Lithuania",
    "Luxembourg", "Madagascar", "Malawi", "Malaysia", "Maldives", "Mali", "Malta",
    "Marshall Islands", "Mauritania", "Mauritius", "Mexico", "Micronesia", "Moldova",
    "Monaco", "Mongolia", "Montenegro", "Morocco", "Mozambique", "Myanmar", "Namibia",
    "Nauru", "Nepal", "Netherlands", "New Zealand", "Nicaragua", "Niger", "Nigeria",
    "North Korea", "North Macedonia", "Norway", "Oman", "Pakistan", "Palau", "Palestine",
    "Panama", "Papua New Guinea", "Paraguay", "Peru", "Philippines", "Poland", "Portugal",
    "Qatar", "Romania", "Russia", "Rwanda", "Saint Kitts and Nevis", "Saint Lucia",
    "Saint Vincent and the Grenadines", "Samoa", "San Marino", "Sao Tome and Principe",
    "Saudi Arabia", "Senegal", "Serbia", "Seychelles", "Sierra Leone", "Singapore",
    "Slovakia", "Slovenia", "Solomon Islands", "Somalia", "South Africa", "South Korea",
    "South Sudan", "Spain", "Sri Lanka", "Sudan", "Suriname", "Sweden", "Switzerland",
    "Syria", "Taiwan", "Tajikistan", "Tanzania", "Thailand", "Timor-Leste", "Togo", "Tonga",
    "Trinidad and Tobago", "Tunisia", "Turkey", "Turkmenistan", "Tuvalu", "Uganda",
    "Ukraine", "United Arab Emirates", "United Kingdom", "United States", "Uruguay",
    "Uzbekistan", "Vanuatu", "Vatican City", "Venezuela", "Vietnam", "Yemen", "Zambia",
    "Zimbabwe",
)  # fmt: skip

#: Other spellings, keyed by normalized form.
ALIASES = {
    "usa": "United States",
    "us": "United States",
    "u s": "United States",
    "united states of america": "United States",
    "america": "United States",
    "uk": "United Kingdom",
    "u k": "United Kingdom",
    "great britain": "United Kingdom",
    "britain": "United Kingdom",
    "england": "United Kingdom",
    "scotland": "United Kingdom",
    "wales": "United Kingdom",
    "northern ireland": "United Kingdom",
    "ivory coast": "Côte d'Ivoire",
    "cote d ivoire": "Côte d'Ivoire",
    "cape verde": "Cabo Verde",
    "drc": "Democratic Republic of the Congo",
    "dr congo": "Democratic Republic of the Congo",
    "congo kinshasa": "Democratic Republic of the Congo",
    "republic of the congo": "Congo",
    "congo brazzaville": "Congo",
    "swaziland": "Eswatini",
    "the gambia": "Gambia",
    "czech republic": "Czechia",
    "holland": "Netherlands",
    "the netherlands": "Netherlands",
    "uae": "United Arab Emirates",
    "korea": "South Korea",
    "republic of korea": "South Korea",
    "russian federation": "Russia",
    "turkiye": "Turkey",
    "east timor": "Timor-Leste",
    "burma": "Myanmar",
    "viet nam": "Vietnam",
    "lao pdr": "Laos",
    "macedonia": "North Macedonia",
    "myanmar burma": "Myanmar",
    "st kitts and nevis": "Saint Kitts and Nevis",
    "st lucia": "Saint Lucia",
    "st vincent and grenadines": "Saint Vincent and the Grenadines",
    "palestinian territories": "Palestine",
    "cabo verde": "Cabo Verde",
}

#: Nationality words members type in the Applicant Kit ("Ghanaian").
DEMONYMS = {
    "ghanaian": "Ghana",
    "nigerian": "Nigeria",
    "kenyan": "Kenya",
    "togolese": "Togo",
    "beninese": "Benin",
    "ivorian": "Côte d'Ivoire",
    "burkinabe": "Burkina Faso",
    "senegalese": "Senegal",
    "liberian": "Liberia",
    "sierra leonean": "Sierra Leone",
    "gambian": "Gambia",
    "malian": "Mali",
    "nigerien": "Niger",
    "cameroonian": "Cameroon",
    "ugandan": "Uganda",
    "tanzanian": "Tanzania",
    "rwandan": "Rwanda",
    "ethiopian": "Ethiopia",
    "south african": "South Africa",
    "zambian": "Zambia",
    "zimbabwean": "Zimbabwe",
    "egyptian": "Egypt",
    "moroccan": "Morocco",
    "british": "United Kingdom",
    "american": "United States",
    "canadian": "Canada",
    "german": "Germany",
    "french": "France",
    "indian": "India",
    "chinese": "China",
}


#: Accented letters folded the same way in SQL (service.country_gate).
ACCENTED = "áàâäãåçéèêëíìîïñóòôöõúùûüý"
PLAIN = "aaaaaaceeeeiiiinooooouuuuy"
_FOLD = str.maketrans(ACCENTED, PLAIN)


def normalize(text: str) -> str:
    folded = (text or "").lower().translate(_FOLD).replace("&", " and ")
    # Punctuation becomes a space first ("d’Ivoire"), then other accents drop.
    folded = re.sub(r"[^\w ]|_", " ", folded)
    folded = unicodedata.normalize("NFKD", folded).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", folded)).strip()


_BY_KEY = {normalize(name): name for name in COUNTRIES} | ALIASES


def country(text: str) -> str | None:
    """The canonical country for a name, alias or nationality word; None otherwise."""
    key = normalize(text)
    return _BY_KEY.get(key) or DEMONYMS.get(key)


def known_keys() -> list[str]:
    """Every normalized spelling that means exactly one country."""
    return sorted(_BY_KEY)


def keys_for(name: str) -> list[str]:
    """Normalized spellings of one canonical country."""
    return sorted(key for key, value in _BY_KEY.items() if value == name)
