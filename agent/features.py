"""
agent/features.py
-----------------
Converts raw placement records (from MongoDB) and parsed resume dicts
into a NumPy feature matrix ready for Logistic Regression.

Feature vector (19 features per sample):

  Continuous / ordinal:
    [0]  ni_match_score         C1 raw score
    [1]  diplome_match_score    C2 raw score
    [2]  exp_match_score        C3 raw score
    [3]  anciennete_score       C5 raw score
    [4]  residence_score        C6 raw score
    [5]  offre_exp_years        offer-required years (normalised 0-1, cap 40)
    [6]  demandeur_exp_years    candidate years (normalised 0-1, cap 40)
    [7]  anciennete_days        raw days (normalised 0-1, cap 3650)

  Strategy one-hot (4):
    [8]  is_S0
    [9]  is_S1
    [10] is_S2
    [11] is_S3

  NI level one-hot (5):
    [12] ni_sans
    [13] ni_primaire
    [14] ni_moyen
    [15] ni_secondaire
    [16] ni_universitaire

  Residence proximity one-hot (3):
    [17] res_meme_commune
    [18] res_meme_wilaya
    [19] res_autres

Total: 20 features.
"""

from __future__ import annotations

import sys
import os
import numpy as np
from datetime import datetime, date
from pathlib import Path

# Allow sibling imports when run as script
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scoring.scoring_engine import (
    score_c1, score_c2, score_c3, score_c5, score_c6,
    detect_strategy, _canon_ni, _parse_date,
)
from scoring.scoring_config import (
    DEFAULT_RESIDENCE_SCOPE, WILAYA_ALGER_COMMUNES,
)

N_FEATURES = 20

_NI_ORDER = ["sans", "primaire", "moyen", "secondaire", "universitaire"]
_STRAT_ORDER = ["S0", "S1", "S2", "S3"]


def _ni_onehot(ni_raw: str) -> list:
    canon = _canon_ni(ni_raw)
    return [int(canon == k) for k in _NI_ORDER]


def _strat_onehot(strat: str) -> list:
    return [int(strat == s) for s in _STRAT_ORDER]


def _residence_proximity(offre_lieu: str, demandeur_commune: str) -> tuple:
    lieu    = str(offre_lieu).strip().upper()
    commune = str(demandeur_commune).strip().upper()
    if lieu == commune:
        prox = "meme_commune"
    elif commune in WILAYA_ALGER_COMMUNES:
        prox = "meme_wilaya"
    else:
        prox = "autres"
    return prox


def record_to_features(record: dict) -> np.ndarray:
    """
    Convert one placement record (or candidate+offer dict) to a 1-D
    numpy array of shape (N_FEATURES,).

    `record` must contain at minimum:
        offre_ni, offre_diplome, offre_exp_years, offre_metier, offre_lieu,
        date_offre, demandeur_ni, demandeur_diplome, demandeur_exp_years,
        demandeur_metier, demandeur_commune, date_inscription
    """
    # --- Criterion scores -------------------------------------------------
    c1 = score_c1(record.get("offre_ni", ""), record.get("demandeur_ni", ""))
    c2 = score_c2(record.get("offre_diplome", ""),
                  record.get("demandeur_diplome", ""),
                  record.get("offre_ni", ""),
                  record.get("demandeur_ni", ""))
    c3 = score_c3(record.get("offre_exp_years", 0),
                  record.get("demandeur_exp_years", 0),
                  record.get("offre_metier", ""),
                  record.get("demandeur_metier", ""))
    c5 = score_c5(record.get("date_offre", ""), record.get("date_inscription", ""))
    c6 = score_c6(record.get("offre_lieu", ""),
                  record.get("demandeur_commune", ""),
                  record.get("residence_scope", DEFAULT_RESIDENCE_SCOPE))

    # --- Continuous scalars -----------------------------------------------
    offre_exp  = min(int(record.get("offre_exp_years",       0) or 0), 40) / 40.0
    dem_exp    = min(int(record.get("demandeur_exp_years",    0) or 0), 40) / 40.0
    anc_days   = int(record.get("anciennete_days", 0) or 0)
    # anciennete_days may not be pre-computed for new resumes
    if anc_days == 0:
        d_offre = _parse_date(record.get("date_offre", ""))
        d_insc  = _parse_date(record.get("date_inscription", ""))
        anc_days = max((d_offre - d_insc).days, 0)
    anc_norm = min(anc_days, 3650) / 3650.0

    # --- Categorical one-hots ---------------------------------------------
    strat = detect_strategy(record.get("demandeur_ni", ""),
                            record.get("strategy", None))
    strat_oh = _strat_onehot(strat)
    ni_oh    = _ni_onehot(record.get("demandeur_ni", ""))
    prox     = _residence_proximity(record.get("offre_lieu", ""),
                                    record.get("demandeur_commune", ""))
    res_oh   = [int(prox == p) for p in ("meme_commune", "meme_wilaya", "autres")]

    vec = [c1, c2, c3, c5, c6,
           offre_exp, dem_exp, anc_norm,
           *strat_oh,
           *ni_oh,
           *res_oh]

    return np.array(vec, dtype=np.float32)


FEATURE_NAMES = [
    "c1_ni_match",
    "c2_diplome_match",
    "c3_exp_match",
    "c5_anciennete",
    "c6_residence",
    "offre_exp_years_norm",
    "dem_exp_years_norm",
    "anciennete_days_norm",
    "is_S0", "is_S1", "is_S2", "is_S3",
    "ni_sans", "ni_primaire", "ni_moyen", "ni_secondaire", "ni_universitaire",
    "res_meme_commune", "res_meme_wilaya", "res_autres",
]

assert len(FEATURE_NAMES) == N_FEATURES, \
    f"FEATURE_NAMES length {len(FEATURE_NAMES)} != N_FEATURES {N_FEATURES}"


def build_matrix(records: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    """
    Build (X, y) from a list of placement records.

    y = 1 if placement_success == 1 (all real placements), 0 otherwise.
    For training we'll use soft-negative samples generated internally.
    """
    X = np.vstack([record_to_features(r) for r in records])
    y = np.array([int(r.get("placement_success", 1)) for r in records],
                 dtype=np.int8)
    return X, y
