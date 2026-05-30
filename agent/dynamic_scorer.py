"""
agent/dynamic_scorer.py
-----------------------
Drop-in replacement for scoring_engine.compute_employability_score() that
applies ML-derived weight overrides when available.

Weight resolution priority:
    1. ML-trained overrides (from MongoDB referential or local JSON cache)
    2. Hand-tuned base weights (scoring_config.RAW_STRATEGY_WEIGHTS)

Usage:
    from agent.dynamic_scorer import DynamicScorer

    scorer = DynamicScorer.from_cache()          # offline
    scorer = DynamicScorer.from_mongo(db)        # live

    result = scorer.score(record)                # same schema as scoring_engine
    result = scorer.score_resume(parsed_resume, offer_record)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scoring.scoring_engine import (
    score_c1, score_c2, score_c3, score_c4, score_c5, score_c6,
    detect_strategy, classify, _canon_ni,
)

from scoring.scoring_config import (
    get_normalized_weights, DEFAULT_RESIDENCE_SCOPE,
)

from agent.trainer import CACHE_PATH

STRATEGIES = ["S0", "S1", "S2", "S3"]


class DynamicScorer:
    """
    Stateful scorer that holds ML weight overrides per strategy.

    Attributes:
        overrides:  dict[strategy_code → weight_dict]
                    weight_dict keys: C1..C6, values normalised to sum=1
        meta:       dict[strategy_code → training metadata]
    """

    def __init__(self, overrides: dict[str, dict], meta: dict[str, dict] | None = None):
        self.overrides = overrides
        self.meta = meta or {}

    # ── Factory methods ────────────────────────────────────────────────────

    @classmethod
    def from_cache(cls, path: Path = CACHE_PATH) -> "DynamicScorer":
        """Load weight overrides from local JSON cache (no DB needed)."""

        if not path.exists():
            print("[DynamicScorer] No cache found — using base weights.")
            return cls._base_only()

        with open(path, encoding="utf-8") as f:
            results = json.load(f)

        overrides = {}
        meta = {}

        for strat, res in results.items():
            wo = res.get("weight_overrides")

            if wo:
                overrides[strat] = wo
                meta[strat] = {
                    "n_samples": res.get("n_samples"),
                    "accuracy": res.get("accuracy"),
                    "trained_at": res.get("trained_at"),
                }

        print(
            f"[DynamicScorer] Loaded ML overrides for strategies: "
            f"{list(overrides.keys())}"
        )

        return cls(overrides, meta)

    @classmethod
    def from_mongo(cls, db) -> "DynamicScorer":
        """Load weight overrides from MongoDB referential collection."""

        docs = list(db["referential"].find({"type": "ml_weight_override"}))

        overrides = {}
        meta = {}

        for doc in docs:
            strat = doc.get("strategy")
            wo = doc.get("weight_overrides")

            if strat and wo:
                overrides[strat] = wo

                meta[strat] = {
                    "n_samples": doc.get("n_samples"),
                    "accuracy": doc.get("accuracy"),
                    "trained_at": doc.get("trained_at"),
                }

        if not overrides:
            print("[DynamicScorer] No ML overrides in DB — using base weights.")
        else:
            print(
                f"[DynamicScorer] Loaded ML overrides for: "
                f"{list(overrides.keys())}"
            )

        return cls(overrides, meta)

    @classmethod
    def _base_only(cls) -> "DynamicScorer":
        """Fallback: use hand-tuned base weights for all strategies."""

        overrides = {
            s: get_normalized_weights(s)
            for s in STRATEGIES
        }

        return cls(overrides)

    # ── Weight resolution ──────────────────────────────────────────────────

    def get_weights(self, strategy: str) -> dict:
        """Return weight dict for strategy, preferring ML overrides."""

        if strategy in self.overrides:
            return self.overrides[strategy]

        return get_normalized_weights(strategy)

    # ── Main scoring call ──────────────────────────────────────────────────

    def score(
        self,
        record: dict,
        strategy: str | None = None,
        residence_scope: str | None = None,
    ) -> dict:
        """
        Compute employability score with ML-overridden weights.

        Returns the same schema as scoring_engine.compute_employability_score().
        """

        strat = detect_strategy(
            record.get("demandeur_ni", ""),
            strategy
        )

        weights = self.get_weights(strat)

        # ── Calculate scores ───────────────────────────────────────────────

        c1 = score_c1(
            record.get("offre_ni", ""),
            record.get("demandeur_ni", "")
        )
        print(f"[DEBUG] C1 (NI Match Score): {c1}")

        c2 = score_c2(
            record.get("offre_diplome", ""),
            record.get("demandeur_diplome", ""),
            record.get("offre_ni", ""),
            record.get("demandeur_ni", "")
        )
        print(f"[DEBUG] C2 (Diploma Score): {c2}")

        c3 = score_c3(
            record.get("offre_exp_years", 0),
            record.get("demandeur_exp_years", 0),
            record.get("offre_metier", ""),
            record.get("demandeur_metier", "")
        )
        print(f"[DEBUG] C3 (Experience Score): {c3}")

        c4 = score_c4()
        print(f"[DEBUG] C4 (Fixed Score): {c4}")

        c5 = score_c5(
            record.get("date_offre", ""),
            record.get("date_inscription", "")
        )
        print(f"[DEBUG] C5 (Date Score): {c5}")

        scope = residence_scope or record.get(
            "residence_scope",
            DEFAULT_RESIDENCE_SCOPE
        )

        c6 = score_c6(
            record.get("offre_lieu", ""),
            record.get("demandeur_commune", ""),
            scope
        )
        print(f"[DEBUG] C6 (Residence Score): {c6}")

        # ── Store scores ──────────────────────────────────────────────────

        scores = {
            "C1": c1,
            "C2": c2,
            "C3": c3,
            "C4": c4,
            "C5": c5,
            "C6": c6,
        }

        print(f"[DEBUG] Final Scores Dictionary: {scores}")
        print(f"[DEBUG] Weights Used: {weights}")

        # ── Compute weighted employability score ──────────────────────────

        num = sum(
            weights.get(k, 0) * scores[k]
            for k in scores
        )

        denom = sum(
            weights.get(k, 0)
            for k in scores
        )

        te = round((num / denom) * 100, 2) if denom > 0 else 0.0

        print(f"[DEBUG] Weighted Sum (num): {num}")
        print(f"[DEBUG] Weight Sum (denom): {denom}")
        print(f"[DEBUG] Final Employability Score: {te}")

        ml_meta = self.meta.get(strat)

        return {
            "strategy": strat,

            "weights": {
                k: round(weights.get(k, 0), 4)
                for k in scores
            },

            "criterion_scores": {
                k: round(v, 4)
                for k, v in scores.items()
            },

            "employability_score": te,

            "classification": classify(te),

            "ml_override_active": strat in self.overrides,

            "ml_meta": ml_meta,
        }

    def score_resume(
        self,
        parsed_resume: dict,
        offer: dict,
        residence_scope: str | None = None,
    ) -> dict:
        """
        Score a candidate from a parsed resume dict + an offer dict.

        `parsed_resume` comes from resume_parser.parser.parse_resume().
        `offer` must contain:
            offre_ni,
            offre_diplome,
            offre_exp_years,
            offre_metier,
            offre_lieu,
            date_offre.

        Returns the same schema as score(), plus `parsed_fields`.
        """

        record = {
            **offer,
            **parsed_resume
        }

        result = self.score(
            record,
            residence_scope=residence_scope
        )

        result["parsed_fields"] = {
            k: v
            for k, v in parsed_resume.items()
            if k not in ("raw_text",)
        }

        return result

    # ── Summary printout ───────────────────────────────────────────────────

    def print_override_summary(self) -> None:

        print("\n── ML Weight Overrides ────────────────────────────────")

        for strat in STRATEGIES:

            weights = self.get_weights(strat)

            m = self.meta.get(strat, {})

            active = strat in self.overrides

            label = "ML" if active else "base"

            acc_str = (
                f"  acc={m.get('accuracy', '?'):.3f}"
                if active and m.get("accuracy")
                else ""
            )

            print(f"  {strat} [{label}]{acc_str}")

            for c, w in sorted(weights.items()):

                bar = "█" * int(w * 30)

                print(f"    {c}: {w:.4f}  {bar}")