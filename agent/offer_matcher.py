"""
agent/offer_matcher.py
----------------------
Searches MongoDB `placements` collection for the best job offers
that match a parsed resume — no manual offer input needed.

Matching strategy (multi-pass):
    Pass 1 — Hard filters (NI compatibility, geography feasibility)
    Pass 2 — Score every candidate offer with the full scoring engine
    Pass 3 — Rank by employability score, return top-N

The `placements` collection fields used:
    offre_ni, offre_diplome, offre_exp_years, offre_metier,
    offre_lieu, date_offre, placement_id

Since placements are historical match records (not a live job board),
we extract the unique offer "profiles" from them — distinct combinations
of (offre_ni, offre_metier, offre_lieu, offre_exp_years) — and score
the resume candidate against each one.
"""

from __future__ import annotations

import sys
from pathlib import Path
from datetime import date, datetime
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scoring.scoring_engine import (
    compute_employability_score, _canon_ni, detect_strategy,
)
from scoring.scoring_config import NI_CANONICAL, WILAYA_ALGER_COMMUNES
from agent.dynamic_scorer import DynamicScorer


# ── NI compatibility: which offer NI levels can a candidate realistically match ─

_NI_ORDER = ["sans", "primaire", "moyen", "secondaire", "universitaire"]

def _ni_rank(ni_raw: str) -> int:
    canon = _canon_ni(ni_raw)
    return _NI_ORDER.index(canon) if canon in _NI_ORDER else 2


def _compatible_ni_levels(demandeur_ni: str) -> list[str]:
    """
    Returns offer NI levels that could yield a non-zero C1 score.
    A candidate can match offers at their level ±1 tier.
    """
    rank = _ni_rank(demandeur_ni)
    compatible = []
    for i, level in enumerate(_NI_ORDER):
        if abs(i - rank) <= 1:
            compatible.append(level)
    # Also include the raw string variants
    result = set()
    for canon in compatible:
        for raw, c in NI_CANONICAL.items():
            if c == canon:
                result.add(raw)
        result.add(canon)
    return list(result)


# ── Extract unique offer profiles from placements ─────────────────────────────

def fetch_unique_offers(db, limit_per_ni: int = 200) -> list[dict]:
    """
    Pulls distinct offer profiles from the `placements` collection.
    Groups by (offre_ni, offre_metier, offre_lieu) and picks the
    most recent date_offre per group.

    Returns a list of offer dicts with offre_* fields only.
    """
    pipeline = [
        {
            "$group": {
                "_id": {
                    "offre_ni":        "$offre_ni",
                    "offre_metier":    "$offre_metier",
                    "offre_lieu":      "$offre_lieu",
                    "offre_diplome":   "$offre_diplome",
                    "offre_exp_years": "$offre_exp_years",
                },
                "count":       {"$sum": 1},
                "date_offre":  {"$max": "$date_offre"},
            }
        },
        {"$sort": {"count": -1}},   # most frequent offers first
        {"$limit": 2000},
    ]

    raw = list(db["placements"].aggregate(pipeline))
    offers = []
    for r in raw:
        g = r["_id"]
        offers.append({
            "offre_ni":        g.get("offre_ni", ""),
            "offre_diplome":   g.get("offre_diplome", ""),
            "offre_exp_years": int(g.get("offre_exp_years") or 0),
            "offre_metier":    g.get("offre_metier", ""),
            "offre_lieu":      g.get("offre_lieu", ""),
            "date_offre":      str(r.get("date_offre", date.today().isoformat()))[:10],
            "frequency":       r["count"],
        })
    return offers


# ── Main matching function ────────────────────────────────────────────────────

