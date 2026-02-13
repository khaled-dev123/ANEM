# agents/recommendation_agent.py
"""
Agent 2: Prescriptive Recommendation (Full Comparison)
Compares to ALL optimal profiles → shows top 10 similarities + gaps + suggestions
"""

from pymongo import MongoClient
from dotenv import load_dotenv
import os
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction import DictVectorizer
import numpy as np

load_dotenv()
client = MongoClient(os.getenv("MONGODB_URI"))
db = client[os.getenv("DATABASE_NAME")]

OPTIMAL_THRESHOLD = 70.0

def vectorize_profile(profil):
    features = {}
    
    # Diplomas
    for d in profil.get("diplomes", []):
        niveau = d.get("niveau", "none").replace(" ", "_").replace("+", "plus")
        features[f"diplome_{niveau}"] = 1
    
    # Tech skills
    for c in profil.get("competences_techniques", []):
        nom = c.get("nom", "unknown").replace(" ", "_")
        features[f"comp_{nom}"] = c.get("etoiles", 0)
    
    # Soft skills
    for s in profil.get("soft_skills", []):
        features[f"soft_{s.replace(' ', '_')}"] = 1
    
    # Experience
    max_months = max((e.get("duree_mois", 0) for e in profil.get("experiences", [])), default=0)
    features["experience_months"] = max_months
    
    # Languages
    level_map = {"Natif": 5, "Courant": 4, "Intermédiaire": 3, "Élémentaire": 2, "Aucun": 0}
    for l in profil.get("langues", []):
        langue = l.get("langue", "unknown").replace(" ", "_")
        features[f"lang_{langue}"] = level_map.get(l.get("niveau", ""), 0)
    
    return features

def compare_to_all_optimal(profil_id: str):
    current = db.profils.find_one({"id_demandeur": profil_id})
    if not current:
        print("Profil non trouvé")
        return
    
    if current.get("full_te", 0) >= OPTIMAL_THRESHOLD:
        print("Profil déjà optimal — aucune recommandation nécessaire")
        return
    
    csp = current["csp"]
    
    # All optimal in same CSP
    optimal_profiles = list(db.profils.find({
        "csp": csp,
        "full_te": {"$gte": OPTIMAL_THRESHOLD}
    }))
    
    # Fallback if few
    if len(optimal_profiles) < 5:
        print(f"Seulement {len(optimal_profiles)} optimaux dans le même CSP — comparaison avec tous les optimaux")
        optimal_profiles = list(db.profils.find({
            "full_te": {"$gte": OPTIMAL_THRESHOLD}
        }))
    
    if not optimal_profiles:
        print("Aucun profil optimal trouvé")
        return
    
    # Vectorize all
    vectorizer = DictVectorizer(sparse=False)
    current_vec = vectorizer.fit_transform([vectorize_profile(current)])
    optimal_vecs = vectorizer.transform([vectorize_profile(p) for p in optimal_profiles])
    
    # Cosine similarity to ALL optimal
    similarities = cosine_similarity(current_vec, optimal_vecs)[0]
    
    # Stats
    avg_similarity = np.mean(similarities)
    print(f"\nSimilarité moyenne avec {len(optimal_profiles)} profils optimaux: {avg_similarity:.3f}")
    
    # Top 10 most similar
    top_indices = np.argsort(similarities)[-10:][::-1]
    print("\nTop 10 profils optimaux les plus similaires:")
    for idx in top_indices:
        neighbor = optimal_profiles[idx]
        sim = similarities[idx]
        print(f"  - {neighbor['id_demandeur']} (TE: {neighbor.get('full_te', 'N/A'):.1f}%) — similarité: {sim:.3f}")
    
    # Use top 10 for gaps/prescriptions
    top_neighbors = [optimal_profiles[i] for i in top_indices]
    avg_top_vec = np.mean(vectorizer.transform([vectorize_profile(p) for p in top_neighbors]), axis=0)
    current_vec_flat = current_vec[0]
    
    gaps = avg_top_vec - current_vec_flat
    feature_names = vectorizer.get_feature_names_out()
    gap_features = [(feature_names[i], gaps[i]) for i in range(len(gaps)) if gaps[i] > 0.5]
    gap_features.sort(key=lambda x: x[1], reverse=True)
    
    prescriptions = []
    for feature, strength in gap_features[:6]:
        if feature.startswith("diplome_"):
            niveau = feature.replace("diplome_", "").replace("_", " ").replace("plus", "+")
            prescriptions.append(f"Obtenir un {niveau}")
        elif feature.startswith("comp_"):
            comp = feature.replace("comp_", "").replace("_", " ")
            prescriptions.append(f"Améliorer la compétence {comp} (viser 4-5 étoiles)")
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
    if prescriptions:
        for rec in prescriptions:
            print(f"• {rec}")
    else:
        print("• Profil déjà très proche des optimaux")

# Test on random low/medium TE
if __name__ == "__main__":
    low_te = list(db.profils.find({"full_te": {"$lt": OPTIMAL_THRESHOLD}}, {"id_demandeur": 1}).limit(20))
    if not low_te:
        print("Tous les profils sont optimaux !")
    else:
        test = np.random.choice(low_te)
        print(f"Test sur profil aléatoire: {test['id_demandeur']}")
        compare_to_all_optimal(test["id_demandeur"])