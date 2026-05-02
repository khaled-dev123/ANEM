"""
agent/trainer.py
----------------
Trains one Logistic Regression model per strategy (S0–S3) on the 37,358
real placement records from MongoDB Atlas.

Pipeline:
    1. Fetch placements from MongoDB (batch cursor)
    2. Generate soft negatives (shuffled / mismatched pairs) so the
       model has negative examples to learn from
    3. Build feature matrix via agent/features.py
    4. Train sklearn LogisticRegression per strategy
    5. Extract per-strategy feature importances (|coefficients|)
    6. Write weight overrides back to MongoDB (referential collection)
       and to a local JSON cache

Weight override schema stored in MongoDB `referential`:
    {
        type: "ml_weight_override",
        strategy: "S2",
        trained_at: "2025-...",
        n_samples: 1842,
        accuracy: 0.87,
        feature_importances: {
            "c1_ni_match": 0.34,
            ...
        },
        weight_overrides: {          ← normalised to sum=1, C4 zeroed for S1
            "C1": 0.31,
            "C2": 0.18,
            ...
        }
    }
"""

from __future__ import annotations

import json
import os
import sys
import random
import copy
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np

# Allow sibling imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.features import (
    record_to_features, build_matrix, FEATURE_NAMES, N_FEATURES,
)
from scoring.scoring_config import (
    get_normalized_weights, RAW_STRATEGY_WEIGHTS,
)

# ── Optional sklearn import (hard-fail with helpful message) ─────────────────
try:
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    from sklearn.model_selection import cross_val_score
    from sklearn.metrics import accuracy_score
    SKLEARN_OK = True
except ImportError:
    SKLEARN_OK = False

# ── Feature → criterion mapping ──────────────────────────────────────────────
# Tells us which LR coefficient feeds back into which scoring weight.
FEATURE_TO_CRITERION = {
    "c1_ni_match":     "C1",
    "c2_diplome_match":"C2",
    "c3_exp_match":    "C3",
    "c5_anciennete":   "C5",
    "c6_residence":    "C6",
    # other features don't map directly to a single criterion
}

STRATEGIES = ["S0", "S1", "S2", "S3"]
CACHE_PATH  = Path(__file__).resolve().parent.parent / "ml_weight_cache.json"


# ── Negative sample generation ────────────────────────────────────────────────

def _generate_negatives(positives: list[dict], ratio: float = 1.0) -> list[dict]:
    """
    Create synthetic negative samples by randomly mismatching candidate
    and offer fields from the positive pool.
    This is necessary because the dataset only contains successful placements.
    """
    n_neg = int(len(positives) * ratio)
    negatives = []
    indices = list(range(len(positives)))

    for _ in range(n_neg):
        # Pick two different records and swap demandeur fields
        i, j = random.sample(indices, 2)
        rec = copy.copy(positives[i])
        donor = positives[j]
        # Swap demandeur fields → likely bad match
        rec["demandeur_ni"]         = donor["demandeur_ni"]
        rec["demandeur_diplome"]    = donor["demandeur_diplome"]
        rec["demandeur_exp_years"]  = donor["demandeur_exp_years"]
        rec["demandeur_metier"]     = donor["demandeur_metier"]
        rec["demandeur_commune"]    = donor["demandeur_commune"]
        rec["date_inscription"]     = donor.get("date_inscription", "2010-01-01")
        rec["anciennete_days"]      = 0
        rec["placement_success"]    = 0
        negatives.append(rec)

    return negatives


# ── Per-criterion importance from LR coefficients ─────────────────────────────

def _coef_to_criterion_importances(coef: np.ndarray) -> dict:
    """
    Map LR |coefficients| to per-criterion importance scores.
    Features that map to the same criterion are averaged.
    """
    abs_coef = np.abs(coef)
    criterion_vals: dict[str, list] = {c: [] for c in ("C1","C2","C3","C4","C5","C6")}

    for i, fname in enumerate(FEATURE_NAMES):
        crit = FEATURE_TO_CRITERION.get(fname)
        if crit:
            criterion_vals[crit].append(abs_coef[i])

    # C4 has no direct feature (dataset has no language field) → keep as-is
    criterion_vals["C4"] = [1.0]

    return {c: float(np.mean(v)) if v else 0.0 for c, v in criterion_vals.items()}


def _importances_to_weight_overrides(
    importances: dict, strategy: str
) -> dict:
    """
    Blend ML-derived importances (50%) with hand-tuned base weights (50%)
    and normalise to sum=1. C4 is zeroed for S1 as per original config.
    """
    base = get_normalized_weights(strategy)  # already normalised
    blended = {}
    for c in ("C1","C2","C3","C4","C5","C6"):
        ml_w   = importances.get(c, 0.0)
        base_w = base.get(c, 0.0)
        blended[c] = 0.5 * ml_w + 0.5 * base_w

    # S1: C4 (Languages) is irrelevant in execution strategy
    if strategy == "S1":
        blended["C4"] = 0.0

    total = sum(blended.values())
    if total > 0:
        blended = {c: round(v / total, 4) for c, v in blended.items()}

    return blended


