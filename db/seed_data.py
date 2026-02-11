# db/seed_data.py
"""
Complete coherent synthetic population seeding for ANEM Employabilité.
Run: python db/seed_data.py

This will:
1. Clear existing data (optional, comment if you want to append)
2. Seed referentiels (metiers, secteurs, CSP, niveaux, wilayas)
3. Seed profils (job seekers with detailed attributes)
4. Seed offres (job offers with requirements)
5. Seed placements (linked matches with realistic waiting times)
"""

import uuid
from pymongo import MongoClient
from datetime import datetime, date, timezone, timedelta
from random import choice, randint, uniform
from faker import Faker
import os
from dotenv import load_dotenv

# ────────────────────────────────────────────────
# CONFIG
# ────────────────────────────────────────────────

load_dotenv()
MONGODB_URI = os.getenv("MONGODB_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "anem_employabilite")

# Collections
COLLECTIONS = ["profils", "offres", "placements", "referentiels"]

# ────────────────────────────────────────────────
# ALGERIAN DATA
# ────────────────────────────────────────────────

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

SOFT_SKILLS_POOL = [
    "Travail en équipe", "Communication orale", "Autonomie", "Gestion du stress",
    "Esprit d'initiative", "Leadership", "Adaptabilité", "Rigueur", "Créativité"
]

TECH_COMPETENCES_POOL = [
    "Python", "SQL", "Excel", "Power BI", "Java", "JavaScript", "HTML/CSS",
    "Gestion de projet", "Anglais professionnel", "Comptabilité", "Marketing digital",
    "AutoCAD", "SAP", "NoSQL", "Machine Learning", "Réseaux informatiques"
]

MALE_FIRST = ["Mohamed", "Ahmed", "Yacine", "Amine", "Sofiane", "Mehdi", "Karim", "Bilal"]
FEMALE_FIRST = ["Fatima", "Yasmine", "Meriem", "Amina", "Sarah", "Lina", "Imane", "Zahra"]
SURNAMES = ["Saidi", "Slimani", "Touati", "Benali", "Mansouri", "Brahimi", "Dahmani", "Cherif"]

# ────────────────────────────────────────────────
# HELPERS
# ────────────────────────────────────────────────

fake = Faker('fr_FR')

def to_datetime(d):
    """Convert date to datetime (midnight UTC)"""
    if isinstance(d, date) and not isinstance(d, datetime):
        return datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc)
    elif isinstance(d, datetime):
        return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d
    return d

def random_date_past_years(years_back=10):
    start = datetime.now() - timedelta(days=365 * years_back)
    return fake.date_between(start_date=start, end_date="today")

def random_diplomes():
    """Generate realistic diplomas for job seekers"""
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
    """Generate work experiences"""
    num = randint(0, 5)
    experiences = []
    current_year = datetime.now().year
    for _ in range(num):
        duree_mois = randint(3, 120)  # 3 months to 10 years
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
    """Generate technical competencies with ratings"""
    num = randint(0, 8)
    return [
        {"nom": choice(TECH_COMPETENCES_POOL), "etoiles": randint(1, 5)}
        for _ in range(num)
    ]

def random_soft_skills():
    """Generate unique soft skills"""
    num = randint(0, 6)
    return list(set(choice(SOFT_SKILLS_POOL) for _ in range(num)))

# ────────────────────────────────────────────────
# CLEAR COLLECTIONS
# ────────────────────────────────────────────────

def clear_collections():
    """Clear all collections (comment this in main if you want to keep existing data)"""
    client = MongoClient(MONGODB_URI)
    db = client[DATABASE_NAME]
    for coll in COLLECTIONS:
        count = db[coll].delete_many({}).deleted_count
        print(f"Cleared {count} documents from {coll}")

# ────────────────────────────────────────────────
# REFERENTIELS
# ────────────────────────────────────────────────

REFERENTIEL_TYPES = ["metier", "secteur", "csp", "niveau_etude", "wilaya"]

def generate_referentiel():
    """Generate a single referentiel document"""
    ref_type = choice(REFERENTIEL_TYPES)
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
        libelle = choice(CSP_CATEGORIES)
        code = f"CSP-{libelle[:4].upper().replace(' ', '')}-{unique_suffix}"
        return {
            "type": ref_type,
            "code": code,
            "libelle": libelle,
            "niveau_hierarchique": choice(["Cadre", "Exécution", "Intermédiaire"]),
            "created_at": datetime.now(timezone.utc)
        }
    
    elif ref_type == "niveau_etude":
        libelle = choice(DIPLOMES_LEVELS)
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

