# db/seed_data.py
"""
Single file for complete coherent synthetic population seeding.
Run: python db/seed_data.py
It will:
1. Clear existing data (optional, comment if you want to append)
2. Seed referentiels (small lookup)
3. Seed profils (300 balanced across CSPs)
4. Seed offres (400, balanced CSP + tension variation)
5. Seed placements (250 linked, realistic waiting times)
"""

from pymongo import MongoClient
from datetime import datetime, timedelta, timezone
from random import choice, randint, uniform
from faker import Faker
import os
from dotenv import load_dotenv

load_dotenv()
MONGODB_URI = os.getenv("MONGODB_URI")
DATABASE_NAME = "anem_employabilite"

# Collections
COLLECTIONS = ["profils", "offres", "placements", "referentiels"]

# Algerian data
WILAYAS = [
    "Adrar", "Chlef", "Laghouat", "Oum El Bouaghi", "Batna", "Béjaïa", "Biskra",
    "Béchar", "Blida", "Bouira", "Tamanrasset", "Tébessa", "Tlemcen", "Tiaret",
    "Tizi Ouzou", "Alger", "Djelfa", "Jijel", "Sétif", "Saïda", "Skikda",
    "Sidi Bel Abbès", "Annaba", "Guelma", "Constantine", "Médéa", "Mostaganem",
    "M'Sila", "Mascara", "Ouargla", "Oran", "El Bayadh", "Illizi", "Bordj Bou Arréridj",
    "Boumerdès", "El Tarf", "Tindouf", "Tissemsilt", "El Oued", "Khenchela",
    "Souk Ahras", "Tipaza", "Mila", "Aïn Defla", "Naâma", "Aïn Témouchent",
    "Ghardaïa", "Relizane"
]

CSP_CATEGORIES = [
    "Management",
    "Personnel professionnel",
    "Encadrement de support",
    "Personnel d'aide"
]

DIPLOMES_LEVELS = [
    "Sans diplôme",
    "Diplôme FP NIVEAU 1",
    "Diplôme FP NIVEAU 2",
    "Diplôme FP NIVEAU 3",
    "Diplôme BAC +3",
    "Diplôme Bac +5",
    "Diplôme Bac +7 et plus"
]

MALE_FIRST = ["Mohamed", "Ahmed", "Yacine", "Amine", "Sofiane", "Mehdi", "Karim", "Bilal"]
FEMALE_FIRST = ["Fatima", "Yasmine", "Meriem", "Amina", "Sarah", "Lina", "Imane", "Zahra"]
SURNAMES = ["Saidi", "Slimani", "Touati", "Benali", "Mansouri", "Brahimi", "Dahmani", "Cherif"]

SOFT_SKILLS = ["Travail en équipe", "Communication", "Autonomie", "Leadership", "Adaptabilité"]
TECH_SKILLS = ["Python", "SQL", "Excel", "Java", "JavaScript", "Anglais", "Gestion de projet"]

fake = Faker('fr_FR')

def to_datetime(dt):
    if isinstance(dt, datetime):
        return dt
    return datetime.combine(dt, datetime.min.time(), tzinfo=timezone.utc)

# Clear collections (comment if you want to keep existing data)
def clear_collections():
    client = MongoClient(MONGODB_URI)
    db = client[DATABASE_NAME]
    for coll in COLLECTIONS:
        db[coll].delete_many({})
        print(f"Cleared {coll}")

# Referentiels
def seed_referentiels():
    client = MongoClient(MONGODB_URI)
    db = client[DATABASE_NAME]
    docs = [{"type": "csp", "code": csp[:3].upper(), "libelle": csp} for csp in CSP_CATEGORIES]
    db["referentiels"].insert_many(docs)
    print(f"Seeded {len(docs)} referentiels")

# Profils
def generate_profil():
    genre = choice(["M", "F"])
    prenom = choice(MALE_FIRST) if genre == "M" else choice(FEMALE_FIRST)
    nom = choice(SURNAMES)
    nom_complet = f"{prenom} {nom}"
    csp = choice(CSP_CATEGORIES)
    
    return {
        "id_demandeur": f"DEM-{fake.uuid4()[:8].upper()}",
        "nom_complet": nom_complet,
        "genre": genre,
        "wilaya": choice(WILAYAS),
        "csp": csp,
        "date_inscription": to_datetime(fake.date_time_between("-36m", "now")),
        "diplomes": [{"niveau": choice(DIPLOMES_LEVELS)} for _ in range(randint(0, 2))],
        "experiences": [{"duree_mois": randint(0, 120)} for _ in range(randint(0, 4))],
        "competences_techniques": [{"nom": choice(TECH_SKILLS), "etoiles": randint(1,5)} for _ in range(randint(0, 8))],
        "soft_skills": [choice(SOFT_SKILLS) for _ in range(randint(0, 5))],
        "created_at": datetime.utcnow()
    }

def seed_profils(count=300):
    client = MongoClient(MONGODB_URI)
    db = client[DATABASE_NAME]
    docs = [generate_profil() for _ in range(count)]
    db["profils"].insert_many(docs)
    print(f"Seeded {count} profils")

# Offres
def generate_offre():
    csp = choice(CSP_CATEGORIES)
    return {
        "id_offre": f"OFF-{fake.uuid4()[:8].upper()}",
        "titre": fake.job(),
        "csp": csp,
        "wilaya": choice(WILAYAS),
        "date_publication": to_datetime(fake.date_time_between("-18m", "now")),
        "competences_requises": [choice(TECH_SKILLS) for _ in range(randint(3,8))],
        "created_at": datetime.utcnow()
    }

def seed_offres(count=400):
    client = MongoClient(MONGODB_URI)
    db = client[DATABASE_NAME]
    docs = [generate_offre() for _ in range(count)]
    db["offres"].insert_many(docs)
    print(f"Seeded {count} offres")

# Placements
def seed_placements(count=250):
    client = MongoClient(MONGODB_URI)
    db = client[DATABASE_NAME]
    profil_ids = [p["id_demandeur"] for p in db.profils.find({}, {"id_demandeur": 1})]
    offre_ids = [o["id_offre"] for o in db.offres.find({}, {"id_offre": 1})]
    
    docs = []
    for _ in range(count):
        profil_id = choice(profil_ids)
        profil = db.profils.find_one({"id_demandeur": profil_id})
        csp = profil["csp"] if profil else choice(CSP_CATEGORIES)
        docs.append({
            "id_placement": f"PL-{fake.uuid4()[:8].upper()}",
            "id_demandeur": profil_id,
            "id_offre": choice(offre_ids),
            "csp": csp,
            "duree_attente_jours": randint(10, 180),
            "date_placement": to_datetime(fake.date_time_between("-24m", "now")),
            "created_at": datetime.utcnow()
        })
    db["placements"].insert_many(docs)
    print(f"Seeded {count} placements (linked)")

# Main
if __name__ == "__main__":
    clear_collections()          # Comment this line if you want to keep existing data
    seed_referentiels()
    seed_profils(300)
    seed_offres(300)
    seed_placements(300)
    print("🎉 Full coherent population seeded! Ready for scoring & agents.")