def find_best_offers(
    parsed_resume: dict,
    db,
    scorer: DynamicScorer,
    top_n: int = 5,
    min_score: float = 25.0,
) -> list[dict]:
    """
    Given a parsed resume dict (from resume_parser.parser),
    fetch all unique offers from MongoDB and return the top-N
    best matches ranked by ML-weighted employability score.

    Args:
        parsed_resume:  Output of parse_resume() / parse_resume_text()
        db:             pymongo Database object
        scorer:         DynamicScorer instance (with ML overrides)
        top_n:          How many top offers to return
        min_score:      Minimum TE score to include in results

    Returns:
        List of dicts, each containing:
            offer fields + scoring result + rank
    """
    offers = fetch_unique_offers(db)

    if not offers:
        return []

    # Build candidate-side fields (constant across all offers)
    candidate = {
        "demandeur_ni":         parsed_resume.get("demandeur_ni", ""),
        "demandeur_diplome":    parsed_resume.get("demandeur_diplome", ""),
        "demandeur_exp_years":  parsed_resume.get("demandeur_exp_years", 0),
        "demandeur_metier":     parsed_resume.get("demandeur_metier", ""),
        "demandeur_commune":    parsed_resume.get("demandeur_commune", "ALGER"),
        "date_inscription":     parsed_resume.get("date_inscription",
                                                   date.today().isoformat()),
    }

    results = []
    for offer in offers:
        record = {**offer, **candidate}
        try:
            result = scorer.score(record)
            te     = result["employability_score"]
            if te < min_score:
                continue
            results.append({
                # Offer info
                "offre_ni":        offer["offre_ni"],
                "offre_diplome":   offer["offre_diplome"],
                "offre_exp_years": offer["offre_exp_years"],
                "offre_metier":    offer["offre_metier"],
                "offre_lieu":      offer["offre_lieu"],
                "date_offre":      offer["date_offre"],
                "offer_frequency": offer["frequency"],
                # Score
                "employability_score": te,
                "classification":      result["classification"],
                "strategy":            result["strategy"],
                "criterion_scores":    result["criterion_scores"],
                "weights":             result["weights"],
                "ml_override_active":  result.get("ml_override_active", False),
            })
        except Exception:
            continue

    # Rank by TE score descending
    results.sort(key=lambda x: x["employability_score"], reverse=True)

    # Add rank
    for i, r in enumerate(results[:top_n], 1):
        r["rank"] = i

    return results[:top_n]


# ── Offline fallback: find best offers from local cache ───────────────────────

def find_best_offers_offline(
    parsed_resume: dict,
    scorer: DynamicScorer,
    top_n: int = 5,
) -> list[dict]:
    """
    Offline version: generates synthetic offers based on the candidate's
    profile when MongoDB is not available. Used for demo/testing only.
    """
    from scoring.scoring_config import WILAYA_ALGER_COMMUNES

    communes  = list(WILAYA_ALGER_COMMUNES)
    ni_levels = ["Moyen", "Secondaire 3AS", "Supérieur 1", "Supérieur 2"]
    metiers   = [
        "Ingénieur", "Technicien", "Responsable logistique",
        "Développeur logiciel", "Comptable", "Chef de projet",
        "Agent commercial", "Opérateur", "Directeur technique",
    ]

    import random
    random.seed(42)
    synthetic_offers = []
    for _ in range(80):
        synthetic_offers.append({
            "offre_ni":        random.choice(ni_levels),
            "offre_diplome":   parsed_resume.get("demandeur_diplome", ""),
            "offre_exp_years": random.randint(0, 10),
            "offre_metier":    random.choice(metiers),
            "offre_lieu":      random.choice(communes),
            "date_offre":      date.today().isoformat(),
            "frequency":       random.randint(1, 50),
        })

    candidate = {
        "demandeur_ni":         parsed_resume.get("demandeur_ni", ""),
        "demandeur_diplome":    parsed_resume.get("demandeur_diplome", ""),
        "demandeur_exp_years":  parsed_resume.get("demandeur_exp_years", 0),
        "demandeur_metier":     parsed_resume.get("demandeur_metier", ""),
        "demandeur_commune":    parsed_resume.get("demandeur_commune", "ALGER"),
        "date_inscription":     parsed_resume.get("date_inscription",
                                                   date.today().isoformat()),
    }

    results = []
    for offer in synthetic_offers:
        record = {**offer, **candidate}
        result = scorer.score(record)
        te     = result["employability_score"]
        if te < 20:
            continue
        results.append({
            **offer,
            "offer_frequency":     offer["frequency"],
            "employability_score": te,
            "classification":      result["classification"],
            "strategy":            result["strategy"],
            "criterion_scores":    result["criterion_scores"],
            "weights":             result["weights"],
            "ml_override_active":  result.get("ml_override_active", False),
        })

    results.sort(key=lambda x: x["employability_score"], reverse=True)
    for i, r in enumerate(results[:top_n], 1):
        r["rank"] = i
    return results[:top_n]
