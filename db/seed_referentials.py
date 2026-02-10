
from pymongo import MongoClient
from datetime import datetime, date, timezone,timedelta
from random import choice, randint, uniform
from faker import Faker
import os
from dotenv import load_dotenv

# ────────────────────────────────────────────────
# CONFIG
# ────────────────────────────────────────────────

load_dotenv()
MONGODB_URI = os.getenv("MONGODB_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME")
COLLECTION_NAME = "profils"

# Helper to convert date → datetime (midnight UTC)
def to_datetime(d):
    if isinstance(d, date):
        return datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc)
    elif isinstance(d, datetime):
        return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d
    return d

# ────────────────────────────────────────────────
# REFERENTIELS GENERATOR
# ────────────────────────────────────────────────

REFERENTIEL_TYPES = [
    "metier",
    "secteur",
    "csp",
    "niveau_etude",
    "wilaya"          # optional — useful if you want centralized list
]

# Realistic Algerian / common values
METIERS = [
    "Développeur Full Stack", "Ingénieur en Génie Civil", "Comptable", "Infirmier Diplômé d'État",
    "Enseignant du Primaire", "Commercial Terrain", "Technicien Maintenance", "Chef de Projet IT",
    "Ouvrier Qualifié BTP", "Agent de Sécurité", "Cadre Administratif", "Responsable RH",
    "Médecin Généraliste", "Aide-soignant", "Électricien", "Chauffeur Poids Lourd"
]

SECTEURS = [
    "Informatique et Télécoms", "Bâtiment et Travaux Publics", "Commerce et Distribution",
    "Santé et Action Sociale", "Éducation et Formation", "Industrie Manufacturière",
    "Transport et Logistique", "Administration Publique", "Hôtellerie et Restauration",
    "Agriculture et Agroalimentaire", "Énergie et Mines", "Banque et Assurance"
]

CSP_EXTRA = [
    "Cadres supérieurs", "Professions intermédiaires", "Employés", "Ouvriers non qualifiés"
]  # your main 4 are already in CSP_CATEGORIES

NIVEAUX_ETUDE = DIPLOMES_LEVELS  # reuse from earlier

def generate_referentiel():
    ref_type = choice(REFERENTIEL_TYPES)
    
    if ref_type == "metier":
        libelle = choice(METIERS)
        code = f"MET-{libelle[:3].upper()}{randint(10,99):02d}"
        competences = [choice(TECH_COMPETENCES_POOL) for _ in range(randint(3,7))]
        return {
            "type": ref_type,
            "code": code,
            "libelle": libelle,
            "competences_cle": competences,
            "csp_associe": choice(CSP_CATEGORIES),
            "tension_marche": choice(["Forte", "Moyenne", "Faible"]),
            "created_at": datetime.utcnow()
        }
    
    elif ref_type == "secteur":
        libelle = choice(SECTEURS)
        return {
            "type": ref_type,
            "code": f"SEC-{libelle[:3].upper()}{randint(100,999)}",
            "libelle": libelle,
            "description": fake.sentence(nb_words=8)[:80],
            "created_at": datetime.utcnow()
        }
    
    elif ref_type == "csp":
        libelle = choice(CSP_CATEGORIES + CSP_EXTRA)
        return {
            "type": ref_type,
            "code": f"CSP-{libelle[:4].upper().replace(' ', '')}",
            "libelle": libelle,
            "niveau_hierarchique": choice(["Cadre", "Exécution", "Intermédiaire"]),
            "created_at": datetime.utcnow()
        }
    
    elif ref_type == "niveau_etude":
        libelle = choice(NIVEAUX_ETUDE)
        return {
            "type": ref_type,
            "code": f"NIV-{libelle[:6].upper().replace(' ', '').replace('+','PLUS')}",
            "libelle": libelle,
            "score_base": randint(0,10),  # hint for scoring later
            "created_at": datetime.utcnow()
        }
    
    else:  # wilaya
        libelle = choice(WILAYAS)
        return {
            "type": ref_type,
            "code": f"WIL-{libelle[:3].upper()}",
            "libelle": libelle,
            "region": choice(["Nord", "Sud", "Est", "Ouest", "Centre"]),
            "created_at": datetime.utcnow()
        }

def seed_referentiels(count=150):
    client = MongoClient(MONGODB_URI)
    db = client[DATABASE_NAME]
    collection = db["referentiels"]
    
    # Optional: clear old ones if re-running
    # collection.delete_many({})
    
    documents = [generate_referentiel() for _ in range(count)]
    result = collection.insert_many(documents)
    
    print(f"Inserted {len(result.inserted_ids)} referentiels documents.")
    print(f"Total in referentiels: {collection.count_documents({})}")
    
    # Quick stats
    types_count = collection.aggregate([
        {"$group": {"_id": "$type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ])
    print("Répartition par type:")
    for t in types_count:
        print(f"  {t['_id']}: {t['count']}")

if __name__ == "__main__":
    # Run this after profils/offres if you want
    seed_referentiels(count=120)  # small is fine — increase if needed