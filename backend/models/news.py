"""GovEase - news record shape, vocabularies and serialization.

Single source of truth for the news schema. The API, the collector and
/api/meta all import from here so the category list can never drift
between the backend and the frontend.
"""

import hashlib
import re

# --- Controlled vocabularies (spec section 6) -------------------------------

CATEGORIES = [
    "Schemes",
    "Announcements",
    "Policies",
    "Notifications",
    "Citizen Services",
    "Eligibility Updates",
    "Deadlines",
    "Education",
    "Employment",
    "Agriculture",
    "Health",
    "Other",
]

IMPORTANCE_LEVELS = ["high", "normal", "low"]

STATE_LEVELS = ["Central", "State"]

DEFAULT_CATEGORY = "Other"
DEFAULT_IMPORTANCE = "normal"

# Keyword hints used to refine a source's default category. First match wins,
# so the order here is the priority order.
CATEGORY_KEYWORDS = [
    ("Schemes", ("scheme", "yojana", "abhiyan", "mission", "subsidy", "grant")),
    ("Deadlines", ("last date", "deadline", "extended", "closing date", "due date")),
    ("Eligibility Updates", ("eligibility", "eligible", "criteria", "qualify")),
    ("Employment", ("recruitment", "vacancy", "employment", "job", "hiring")),
    ("Education", ("education", "student", "school", "university", "exam", "scholarship")),
    ("Health", ("health", "hospital", "medical", "ayush", "disease", "vaccine")),
    ("Agriculture", ("agriculture", "farmer", "crop", "kisan", "irrigation")),
    ("Policies", ("policy", "framework", "guideline", "regulation", "amendment", "reform")),
    ("Notifications", ("notification", "circular", "notice", "order", "directive")),
    ("Citizen Services", ("citizen", "service", "portal", "helpline", "grievance", "consumer")),
    ("Announcements", ("announce", "launch", "inaugurat", "press release")),
]

# Hosts we accept as genuinely official for the verified badge.
# Kept as an exact-match set plus a dotted-suffix set on purpose: a bare
# "gov.in" suffix test would also accept "notgov.in" or "fakegov.in".
GOVERNMENT_DOMAINS_EXACT = ("gov.in", "nic.in")
GOVERNMENT_DOMAIN_SUFFIXES = (".gov.in", ".nic.in")

# A few official bodies publish from their own domain rather than gov.in.
# Each entry here was checked by hand against the body's real website; do not
# add a host you have not verified the same way. Keeping this as an explicit
# short list, rather than relaxing the suffix rule, is what stops a lookalike
# domain from earning the verified badge.
GOVERNMENT_EXTRA_HOSTS = (
    "rbi.org.in",     # Reserve Bank of India
    "mygov.in",       # MyGov, Government of India
)

# --- Field list -------------------------------------------------------------

NEWS_FIELDS = [
    "id", "title", "summary", "content", "category", "department",
    "published_date", "detected_at", "last_checked",
    "source_name", "source_url", "state_level", "importance",
    "tags", "deadline", "location", "image_url",
    "content_hash", "data_origin",
]


def categorize(title, summary="", default=DEFAULT_CATEGORY):
    """Pick a category from text, falling back to the source's default."""
    haystack = f"{title} {summary}".lower()
    for category, keywords in CATEGORY_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            return category
    return default if default in CATEGORIES else DEFAULT_CATEGORY


def make_content_hash(title, source_url):
    """Stable identity for an update, used for deduplication.

    Normalizes whitespace and case so the same item re-published with
    cosmetic differences does not create a duplicate row.
    """
    normalized_title = re.sub(r"\s+", " ", (title or "").strip().lower())
    normalized_url = (source_url or "").strip().lower()
    return hashlib.sha256(f"{normalized_title}|{normalized_url}".encode("utf-8")).hexdigest()


def is_official_source(source_url):
    """True only for real government hosts - drives the verified badge.

    The frontend must not show 'Verified Government Source' for anything
    else, per spec section 9.
    """
    if not source_url:
        return False
    match = re.match(r"^https?://([^/:?#]+)", source_url.strip(), re.IGNORECASE)
    if not match:
        return False
    host = match.group(1).lower().rstrip(".")
    if host in GOVERNMENT_DOMAINS_EXACT or host.endswith(GOVERNMENT_DOMAIN_SUFFIXES):
        return True
    return any(
        host == extra or host.endswith("." + extra) for extra in GOVERNMENT_EXTRA_HOSTS
    )


def row_to_dict(row):
    """sqlite3.Row -> JSON-ready dict matching the documented API contract."""
    if row is None:
        return None
    item = {field: row[field] for field in NEWS_FIELDS if field in row.keys()}
    raw_tags = item.get("tags") or ""
    item["tags"] = [t.strip() for t in raw_tags.split(",") if t.strip()]
    item["is_official_source"] = is_official_source(item.get("source_url"))
    return item
