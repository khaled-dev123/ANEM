# employability_score.py
from resource_score import compute_resources_score, WEIGHTS_RES_MARKET, classify_te
from market_score import compute_market_score
from pymongo import MongoClient
from dotenv import load_dotenv
import os
from datetime import datetime, date, timezone,timedelta

load_dotenv()
client = MongoClient(os.getenv("MONGODB_URI"))
db = client[os.getenv("DATABASE_NAME")]

def show_employability_score(profil_id: str):
    res_result = compute_resources_score(profil_id)
    if "error" in res_result:
        print(f"Erreur Resources: {res_result['error']}")
        return
    
    market_result = compute_market_score(res_result["csp"])
    if "error" in market_result:
        print(f"Erreur Market: {market_result['error']}")
        return
    
    csp = res_result["csp"]
    resources = res_result["resources_score"]
    market = market_result["market_score"]
    
    res_weight = WEIGHTS_RES_MARKET[csp]["resources"]
    mkt_weight = WEIGHTS_RES_MARKET[csp]["market"]
    
    full_te = (resources * res_weight / 100) + (market * mkt_weight / 100)
    
    print(f"\n=== Score Employabilité pour {profil_id} ({csp}) ===")
    print(f"  Resources: {resources:.1f}%")
    print(f"     - Savoir: {res_result['savoir_norm']:.1f}%")
    print(f"     - Savoir-faire: {res_result['savoir_faire_norm']:.1f}%")
    print(f"     - Savoir-être: {res_result['savoir_etre_norm']:.1f}%")
    print(f"  Market: {market:.1f}%")
    print(f"     - Tension: {market_result['tension_norm']:.1f}%")
    print(f"     - Durée attente: {market_result['duree_norm']:.1f}%")
    print(f"  Full TE: {full_te:.1f}% → {classify_te(full_te)}")
# employability_score.py

if __name__ == "__main__":
    print("Entrez un id_demandeur (ex: DEM-5E06C3DD) ou 'random' pour un aléatoire :")
    user_input = input("> ").strip()
    
    if user_input.lower() == "random":
        random_p = db.profils.aggregate([{"$sample": {"size": 1}}]).next()
        profil_id = random_p["id_demandeur"]
    else:
        profil_id = user_input
    
    show_employability_score(profil_id)