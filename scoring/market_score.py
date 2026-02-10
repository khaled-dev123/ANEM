
"""
Market Score computation: tension offre/demande + durée attente moyenne
Uses data from offres and placements collections.
"""

from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()
client = MongoClient(os.getenv("MONGODB_URI"))
db = client[os.getenv("DATABASE_NAME")]  # change if your DB name is different

WEIGHTS_MARKET = {
    "Management": {"tension": 0.7, "duree": 0.3},
    "Personnel professionnel": {"tension": 0.5, "duree": 0.5},
    "Encadrement de support": {"tension": 0.6, "duree": 0.4},
    "Personnel d'aide": {"tension": 0.3, "duree": 0.7},
}

def get_tension_score(csp: str) -> float:
    num_demands = db.profils.count_documents({"csp": csp})
    num_offers = db.offres.count_documents({
        "csp": csp,
        "statut": {"$in": ["Ouverte", "En cours"]}
    })
    
    if num_demands == 0:
        return 0.0
    
    ratio = num_offers / num_demands
    return min(100.0, 100 * ratio / (1 + ratio))  # sigmoid: slower rise, maxes at 100 only if ratio very high  # was 50, now 25 → needs ratio ≥4 for 100
def get_duree_score(csp: str) -> float:
    """
    Durée moyenne attente from placements (days)
    Normalize inverse: shorter = better (0 days → 100, 180 days → 0)
    """
    pipeline = [
        {"$match": {"csp": csp}},
        {"$group": {"_id": None, "avg_duree": {"$avg": "$duree_attente_jours"}}}
    ]
    result = list(db.placements.aggregate(pipeline))
    
    if not result or not result[0].get("avg_duree"):
        return 50.0  # neutral default if no data
    
    avg_days = result[0]["avg_duree"]
    # Shorter is better: linear scale from 0 to 180 days
    return max(0.0, 100.0 - (avg_days / 180.0 * 100.0))


def compute_market_score(csp: str) -> dict:
    if csp not in WEIGHTS_MARKET:
        return {"error": f"Unknown CSP: {csp}"}
    
    weights = WEIGHTS_MARKET[csp]
    
    tension_norm = get_tension_score(csp)
    duree_norm = get_duree_score(csp)
    
    market_score = (
        tension_norm * weights["tension"] +
        duree_norm * weights["duree"]
    )
    
    return {
        "csp": csp,
        "tension_norm": round(tension_norm, 1),
        "duree_norm": round(duree_norm, 1),
        "market_score": round(market_score, 1)
    }


# Quick test
if __name__ == "__main__":
    # Test on each CSP
    for csp in ["Management", "Personnel professionnel", "Encadrement de support", "Personnel d'aide"]:
        result = compute_market_score(csp)
        print(f"\nMarket Score for {csp}:")
        print(result)