def seed_referentiels(count=120):
    """Seed referentiels collection"""
    client = MongoClient(MONGODB_URI)
    db = client[DATABASE_NAME]
    collection = db["referentiels"]
    
    documents = [generate_referentiel() for _ in range(count)]
    result = collection.insert_many(documents)
    
    print(f"✓ Inserted {len(result.inserted_ids)} referentiels")
    
    # Stats by type
    types_count = collection.aggregate([
        {"$group": {"_id": "$type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ])
    print("  Répartition par type:")
    for t in types_count:
        print(f"    {t['_id']}: {t['count']}")

# ────────────────────────────────────────────────
# PROFILS
# ────────────────────────────────────────────────

def generate_profil():
    """Generate a complete job seeker profile"""
    csp = choice(CSP_CATEGORIES)
    genre = choice(["M", "F"])
    prenom = choice(MALE_FIRST) if genre == "M" else choice(FEMALE_FIRST)
    nom = choice(SURNAMES)
    nom_complet = f"{prenom} {nom}"
    
    inscription_date_raw = fake.date_between(start_date="-36m", end_date="today")
    inscription_date = to_datetime(inscription_date_raw)
    
    # Generate and force diplomas (70% have at least one)
    diplomes = random_diplomes()
    if randint(1, 10) <= 7:
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
            "date_debut": fake.date_time_between(start_date="-5y", end_date="-1y").strftime("%Y-%m-%d"),
            "entreprise": fake.company()[:30],
            "competences": [choice(TECH_COMPETENCES_POOL) for _ in range(randint(1,3))]
        }]

    return {
        "id_demandeur": f"DEM-{fake.uuid4()[:8].upper()}",
        "nom_complet": nom_complet,
        "date_naissance": to_datetime(fake.date_of_birth(minimum_age=18, maximum_age=60)),
        "genre": genre,
        "wilaya": choice(WILAYAS),
        "commune": "Algérie",
        "telephone": f"0{randint(5,7)}{fake.msisdn()[3:]}",
        "email": fake.email(),
        "csp": csp,
        "date_inscription": inscription_date,
        "diplomes": diplomes,
        "experiences": experiences,
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

def seed_profils(count=300):
    """Seed profils collection"""
    client = MongoClient(MONGODB_URI)
    db = client[DATABASE_NAME]
    collection = db["profils"]
    
    documents = [generate_profil() for _ in range(count)]
    result = collection.insert_many(documents)
    
    print(f"✓ Inserted {len(result.inserted_ids)} profils")
    
    # Stats by CSP
    for csp in CSP_CATEGORIES:
        count_csp = collection.count_documents({"csp": csp})
        print(f"    {csp}: {count_csp}")

# ────────────────────────────────────────────────
# OFFRES
# ────────────────────────────────────────────────

def generate_offre():
    """Generate a job offer"""
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
    """Seed offres collection"""
    client = MongoClient(MONGODB_URI)
    db = client[DATABASE_NAME]
    collection = db["offres"]
    
    documents = [generate_offre() for _ in range(count)]
    result = collection.insert_many(documents)
    
    print(f"✓ Inserted {len(result.inserted_ids)} offres")
    
    # Stats per CSP
    for csp in CSP_CATEGORIES:
        open_count = collection.count_documents({"csp": csp, "statut": {"$in": ["Ouverte", "En cours"]}})
        print(f"    {csp}: {open_count} ouvertes/en cours")

# ────────────────────────────────────────────────
# PLACEMENTS
# ────────────────────────────────────────────────

def seed_placements(count=250):
    """Seed placements collection with realistic links"""
    client = MongoClient(MONGODB_URI)
    db = client[DATABASE_NAME]
    
    profil_ids = [p["id_demandeur"] for p in db.profils.find({}, {"id_demandeur": 1})]
    offre_ids = [o["id_offre"] for o in db.offres.find({}, {"id_offre": 1})]
    
    if not profil_ids or not offre_ids:
        print("⚠ No profils or offres found. Seed those first!")
        return
    
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
            "created_at": datetime.now(timezone.utc)
        })
    
    result = db["placements"].insert_many(docs)
    print(f"✓ Inserted {len(result.inserted_ids)} placements (linked)")

# ────────────────────────────────────────────────
# MAIN
# ────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n🌱 Starting ANEM Employabilité Database Seeding...\n")
    
    # Comment this line if you want to keep existing data
    clear_collections()
    
    print("\n1️⃣ Seeding Referentiels...")
    seed_referentiels(count=120)
    
    print("\n2️⃣ Seeding Profils...")
    seed_profils(count=300)
    
    print("\n3️⃣ Seeding Offres...")
    seed_offres(count=400)
    
    print("\n4️⃣ Seeding Placements...")
    seed_placements(count=250)
    
    print("\n🎉 Full coherent population seeded! Ready for scoring & agents.\n")