
from pymongo import MongoClient
from dotenv import load_dotenv
import os
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

load_dotenv()
client = MongoClient(os.getenv("MONGODB_URI"))
db = client[os.getenv("DATABASE_NAME")]

def vectorize_profil(profil):
    """Simple vector for similarity (C1-C6 features)"""
    vec = [
        1 if profil.get("ni") else 0,
        len(profil.get("diplomes", [])),
        sum(e.get("annees", 0) for e in profil.get("experiences", [])),
        len(profil.get("langues", [])),
        1 if profil.get("date_debut_validite") else 0,
        1 if profil.get("commune_residence") else 0
    ]
    return np.array(vec, dtype=float)

def generate_recommendations(profil_id: str, top_k: int = 10):
    """Find gaps and generate recommendations"""
    target = db.profils.find_one({"id_demandeur": profil_id})
    if not target:
        return {"error": "Profil not found"}

    optimal_profil = list(db.profils.find(
        {"full_te": {"$gte": 70}},
        {"id_demandeur": 1, "diplomes": 1, "experiences": 1, "langues": 1, "commune_residence": 1}
    ).limit(top_k))

    if not optimal_profil:
        return {"message": "No optimal profiles found for comparison"}

    # Vectorize for similarity
    target_vec = vectorize_profil(target)
    optimal_vecs = [vectorize_profil(p) for p in optimal_profil]
    
    similarities = cosine_similarity([target_vec], optimal_vecs)[0]
    best_match_idx = np.argmax(similarities)
    best_match = optimal_profil[best_match_idx]


    gaps = []
    if not target.get("diplomes"):
        gaps.append("Acquire a higher diploma (C2)")
    if sum(e.get("annees", 0) for e in target.get("experiences", [])) < 3:
        gaps.append("Gain more professional experience (C3)")
    if not any(l.get("niveau") in ["B2", "C1"] for l in target.get("langues", [])):
        gaps.append("Improve foreign language level to B2 or higher (C4)")
    if target.get("commune_residence") != best_match.get("commune_residence"):
        gaps.append("Consider relocating closer to job opportunities (C6)")

    recommendations = [f"Recommendation: {gap}" for gap in gaps]

    return {
        "profil_id": profil_id,
        "best_matching_optimal_profil": best_match["id_demandeur"],
        "similarity_score": round(float(similarities[best_match_idx]) * 100, 1),
        "gaps": gaps,
        "recommendations": recommendations
    }


if __name__ == "__main__":
    # Test with one profil
    test_id = "DEM-5E06C3DD"   # replace with a real ID
    result = generate_recommendations(test_id)
    print(result)