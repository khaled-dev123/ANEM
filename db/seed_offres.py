from random import choice, randint
from datetime import datetime
from pymongo import MongoClient
from faker import Faker

fake = Faker("fr_FR")

CSP_CATEGORIES = ["Cadre", "Agent de maîtrise", "Employé", "Ouvrier"]

# 48 standard Algerian wilayas
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

TECH_COMPETENCES_POOL = ["Python", "JavaScript", "Java", "SQL", "Docker", "Git", "AWS", "React", "Node.js", "HTML/CSS"]
SOFT_SKILLS_POOL = ["Communication", "Teamwork", "Problem-solving", "Leadership", "Adaptability", "Creativity", "Time Management"]
DIPLOMES_LEVELS = ["FP N1", "FP N2", "Bac", "Bac+2", "Bac+3", "Bac+5", "Doctorat"]

def generate_offre():
    csp = choice(CSP_CATEGORIES)
    secteur = choice([
        "Informatique et Télécommunications", "Bâtiment et Travaux Publics", "Commerce et Distribution",
        "Santé", "Éducation et Formation", "Industrie", "Banque et Assurance", "Hôtellerie et Restauration",
        "Transport et Logistique", "Administration Publique"
    ])
    
    titre_base = fake.job()
    niveau = choice(["", "Junior", "Confirmé", "Senior", "Expert"])
    titre = f"{titre_base} - {niveau}".strip(" -")

    return {
        "id_offre": f"OFF-{fake.uuid4()[:8].upper()}",
        "titre": titre,
        "csp": csp,
        "csp_code": csp[:3].upper(),
        "secteur": secteur,
        "metier_referentiel": titre_base,
        "wilaya": choice(WILAYAS),
        "date_publication": fake.date_time_between(start_date="-18m", end_date="-1m"),
        "date_cloture": fake.date_time_between(start_date="now", end_date="+6m"),
        "competences_requises": list({choice(TECH_COMPETENCES_POOL) for _ in range(randint(3, 10))}),
        "soft_skills": list({choice(SOFT_SKILLS_POOL) for _ in range(randint(2, 6))}),
        "niveau_etude_min": choice(DIPLOMES_LEVELS[2:]),
        "experience_min_mois": choice([0, 12, 24, 36, 60, 120]),
        "salaire": {
            "min": randint(40000, 80000),
            "max": randint(90000, 200000),
            "devise": "DZD"
        },
        "nb_postes": randint(1, 10),
        "entreprise": fake.company(),
        "statut": choice(["Ouverte", "En cours", "Pourvue", "Annulée"]),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }

def seed_offres(count=400):
    client = MongoClient(MONGODB_URI)
    db = client[DATABASE_NAME]
    collection = db["offres"]

    documents = [generate_offre() for _ in range(count)]
    result = collection.insert_many(documents)

    print(f"Inserted {len(result.inserted_ids)} synthetic offres.")
    print(f"Total offres: {collection.count_documents({})}")

    pipeline = [{"$group": {"_id": "$csp", "count": {"$sum": 1}}}]
    print("Offres par CSP:")
    for stat in collection.aggregate(pipeline):
        print(f"  {stat['_id']}: {stat['count']}")

if __name__ == "__main__":
    seed_offres(count=300)
