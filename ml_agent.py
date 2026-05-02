"""
ml_agent.py
-----------
Main entry point for the ML agent.

Workflow:
    1. Connect to MongoDB Atlas
    2. Fetch all 37,358 placement records
    3. Train one Logistic Regression per strategy (S0–S3)
    4. Extract per-strategy feature importances
    5. Compute dynamic weight overrides (blend ML + base)
    6. Push overrides back to MongoDB referential collection
    7. Save local JSON cache (ml_weight_cache.json)

Then:
    8. Accept a new .txt resume + offer dict
    9. Parse the resume
   10. Score it with ML-overridden weights
   11. Print full breakdown

Usage:
    # Train only
    python ml_agent.py --train

    # Score a resume (uses cached weights if already trained)
    python ml_agent.py --resume path/to/resume.txt \\
                       --offre-ni "Supérieur 1" \\
                       --offre-diplome "Génie civil" \\
                       --offre-exp 2 \\
                       --offre-metier "Ingénieur" \\
                       --offre-lieu "CHERAGA" \\
                       --date-offre "2025-06-01"

    # Train then immediately score
    python ml_agent.py --train --resume path/to/resume.txt ...

    # Print current weight overrides
    python ml_agent.py --show-weights

    # Demo mode (no MongoDB needed, uses synthetic data)
    python ml_agent.py --demo
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from datetime import datetime, date
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from agent.features   import record_to_features, FEATURE_NAMES
from agent.trainer    import train_all, save_cache, load_cache, push_to_mongo, CACHE_PATH
from agent.dynamic_scorer import DynamicScorer
from resume_parser.parser  import parse_resume, parse_resume_text
from scoring.scoring_config import (
    NI_CANONICAL, get_normalized_weights, WILAYA_ALGER_COMMUNES,
)

# ── MongoDB helpers ───────────────────────────────────────────────────────────

def connect_mongo():
    """Connect to MongoDB Atlas. Returns (client, db) or raises."""
    try:
        from pymongo import MongoClient
        from dotenv import load_dotenv
        load_dotenv()
        uri = os.getenv("MONGODB_URI")
        if not uri:
            raise ValueError("MONGODB_URI not set in environment / .env")
        client = MongoClient(uri, serverSelectionTimeoutMS=8000)
        client.admin.command("ping")
        db = client["employability_db"]
        print(f"✅ Connected to MongoDB Atlas — db: employability_db")
        return client, db
    except ImportError:
        raise ImportError("pymongo not installed. Run: pip install pymongo python-dotenv")


def fetch_placements(db, limit: int | None = None) -> list[dict]:
    """Fetch placement records from MongoDB."""
    print(f"📥 Fetching placements from MongoDB...")
    query  = {}
    cursor = db["placements"].find(query, {"_id": 0})
    if limit:
        cursor = cursor.limit(limit)
    records = list(cursor)
    print(f"   → {len(records)} records fetched.")
    return records


# ── Synthetic demo data ───────────────────────────────────────────────────────

def _make_synthetic_records(n: int = 500) -> list[dict]:
    """
    Generate synthetic placement records for demo / offline testing.
    These mimic the structure of the real dataset.
    """
    random.seed(42)
    nis = [
        ("Sans niveau",  "S0"), ("Primaire", "S0"),
        ("Moyen",        "S1"), ("Secondaire 2AS", "S1"),
        ("Supérieur 1",  "S2"), ("Supérieur 2", "S3"),
        ("Universitaire","S3"),
    ]
    diplomes = [
        "Génie civil", "Informatique", "Gestion", "Commerce",
        "Mécanique", "Électronique", "Comptabilité", "Économie",
        "Droit", "Architecture", "", "Agronomie",
    ]
    metiers = [
        "Ingénieur", "Technicien", "Responsable logistique",
        "Comptable", "Agent commercial", "Opérateur",
        "Chef de projet", "Directeur", "Assistant administratif",
    ]
    communes = list(WILAYA_ALGER_COMMUNES)[:20] + ["TIZI OUZOU", "BLIDA", "TIPAZA"]

    records = []
    for i in range(n):
        ni_label, _ = random.choice(nis)
        metier = random.choice(metiers)
        diplome = random.choice(diplomes)
        commune = random.choice(communes)

        # Generate plausible dates
        insc_year = random.randint(2012, 2018)
        insc_date = f"{insc_year}-{random.randint(1,12):02d}-{random.randint(1,28):02d}"
        offre_year = insc_year + random.randint(0, 3)
        offre_date = f"{offre_year}-{random.randint(1,12):02d}-{random.randint(1,28):02d}"
        anc_days = max(0, (datetime.fromisoformat(offre_date) -
                           datetime.fromisoformat(insc_date)).days)

        exp = random.randint(0, 15)

        records.append({
            "placement_id":         f"SYNTH-{i+1:05d}",
            "offre_ni":             ni_label,
            "offre_diplome":        diplome,
            "offre_exp_years":      max(0, exp - random.randint(0, 2)),
            "offre_metier":         metier,
            "offre_lieu":           random.choice(communes[:15]),
            "date_offre":           offre_date,
            "demandeur_ni":         ni_label,
            "demandeur_diplome":    diplome,
            "demandeur_exp_years":  exp,
            "demandeur_metier":     metier,
            "demandeur_commune":    commune,
            "date_inscription":     insc_date,
            "anciennete_days":      anc_days,
            "placement_success":    1,
        })
    return records


# ── Training pipeline ─────────────────────────────────────────────────────────

def run_training(records: list[dict], db=None) -> dict:
    """Train all strategies and persist results."""
    print(f"\n🧠 Training Logistic Regression models on {len(records)} records...")
    results = train_all(records, verbose=True)

    save_cache(results)

    if db is not None:
        push_to_mongo(results, db)

    return results


# ── Resume scoring pipeline ───────────────────────────────────────────────────

def run_resume_scoring(
    resume_path: str,
    offer: dict,
    scorer: DynamicScorer,
) -> dict:
    """Parse a resume and score it against an offer."""
    print(f"\n📄 Parsing resume: {resume_path}")
    parsed = parse_resume(resume_path)

    print(f"   NI detected:      {parsed['demandeur_ni']}")
    print(f"   Diplôme:          {parsed['demandeur_diplome'] or '(none detected)'}")
    print(f"   Expérience:       {parsed['demandeur_exp_years']} ans")
    print(f"   Métier:           {parsed['demandeur_metier'] or '(none detected)'}")
    print(f"   Commune:          {parsed['demandeur_commune']}")
    print(f"   Langues:          {', '.join(parsed['languages']) or '(none)'}")

    result = scorer.score_resume(parsed, offer)
    return result


# ── Result display ────────────────────────────────────────────────────────────

def print_score_result(result: dict) -> None:
    s = result
    print("\n" + "═" * 55)
    print(f"  EMPLOYABILITY SCORE   {s['employability_score']:.1f} / 100")
    print(f"  Classification:       {s['classification']}")
    print(f"  Strategy:             {s['strategy']}")
    print(f"  ML override active:   {'✅ YES' if s.get('ml_override_active') else '⬜ NO (base weights)'}")
    if s.get("ml_meta"):
        m = s["ml_meta"]
        print(f"  ML accuracy (CV):     {m.get('accuracy', '?'):.3f}")
        print(f"  Trained on:           {m.get('n_samples', '?')} samples")
    print("═" * 55)
    print(f"  {'Criterion':<28} {'Score':>6}  {'Weight':>7}  {'Contrib':>7}")
    print(f"  {'-'*28} {'-'*6}  {'-'*7}  {'-'*7}")
    labels = {
        "C1": "Niveau instruction",
        "C2": "Diplômes",
        "C3": "Expériences",
        "C4": "Langues",
        "C5": "Ancienneté",
        "C6": "Résidence",
    }
    for k in ("C1","C2","C3","C4","C5","C6"):
        sc = s["criterion_scores"].get(k, 0)
        w  = s["weights"].get(k, 0)
        contrib = sc * w * 100
        print(f"  {k} {labels[k]:<24}  {sc:>6.3f}  {w:>7.4f}  {contrib:>7.1f}")
    print("═" * 55)


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="ML agent for ANEM employability scoring",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--train",        action="store_true",
                   help="Fetch placements from MongoDB and train LR models")
    p.add_argument("--demo",         action="store_true",
                   help="Run in demo mode with synthetic data (no MongoDB needed)")
    p.add_argument("--show-weights", action="store_true",
                   help="Print current weight overrides and exit")
    p.add_argument("--resume",       type=str, metavar="FILE",
                   help="Path to a plain-text resume (.txt) to score")

    # Offer fields for scoring
    p.add_argument("--offre-ni",      default="Supérieur 1")
    p.add_argument("--offre-diplome", default="")
    p.add_argument("--offre-exp",     type=int, default=2)
    p.add_argument("--offre-metier",  default="")
    p.add_argument("--offre-lieu",    default="ALGER")
    p.add_argument("--date-offre",    default=date.today().isoformat())
    p.add_argument("--residence-scope", default="S2",
                   choices=["S1","S2","S3"])

    p.add_argument("--limit", type=int, default=None,
                   help="Limit number of records fetched from MongoDB (for testing)")
    return p


def main():
    args = build_parser().parse_args()

    # ── Demo mode: no MongoDB ─────────────────────────────────────────────
    if args.demo:
        print("🎭 Running in DEMO mode (synthetic data, no MongoDB required)")
        records = _make_synthetic_records(n=800)
        results = run_training(records, db=None)
        scorer  = DynamicScorer.from_cache()
        scorer.print_override_summary()

        # Demo resume text
        demo_resume = """
        Ahmed Benali
        Adresse: 12 Rue des Oliviers, Cheraga, Alger
        Date d'inscription: 15/03/2016

        FORMATION
        Licence en Informatique — Université d'Alger 1 (Bac+3)
        Obtenu en 2014

        EXPÉRIENCE PROFESSIONNELLE
        Développeur logiciel — TechAlger SARL
        2014 – 2019

        Technicien informatique — InfoSolutions DZ
        2012 – 2014

        LANGUES
        Français (courant), Anglais (intermédiaire), Arabe (maternel)
        """
        parsed = parse_resume_text(demo_resume, "demo_resume.txt")
        print(f"\n📄 Demo resume parsed:")
        print(f"   NI: {parsed['demandeur_ni']} | Exp: {parsed['demandeur_exp_years']} ans"
              f" | Métier: {parsed['demandeur_metier']}")

        offer = {
            "offre_ni":        "Supérieur 1",
            "offre_diplome":   "Informatique",
            "offre_exp_years": 3,
            "offre_metier":    "Développeur logiciel",
            "offre_lieu":      "CHERAGA",
            "date_offre":      "2019-09-01",
        }
        result = scorer.score_resume(parsed, offer)
        print_score_result(result)
        return

    # ── Show weights only ─────────────────────────────────────────────────
    if args.show_weights:
        scorer = DynamicScorer.from_cache()
        scorer.print_override_summary()
        return

    # ── Training (requires MongoDB) ───────────────────────────────────────
    db = None
    if args.train:
        client, db = connect_mongo()
        records = fetch_placements(db, limit=args.limit)
        run_training(records, db=db)

    # ── Load scorer (from cache or DB) ────────────────────────────────────
    if db is not None:
        scorer = DynamicScorer.from_mongo(db)
    else:
        scorer = DynamicScorer.from_cache()

    scorer.print_override_summary()

    # ── Score a resume ────────────────────────────────────────────────────
    if args.resume:
        offer = {
            "offre_ni":        args.offre_ni,
            "offre_diplome":   args.offre_diplome,
            "offre_exp_years": args.offre_exp,
            "offre_metier":    args.offre_metier,
            "offre_lieu":      args.offre_lieu,
            "date_offre":      args.date_offre,
        }
        result = run_resume_scoring(args.resume, offer, scorer)
        print_score_result(result)

    if db is not None:
        db.client.close()


if __name__ == "__main__":
    main()
