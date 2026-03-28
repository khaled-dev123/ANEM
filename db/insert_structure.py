# db/insert_new_structure.py
from pymongo import MongoClient
from dotenv import load_dotenv
import os
from datetime import datetime, timezone
import uuid

load_dotenv()
client = MongoClient(os.getenv("MONGODB_URI"))
db = client[os.getenv("DATABASE_NAME")]

# 1. Create collections if they don't exist
for coll in ["profils", "offres", "placements", "strategies", "matching_matrices"]:
    if coll not in db.list_collection_names():
        db.create_collection(coll)
        print(f"✅ Created collection: {coll}")

# 2. Insert sample strategies (S0 - S3)
strategies = [
    {"code": "S3", "libelle": "Stratégie orientée cadre", "poids": {"C1":3,"C2":2,"C3":1,"C4":1,"C5":1,"C6":1}},
    {"code": "S2", "libelle": "Stratégie orientée professionalité", "poids": {"C1":2,"C2":1,"C3":2,"C4":1,"C5":2,"C6":2}},
    {"code": "S1", "libelle": "Stratégie orientée exécution", "poids": {"C1":2,"C2":1,"C3":1,"C4":0,"C5":3,"C6":3}},
    {"code": "S0", "libelle": "Distribution uniforme", "poids": {"C1":1,"C2":1,"C3":1,"C4":1,"C5":1,"C6":1}}
]
db.strategies.insert_many(strategies)
print("✅ Inserted 4 strategies (S0-S3)")

# 3. Insert a few sample profils and offres using the new structure
sample_profil = {
    "id_demandeur": f"DEM-{uuid.uuid4().hex[:8].upper()}",
    "csp": "Management",
    "ni": "Supérieur 1",
    "diplomes": [{"niveau": "Diplôme Bac +5", "specialite": "Informatique", "filiere": "Génie logiciel"}],
    "experiences": [{"annees": 4, "metier": "Développeur Full Stack", "domaine": "Informatique"}],
    "langues": [{"langue": "Anglais", "niveau": "B2"}, {"langue": "Français", "niveau": "C1"}],
    "date_debut_validite": datetime.now(timezone.utc) - timedelta(days=90),
    "commune_residence": "Cheraga",
    "created_at": datetime.now(timezone.utc)
}

sample_offre = {
    "id_offre": f"OFF-{uuid.uuid4().hex[:8].upper()}",
    "csp": "Management",
    "ni": "Supérieur 1",
    "diplomes": [{"niveau": "Diplôme Bac +5", "specialite": "Informatique"}],
    "nb_annee_exp": 3,
    "langues": [{"langue": "Anglais", "niveau": "B2"}],
    "date_confirmation": datetime.now(timezone.utc),
    "commune_lieu_travail": "Cheraga",
    "statut": "Ouverte",
    "created_at": datetime.now(timezone.utc)
}

db.profils.insert_one(sample_profil)
db.offres.insert_one(sample_offre)
print("✅ Inserted sample profil + offre with new structure")

print("\n✅ Done! Your new structure is now in the database.")
print("You can now start building Agent 1 and the matching engine.")