
"""
score_profiles.py  (v2 — ANEM criteria)
----------------------------------------
Scores standalone candidate profiles from the `profiles` collection.
These are synthetic profiles from generate_data.py (or manually created ones).

The `placements` collection (real data) is already scored during load_real_data.py.
This script handles the profile collection separately.

Usage:
    python score_profiles.py                      # Score unscored profiles
    python score_profiles.py --all                # Re-score all
    python score_profiles.py --profile PRF-0042   # Single profile
    python score_profiles.py --report             # Distribution report
"""

import argparse
import os
from datetime import datetime

from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv

from scoring_engine import compute_employability_score

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME     = "employability_db"
BATCH_SIZE  = 200


# ── Map synthetic profile → scoring_engine input dict ────────────────────────

def profile_to_record(profile: dict, best_offer: dict = None) -> dict:
    """
    Converts a synthetic profile document to the flat record format
    expected by compute_employability_score().

    If best_offer is provided (nearest active offer), we use it for
    offer-side fields. Otherwise we use self-reported target fields.
    """
    edu   = profile.get("education", {})
    exp   = profile.get("experience", {})
    skl   = profile.get("skills", {})
    pers  = profile.get("personal", {})

    # Map Bac-system levels → ANEM NI categories
    bac_to_ni = {
        "Bac":      "Secondaire 3AS",
        "Bac+2":    "Supérieur 1",
        "Bac+3":    "Supérieur 1",
        "Bac+5":    "Supérieur 2",
        "Doctorat": "UNIVERSITAIRE",
    }
    demandeur_ni = bac_to_ni.get(edu.get("level", "Bac"), "MOYEN")

    # Use the best matching offer if available, otherwise self-target
    if best_offer:
        offre_ni         = best_offer.get("required_skills", {}).get("min_education_level", demandeur_ni)
        offre_exp_years  = best_offer.get("required_skills", {}).get("min_experience_years", 0)
        offre_metier     = best_offer.get("title", "")
        offre_lieu       = best_offer.get("region", "ALGER")
        offre_diplome    = best_offer.get("required_skills", {}).get("field", edu.get("field", ""))
        date_offre       = best_offer.get("created_at", datetime.utcnow().isoformat())
    else:
        offre_ni         = demandeur_ni
        offre_exp_years  = max(0, exp.get("years_total", 0) - 1)
        offre_metier     = profile.get("target_sector", "")
        offre_lieu       = pers.get("city", "ALGER")
        offre_diplome    = edu.get("field", "")
        date_offre       = datetime.utcnow().isoformat()

    return {
        "offre_ni":            offre_ni,
        "offre_diplome":       offre_diplome,
        "offre_exp_years":     offre_exp_years,
        "offre_metier":        offre_metier,
        "offre_lieu":          offre_lieu,
        "date_offre":          date_offre,

        "demandeur_ni":         demandeur_ni,
        "demandeur_diplome":    edu.get("field", ""),
        "demandeur_exp_years":  exp.get("years_total", 0),
        "demandeur_metier":     (exp.get("jobs") or [{}])[0].get("title", ""),
        "demandeur_commune":    pers.get("city", "ALGER"),
        "date_inscription":     profile.get("created_at", datetime.utcnow().isoformat()),
    }


# ── Find nearest active offer for a profile ───────────────────────────────────

def find_best_offer(db, profile: dict) -> dict | None:
    """Finds the most relevant active offer for a profile (same sector, active)."""
    sector = profile.get("target_sector")
    offer  = db.job_offers.find_one(
        {"sector": sector, "is_active": True},
        sort=[("market.applications_count", 1)],   # least contested first
    )
    return offer


# ── Score a single profile ────────────────────────────────────────────────────

def score_profile(profile: dict, best_offer: dict) -> dict:
    record = profile_to_record(profile, best_offer)
    result = compute_employability_score(record)
    return {
        "resource_score":      result["criterion_scores"].get("C1", 0) * 100,  # C1 as proxy RS
        "market_score":        result["criterion_scores"].get("C3", 0) * 100,  # C3 as proxy MS
        "employability_score": result["employability_score"],
        "classification":      result["classification"],
        "strategy":            result["strategy"],
        "criterion_scores":    result["criterion_scores"],
        "weights":             result["weights"],
        "scored_at":           datetime.utcnow().isoformat(),
    }


# ── Batch runner ──────────────────────────────────────────────────────────────

def run(score_all: bool = False, single_id: str = None, report: bool = False):
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    db = client[DB_NAME]

    # Which profiles to score
    if single_id:
        query = {"profile_id": single_id}
    elif score_all:
        query = {}
    else:
        query = {"scores.employability_score": None}

    profiles = list(db.profiles.find(query))
    print(f"Profiles to score: {len(profiles)}")

    if not profiles:
        print("Nothing to score. Use --all to re-score existing profiles.")
        client.close()
        return

    operations = []
    for profile in profiles:
        best_offer = find_best_offer(db, profile)
        scores     = score_profile(profile, best_offer)
        operations.append(UpdateOne(
            {"_id": profile["_id"]},
            {"$set": {"scores": scores}},
        ))

    # Bulk write
    total_updated = 0
    for i in range(0, len(operations), BATCH_SIZE):
        batch  = operations[i: i + BATCH_SIZE]
        result = db.profiles.bulk_write(batch, ordered=False)
        total_updated += result.modified_count

    print(f"✅ {total_updated} profile(s) scored and updated.")

    if single_id and profiles:
        p  = profiles[0]
        bo = find_best_offer(db, p)
        s  = score_profile(p, bo)
        print(f"\n── {single_id} ───────────────────────────────────────")
        print(f"  Strategy:            {s['strategy']}")
        print(f"  Employability (TE):  {s['employability_score']}")
        print(f"  Classification:      {s['classification']}")
        print(f"  Criterion scores:")
        for k, v in s["criterion_scores"].items():
            print(f"    {k}: {v:.3f}  (w={s['weights'][k]:.3f})")

    if report:
        pipeline = [
            {"$match": {"scores.employability_score": {"$ne": None}}},
            {"$group": {
                "_id":    "$scores.classification",
                "count":  {"$sum": 1},
                "avg_te": {"$avg": "$scores.employability_score"},
            }},
            {"$sort": {"avg_te": -1}},
        ]
        print("\n── Score Distribution (profiles) ────────────────────")
        print(f"  {'Class':<12} {'Count':>6} {'Avg TE':>8}")
        for r in db.profiles.aggregate(pipeline):
            print(f"  {str(r['_id']):<12} {r['count']:>6} {r['avg_te']:>8.1f}")

    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--all",     action="store_true")
    parser.add_argument("--profile", type=str)
    parser.add_argument("--report",  action="store_true")
    args = parser.parse_args()
    run(score_all=args.all, single_id=args.profile, report=args.report)
