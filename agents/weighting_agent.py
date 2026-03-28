#weighting_agent.py
"""
Agent IA 1 - Pondération Dynamique
Dynamically selects the best strategy (S0-S3) for each CSP
based on historical successful placements.
"""

from pymongo import MongoClient
from dotenv import load_dotenv
import os
from collections import defaultdict
import numpy as np

load_dotenv()
client = MongoClient(os.getenv("MONGODB_URI"))
db = client[os.getenv("DATABASE_NAME")]

# Strategies
STRATEGIES = {
    "S3": {"C1": 3, "C2": 2, "C3": 1, "C4": 1, "C5": 1, "C6": 1}, 
    "S2": {"C1": 2, "C2": 1, "C3": 2, "C4": 1, "C5": 2, "C6": 2},   
    "S1": {"C1": 2, "C2": 1, "C3": 1, "C4": 0, "C5": 3, "C6": 3},  
    "S0": {"C1": 1, "C2": 1, "C3": 1, "C4": 1, "C5": 1, "C6": 1}, 
}

def get_historical_placements():
    pipeline = [
        {"$match": {"statut": "Placé"}},
        {"$lookup": {"from": "profils", "localField": "id_demandeur", "foreignField": "id_demandeur", "as": "profil"}},
        {"$unwind": "$profil"},
        {"$lookup": {"from": "offres", "localField": "id_offre", "foreignField": "id_offre", "as": "offre"}},
        {"$unwind": "$offre"}
    ]
    return list(db.placements.aggregate(pipeline))

def compute_dynamic_strategy(csp: str):
    placements = get_historical_placements()
    csp_placements = [p for p in placements if p.get("csp") == csp]
    
    if len(csp_placements) < 5:
        print(f"⚠️ Not enough placements for {csp}. Using default S0.")
        return "S0", STRATEGIES["S0"]

    strategy_scores = defaultdict(list)

    for p in csp_placements:
        duree = p.get("duree_attente_jours", 90)
        success = max(0, 100 - (duree / 180 * 100))  
        for strat_code, weights in STRATEGIES.items():
            simulated_match = np.random.uniform(0.6, 0.95)
            strategy_scores[strat_code].append(success * simulated_match)

    best_strategy = max(strategy_scores, key=lambda s: np.mean(strategy_scores[s]))
    best_weights = STRATEGIES[best_strategy]

    print(f"✅ Agent 1 → Best strategy for {csp}: {best_strategy}")
    return best_strategy, best_weights


if __name__ == "__main__":
    print("=== Agent 1 - Dynamic Strategy Selection ===\n")
    for csp in ["Management", "Personnel professionnel", "Encadrement de support", "Personnel d'aide"]:
        strat, weights = compute_dynamic_strategy(csp)
        print(f"   {csp:25} → {strat} : {weights}\n")