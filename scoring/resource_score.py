from pymongo import MongoClient
from dotenv import load_dotenv
import os
from datetime import datetime, timezone
from typing import Dict, List, Any

load_dotenv()
client = MongoClient(os.getenv("MONGODB_URI"))
db = client[os.getenv("DATABASE_NAME")]

# Constants (from your Excel)
CSP_CATEGORIES = ["Management", "Personnel professionnel", "Encadrement de support", "Personnel d'aide"]

WEIGHTS_RESOURCES = {
    "Management": {"savoir": 45, "savoir_faire": 30, "savoir_etre": 25},
    "Personnel professionnel": {"savoir": 33, "savoir_faire": 50, "savoir_etre": 17},
    "Encadrement de support": {"savoir": 34, "savoir_faire": 33, "savoir_etre": 33},
    "Personnel d'aide": {"savoir": 0, "savoir_faire": 100, "savoir_etre": 0},
}
WEIGHTS_RES_MARKET = {
    "Management": {"resources": 80, "market": 20},
    "Personnel professionnel": {"resources": 50, "market": 50},
    "Encadrement de support": {"resources": 40, "market": 60},
    "Personnel d'aide": {"resources": 10, "market": 90},
}
SAVOIR_SCORES = {
    "Sans diplôme": 0,
    "Diplôme FP NIVEAU 1": 2,
    "Diplôme FP NIVEAU 2": 3,
    "Diplôme FP NIVEAU 3": 4,
    "Diplôme BAC +3": 6,
    "Diplôme Bac +5": 8,
    "Diplôme Bac +7 et plus": 10,
}

SAVOIR_BONUS = {
    "Diplôme FP NIVEAU 1": 1,
    "Diplôme FP NIVEAU 2": 1,
    "Diplôme FP NIVEAU 3": 2,
    "Diplôme BAC +3": 2,
    "Diplôme Bac +5": 3,
    "Diplôme Bac +7 et plus": 3,
}

COMP_TECH_BONUS_PER_EXTRA = 2

def get_savoir_score(diplomes: List[Dict]) -> float:
    if not diplomes:
        return 0.0
    sorted_dipl = sorted(
        diplomes,
        key=lambda d: SAVOIR_SCORES.get(d.get("niveau", ""), 0),
        reverse=True
    )
    base = SAVOIR_SCORES.get(sorted_dipl[0].get("niveau", ""), 0)
    bonus = SAVOIR_BONUS.get(sorted_dipl[1].get("niveau", ""), 0) if len(sorted_dipl) > 1 else 0
    return base + bonus

def get_experience_score(experiences: List[Dict]) -> float:
    if not experiences:
        return 0.0
    max_mois = max(exp.get("duree_mois", 0) for exp in experiences)
    if max_mois < 12:
        return 1.0
    elif max_mois < 36:
        return 3.0
    elif max_mois < 60:
        return 5.0
    else:
        return 8.0

def get_comp_tech_score(comps: List[Dict]) -> float:
    if not comps:
        return 0.0
    num = len(comps)
    base = 0
    if num == 0:
        base = 0
    elif num <= 2:
        base = 2
    elif num == 3:
        base = 5
    else:
        base = 8
    extras = max(0, num - 4)  # after first 4
    bonus = min(extras, 3) * COMP_TECH_BONUS_PER_EXTRA
    return base + bonus

def get_savoir_faire_score(experiences, competences_techniques) -> float:
    exp = get_experience_score(experiences)
    comp = get_comp_tech_score(competences_techniques)
    return comp + 2 * exp

def get_savoir_etre_score(soft_skills: List[str]) -> float:
    return 10.0 if soft_skills else 0.0

def compute_resources_score(profil_id=None):
    if profil_id:
        profil = db.profils.find_one({"id_demandeur": profil_id})
    else:
        profil = db.profils.find_one()  # random first one
    
    if not profil:
        return {"error": "No profil found"}
    
    csp = profil.get("csp")
    if csp not in CSP_CATEGORIES:
        return {"error": f"Unknown CSP: {csp}"}
    
    weights = WEIGHTS_RESOURCES[csp]
    
    savoir_raw = get_savoir_score(profil.get("diplomes", []))
    savoir_norm = min(100, (savoir_raw / 13.0) * 100)
    
    sf_raw = get_savoir_faire_score(profil.get("experiences", []), profil.get("competences_techniques", []))
    sf_norm = min(100, (sf_raw / 32.0) * 100)
    
    se_norm = (get_savoir_etre_score(profil.get("soft_skills", [])) / 10.0) * 100
    
    resources = (
        savoir_norm * weights["savoir"] / 100 +
        sf_norm * weights["savoir_faire"] / 100 +
        se_norm * weights["savoir_etre"] / 100
    )
    
    return {
        "csp": csp,
        "savoir_norm": round(savoir_norm, 1),
        "savoir_faire_norm": round(sf_norm, 1),
        "savoir_etre_norm": round(se_norm, 1),
        "resources_score": round(resources, 1)
    }

def classify_te(te_score: float) -> str:
    if te_score >= 70:
        return "Employabilité Optimale"
    elif te_score >= 40:
        return "Employabilité moyenne"
    elif te_score >= 20:
        return "Employabilité faible"
    else:
        return "Employabilité nulle"
