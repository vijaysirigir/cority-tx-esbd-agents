"""
Cority ESHQ relevance engine.

Cority is the global leader in EHS+ (Environment, Safety, Health, Quality +
Sustainability/ESG) software. This module decides whether a TX SmartBuy / ESBD
solicitation is a fit for Cority's solutions and, if so, *why* - by scoring the
solicitation text against weighted keyword groups mapped to Cority's product
pillars.

It is deterministic and fully offline (no API keys), so Agent 2 runs instantly
and explains every match. Tune the weights/keywords below to sharpen results.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Each pillar maps to the keywords that signal it. Weight = how strongly a hit
# in this pillar indicates a genuine Cority opportunity.
PILLARS: dict[str, dict] = {
    "Environmental": {
        "weight": 3,
        "keywords": [
            "environmental management", "environmental compliance", "air emissions",
            "air quality", "ghg", "greenhouse gas", "carbon", "emissions tracking",
            "water quality", "wastewater", "waste management", "hazardous waste",
            "spill", "remediation", "permit management", "epa", "environmental data",
            "stormwater", "discharge monitoring",
        ],
    },
    "Safety": {
        "weight": 3,
        "keywords": [
            "safety management", "occupational safety", "incident management",
            "incident reporting", "injury tracking", "injury and illness",
            "osha", "near miss", "hazard", "job safety analysis", "jsa",
            "behavior based safety", "safety observation", "risk assessment",
            "contractor safety", "permit to work", "lockout tagout", "loto",
            "safety data", "ehs", "eh&s", "esh", "workplace safety",
        ],
    },
    "Health": {
        "weight": 3,
        "keywords": [
            "occupational health", "industrial hygiene", "medical surveillance",
            "employee health", "clinic management", "case management",
            "exposure monitoring", "ergonomics", "hearing conservation",
            "respiratory protection", "wellness", "health surveillance",
            "fitness for duty", "workers compensation", "workers' compensation",
        ],
    },
    "Quality": {
        "weight": 3,
        "keywords": [
            "quality management", "quality management system", "qms",
            "document control", "corrective action", "capa", "nonconformance",
            "non-conformance", "management of change", "moc", "supplier quality",
            "audit management", "inspection management", "iso 9001",
            "calibration", "complaint management", "continuous improvement",
        ],
    },
    "Sustainability / ESG": {
        "weight": 2,
        "keywords": [
            "sustainability", "esg", "esg reporting", "sustainability reporting",
            "carbon footprint", "net zero", "decarbonization", "scope 1",
            "scope 2", "scope 3", "ghg inventory", "climate", "csr",
        ],
    },
    "Compliance / Risk": {
        "weight": 2,
        "keywords": [
            "regulatory compliance", "compliance management", "compliance software",
            "enterprise risk", "risk management software", "audit", "inspection",
            "training management", "learning management", "permit tracking",
            "regulatory reporting", "compliance tracking", "ehsq", "eshq",
        ],
    },
}

# Cority sells software, so a "software/platform/SaaS" signal strongly increases
# confidence that a matched solicitation is actually addressable.
SOFTWARE_SIGNALS = [
    "software", "saas", "system", "platform", "application", "module",
    "license", "licence", "subscription", "cloud", "database", "implementation",
    "digital", "automation", "enterprise software", "information system",
    "data management", "web-based", "web based", "solution",
]

# Phrases that usually mean physical services / goods, not Cority software.
# A strong hit here without a software signal drags the score down.
NEGATIVE_SIGNALS = [
    "construction", "road", "asphalt", "paving", "janitorial", "landscaping",
    "catering", "food service", "furniture", "vehicle", "uniform", "plumbing",
    "hvac repair", "demolition", "lawn", "snow removal", "tree", "fuel",
    "groundskeeping", "security guard", "staffing", "temporary labor",
]

# Common ESBD / CSV column names that hold the text we want to score.
# (The live ESBD export uses "Name" for the title and "NIGP Codes" for the
# commodity description — both are included here.)
TEXT_FIELDS = [
    "Name", "Title", "title", "Solicitation Title", "Description", "description",
    "Short Description", "Summary", "Class/Item", "Class Item", "Commodity",
    "NIGP Codes", "NIGP", "Agency", "Notes",
]
ID_FIELDS = ["Solicitation ID", "SolicitationID", "Solicitation", "ID",
             "Solicitation Number", "Number"]


@dataclass
class Match:
    """Scoring result for a single solicitation row."""
    score: int = 0
    pillars: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    software_signal: bool = False
    negative_signal: bool = False
    recommendation: str = ""

    @property
    def is_fit(self) -> bool:
        return self.score >= 3


def _haystack(row: dict) -> str:
    """Concatenate all useful text from a CSV row into one lowercase blob."""
    parts = []
    for k, v in row.items():
        if v is None:
            continue
        parts.append(str(v))
    return " ".join(parts).lower()


def _find(haystack: str, terms: list[str]) -> list[str]:
    hits = []
    for t in terms:
        # word-ish boundary so 'moc' doesn't match 'remote', etc.
        pattern = r"(?<![a-z])" + re.escape(t) + r"(?![a-z])"
        if re.search(pattern, haystack):
            hits.append(t)
    return hits


def score_row(row: dict, min_score: int = 3) -> Match:
    """Score one CSV row for Cority ESHQ relevance."""
    hay = _haystack(row)
    m = Match()

    for pillar, cfg in PILLARS.items():
        hits = _find(hay, cfg["keywords"])
        if hits:
            m.pillars.append(pillar)
            m.keywords.extend(hits)
            m.score += cfg["weight"] + (len(hits) - 1)  # extra weight per add'l hit

    sw = _find(hay, SOFTWARE_SIGNALS)
    if sw:
        m.software_signal = True
        if m.score > 0:
            m.score += 2  # software + EHS topic = strong fit

    neg = _find(hay, NEGATIVE_SIGNALS)
    if neg and not m.software_signal:
        m.negative_signal = True
        m.score = max(0, m.score - 3)

    m.keywords = sorted(set(m.keywords))
    m.pillars = sorted(set(m.pillars))
    m.recommendation = _recommend(m)
    return m


def _recommend(m: Match) -> str:
    if m.score >= 8:
        return "Strong fit - prioritize. Pull full RFP via Agent 3 and route to capture team."
    if m.score >= 5:
        return "Good fit - review RFP details and confirm scope alignment."
    if m.score >= 3:
        return "Possible fit - quick human review recommended."
    return "Low relevance."


def pick_id(row: dict) -> str:
    for f in ID_FIELDS:
        if f in row and str(row[f]).strip():
            return str(row[f]).strip()
    # Fallback: any column whose name contains 'solicit'
    for k, v in row.items():
        if k and "solicit" in k.lower() and str(v).strip():
            return str(v).strip()
    return ""


def pick_title(row: dict) -> str:
    for f in ("Name", "Title", "Solicitation Title", "title", "Description",
              "Summary"):
        if f in row and str(row[f]).strip():
            return str(row[f]).strip()
    return ""
