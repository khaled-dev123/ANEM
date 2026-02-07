from pymongo import MongoClient
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()
client = MongoClient(os.getenv("MONGODB_URI"))
db = client[os.getenv("DATABASE_NAME")]

profil = {
    "id_demandeur": "DEM-TEST-001",
    "nom_complet": "Zackie Benali",
    "wilaya": "Alger",
    "csp": "Management",
    "diplomes": [
        {"niveau": "Diplôme Bac +5", "domaine": "Informatique", "annee": 2024}
    ],
    "experiences": [
        {"poste": "Stagiaire IA", "duree_mois": 6, "date_debut": "2025-06-01"}
    ],
    "competences_techniques": [
        {"nom": "Python", "etoiles": 4},
        {"nom": "MongoDB", "etoiles": 3}
    ],
    "soft_skills": ["Autonomie", "Communication"],
    "date_inscription": datetime(2025, 12, 1),
    "created_at": datetime.utcnow()
}

result = db.profils.insert_one(profil)
print("Inserted profil with ID:", result.inserted_id)

# Quick check
found = db.profils.find_one({"id_demandeur": "DEM-TEST-001"})
print("Found:", found)