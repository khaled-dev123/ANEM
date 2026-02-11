from random import choice, randint
from datetime import datetime
from pymongo import MongoClient
from faker import Faker
import os

fake = Faker("fr_FR")

# ─── SAFETY GUARD ─────────────────────────────────────────────
if os.getenv("ENV") == "prod":
    raise RuntimeError("❌ Seeding placements is disabled in production")

# ─── CONFIG ──────────────────────────────────────────────────
MONGODB_URI = os.getenv("MONGODB_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "employability_ai")

CSP_CATEGORIES = ["Cadre", "Agent de maîtrise", "Employé", "Ouvrier"]

# All 48 standard Algerian wilayas
WILAYAS = [
    "Adrar", "Chlef", "Laghouat", "Oum El Bouaghi", "Batna", "Béjaïa",
    "Biskra", "Béchar", "Blida", "Bouira", "Tamanrasset", "Tébessa",
    "Tlemcen", "Tiaret", "Tizi Ouzou", "Alger", "Djelfa", "Jijel",
    "Sétif", "Saïda", "Skikda", "Sidi Bel Abbès", "Annaba", "Guelma",
    "Constantine", "Médéa", "Mostaganem", "M'Sila", "Mascara", "Ouargla",
    "Oran", "El Bayadh", "Illizi", "Bordj Bou Arréridj", "Boumerdès",
    "El Tarf", "Tindouf", "Tissemsilt", "El Oued", "Khenchela",
    "Souk Ahras", "Tipaza", "Mila", "Aïn Defla", "Naâma", "Aïn Témouchent",
    "Ghardaïa", "Relizane"
]

# ─── DATA ACCESS ──────────────────────────────────────────────
def get_existing_ids(db):
    """Fetch profiles and offres from DB"""
    profils = list(db.profils.find({}, {"id_demandeur": 1, "csp": 1}))
    offres = list(db.offres.find({}, {"id_offre": 1}))

    if not profils or not offres:
        raise RuntimeError("Profils or Offres collections are empty. Seed them first.")

    return profils, [o["id_offre"] for o in offres]

# ─── GENERATOR ────────────────────────────────────────────────
def generate_placement(profils, offre_ids):
    profil = choice(profils)

    return {
        "id_placement": f"PL-{fake.uuid4()[:8].upper()}",
        "id_demandeur": profil["id_demandeur"],
        "id_offre": choice(offre_ids),
        "date_placement": fake.date_time_between(start_date="-24m", end_date="-1m"),
        "duree_attente_jours": randint(5, 180),
        "salaire_initial": randint(45000, 180000),
        "csp": profil.get("csp", choice(CSP_CATEGORIES)),
        "wilaya": choice(WILAYAS),
        "statut": "Réussi",
        "created_at": datetime.utcnow()
    }

# ─── SEEDER ───────────────────────────────────────────────────
def seed_placements(count=250):
    client = MongoClient(MONGODB_URI)
    db = client[DATABASE_NAME]
    collection = db.placements

    profils, offre_ids = get_existing_ids(db)

    documents = [generate_placement(profils, offre_ids) for _ in range(count)]
    result = collection.insert_many(documents)

    print(f"✅ Inserted {len(result.inserted_ids)} synthetic placements")
    print(f"📊 Total placements: {collection.count_documents({})}")

    # Quick stats: average waiting time per CSP
    pipeline = [
        {"$group": {"_id": "$csp", "avg_wait_days": {"$avg": "$duree_attente_jours"}}}
    ]

    print("📈 Average waiting time per CSP:")
    for stat in collection.aggregate(pipeline):
        print(f"  {stat['_id']}: {stat['avg_wait_days']:.1f} days")

# ─── ENTRY POINT ──────────────────────────────────────────────
if __name__ == "__main__":
    seed_placements(count=250)  # adjust number as needed