# ── Single-strategy trainer ───────────────────────────────────────────────────

def train_strategy(
    records: list[dict],
    strategy: str,
    cv: int = 5,
    verbose: bool = True,
) -> dict:
    """
    Trains a Logistic Regression on the subset of records for a given strategy.

    Returns a result dict containing:
        strategy, n_samples, accuracy, feature_importances, weight_overrides
    """
    if not SKLEARN_OK:
        raise ImportError("scikit-learn is required. pip install scikit-learn")

    # Filter to this strategy's records (+ same-strategy negatives)
    pos = [r for r in records
           if _infer_strategy(r.get("demandeur_ni", "")) == strategy]

    if len(pos) < 20:
        if verbose:
            print(f"  [WARN] {strategy}: only {len(pos)} samples — skipping training.")
        return {
            "strategy":            strategy,
            "n_samples":           len(pos),
            "accuracy":            None,
            "feature_importances": {},
            "weight_overrides":    get_normalized_weights(strategy),
            "skipped":             True,
        }

    neg    = _generate_negatives(pos, ratio=1.0)
    all_r  = pos + neg
    random.shuffle(all_r)

    X, y = build_matrix(all_r)

    model = Pipeline([
        ("scaler", StandardScaler()),
        ("lr", LogisticRegression(
            max_iter=1000,
            C=1.0,
            class_weight="balanced",
            solver="lbfgs",
            random_state=42,
        )),
    ])

    # Cross-validation accuracy
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        cv_scores = cross_val_score(model, X, y, cv=min(cv, 5), scoring="accuracy")
    accuracy = float(np.mean(cv_scores))

    # Full fit for coefficients
    model.fit(X, y)
    coef = model.named_steps["lr"].coef_[0]

    feat_imp = {}
    abs_coef = np.abs(coef)
    total_abs = abs_coef.sum()
    for i, fname in enumerate(FEATURE_NAMES):
        feat_imp[fname] = round(float(abs_coef[i] / total_abs), 6) if total_abs > 0 else 0.0

    crit_imp = _coef_to_criterion_importances(coef)
    w_overrides = _importances_to_weight_overrides(crit_imp, strategy)

    if verbose:
        print(f"  {strategy}: n={len(pos)} pos + {len(neg)} neg "
              f"| CV acc={accuracy:.3f}")

    return {
        "strategy":            strategy,
        "n_samples":           len(pos),
        "accuracy":            round(accuracy, 4),
        "feature_importances": feat_imp,
        "criterion_importances": {c: round(v, 4) for c, v in crit_imp.items()},
        "weight_overrides":    w_overrides,
        "trained_at":          datetime.utcnow().isoformat(),
        "skipped":             False,
    }


def _infer_strategy(ni_raw: str) -> str:
    from scoring.scoring_engine import detect_strategy
    return detect_strategy(ni_raw)


# ── Full training run ─────────────────────────────────────────────────────────

def train_all(
    records: list[dict],
    verbose: bool = True,
) -> dict[str, dict]:
    """
    Train one LR model per strategy on `records`.

    Returns a dict keyed by strategy code.
    """
    if not SKLEARN_OK:
        raise ImportError("scikit-learn is required. pip install scikit-learn")

    results = {}
    for strat in STRATEGIES:
        if verbose:
            print(f"\n── Training strategy {strat} ─────────────────────")
        results[strat] = train_strategy(records, strat, verbose=verbose)

    return results


def save_cache(results: dict[str, dict], path: Path = CACHE_PATH) -> None:
    """Save training results to a local JSON cache."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n💾 Weight cache saved → {path}")


def load_cache(path: Path = CACHE_PATH) -> dict[str, dict] | None:
    """Load cached training results, or None if not found."""
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


def push_to_mongo(results: dict[str, dict], db) -> None:
    """
    Upsert ML weight override documents into the `referential` collection.
    db is a pymongo Database object.
    """
    from pymongo import UpdateOne
    ops = []
    for strat, res in results.items():
        doc = {
            "type":                 "ml_weight_override",
            "strategy":             strat,
            "trained_at":           res.get("trained_at", datetime.utcnow().isoformat()),
            "n_samples":            res.get("n_samples"),
            "accuracy":             res.get("accuracy"),
            "feature_importances":  res.get("feature_importances", {}),
            "criterion_importances":res.get("criterion_importances", {}),
            "weight_overrides":     res.get("weight_overrides", {}),
        }
        ops.append(UpdateOne(
            {"type": "ml_weight_override", "strategy": strat},
            {"$set": doc},
            upsert=True,
        ))
    if ops:
        db["referential"].bulk_write(ops, ordered=False)
        print(f"✅ {len(ops)} weight-override documents upserted into referential.")
