
from __future__ import annotations

import sys
from pathlib import Path
from datetime import date, datetime
from collections import defaultdict
from thefuzz import fuzz
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

def fetch_unique_candidates(db, limit: int = 2000) -> list[dict]:
    pipeline = [
        {
            "$group": {
                "_id": {
                    "demandeur_ni":        "$demandeur_ni",
                    "demandeur_diplome":   "$demandeur_diplome",
                    "demandeur_metier":    "$demandeur_metier",
                    "demandeur_exp_years": "$demandeur_exp_years",
                    "demandeur_commune":   "$demandeur_commune",
                },
                "count":            {"$sum": 1},
                "date_inscription": {"$max": "$date_inscription"},
                "anciennete_days":  {"$avg": "$anciennete_days"},
            }
        },
        {"$sort": {"count": -1}},
        {"$limit": limit},
    ]

    raw = list(db["placements"].aggregate(pipeline))
    candidates = []
    for r in raw:
        g = r["_id"]
        candidates.append({
            "demandeur_ni":        g.get("demandeur_ni", ""),
            "demandeur_diplome":   g.get("demandeur_diplome", ""),
            "demandeur_metier":    g.get("demandeur_metier", ""),
            "demandeur_exp_years": int(g.get("demandeur_exp_years") or 0),
            "demandeur_commune":   g.get("demandeur_commune", ""),
            "date_inscription":    str(r.get("date_inscription", date.today().isoformat()))[:10],
            "anciennete_days":     int(r.get("anciennete_days", 0)),
            "frequency":          r["count"],
        })
    return candidates

# ── Main matching function ────────────────────────────────────────────────────
# Fixed _mmr_rerank — append/remove were inside the for loop
# Also fixes te_range variable name typo (re_range → te_range)

def _mmr_rerank(results: list[dict], top_n: int, lambda_: float = 0.7) -> list[dict]:
    if top_n >= len(results):
        return results

    scores = [r["employability_score"] for r in results]
    min_te, max_te = min(scores), max(scores)
    te_range = max_te - min_te or 1.0
    norm = {id(r): (r["employability_score"] - min_te) / te_range for r in results}

    def _sim(a: dict, b: dict) -> float:
        metier_sim = fuzz.token_set_ratio(
            a["offre_metier"].lower(), b["offre_metier"].lower()
        ) / 100.0
        a_lieu, b_lieu = a["offre_lieu"].lower(), b["offre_lieu"].lower()
        if a_lieu == b_lieu:
            lieu_sim = 1.0
        elif a_lieu[:4] == b_lieu[:4]:
            lieu_sim = 0.5
        else:
            lieu_sim = 0.0
        return 0.7 * metier_sim + 0.3 * lieu_sim

    selected = []
    remaining = list(results)
    selected.append(remaining.pop(0))

    while len(selected) < top_n and remaining:
        best, best_mmr = None, -1.0
        for candidate in remaining:
            relevance  = norm[id(candidate)]
            redundancy = max(_sim(candidate, s) for s in selected)
            mmr = lambda_ * relevance - (1 - lambda_) * redundancy
            if mmr > best_mmr:
                best_mmr = mmr
                best = candidate
        best["mmr_score"] = round(best_mmr, 4)
        selected.append(best)
        remaining.remove(best)

    selected[0]["mmr_score"] = round(lambda_ * norm[id(selected[0])], 4)
    return selected


