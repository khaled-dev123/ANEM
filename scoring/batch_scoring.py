from .full_te import compute_full_te
from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()
client = MongoClient(os.getenv("MONGODB_URI"))
db = client[os.getenv("DATABASE_NAME")]

def score_and_save_all(batch_size=50):
    cursor = db.profils.find({}, {"id_demandeur": 1})
    updated = 0
    
    for p in cursor:
        result = compute_full_te(p["id_demandeur"], save_to_db=True)
        if "full_te" in result:
            updated += 1
        
        if updated % batch_size == 0 and updated > 0:
            print(f"Updated {updated} profiles...")
    
    print(f"Finished: {updated} profiles scored and saved.")

def show_top_optimale(limit=10):
    top = db.profils.find(
        {"te_classification": "Employabilité Optimale"},
        {"id_demandeur": 1, "csp": 1, "full_te": 1}
    ).sort("full_te", -1).limit(limit)
    
    print(f"\nTop {limit} Optimale:")
    for p in top:
        print(f"{p['id_demandeur']} ({p.get('csp')}): {p.get('full_te')}%")

if __name__ == "__main__":
    score_and_save_all()
    show_top_optimale()