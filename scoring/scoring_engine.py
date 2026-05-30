"""
scoring_engine.py  (v2 — ANEM criteria C1–C6)
----------------------------------------------
Stateless scoring functions. No MongoDB, no I/O.
Takes plain dicts, returns floats.

Each criterion returns a score ∈ [0, 1].
Final TE is scaled to [0, 100].

Input dict expected by compute_employability_score():
{
    "offre_ni":          str,   # e.g. "Supérieur 1"
    "offre_diplome":     str,   # e.g. "Génie civil"
    "offre_exp_years":   int,   # e.g. 2
    "offre_metier":      str,   # e.g. "Ingénieur"
    "offre_lieu":        str,   # e.g. "EL ACHOUR"
    "date_offre":        str,   # ISO date string

    "demandeur_ni":      str,
    "demandeur_diplome": str,
    "demandeur_exp_years": int,
    "demandeur_metier":  str,
    "demandeur_commune": str,
    "date_inscription":  str,   # ISO date string

    "strategy":          str,   # "S0"/"S1"/"S2"/"S3" — optional, auto-detected
    "residence_scope":   str,   # "S1"/"S2"/"S3" — optional, defaults to "S2"
}
"""
from thefuzz import fuzz
from datetime import datetime
from scoring.scoring_config import (
    NI_CANONICAL, M_NI,
    DIPLOME_MEME_SPECIALITE, DIPLOME_MEME_FILIERE,
    DIPLOME_MEME_DOMAINE, DIPLOME_AUTRES,
    years_to_band, M_EXP_YEARS, M_EXP_METIER,
    score_anciennete,
    M_RESIDENCE, DEFAULT_RESIDENCE_SCOPE, WILAYA_ALGER_COMMUNES,
    get_normalized_weights, NI_TO_STRATEGY,
    CLASSIFICATION_THRESHOLDS,
)


# ── Utilities ─────────────────────────────────────────────────────────────────

def _canon_ni(raw: str) -> str:
    """Normalise a raw NI string to one of 5 canonical keys."""
    return NI_CANONICAL.get(str(raw).strip().lower(), "moyen")


def _parse_date(s) -> datetime:
    """Parse ISO date string or return epoch on failure."""
    try:
        return datetime.fromisoformat(str(s)[:10])
    except (ValueError, TypeError):
        return datetime(1970, 1, 1)


def _first_word(s: str) -> str:
    return str(s).strip().split()[0].lower() if s else ""


# ── C1: Niveau d'instruction ──────────────────────────────────────────────────

def score_c1(offre_ni: str, demandeur_ni: str) -> float:
    """
    Fuzzy NI match using M_NI matrix.
    Returns score ∈ [0, 1].
    """
    req   = _canon_ni(offre_ni)
    found = _canon_ni(demandeur_ni)
    return M_NI.get(req, {}).get(found, 0.0)


# ── C2: Diplômes ──────────────────────────────────────────────────────────────

def score_c2(offre_diplome: str, demandeur_diplome: str,
             offre_ni: str = "", demandeur_ni: str = "") -> float:
    """
    Diploma specialité similarity (M6.1).
    Grade similarity (M6.2) approximated using NI match already scored by C1.

    Heuristic levels:
      MEME SPECIALITE → exact string match (normalised)
      MEME FILIERE    → first word matches (broad field)
      MEME DOMAINE    → NI level match (same educational domain)
      AUTRES          → fallback
    """
    o = str(offre_diplome).strip().lower()
    d = str(demandeur_diplome).strip().lower()

    if o == d:
        specialite_score = DIPLOME_MEME_SPECIALITE
    elif len(o) < 6 or len(d) < 6:
        specialite_score = DIPLOME_AUTRES
    else:
        ratio = fuzz.token_set_ratio(o,d)
        if ratio >= 90:
            specialite_score = DIPLOME_MEME_SPECIALITE
        elif ratio >= 70:
            specialite_score = DIPLOME_MEME_FILIERE
        elif ratio >= 45:
            specialite_score = DIPLOME_MEME_DOMAINE
        else:
            specialite_score = DIPLOME_AUTRES

    return specialite_score   # M6.2 grade already captured in C1


# ── C3: Expériences ───────────────────────────────────────────────────────────

def score_c3(offre_exp_years: int, demandeur_exp_years: int,
             offre_metier: str, demandeur_metier: str) -> float:
    # M5.1 — years match
    req_band   = years_to_band(int(offre_exp_years)   if offre_exp_years   is not None else 0)
    found_band = years_to_band(int(demandeur_exp_years) if demandeur_exp_years is not None else 0)
    years_score = M_EXP_YEARS.get(req_band, {}).get(found_band, 0.2)

    # M5.2 — métier proximity
    o_m = str(offre_metier).strip().lower()
    d_m = str(demandeur_metier).strip().lower()

    if o_m == d_m:
        proximity = "meme_emploi"
    elif len(o_m) < 6 or len(d_m) < 6:
        proximity = "autre"
    else:
        ratio = fuzz.token_set_ratio(o_m,d_m)
        if ratio >= 85:
            proximity = "meme_emploi"
        elif ratio >= 60:
            proximity = "meme_metier"
        else:
            proximity = "autre"

    # SP(Expérience) = M5.1[years_band] × M5.2[métier_proximity]
    metier_score = M_EXP_METIER.get(proximity, 0.20)
    return round(years_score * metier_score, 4)


# ── C4: Langues ───────────────────────────────────────────────────────────────

def score_c4() -> float:
    """
    Language criterion. Dataset contains no language fields.
    Returns neutral 1.0 so it doesn't penalise candidates unfairly.
    Weight is zeroed in S1 strategy automatically.
    """
    return 1.0


# ── C5: Ancienneté ────────────────────────────────────────────────────────────

