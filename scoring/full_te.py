
from .resource_score import compute_resources_score
from .market_score import compute_market_score
from .resource_score import classify_te 
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime, timezone
import os

load_dotenv()
client = MongoClient(os.getenv("MONGODB_URI"))
db = client[os.getenv("DATABASE_NAME")]

WEIGHTS_RES_MARKET = {  # keep here or move to a constants.py
    "Management": {"resources": 80, "market": 20},
    "Personnel professionnel": {"resources": 50, "market": 50},
    "Encadrement de support": {"resources": 40, "market": 60},
    "Personnel d'aide": {"resources": 10, "market": 90},
}

def compute_full_te(profil_id: str, save_to_db: bool = False):
    res = compute_resources_score(profil_id)
    if "error" in res:
        return res
    
    mkt = compute_market_score(res["csp"])
    if "error" in mkt:
        return mkt
    
    csp = res["csp"]
    full_te = (
        res["resources_score"] * WEIGHTS_RES_MARKET[csp]["resources"] / 100 +
        mkt["market_score"] * WEIGHTS_RES_MARKET[csp]["market"] / 100
    )
    
    result = {
        "profil_id": profil_id,
        "csp": csp,
        "resources_score": round(res["resources_score"], 1),
        "market_score": round(mkt["market_score"], 1),
        "full_te": round(full_te, 1),
        "classification": classify_te(full_te)
    }
    
    if save_to_db:
        db.profils.update_one(
            {"id_demandeur": profil_id},
            {"$set": {
                "full_te": result["full_te"],
                "te_classification": result["classification"],
                "last_scored": datetime.now(timezone.utc)
            }}
        )
    
    return result