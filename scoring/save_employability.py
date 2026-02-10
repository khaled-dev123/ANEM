from pymongo import MongoClient
from dotenv import load_dotenv
import os
from datetime import datetime, timezone
from market_score import compute_market_score # import if separate file
from resource_score import compute_resources_score, WEIGHTS_RES_MARKET, classify_te

#DB init
load_dotenv()
client = MongoClient(os.getenv("MONGODB_URI"))
db = client[os.getenv("DATABASE_NAME")]


#functions

def compute_full_te(profil_id=None):
    # Get resources
    res_result = compute_resources_score(profil_id)
    if "error" in res_result:
        return res_result
    
    csp = res_result["csp"]
    resources_score = res_result["resources_score"]
    
    # Get market
    market_result = compute_market_score(csp)
    if "error" in market_result:
        return market_result
    
    market_score = market_result["market_score"]
    
    # Full TE
    res_weight = WEIGHTS_RES_MARKET[csp]["resources"]
    mkt_weight = WEIGHTS_RES_MARKET[csp]["market"]
    
    full_te = (resources_score * res_weight / 100) + (market_score * mkt_weight / 100)
    
    return {
        "csp": csp,
        "resources_score": resources_score,
        "market_score": market_score,
        "full_te": round(full_te, 1),
        "classification": classify_te(full_te)
    }
def save_all_te(batch_size=50):
    cursor = db.profils.find({}, {"id_demandeur": 1})
    updated = 0
    
    for p in cursor:
        result = compute_full_te(p["id_demandeur"])
        if "full_te" in result:
            db.profils.update_one(
                {"id_demandeur": p["id_demandeur"]},
                {"$set": {
                    "full_te": result["full_te"],
                    "te_classification": result["classification"],
                    "last_scored": datetime.now(timezone.utc)
                }}
            )
            updated += 1
        
        if updated % batch_size == 0 and updated > 0:
            print(f"Updated {updated} profiles...")
    
    print(f"Finished: {updated} profiles scored and saved.")
    
save_all_te(batch_size=50)
print("score employabilité calculé et sauvegardé pour tous les profils.")