"""City of Taguig barangays, including the 10 EMBO barangays.

Source: PSA PSGC; checked against it by the maintainer (2026-11-26).
"""

from django.utils.text import slugify

_NAMES = [
    "Bagumbayan",
    "Bambang",
    "Calzada",
    "Cembo",
    "Central Bicutan",
    "Central Signal Village",
    "Comembo",
    "East Rembo",
    "Fort Bonifacio",
    "Hagonoy",
    "Ibayo-Tipas",
    "Katuparan",
    "Ligid-Tipas",
    "Lower Bicutan",
    "Maharlika Village",
    "Napindan",
    "New Lower Bicutan",
    "North Daang Hari",
    "North Signal Village",
    "Palingon",
    "Pembo",
    "Pinagsama",
    "Pitogo",
    "Post Proper Northside",
    "Post Proper Southside",
    "Rizal",
    "San Miguel",
    "Santa Ana",
    "South Cembo",
    "South Daang Hari",
    "South Signal Village",
    "Tanyag",
    "Tuktukan",
    "Upper Bicutan",
    "Ususan",
    "Wawa",
    "West Rembo",
    "Western Bicutan",
]

OUTSIDE_TAGUIG = "outside-taguig"

BARANGAYS: list[tuple[str, str]] = [(slugify(name), name) for name in _NAMES] + [
    (OUTSIDE_TAGUIG, "I don't live in Taguig")
]

TAGUIG_BARANGAYS: frozenset[str] = frozenset(value for value, _ in BARANGAYS[:-1])
