"""
Cority Opportunity Scoring Engine  (the brain of Agent 2)
=========================================================

Implements the multi-factor procurement-analyst scoring model:

    Opportunity Score (0-100) =
        Keyword Density      x 0.20
      + Semantic Similarity  x 0.30
      + Agency Fit           x 0.15
      + Technology Intent    x 0.20
      + Budget Potential     x 0.15

Each sub-score is 0-100. The engine is deterministic and fully offline (no API
keys, no heavyweight ML), so it runs instantly and can explain every number.

"Semantic similarity" is implemented as TF-IDF cosine similarity between the
solicitation text and a curated solution profile for each Cority pillar — a real
vector-space cosine method. It can later be swapped for transformer/API
embeddings without touching the rest of the pipeline (see semantic_similarity()).

Outputs per solicitation:
  * the five sub-scores + final Opportunity Score
  * action tier (Immediate Executive Review ... Archive)
  * ranked recommended Cority modules with confidence
  * an executive summary (overview, why Cority fits, requirements, risks,
    likely competitors, sales actions, discovery questions)
  * extracted solicitation metadata (what the CSV exposes; the rest is
    enriched later by Agent 3)
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

from agents import cority_keywords as ck

# ---------------------------------------------------------------------------
# 1. Weights (must sum to 1.0)
# ---------------------------------------------------------------------------
WEIGHTS = {
    "keyword": 0.20,
    "semantic": 0.30,
    "agency": 0.15,
    "technology": 0.20,
    "budget": 0.15,
}

# ---------------------------------------------------------------------------
# 2. Cority solution profiles — one rich document per pillar. These are the
#    reference vectors the solicitation text is compared against (cosine).
# ---------------------------------------------------------------------------
PILLAR_PROFILES: dict[str, str] = {
    "Environmental": (
        "environmental management compliance air emissions monitoring waste "
        "management hazardous waste water wastewater stormwater discharge "
        "environmental reporting permits spill remediation epa clean air clean "
        "water sustainability emissions tracking environmental data management"
    ),
    "Health": (
        "occupational health medical surveillance industrial hygiene exposure "
        "monitoring employee health clinic case management ergonomics hearing "
        "conservation respiratory protection health surveillance fitness for "
        "duty workers compensation employee wellness occupational medicine"
    ),
    "Safety": (
        "safety management occupational safety incident management incident "
        "reporting injury illness tracking osha near miss hazard identification "
        "risk assessment job safety analysis behavior based safety observations "
        "contractor management permit to work lockout tagout corrective actions "
        "workplace safety ehs management system"
    ),
    "Quality": (
        "quality management system qms document control corrective action "
        "preventive action capa nonconformance non conformance management of "
        "change supplier quality audit management inspection management iso 9001 "
        "calibration complaint management continuous improvement quality assurance"
    ),
    "Sustainability": (
        "sustainability esg reporting environmental social governance carbon "
        "accounting greenhouse gas ghg emissions inventory scope 1 scope 2 "
        "scope 3 climate risk net zero decarbonization carbon footprint "
        "sustainability management corporate social responsibility disclosure"
    ),
}

# ---------------------------------------------------------------------------
# 3. Agency Fit — sectors where Cority wins, with cue words.
# ---------------------------------------------------------------------------
AGENCY_SECTORS: dict[str, list[str]] = {
    "Energy / Utilities": ["energy", "utility", "utilities", "electric", "power",
                            "gas", "oil", "pipeline", "grid"],
    "Water": ["water", "wastewater", "river authority", "water district",
              "municipal water", "water authority"],
    "Transportation": ["transportation", "transit", "dot", "txdot", "highway",
                       "aviation", "airport", "port", "rail", "fleet"],
    "Manufacturing": ["manufacturing", "industrial", "plant", "production",
                      "chemical", "refinery"],
    "Public Works": ["public works", "facilities", "infrastructure",
                     "general land office", "buildings"],
    "Environmental Agencies": ["environmental quality", "tceq", "parks and "
                               "wildlife", "natural resources", "commission on "
                               "environmental"],
    "Universities / Education": ["university", "college", "a&m", "state "
                                 "university", "academic", "campus", "school "
                                 "district", "education"],
    "Healthcare": ["health", "hospital", "medical", "health services",
                   "state hospital", "health and human"],
}

# ---------------------------------------------------------------------------
# 4. Technology Intent phrases (Cority sells software).
# ---------------------------------------------------------------------------
TECH_PHRASES = [
    "software", "saas", "cloud", "platform", "system", "application",
    "module", "license", "licence", "subscription", "data hosting",
    "web-based", "web based", "database", "enterprise application",
    "management system", "compliance software", "reporting platform",
    "information system", "digital", "implementation", "automation",
    "data management", "ehs management", "incident management system",
]

# ---------------------------------------------------------------------------
# 5. Budget Potential signals (scale / scope / duration).
# ---------------------------------------------------------------------------
BUDGET_SIGNALS = [
    "statewide", "state-wide", "enterprise", "enterprise-wide", "agency-wide",
    "system-wide", "multiple locations", "multiple sites", "all facilities",
    "districts", "multi-year", "multi year", "term contract", "master "
    "agreement", "indefinite delivery", "idiq", "annual", "renewal",
    "department-wide", "nationwide", "all agencies",
]
LARGE_AGENCY_CUES = ["health and human", "txdot", "department of", "university "
                     "of", "a&m system", "general land office", "comptroller",
                     "commission", "state of texas"]

# ---------------------------------------------------------------------------
# 6. Recommended-module mapping: Cority module -> trigger concepts.
# ---------------------------------------------------------------------------
MODULE_TRIGGERS: dict[str, list[str]] = {
    "Incident Management": ["incident", "near miss", "injury", "illness",
                            "accident", "osha recordkeeping"],
    "Safety Management": ["safety management", "safety program", "ehs", "esh",
                          "workplace safety", "occupational safety"],
    "Hazard Identification & Risk Assessment": ["hazard", "risk assessment",
                                                "job safety analysis", "jsa",
                                                "risk management"],
    "Contractor Management": ["contractor", "contractor safety",
                              "contractor management"],
    "Permit to Work": ["permit to work", "permit", "lockout", "tagout"],
    "Corrective Actions / CAPA": ["corrective action", "capa", "preventive "
                                  "action"],
    "Audits & Inspections": ["audit", "inspection", "compliance audit"],
    "Quality Management": ["quality management", "qms", "nonconformance",
                           "non-conformance", "iso 9001", "calibration"],
    "Environmental Compliance": ["environmental", "air emissions", "waste",
                                 "water", "wastewater", "epa", "spill",
                                 "stormwater", "permit management"],
    "Occupational Health": ["occupational health", "medical surveillance",
                            "industrial hygiene", "exposure", "clinic",
                            "employee health"],
    "Sustainability / ESG": ["esg", "sustainability", "carbon", "ghg",
                             "greenhouse gas", "climate", "net zero",
                             "emissions inventory"],
}

# Likely competitors, surfaced by dominant pillar.
COMPETITORS_BY_PILLAR = {
    "Safety": ["VelocityEHS", "Intelex", "Benchmark Gensuite", "Enablon"],
    "Environmental": ["Enablon", "Sphera", "VelocityEHS", "Intelex"],
    "Health": ["Medgate (Cority legacy)", "Enablon", "VelocityEHS"],
    "Quality": ["ETQ Reliance", "MasterControl", "Intelex"],
    "Sustainability": ["Sphera", "Watershed", "Persefoni", "Enablon"],
}

_STOP = set("the a an and or of for to in on with by from at as is are be this "
            "that these those will shall must may can any all other includes "
            "including provide provided services service request proposal rfp "
            "rfq solicitation texas state agency department".split())

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9\-&']+")


# ---------------------------------------------------------------------------
@dataclass
class Analysis:
    solicitation_id: str = ""
    title: str = ""
    agency: str = ""
    due: str = ""
    subscores: dict = field(default_factory=dict)     # keyword/semantic/...
    score: int = 0
    action: str = ""
    tier: str = ""
    pillars: list = field(default_factory=list)
    modules: list = field(default_factory=list)        # [{module, confidence}]
    matched_concepts: list = field(default_factory=list)
    competitors: list = field(default_factory=list)
    why_fits: str = ""
    risks: list = field(default_factory=list)
    sales_actions: list = field(default_factory=list)
    discovery_questions: list = field(default_factory=list)
    executive_summary: str = ""
    extracted: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Tokenisation + TF-IDF cosine (the "semantic similarity")
# ---------------------------------------------------------------------------
def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall((text or "").lower())
            if t not in _STOP and len(t) > 1]


# Precompute pillar document-frequency for IDF (corpus = the pillar profiles).
_PILLAR_TOKENS = {p: _tokens(t) for p, t in PILLAR_PROFILES.items()}
_N_DOCS = len(_PILLAR_TOKENS)
_DF: Counter = Counter()
for _toks in _PILLAR_TOKENS.values():
    for _t in set(_toks):
        _DF[_t] += 1


def _idf(term: str) -> float:
    # smoothed idf over the pillar corpus
    return math.log((_N_DOCS + 1) / (_DF.get(term, 0) + 1)) + 1.0


def _tfidf_vec(tokens: list[str]) -> dict[str, float]:
    tf = Counter(tokens)
    n = max(len(tokens), 1)
    return {t: (c / n) * _idf(t) for t, c in tf.items()}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(a[t] * b[t] for t in common)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


_PILLAR_VECS = {p: _tfidf_vec(toks) for p, toks in _PILLAR_TOKENS.items()}


def semantic_similarity(text: str) -> tuple[int, dict[str, float]]:
    """TF-IDF cosine of `text` against each Cority pillar profile.

    Returns (0-100 score, {pillar: raw_cosine}). The best-matching pillars
    drive the score; a small breadth bonus rewards multi-pillar relevance.
    Swap the body of this function for API/transformer embeddings to upgrade.
    """
    vec = _tfidf_vec(_tokens(text))
    sims = {p: _cosine(vec, pv) for p, pv in _PILLAR_VECS.items()}
    ordered = sorted(sims.values(), reverse=True)
    best = ordered[0] if ordered else 0.0
    second = ordered[1] if len(ordered) > 1 else 0.0
    # Raw short-text cosines run ~0.05-0.45; scale so a strong match -> ~90.
    raw = best * 0.85 + second * 0.15
    score = round(_saturate(raw, full=0.36) * 100)
    return min(100, score), sims


def _saturate(x: float, full: float) -> float:
    """Map x in [0, full] -> [0,1] with gentle easing past `full`."""
    if x <= 0:
        return 0.0
    return min(1.0, (x / full) ** 0.85)


# ---------------------------------------------------------------------------
# Sub-scores
# ---------------------------------------------------------------------------
_ALL_KEYWORDS: list[str] = sorted({kw for cfg in ck.PILLARS.values()
                                   for kw in cfg["keywords"]})


def _find(text: str, terms: list[str]) -> list[str]:
    low = text.lower()
    hits = []
    for t in terms:
        pat = r"(?<![a-z])" + re.escape(t.lower()) + r"(?![a-z])"
        if re.search(pat, low):
            hits.append(t)
    return hits


def keyword_density(text: str) -> tuple[int, list[str]]:
    """Coverage (# unique EHSQ keywords) blended with density per 1000 words."""
    toks = _tokens(text)
    nwords = max(len(toks), 1)
    hits = _find(text, _ALL_KEYWORDS)
    unique = len(hits)
    # total occurrences (count repeats)
    low = text.lower()
    total = sum(len(re.findall(r"(?<![a-z])" + re.escape(k.lower()) + r"(?![a-z])", low))
                for k in hits)
    density = total / nwords * 1000.0
    coverage_pts = min(100.0, unique * 18.0)
    density_pts = min(100.0, density * 3.0)
    score = round(0.6 * coverage_pts + 0.4 * density_pts)
    return min(100, score), hits


def agency_fit(text: str, agency: str) -> tuple[int, list[str]]:
    """Sector match against Cority's strongest verticals. Falls back to a
    neutral baseline when the CSV only exposes an agency *number*."""
    blob = f"{agency} {text}"
    # Word-boundary match so cues like 'port' don't match inside 'support'.
    matched = [sector for sector, cues in AGENCY_SECTORS.items()
               if _find(blob, cues)]
    if matched:
        return (88 if len(matched) == 1 else 100), matched
    # No clear sector. If we have a real agency name, mild signal; if it's just
    # a number/blank (CSV limitation), stay neutral — Agent 3 enriches this.
    has_name = bool(re.search(r"[a-z]{4,}", agency or ""))
    return (50 if has_name else 60), []


def technology_intent(text: str) -> tuple[int, list[str]]:
    hits = _find(text, TECH_PHRASES)
    score = min(100, len(hits) * 38)
    return score, hits


def budget_potential(text: str, agency: str, estimated_value: str = "") -> tuple[int, list[str]]:
    blob = f"{agency} {text}".lower()
    signals = _find(blob, BUDGET_SIGNALS)
    score = 40 + 15 * len(signals)            # baseline 40 (unknown at CSV stage)
    if any(c in blob for c in LARGE_AGENCY_CUES):
        score += 10
    val = _parse_money(estimated_value)
    if val:
        score = max(score, 60 + min(35, int(val / 1_000_000) * 5))
    return min(100, score), signals


def _parse_money(s: str) -> float:
    if not s:
        return 0.0
    m = re.search(r"[\d,]+(?:\.\d+)?", s.replace("$", ""))
    if not m:
        return 0.0
    try:
        v = float(m.group(0).replace(",", ""))
    except ValueError:
        return 0.0
    if "m" in s.lower() or "million" in s.lower():
        v *= 1_000_000
    return v


# ---------------------------------------------------------------------------
# Modules + tiers + summary
# ---------------------------------------------------------------------------
def recommended_modules(text: str, semantic: int) -> tuple[list[dict], list[str]]:
    out = []
    concepts: list[str] = []
    for module, triggers in MODULE_TRIGGERS.items():
        hits = _find(text, triggers)
        if hits:
            concepts.extend(hits)
            conf = min(98, 55 + 11 * len(hits) + semantic // 6)
            out.append({"module": module, "confidence": conf})
    out.sort(key=lambda m: m["confidence"], reverse=True)
    return out, sorted(set(concepts))


def tier_for(score: int) -> tuple[str, str]:
    if score >= 90:
        return "Immediate Executive Review", "exec"
    if score >= 80:
        return "High Priority Opportunity", "high"
    if score >= 70:
        return "Sales Review", "sales"
    if score >= 60:
        return "Monitor", "monitor"
    return "Archive", "archive"


def analyze(row: dict) -> Analysis:
    """Run the full multi-factor analysis on one CSV row."""
    text = _row_text(row)
    sid = ck.pick_id(row)
    title = ck.pick_title(row)
    agency = _row_agency(row)
    due = _row_due(row)

    kw_score, kw_hits = keyword_density(text)
    sem_score, sims = semantic_similarity(text)
    ag_score, ag_sectors = agency_fit(text, agency)
    tech_score, tech_hits = technology_intent(text)
    bud_score, bud_signals = budget_potential(text, agency)

    final = round(
        kw_score * WEIGHTS["keyword"]
        + sem_score * WEIGHTS["semantic"]
        + ag_score * WEIGHTS["agency"]
        + tech_score * WEIGHTS["technology"]
        + bud_score * WEIGHTS["budget"]
    )
    final = max(0, min(100, final))
    action, tier = tier_for(final)

    pillars = [p for p, s in sorted(sims.items(), key=lambda kv: kv[1],
                                    reverse=True) if s > 0.04][:3]
    modules, concepts = recommended_modules(text, sem_score)
    competitors = _competitors(pillars)

    a = Analysis(
        solicitation_id=sid, title=title, agency=agency, due=due,
        subscores={"keyword": kw_score, "semantic": sem_score,
                   "agency": ag_score, "technology": tech_score,
                   "budget": bud_score},
        score=final, action=action, tier=tier, pillars=pillars,
        modules=modules, matched_concepts=concepts, competitors=competitors,
    )
    a.why_fits = _why(a, kw_hits, tech_hits)
    a.risks = _risks(a, tech_score, ag_sectors, agency)
    a.sales_actions = _sales_actions(a)
    a.discovery_questions = _discovery(a)
    a.extracted = _extract_metadata(row, sid, title, due)
    a.executive_summary = _exec_summary(a)
    return a


# ---------------------------------------------------------------------------
# Field helpers
# ---------------------------------------------------------------------------
def _row_text(row: dict) -> str:
    return " ".join(str(v) for v in row.values() if v is not None)


def _row_agency(row: dict) -> str:
    for k, v in row.items():
        if k and ("agency" in k.lower() or "member name" in k.lower()
                  or "organization" in k.lower()) and str(v).strip():
            return str(v).strip()
    return ""


def _row_due(row: dict) -> str:
    for k, v in row.items():
        if k and "due" in k.lower() and str(v).strip():
            return str(v).strip()
    return ""


def _extract_metadata(row: dict, sid: str, title: str, due: str) -> dict:
    """The schema from the prompt. CSV exposes a subset; the rest is enriched
    by Agent 3 from the detail page (left blank here)."""
    def g(*names):
        for n in names:
            for k, v in row.items():
                if k and n in k.lower() and str(v).strip():
                    return str(v).strip()
        return ""
    from urllib.parse import quote
    import config
    return {
        "solicitation_id": sid,
        "solicitation_title": title,
        "status": g("status"),
        "contact_name": "",
        "contact_number": "",
        "contact_email": "",
        "bid_response_email": "",
        "response_due_date": due,
        "response_due_time": g("due time", "time"),
        "agency": _row_agency(row) or g("agency"),
        "posting_requirement": g("posting"),
        "procurement_type": g("type"),
        "contract_term": "",
        "estimated_value": "",
        "vendor_questions_deadline": "",
        "source_url": config.DETAIL_URL_TEMPLATE.format(id=quote(str(sid))) if sid else "",
    }


def _competitors(pillars: list[str]) -> list[str]:
    out: list[str] = []
    for p in pillars:
        for c in COMPETITORS_BY_PILLAR.get(p, []):
            if c not in out:
                out.append(c)
    return out[:5] or ["VelocityEHS", "Intelex", "Enablon"]


def _why(a: Analysis, kw_hits: list[str], tech_hits: list[str]) -> str:
    parts = []
    if a.pillars:
        parts.append("Aligns with Cority's "
                     + ", ".join(a.pillars) + " solution area(s).")
    if a.modules:
        parts.append("Maps to " + ", ".join(m["module"] for m in a.modules[:3]) + ".")
    if tech_hits:
        parts.append("Shows software/technology intent ("
                     + ", ".join(sorted(set(tech_hits))[:4]) + ").")
    if kw_hits:
        parts.append("EHSQ language present: "
                     + ", ".join(sorted(set(kw_hits))[:6]) + ".")
    return " ".join(parts) or "Limited EHSQ signal in the listing metadata."


def _risks(a: Analysis, tech_score: int, ag_sectors: list[str], agency: str) -> list[str]:
    r = []
    if tech_score < 40:
        r.append("Low software intent in the listing — may be a services/goods "
                 "buy rather than a platform purchase. Confirm via full RFP.")
    if not ag_sectors and not re.search(r"[a-z]{4,}", agency or ""):
        r.append("Agency only shown as a member number in the CSV — verify the "
                 "buying organization and sector (Agent 3 pulls this).")
    if a.subscores["budget"] < 50:
        r.append("Scope/budget unclear from the listing — confirm deployment "
                 "size and contract term in the solicitation documents.")
    if a.score < 70:
        r.append("Borderline fit — human review recommended before pursuing.")
    return r or ["No major risks flagged from the listing metadata."]


def _sales_actions(a: Analysis) -> list[str]:
    if a.tier in ("exec", "high"):
        return ["Pull the full RFP + attachments (Agent 3).",
                "Route to the named capture/sales owner immediately.",
                "Confirm bid timeline and incumbent before the questions "
                "deadline.",
                "Prepare a tailored Cority demo on the matched modules."]
    if a.tier == "sales":
        return ["Pull the full RFP + attachments (Agent 3) for a fit review.",
                "Validate scope and budget against Cority modules.",
                "Decide pursue / monitor after document review."]
    return ["Monitor; re-check if scope clarifies or a follow-on RFP appears.",
            "Optionally pull documents (Agent 3) to confirm the assessment."]


def _discovery(a: Analysis) -> list[str]:
    qs = ["What is the current EHSQ system/process, and what is driving this "
          "procurement now?",
          "How many sites, users and business units are in scope?",
          "Is there an incumbent vendor, and what is the contract term/renewal "
          "cadence?"]
    if "Safety" in a.pillars:
        qs.append("How are incidents, hazards and corrective actions tracked "
                  "today, and what OSHA reporting is required?")
    if "Environmental" in a.pillars:
        qs.append("Which environmental permits, emissions and reporting "
                  "obligations must the system support?")
    if "Quality" in a.pillars:
        qs.append("What quality processes (CAPA, audits, nonconformance, ISO) "
                  "need to be digitized?")
    if "Health" in a.pillars:
        qs.append("What occupational-health / medical-surveillance workflows "
                  "are in scope?")
    if "Sustainability" in a.pillars:
        qs.append("What ESG/GHG reporting frameworks and disclosure deadlines "
                  "apply?")
    return qs


def _exec_summary(a: Analysis) -> str:
    mods = "\n".join(f"  - {m['module']} ({m['confidence']}% confidence)"
                     for m in a.modules[:5]) or "  - (none clearly indicated)"
    risks = "\n".join(f"  - {r}" for r in a.risks)
    actions = "\n".join(f"  - {s}" for s in a.sales_actions)
    qs = "\n".join(f"  - {q}" for q in a.discovery_questions)
    sub = a.subscores
    return (
        f"OPPORTUNITY SCORE: {a.score}/100  ->  {a.action}\n"
        f"Sub-scores: Keyword {sub['keyword']} | Semantic {sub['semantic']} | "
        f"Agency Fit {sub['agency']} | Tech Intent {sub['technology']} | "
        f"Budget {sub['budget']}\n\n"
        f"OPPORTUNITY OVERVIEW\n  {a.title or '(untitled)'}\n"
        f"  Agency: {a.agency or 'see RFP'} | Due: {a.due or 'see RFP'} | "
        f"Solicitation: {a.solicitation_id}\n\n"
        f"WHY CORITY FITS\n  {a.why_fits}\n\n"
        f"KEY REQUIREMENTS IDENTIFIED\n  "
        f"{', '.join(a.matched_concepts) or 'To be confirmed from full RFP.'}\n\n"
        f"RECOMMENDED CORITY MODULES\n{mods}\n\n"
        f"RISKS\n{risks}\n\n"
        f"LIKELY COMPETITORS\n  {', '.join(a.competitors)}\n\n"
        f"RECOMMENDED SALES ACTIONS\n{actions}\n\n"
        f"DISCOVERY QUESTIONS\n{qs}\n"
    )


def to_row(a: Analysis) -> list:
    """Sheet-2 row order (see agent2_filter.OUT_HEADERS)."""
    return [
        a.score, a.action, a.solicitation_id, a.title, a.agency, a.due,
        a.subscores["keyword"], a.subscores["semantic"], a.subscores["agency"],
        a.subscores["technology"], a.subscores["budget"],
        "; ".join(f"{m['module']} ({m['confidence']}%)" for m in a.modules),
        a.why_fits, a.executive_summary, a.extracted.get("source_url", ""),
    ]


def to_json(a: Analysis) -> dict:
    return {
        "score": a.score, "action": a.action, "tier": a.tier,
        "solicitation_id": a.solicitation_id, "title": a.title,
        "agency": a.agency, "due": a.due, "subscores": a.subscores,
        "pillars": a.pillars, "modules": a.modules,
        "matched_concepts": a.matched_concepts, "competitors": a.competitors,
        "why_fits": a.why_fits, "risks": a.risks,
        "sales_actions": a.sales_actions,
        "discovery_questions": a.discovery_questions,
        "executive_summary": a.executive_summary, "extracted": a.extracted,
        "source_url": a.extracted.get("source_url", ""),
    }