def score_c5(date_offre, date_inscription) -> float:
    """
    Seniority score from registration date relative to offer date.
    Returns score ∈ [0, 1].
    """
    d_offre = _parse_date(date_offre)
    d_insc  = _parse_date(date_inscription)
    days    = (d_offre - d_insc).days
    return score_anciennete(days)


# ── C6: Résidence ─────────────────────────────────────────────────────────────

def score_c6(offre_lieu: str, demandeur_commune: str,
             residence_scope: str = DEFAULT_RESIDENCE_SCOPE) -> float:
    """
    Geographic mobility score using M_RESIDENCE matrix.

    Proximity classification (all dataset jobs are in Wilaya 16):
      meme_commune → exact match (case-insensitive)
      meme_wilaya  → candidate commune is in WILAYA_ALGER_COMMUNES
      autres       → outside Alger
    """
    lieu    = str(offre_lieu).strip().upper()
    commune = str(demandeur_commune).strip().upper()

    if lieu == commune:
        proximity = "meme_commune"
    elif commune in WILAYA_ALGER_COMMUNES:
        proximity = "meme_wilaya"
    else:
        proximity = "autres"

    scope  = residence_scope if residence_scope in M_RESIDENCE else DEFAULT_RESIDENCE_SCOPE
    matrix = M_RESIDENCE[scope]
    return matrix.get(proximity, 0.0)


# ── Strategy detection ────────────────────────────────────────────────────────

def detect_strategy(demandeur_ni: str, strategy: str = None) -> str:
    """
    Returns the strategy code to use.
    If explicitly passed and valid, use it. Otherwise infer from NI level.
    """
    if strategy in ("S0", "S1", "S2", "S3"):
        return strategy
    canon = _canon_ni(demandeur_ni)
    return NI_TO_STRATEGY.get(canon, "S0")


# ── Classification ────────────────────────────────────────────────────────────

def classify(te: float) -> str:
    for threshold, label in CLASSIFICATION_THRESHOLDS:
        if te >= threshold:
            return label
    return "Nulle"


# ── Master scoring function ───────────────────────────────────────────────────

def compute_employability_score(record: dict, strategy: str = None,
                                residence_scope: str = None) -> dict:
    """
    Computes the full employability score for one candidate–offer pair.

    Args:
        record:           Dict with all offre + demandeur fields.
        strategy:         Force a strategy ("S0"–"S3"). Auto-detected if None.
        residence_scope:  Force residence scope ("S1"–"S3"). Defaults to "S2".

    Returns:
        Dict with criterion scores, weights, TE, and classification.
    """
    # ── Detect strategy ──
    strat = detect_strategy(record.get("demandeur_ni", ""), strategy)
    weights = get_normalized_weights(strat)

    # ── Score each criterion ──
    c1 = score_c1(record.get("offre_ni", ""),
                  record.get("demandeur_ni", ""))

    c2 = score_c2(record.get("offre_diplome", ""),
                  record.get("demandeur_diplome", ""),
                  record.get("offre_ni", ""),
                  record.get("demandeur_ni", ""))

    c3 = score_c3(record.get("offre_exp_years", 0),
                  record.get("demandeur_exp_years", 0),
                  record.get("offre_metier", ""),
                  record.get("demandeur_metier", ""))

    c4 = score_c4()

    c5 = score_c5(record.get("date_offre", ""),
                  record.get("date_inscription", ""))

    scope = residence_scope or record.get("residence_scope", DEFAULT_RESIDENCE_SCOPE)
    c6 = score_c6(record.get("offre_lieu", ""),
                  record.get("demandeur_commune", ""),
                  scope)

    scores = {"C1": c1, "C2": c2, "C3": c3, "C4": c4, "C5": c5, "C6": c6}

    # ── Weighted average → TE ──
    numerator   = sum(weights[k] * scores[k] for k in scores)
    denominator = sum(weights.values())
    te_raw      = (numerator / denominator) if denominator > 0 else 0.0
    te          = round(te_raw * 100, 2)   # scale to [0, 100]

    return {
        "strategy":            strat,
        "weights":             {k: round(v, 4) for k, v in weights.items()},
        "criterion_scores":    {k: round(v, 4) for k, v in scores.items()},
        "employability_score": te,
        "classification":      classify(te),
    }


# ── Quick self-test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Real-looking record drawn from the dataset
    test_record = {
        "offre_ni":             "Supérieur 1",
        "offre_diplome":        "Génie civil",
        "offre_exp_years":      2,
        "offre_metier":         "Responsable de la logistique approvisionnement",
        "offre_lieu":           "CHERAGA",
        "date_offre":           "2015-09-17",

        "demandeur_ni":         "Supérieur 2",
        "demandeur_diplome":    "Génie industriel",
        "demandeur_exp_years":  2,
        "demandeur_metier":     "Responsable de la logistique approvisionnement",
        "demandeur_commune":    "LES EUCALYPTUS",
        "date_inscription":     "2015-08-23",
    }

    result = compute_employability_score(test_record)

    print("── Employability Score ─────────────────────────────")
    print(f"  Strategy:    {result['strategy']}")
    print(f"  TE Score:    {result['employability_score']} / 100")
    print(f"  Class:       {result['classification']}")
    print()
    print("── Criterion Breakdown ─────────────────────────────")
    labels = {
        "C1": "Niveau instruction",
        "C2": "Diplômes",
        "C3": "Expériences",
        "C4": "Langues",
        "C5": "Ancienneté",
        "C6": "Résidence",
    }
    for k, score in result["criterion_scores"].items():
        w = result["weights"][k]
        print(f"  {k} ({labels[k]:<24}) score={score:.3f}  weight={w:.3f}  contrib={score*w*100:.1f}")
