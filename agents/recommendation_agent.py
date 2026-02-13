# agents/recommendation_agent.py
"""
Agent 2: Prescriptive Recommendation
Finds 10 similar optimal profiles → calculates gaps → generates suggestions in French
"""

from pymongo import MongoClient
from dotenv import load_dotenv
import os
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction import DictVectorizer
import numpy as np
from bson import ObjectId  # if you ever need ObjectId queries

load_dotenv()
client = MongoClient(os.getenv("MONGODB_URI"))
db = client[os.getenv("DATABASE_NAME")]

OPTIMAL_THRESHOLD = 70.0  # TE >= 70 = Optimal

def vectorize_profile(profil):
    """Turn profile into feature vector for similarity"""
    features = {}
    
    # Diplomas (one-hot by level)
    for d in profil.get("diplomes", []):
        niveau = d.get("niveau", "none").replace(" ", "_").replace("+", "plus")
        features[f"diplome_{niveau}"] = 1
    
    # Tech skills (name + étoiles level as value)
    for c in profil.get("competences_techniques", []):
        nom = c.get("nom", "unknown").replace(" ", "_")
        features[f"comp_{nom}"] = c.get("etoiles", 0)
    
    # Soft skills (binary)
    for s in profil.get("soft_skills", []):
        features[f"soft_{s.replace(' ', '_')}"] = 1
    
    # Experience (max months)
    max_months = max((e.get("duree_mois", 0) for e in profil.get("experiences", [])), default=0)
    features["experience_months"] = max_months
    
    # Languages (level mapping)
    level_map = {"Natif": 5, "Courant": 4, "Intermédiaire": 3, "Élémentaire": 2, "Aucun": 0}
    for l in profil.get("langues", []):
        langue = l.get("langue", "unknown").replace(" ", "_")
        features[f"lang_{langue}"] = level_map.get(l.get("niveau", ""), 0)
    
    return features

def get_optimal_neighbors(profil_id: str, top_k=10):
    current = db.profils.find_one({"id_demandeur": profil_id})
    if not current:
        return "Profile not found", None, None
    
    if current.get("full_te", 0) >= OPTIMAL_THRESHOLD:
        return "Profile already optimal — no recommendations needed", None, None
    
    csp = current["csp"]
    
    # First try same CSP
    optimal_profiles = list(db.profils.find({
        "csp": csp,
        "full_te": {"$gte": OPTIMAL_THRESHOLD}
    }))
    
    # Fallback: all CSPs if not enough in same
    if len(optimal_profiles) < top_k:
        print(f"Only {len(optimal_profiles)} optimal in same CSP — using all CSPs as fallback")
        optimal_profiles = list(db.profils.find({
            "full_te": {"$gte": OPTIMAL_THRESHOLD}
        }).limit(50))  # limit to avoid too many
    
    if not optimal_profiles:
        return "No optimal profiles found in database", None, None
    
    # Vectorize
    vectorizer = DictVectorizer(sparse=False)
    current_vec = vectorizer.fit_transform([vectorize_profile(current)])
    optimal_vecs = vectorizer.transform([vectorize_profile(p) for p in optimal_profiles])
    
    # Cosine similarity
    similarities = cosine_similarity(current_vec, optimal_vecs)[0]
    
    # Top K
    top_indices = np.argsort(similarities)[-top_k:][::-1]
    neighbors = [optimal_profiles[i] for i in top_indices]
    scores = [similarities[i] for i in top_indices]
    
    return neighbors, scores, vectorizer

def generate_recommendations(profil_id: str):
    current = db.profils.find_one({"id_demandeur": profil_id})
    if not current:
        return "Profil non trouvé"
    
    neighbors, scores, vectorizer = get_optimal_neighbors(profil_id)
    if isinstance(neighbors, str):
        print(neighbors)
        return neighbors
    
    # Average of optimal neighbors
    avg_optimal_vec = np.mean(vectorizer.transform([vectorize_profile(p) for p in neighbors]), axis=0)
    current_vec = vectorizer.transform([vectorize_profile(current)])[0]
    
    # Gaps (optimal average > current, threshold 1.0 for meaningful difference)
    gaps = avg_optimal_vec - current_vec
    feature_names = vectorizer.get_feature_names_out()
    gap_features = [(feature_names[i], gaps[i]) for i in range(len(gaps)) if gaps[i] > 1.0]
    gap_features.sort(key=lambda x: x[1], reverse=True)
    
    # Generate French prescriptions (top 5 gaps)
    prescriptions = []
    for feature, strength in gap_features[:5]:
        if feature.startswith("diplome_"):
            niveau = feature.replace("diplome_", "").replace("_", " ").replace("plus", "+")
            prescriptions.append(f"Obtenir un diplôme {niveau}")
        elif feature.startswith("comp_"):
            comp_name = feature.replace("comp_", "").replace("_", " ")
            prescriptions.append(f"Améliorer la compétence {comp_name} (niveau actuel faible)")
        elif feature.startswith("soft_"):
            soft = feature.replace("soft_", "").replace("_", " ")
            prescriptions.append(f"Développer la compétence comportementale {soft}")
        elif feature == "experience_months":
            prescriptions.append("Gagner plus d'expérience professionnelle")
        elif feature.startswith("lang_"):
            lang = feature.replace("lang_", "").replace("_", " ")
            prescriptions.append(f"Améliorer le niveau en {lang}")
    
    print(f"\nRecommandations pour {profil_id} ({current['csp']}):")
    print(f"TE actuel: {current.get('full_te', 'N/A'):.1f}% → {current.get('te_classification', 'N/A')}")
    print(f"Basé sur {len(neighbors)} profils optimaux similaires")
    if prescriptions:
        for rec in prescriptions:
            print(f"• {rec}")
    else:
        print("• Aucune recommandation majeure — profil déjà proche des optimaux")
    
    return prescriptions

# Quick test — auto picks a random low/medium TE profile
if __name__ == "__main__":
    # Find a random profile with TE < 70
    low_te_profiles = list(db.profils.find(
        {"full_te": {"$lt": OPTIMAL_THRESHOLD}},
        {"id_demandeur": 1}
    ).limit(20))
    
    if not low_te_profiles:
        print("No low/medium TE profiles found — all are optimal!")
    else:
        test_profil = np.random.choice(low_te_profiles)
        test_id = test_profil["id_demandeur"]
        print(f"Testing on random low TE profile: {test_id}")
        generate_recommendations(test_id)