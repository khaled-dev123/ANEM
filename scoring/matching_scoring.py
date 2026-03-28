
from pymongo import MongoClient
from dotenv import load_dotenv
import os
from datetime import datetime, timezone

load_dotenv()
client = MongoClient(os.getenv("MONGODB_URI"))
db = client[os.getenv("DATABASE_NAME")]

# ====================== FUZZY MATRICES ======================

MATRIX_C1 = {
    "Sans Instruction": {"Sans Instruction": 1, "Primaire": 0.7, "Moyen": 0.3, "Secondaire": 0.1, "Universitaire": 0},
    "Primaire": {"Sans Instruction": 0.3, "Primaire": 1, "Moyen": 0.5, "Secondaire": 0.2, "Universitaire": 0},
    "Moyen": {"Sans Instruction": 0, "Primaire": 0.3, "Moyen": 1, "Secondaire": 0.5, "Universitaire": 0},
    "Secondaire": {"Sans Instruction": 0, "Primaire": 0, "Moyen": 0.3, "Secondaire": 1, "Universitaire": 0.5},
    "Universitaire": {"Sans Instruction": 0, "Primaire": 0, "Moyen": 0, "Secondaire": 0.5, "Universitaire": 1}
}

MATRIX_C4 = {
    "A1": {"A1": 1.0, "A2": 0.9, "B1": 0.75, "B2": 0.6, "C1": 0.45, "C2": 0.3},
    "A2": {"A1": 0.6, "A2": 1.0, "B1": 0.9, "B2": 0.75, "C1": 0.6, "C2": 0.45},
    "B1": {"A1": 0.4, "A2": 0.65, "B1": 1.0, "B2": 0.9, "C1": 0.75, "C2": 0.6},
    "B2": {"A1": 0.25, "A2": 0.45, "B1": 0.7, "B2": 1.0, "C1": 0.9, "C2": 0.75},
    "C1": {"A1": 0.1, "A2": 0.3, "B1": 0.55, "B2": 0.8, "C1": 1.0, "C2": 0.9},
    "C2": {"A1": 0.05, "A2": 0.2, "B1": 0.4, "B2": 0.65, "C1": 0.85, "C2": 1.0}
}

MATRIX_C6 = {
    "Même Commune": {"Même Commune": 1.0, "Même Wilaya": 0.7, "Wilaya limitrophe": 0.0, "Même région": 0.0, "Autres": 0.0},
    "Même Wilaya": {"Même Commune": 1.0, "Même Wilaya": 1.0, "Wilaya limitrophe": 0.7, "Même région": 0.2, "Autres": 0.0},
    "Wilaya limitrophe": {"Même Commune": 1.0, "Même Wilaya": 1.0, "Wilaya limitrophe": 1.0, "Même région": 1.0, "Autres": 0.2}
}

STRATEGIES = {
    "S3": {"C1": 3, "C2": 2, "C3": 1, "C4": 1, "C5": 1, "C6": 1},   # Cadre
    "S2": {"C1": 2, "C2": 1, "C3": 2, "C4": 1, "C5": 2, "C6": 2},   # Professionalité
    "S1": {"C1": 2, "C2": 1, "C3": 1, "C4": 0, "C5": 3, "C6": 3},   # Exécution
    "S0": {"C1": 1, "C2": 1, "C3": 1, "C4": 1, "C5": 1, "C6": 1},   # Uniforme
}

def fuzzy_match(value1, value2, matrix):
    """Safe fuzzy lookup"""
    if not value1 or not value2:
        return 0.0
    return matrix.get(str(value1), {}).get(str(value2), 0.4) 

def get_matching_score(profil_id: str, offre_id: str, strategy_code: str = "S0"):
    """Compute fuzzy matching score using C1-C6 matrices"""
    profil = db.profils.find_one({"id_demandeur": profil_id})
    offre = db.offres.find_one({"id_offre": offre_id})
    
    if not profil or not offre:
        return {"error": "Profil or Offre not found"}

    weights = STRATEGIES.get(strategy_code, STRATEGIES["S0"])

    score_c1 = fuzzy_match(profil.get("ni"), offre.get("ni"), MATRIX_C1)

    score_c2 = 1.0 if any(d.get("niveau") == o.get("niveau") for d in profil.get("diplomes", []) for o in offre.get("diplomes", [])) else 0.5

    profil_exp = profil.get("experiences", [{}])[0].get("annees", 0)
    offre_exp = offre.get("nb_annee_exp", 0)
    score_c3 = 1.0 if profil_exp >= offre_exp else 0.6

    score_c4 = max((fuzzy_match(l.get("niveau"), ol.get("niveau"), MATRIX_C4) for l in profil.get("langues", []) for ol in offre.get("langues", [])), default=0.4)

    score_c5 = 1.0 if profil.get("date_debut_validite") <= offre.get("date_confirmation") else 0.3

    score_c6 = fuzzy_match(profil.get("commune_residence"), offre.get("commune_lieu_travail"), MATRIX_C6)

    total = (
        score_c1 * weights["C1"] +
        score_c2 * weights["C2"] +
        score_c3 * weights["C3"] +
        score_c4 * weights["C4"] +
        score_c5 * weights["C5"] +
        score_c6 * weights["C6"]
    )
    final_score = total / sum(weights.values())

    return {
        "profil_id": profil_id,
        "offre_id": offre_id,
        "strategy": strategy_code,
        "matching_score": round(final_score * 100, 1),
        "c1": round(score_c1 * 100, 1),
        "c2": round(score_c2 * 100, 1),
        "c3": round(score_c3 * 100, 1),
        "c4": round(score_c4 * 100, 1),
        "c5": round(score_c5 * 100, 1),
        "c6": round(score_c6 * 100, 1)
    }


#test
if __name__ == "__main__":
    # use real IDs
    result = get_matching_score("DEM-5E06C3DD", "OFF-XXXXXXX", strategy_code="S3")
    print(result)