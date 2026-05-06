from __future__ import annotations

TAG_KEYWORDS: dict[str, list[str]] = {
    "music": [
        "music", "concert", "gig", "live band", "live music", "performance",
        "album launch", "open mic", "jam session",
    ],
    "festival": [
        "festival", "festivals", "fest", "music festival", "food festival", "wine festival",
        "beer festival", "street festival", "cultural festival", "arts festival",
        "film festival", "jazz festival", "outdoor festival", "summer festival",
        "winter festival", "day festival", "weekend festival",
    ],
    "dj": [
        "dj", "deejay", "dancefloor", "techno", "house", "deep house",
        "edm", "trance", "psytrance", "drum and bass", "dnb", "afro house",
    ],
    "club": [
        "club", "nightclub", "party", "rave", "afterparty", "dance party",
        "late night",
    ],
    "bar": [
        "bar", "pub", "cocktail", "cocktails", "beer", "wine", "drinks",
        "happy hour", "taproom", "brewery",
    ],
    "food": [
        "food", "dinner", "lunch", "brunch", "breakfast", "tasting",
        "wine pairing", "street food", "restaurant", "menu", "feast",
    ],
    "market": [
        "market", "night market", "food market", "flea market", "craft market",
        "stalls", "vendors", "pop-up",
    ],
    "comedy": [
        "comedy", "stand-up", "standup", "comedian", "improv", "open mic comedy",
    ],
    "art": [
        "art", "gallery", "exhibition", "installation", "painting",
        "sculpture", "first thursday", "creative",
    ],
    "theatre": [
        "theatre", "theater", "play", "drama", "musical", "stage",
        "cabaret", "opera",
    ],
    "outdoors": [
        "outdoor", "outdoors", "hike", "trail", "run", "beach", "park",
        "sunset", "picnic", "cycling",
    ],
    "sports": [
        "sports", "sport", "rugby", "football", "soccer", "cricket",
        "running", "race", "marathon", "trail run", "cycling",
    ],
    "family": [
        "family", "kids", "children", "child-friendly", "family-friendly",
        "all ages",
    ],
    "date-night": [
        "date night", "romantic", "couples", "sunset", "wine tasting",
        "dinner", "rooftop", "cinema under the stars",
    ],
    "free": [
        "free", "free entry", "no cover", "complimentary", "rsvp free",
    ],
    "cheap": [
        "r50", "r60", "r80", "r100", "under r100", "affordable", "budget",
    ],
    "premium": [
        "vip", "premium", "exclusive", "luxury", "fine dining",
        "champagne", "private table",
    ],
}


EXCLUDE_KEYWORDS: list[str] = [
    "high school", "hoërskool", "hoerskool", "primary school", "laerskool",
    "junior school", "junior skool",
    "learners", "leerders", "pupils", "leerlinge", "students", "studente",
    "matric", "matriek", "grade 8", "graad 8", "grade 9", "graad 9",
    "grade 10", "graad 10", "grade 11", "graad 11", "grade 12", "graad 12",
    "school fundraiser", "skool fondsinsameling", "school concert", "skoolkonsert",
    "school play", "skool toneel", "school fair", "skoolmark", "school market",
    "school reunion", "skoolreünie", "skoolreunie", "school sports", "skoolsport",
]


def tag_event(title: str, venue: str = "", description: str = "") -> list[str]:
    text = f"{title} {venue} {description}".lower()
    return [tag for tag, keywords in TAG_KEYWORDS.items() if any(kw in text for kw in keywords)]


def is_excluded_event(title: str, venue: str = "", description: str = "") -> bool:
    text = f"{title} {venue} {description}".lower()
    return any(kw in text for kw in EXCLUDE_KEYWORDS)
