"""
Script to generate and insert synthetic Algerian job-seeker profiles into MongoDB.
Run this after creating the 'anem_employabilite' database and 'profils' collection.
"""
import uuid
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
# Algerian-specific data
WILAYAS = [
    "Adrar", "Chlef", "Laghouat", "Oum El Bouaghi", "Batna", "Béjaïa", "Biskra",
    "Béchar", "Blida", "Bouira", "Tamanrasset", "Tébessa", "Tlemcen", "Tiaret",
    "Tizi Ouzou", "Alger", "Djelfa", "Jijel", "Sétif", "Saïda", "Skikda",
    "Sidi Bel Abbès", "Annaba", "Guelma", "Constantine", "Médéa", "Mostaganem",
    "M'Sila", "Mascara", "Ouargla", "Oran", "El Bayadh", "Illizi", "Bordj Bou Arréridj",
    "Boumerdès", "El Tarf", "Tindouf", "Tissemsilt", "El Oued", "Khenchela",
    "Souk Ahras", "Tipaza", "Mila", "Aïn Defla", "Naâma", "Aïn Témouchent",
    "Ghardaïa", "Relizane", "Timimoun", "Bordj Badji Mokhtar", "Ouled Djellal",
    "Béni Abbès", "In Salah", "In Guezzam", "Touggourt", "Djanet", "El M'Ghair",
    "El Meniaa"
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

SOFT_SKILLS_POOL = [
    "Travail en équipe", "Communication orale", "Autonomie", "Gestion du stress",
    "Esprit d'initiative", "Leadership", "Adaptabilité", "Rigueur", "Créativité"
]

TECH_COMPETENCES_POOL = [
    "Python", "SQL", "Excel", "Power BI", "Java", "JavaScript", "HTML/CSS",
    "Gestion de projet", "Anglais professionnel", "Comptabilité", "Marketing digital",
    "AutoCAD", "SAP", "NoSQL", "Machine Learning", "Réseaux informatiques"
]

# ────────────────────────────────────────────────
# HELPERS
# ────────────────────────────────────────────────

fake = Faker('fr_FR')  # French 

def random_date_past_years(years_back=10):
    start = datetime.now() - timedelta(days=365 * years_back)
    return fake.date_between(start_date=start, end_date="today")

def random_diplomes():
    # Higher chance of having diplomas (realistic for job seekers)
    num = choice([0, 1, 1, 1, 2, 2, 3])  # biased toward 1–2
    diplomes = []
    
    for _ in range(num):
        niveau = choice(DIPLOMES_LEVELS)
        diplomes.append({
            "niveau": niveau,
            "domaine": choice(["Informatique", "Gestion", "Génie Civil", "Santé", "Commerce", "Langues", "Autre"]),
            "annee_obtention": randint(2015, 2025),
            "etablissement": choice(["USTHB", "Université de Blida", "École Nationale Polytechnique", "Université d'Annaba", "Centre de Formation", "Privé"])
        })
    return diplomes

def random_experiences():
    num = randint(0, 5)
    experiences = []
    current_year = datetime.now().year
    for _ in range(num):
        duree_mois = randint(3, 120)  # 3 mois à 10 ans
        start_year = current_year - (duree_mois // 12 + randint(0, 3))
        experiences.append({
            "poste": fake.job()[:40],
            "entreprise": fake.company()[:30],
            "date_debut": f"{start_year}-{randint(1,12):02d}-01",
            "duree_mois": duree_mois,
            "competences": [choice(TECH_COMPETENCES_POOL) for _ in range(randint(1,4))]
        })
    return experiences

def random_competences_techniques():
    num = randint(0, 8)
    return [
        {"nom": choice(TECH_COMPETENCES_POOL), "etoiles": randint(1, 5)}
        for _ in range(num)
    ]

def random_soft_skills():
    num = randint(0, 6)
    return list(set(choice(SOFT_SKILLS_POOL) for _ in range(num)))  # unique

# ────────────────────────────────────────────────
# Genération de profil
# ────────────────────────────────────────────────
def generate_profil():
    csp = choice(CSP_CATEGORIES)
    inscription_date_raw = fake.date_between(start_date="-36m", end_date="today")
    inscription_date = to_datetime(inscription_date_raw)
    
    # Generate and force diplomas
    diplomes = random_diplomes()
    if randint(1, 10) <= 7:  # 70% chance to guarantee at least 1
        if not diplomes:
            diplomes = [{
                "niveau": choice(DIPLOMES_LEVELS[3:]),
                "domaine": "Informatique",
                "annee_obtention": randint(2018, 2025),
                "etablissement": choice(["USTHB", "Université de Blida", "Autre"])
            }]

    # Generate and force experiences
    experiences = random_experiences()
    if not experiences:
        experiences = [{
            "poste": "Stagiaire / Employé",
            "duree_mois": randint(12, 60),
            "date_debut": fake.date_time_between(start_date="-5y", end_date="-1y"),
            "entreprise": fake.company()[:30]
        }]

    return {
        "id_demandeur": f"DEM-{fake.uuid4()[:8].upper()}",
        "nom_complet": fake.name(),
        "date_naissance": to_datetime(fake.date_of_birth(minimum_age=18, maximum_age=60)),
        "genre": choice(["M", "F"]),
        "wilaya": choice(WILAYAS),
        "commune": "Algerie",
        "telephone": f"0{randint(5,7)}{fake.msisdn()[3:]}",
        "email": fake.email(),
        "csp": csp,
        "date_inscription": inscription_date,
        "diplomes": diplomes,               # ← use the forced version!
        "experiences": experiences,         # ← use the forced version!
        "competences_techniques": random_competences_techniques(),
        "soft_skills": random_soft_skills(),
        "langues": [
            {"langue": "Arabe", "niveau": "Natif"},
            {"langue": "Français", "niveau": choice(["Courant", "Intermédiaire", "Élémentaire"])},
            {"langue": "Anglais", "niveau": choice(["Intermédiaire", "Élémentaire", "Aucun"])}
        ],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
# ────────────────────────────────────────────────
# Insertion dans MongoDB
# ────────────────────────────────────────────────

def seed_profils(count=300):
    client = MongoClient(MONGODB_URI)
    db = client[DATABASE_NAME]
    collection = db[COLLECTION_NAME]

    documents = [generate_profil() for _ in range(count)]
    result = collection.insert_many(documents)

    print(f"Inserted {len(result.inserted_ids)} synthetic profils.")
    print(f"First inserted ID: {result.inserted_ids[0]}")
    print(f"Total documents in {COLLECTION_NAME}: {collection.count_documents({})}")

if __name__ == "__main__":
    # Ajustez le nombre de profils à générer ici
    seed_profils(count=150)   # ← ici

# ────────────────────────────────────────────────
# REFERENTIELS GENERATOR
# ────────────────────────────────────────────────
REFERENTIEL_TYPES = [
    "metier",
    "secteur",
    "csp",
    "niveau_etude",
    "wilaya"
]

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
]

NIVEAUX_ETUDE = DIPLOMES_LEVELS  # assuming this is defined earlier

def generate_referentiel():
    ref_type = choice(REFERENTIEL_TYPES)
    
    # Unique short suffix for all types that can collide
    unique_suffix = str(uuid.uuid4())[:6].upper()
    
    if ref_type == "metier":
        libelle = choice(METIERS)
        code = f"MET-{unique_suffix}"
        competences = [choice(TECH_COMPETENCES_POOL) for _ in range(randint(3,7))]
        return {
            "type": ref_type,
            "code": code,
            "libelle": libelle,
            "competences_cle": competences,
            "csp_associe": choice(CSP_CATEGORIES),
            "tension_marche": choice(["Forte", "Moyenne", "Faible"]),
            "created_at": datetime.now(timezone.utc)
        }
    
    elif ref_type == "secteur":
        libelle = choice(SECTEURS)
        code = f"SEC-{libelle[:3].upper()}-{unique_suffix}"
        return {
            "type": ref_type,
            "code": code,
            "libelle": libelle,
            "description": fake.sentence(nb_words=8)[:80],
            "created_at": datetime.now(timezone.utc)
        }
    
    elif ref_type == "csp":
        libelle = choice(CSP_CATEGORIES + CSP_EXTRA)
        code = f"CSP-{libelle[:4].upper().replace(' ', '')}-{unique_suffix}"
        return {
            "type": ref_type,
            "code": code,
            "libelle": libelle,
            "niveau_hierarchique": choice(["Cadre", "Exécution", "Intermédiaire"]),
            "created_at": datetime.now(timezone.utc)
        }
    
    elif ref_type == "niveau_etude":
        libelle = choice(NIVEAUX_ETUDE)
        clean_lib = libelle[:8].upper().replace(' ', '').replace('+','P')
        code = f"NIV-{clean_lib}-{unique_suffix}"
        return {
            "type": ref_type,
            "code": code,
            "libelle": libelle,
            "score_base": randint(0,10),
            "created_at": datetime.now(timezone.utc)
        }
    
    else:  # wilaya
        libelle = choice(WILAYAS)
        code = f"WIL-{libelle[:3].upper()}-{unique_suffix}"
        return {
            "type": ref_type,
            "code": code,
            "libelle": libelle,
            "region": choice(["Nord", "Sud", "Est", "Ouest", "Centre"]),
            "created_at": datetime.now(timezone.utc)
        }

def seed_referentiels(count=150):
    client = MongoClient(MONGODB_URI)
    db = client[DATABASE_NAME]
    collection = db["referentiels"]
    
    # Optional: clear previous run if you want fresh data
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
    seed_referentiels(count=120)


def generate_offre():
    csp = choice(CSP_CATEGORIES)
    return {
        "id_offre": f"OFF-{uuid.uuid4().hex[:8].upper()}",
        "titre": choice(METIERS) + " - " + choice(["Senior", "Junior", "Confirmé", "Débutant"]),
        "csp": csp,
        "secteur": choice(SECTEURS),
        "wilaya": choice(WILAYAS),
        "date_publication": datetime.now(timezone.utc) - timedelta(days=randint(1, 365)),
        "date_cloture": datetime.now(timezone.utc) + timedelta(days=randint(30, 180)),
        "competences_requises": [choice(TECH_COMPETENCES_POOL) for _ in range(randint(3, 8))],
        "niveau_etude_min": choice(DIPLOMES_LEVELS[2:]),  # at least FP N2+
        "experience_min_mois": choice([0, 12, 24, 36, 60]),
        "statut": choice(["Ouverte", "Ouverte", "Ouverte", "En cours"]),  # bias toward open
        "created_at": datetime.now(timezone.utc)
    }

def seed_offres(count=400):
    client = MongoClient(MONGODB_URI)
    db = client[DATABASE_NAME]
    collection = db["offres"]
    
    documents = [generate_offre() for _ in range(count)]
    result = collection.insert_many(documents)
    
    print(f"Inserted {len(result.inserted_ids)} offres.")
    print(f"Total offres: {collection.count_documents({})}")
    
    # Quick stats per CSP
    for csp in CSP_CATEGORIES:
        open_count = collection.count_documents({"csp": csp, "statut": {"$in": ["Ouverte", "En cours"]}})
        print(f"  {csp}: {open_count} ouvertes/en cours")

if __name__ == "__main__":
    seed_offres(count=400)  # run this