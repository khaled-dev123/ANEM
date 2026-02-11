# agents/weighting_agent.py
"""
Agent 1: Pondération Dynamique
Ajuste les poids Savoir / Savoir-faire / Savoir-être par CSP
en se basant sur les placements réussis (duree_attente_jours faible = succès).
"""

from pymongo import MongoClient
from dotenv import load_dotenv
import os
from scipy.stats import pearsonr  # pour corrélation (pip install scipy si besoin)
import numpy as np
from scoring.resource_score import CSP_CATEGORIES

load_dotenv()
client = MongoClient(os.getenv("MONGODB_URI"))
db = client[os.getenv("DATABASE_NAME")]

# Poids initiaux (fallback si pas assez de data)
DEFAULT_WEIGHTS = {
    "Management": {"savoir": 45, "savoir_faire": 30, "savoir_etre": 25},
    "Personnel professionnel": {"savoir": 33, "savoir_faire": 50, "savoir_etre": 17},
    "Encadrement de support": {"savoir": 34, "savoir_faire": 33, "savoir_etre": 33},
    "Personnel d'aide": {"savoir": 0, "savoir_faire": 100, "savoir_etre": 0},
}

def get_placed_profiles(csp: str, min_placements=5):
    """
    Récupère les profils placés pour un CSP + leurs sub-scores + duree_attente
    """
    pipeline = [
        {"$match": {"csp": csp}},
        {
            "$lookup": {
                "from": "profils",
                "localField": "id_demandeur",
                "foreignField": "id_demandeur",
                "as": "profil"
            }
        },
        {"$unwind": "$profil"},
        {
            "$project": {
                "id_demandeur": 1,
                "duree_attente_jours": 1,
                "savoir_norm": "$profil.resources.savoir_norm",      # assume you saved these after batch
                "savoir_faire_norm": "$profil.resources.savoir_faire_norm",
                "savoir_etre_norm": "$profil.resources.savoir_etre_norm"
            }
        },
        {"$match": {"savoir_norm": {"$exists": True}}}  # only if scored
    ]
    
    results = list(db.placements.aggregate(pipeline))
    if len(results) < min_placements:
        print(f"Pas assez de placements pour {csp} ({len(results)} trouvés)")
        return None
    
    return results


def compute_dynamic_weights(csp: str):
    placed = get_placed_profiles(csp)
    if placed is None:
        return DEFAULT_WEIGHTS.get(csp, {"savoir": 33, "savoir_faire": 33, "savoir_etre": 34})
    
    # Calcul success score : plus courte attente = meilleur
    durees = np.array([p["duree_attente_jours"] for p in placed])
    max_duree = np.max(durees) if len(durees) > 0 else 180
    success_scores = 100 - (durees / max_duree * 100)  # 100 = très rapide
    
    savoirs = np.array([p["savoir_norm"] for p in placed])
    savoir_faires = np.array([p["savoir_faire_norm"] for p in placed])
    savoir_etres = np.array([p["savoir_etre_norm"] for p in placed])
    
    # Corrélation de Pearson (plus fort = plus important)
    corr_savoir, _ = pearsonr(success_scores, savoirs) if len(savoirs) > 1 else (0, 0)
    corr_faire, _ = pearsonr(success_scores, savoir_faires) if len(savoir_faires) > 1 else (0, 0)
    corr_etre, _ = pearsonr(success_scores, savoir_etres) if len(savoir_etres) > 1 else (0, 0)
    
    # Prendre valeurs absolues (corrélation peut être négative)
    corrs = np.abs([corr_savoir, corr_faire, corr_etre])
    
    # Normaliser pour sommer à 100
    if np.sum(corrs) == 0:
        return DEFAULT_WEIGHTS[csp]  # fallback si corrélation nulle
    
    weights_sum = np.sum(corrs)
    new_weights = {
        "savoir": round(corrs[0] / weights_sum * 100, 0),
        "savoir_faire": round(corrs[1] / weights_sum * 100, 0),
        "savoir_etre": round(corrs[2] / weights_sum * 100, 0)
    }
    
    print(f"Nouveaux poids dynamiques pour {csp}: {new_weights}")
    print(f"Basé sur {len(placed)} placements (corr savoir: {corr_savoir:.2f}, faire: {corr_faire:.2f}, etre: {corr_etre:.2f})")
    
    return new_weights


# Test rapide
if __name__ == "__main__":
    for csp in CSP_CATEGORIES:
        compute_dynamic_weights(csp)