def _mmr_rerank_candidates(results: list[dict], top_n: int, lambda_: float = 0.7) -> list[dict]:
    """MMR reranking for candidate results — uses demandeur_metier/demandeur_commune."""
    if top_n >= len(results):
        return results

    scores = [r["employability_score"] for r in results]
    min_te, max_te = min(scores), max(scores)
    te_range = max_te - min_te or 1.0
    norm = {id(r): (r["employability_score"] - min_te) / te_range for r in results}

    def _sim(a: dict, b: dict) -> float:
        metier_sim = fuzz.token_set_ratio(
            (a.get("demandeur_metier") or "").lower(),
            (b.get("demandeur_metier") or "").lower(),
        ) / 100.0
        a_c = (a.get("demandeur_commune") or "").lower()
        b_c = (b.get("demandeur_commune") or "").lower()
        commune_sim = 1.0 if a_c == b_c else (0.5 if a_c[:4] == b_c[:4] else 0.0)
        return 0.7 * metier_sim + 0.3 * commune_sim

    selected = []
    remaining = list(results)
    selected.append(remaining.pop(0))

    while len(selected) < top_n and remaining:
        best, best_mmr = None, -1.0
        for cand in remaining:
            relevance  = norm[id(cand)]
            redundancy = max(_sim(cand, s) for s in selected)
            mmr = lambda_ * relevance - (1 - lambda_) * redundancy
            if mmr > best_mmr:
                best_mmr = mmr
                best = cand
        best["mmr_score"] = round(best_mmr, 4)
        selected.append(best)
        remaining.remove(best)

    selected[0]["mmr_score"] = round(lambda_ * norm[id(selected[0])], 4)
    return selected


def find_best_offers(
    parsed_resume: dict,
    db,
    scorer: DynamicScorer,
    top_n: int = 5,
    min_score: float = 25.0,
    lambda_ : float = 0.7,
) -> list[dict]:
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
    print(f"[DEBUG] fetched {len(offers)} offers")
    print(f"[DEBUG] candidate={candidate}")
    for offer in offers[:3]:
        record = {
            **offer,
            **candidate,
            "offre_exp_years": int(offer.get("offre_exp_years") or 0),
        }
        print(f"[DEBUG] record fields: { {k:v for k,v in record.items() if v is None} }")
        try:
            result = scorer.score(record)
            print(f"[DEBUG] ok te={result['employability_score']}")
        except Exception as e:
            import traceback
            traceback.print_exc()


    results = []
    for offer in offers:
        record = {**offer,**candidate,"offre_exp_years": int(offer.get("offre_exp_years") or 0)}
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
    results.sort(key = lambda x: x["employability_score"], reverse = True)
    selected = _mmr_rerank(results,top_n, lambda_ = lambda_)
    for i, r in enumerate(selected,1):
        r["rank"] = i
        r["diversity_reranked"] = True
    
    return selected

def find_best_candidates(
    offer: dict,
    db,
    scorer: DynamicScorer,
    top_n: int = 5,
    min_score: float = 25.0,
    lambda_: float = 0.7,
) -> list[dict]:
    candidates = fetch_unique_candidates(db)

    if not candidates:
        return []

    results = []
    for candidate in candidates:
        record = {**offer, **candidate, "offre_exp_years": int(offer.get("offre_exp_years") or 0)}
        try:
            result = scorer.score(record)
            te = result["employability_score"]
            if te < min_score:
                continue
            results.append({
                # Candidate info
                "demandeur_ni":        candidate["demandeur_ni"],
                "demandeur_diplome":   candidate["demandeur_diplome"],
                "demandeur_metier":    candidate["demandeur_metier"],
                "demandeur_exp_years": candidate["demandeur_exp_years"],
                "demandeur_commune":   candidate["demandeur_commune"],
                "date_inscription":    candidate["date_inscription"],
                "anciennete_days":     candidate["anciennete_days"],
                "candidate_frequency": candidate["frequency"],
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

    results.sort(key=lambda x: x["employability_score"], reverse=True)
    selected = _mmr_rerank_candidates(results, top_n, lambda_)

    for i, r in enumerate(selected, 1):
        r["rank"] = i
        r["diversity_reranked"] = True

    return selected

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
        record = {**offer,**candidate,"offre_exp_years": int(offer.get("offre_exp_years") or 0)}
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
    selected = _mmr_rerank(results, top_n)
    for i, r in enumerate(selected, 1):
        r["rank"] = i
        r["diversity_reranked"] = True
    return selected
