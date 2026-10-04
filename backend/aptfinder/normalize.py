import re
from dataclasses import dataclass

STREET_SUFFIXES = {
    "avenue": "ave", "av": "ave", "street": "st", "drive": "dr", "boulevard": "blvd", "road": "rd",
    "court": "ct", "lane": "ln", "place": "pl", "terrace": "ter", "parkway": "pkwy", "expressway": "expy",
    "circle": "cir", "highway": "hwy", "square": "sq", "plaza": "plz", "way": "way", "real": "real",
}
DIRECTIONALS = {"north": "n", "south": "s", "east": "e", "west": "w"}
UNIT_DESIGNATOR = re.compile(r"\s(?:#|apt\b|apartment\b|unit\b|ste\b|suite\b|spc\b|space\b|bldg\b|building\b).*$")


def normalize_street_address(street: str | None) -> str | None:
    if not street:
        return None
    text = street.lower().strip()
    text = re.sub(r"[.,]", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = UNIT_DESIGNATOR.sub("", " " + text).strip()
    tokens = [DIRECTIONALS.get(t, STREET_SUFFIXES.get(t, t)) for t in text.split()]
    if not tokens or not re.match(r"^\d+[a-z]?$", tokens[0]):
        return None
    return " ".join(tokens)


def extract_unit_number(street: str | None) -> str | None:
    if not street:
        return None
    match = re.search(r"(?:#|\bapt\b|\bunit\b|\bste\b|\bspc\b)\s*([\w-]+)\s*$", street, re.I)
    return match.group(1) if match else None


MONEY = re.compile(r"\$+\s?(\d[\d,]*(?:\.\d{1,2})?)")
MONTHLY = re.compile(r"(/\s?mo\b|/\s?month|per month|monthly|a month|/mon\b)", re.I)
ONE_TIME = re.compile(r"(one[- ]time|per applicant|application|deposit|move[- ]in|admin)", re.I)

FEE_TYPE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("trash", ("trash", "garbage", "waste", "valet")),
    ("parking", ("parking", "garage", "carport", "permit")),
    ("internet", ("internet", "wifi", "wi-fi", "cable", "tech package", "technology", "broadband")),
    ("utilities", ("utilit", "water", "sewer", "electric", "gas", "rubs", "energy")),
    ("amenity", ("amenity", "amenities", "community fee", "facility")),
    ("pet", ("pet", "dog", "cat")),
    ("insurance", ("insurance",)),
    ("storage", ("storage",)),
)


@dataclass(frozen=True)
class ParsedFee:
    fee_type: str
    description: str
    amount: int | None
    amount_text: str | None
    recurring: bool | None
    mandatory: bool | None


def classify_fee_type(text: str) -> str:
    lowered = text.lower()
    for fee_type, keywords in FEE_TYPE_KEYWORDS:
        if any(k in lowered for k in keywords):
            return fee_type
    return "other"


def parse_fee_text(text: str | None, *, assume_mandatory: bool | None = None) -> list[ParsedFee]:
    """Splits free-text fee disclosures into fee items without guessing amounts that are not stated."""
    if not text or not text.strip():
        return []
    parts = [p.strip() for p in re.split(r"[;\n]|,(?![^()]*\))(?!\s*\d{3}\b)", text) if p.strip()]
    fees = []
    for part in parts:
        amounts = MONEY.findall(part)
        amount = None
        amount_text = None
        if amounts:
            amount_text = MONEY.search(part).group(0)
            if len(amounts) == 1:
                amount = round(float(amounts[0].replace(",", "")))
            else:
                amount_text = part[MONEY.search(part).start():].strip()
        if MONTHLY.search(part):
            recurring = True
        elif ONE_TIME.search(part):
            recurring = False
        else:
            recurring = None
        lowered = part.lower()
        if re.search(r"\b(required|mandatory|must)\b", lowered):
            mandatory = True
        elif "optional" in lowered:
            mandatory = False
        else:
            mandatory = assume_mandatory
        fees.append(ParsedFee(classify_fee_type(part), part, amount, amount_text, recurring, mandatory))
    return fees


WORD_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "half": 0.5}
FREE_PERIOD = re.compile(r"(\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|half)(?:\s|-)(?:a\s)?(week|month)s?\s+(?:of\s+)?free", re.I)
HEDGES = re.compile(r"\b(up to|select|selected|certain|qualified|may|some)\b", re.I)


@dataclass(frozen=True)
class PromotionTerms:
    text: str
    free_weeks: float | None
    is_definite: bool


def parse_promotion(text: str | None) -> PromotionTerms | None:
    if not text or not text.strip():
        return None
    match = FREE_PERIOD.search(text)
    free_weeks = None
    if match:
        raw, period = match.group(1).lower(), match.group(2).lower()
        quantity = WORD_NUMBERS.get(raw)
        if quantity is None:
            quantity = float(raw)
        free_weeks = quantity * (52 / 12 if period == "month" else 1)
    return PromotionTerms(text=text.strip(), free_weeks=free_weeks, is_definite=free_weeks is not None and not HEDGES.search(text))


def estimate_effective_rent(base_rent: int, lease_term_months: int | None, promo: PromotionTerms | None) -> tuple[int | None, str | None]:
    """Only computes an effective rent when the promotion is unconditional and the lease term is known."""
    if promo is None or not promo.is_definite or not promo.free_weeks or not lease_term_months:
        return None, None
    lease_weeks = lease_term_months * 52 / 12
    if promo.free_weeks >= lease_weeks:
        return None, None
    effective = round(base_rent * (lease_weeks - promo.free_weeks) / lease_weeks)
    method = (
        f"Derived: ${base_rent:,} × ({lease_weeks:.1f} − {promo.free_weeks:g} free weeks) / {lease_weeks:.1f} weeks "
        f"for a {lease_term_months}-month lease. Not a quoted price."
    )
    return effective, method
