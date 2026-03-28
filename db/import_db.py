# db/import_dataset.py
"""
Import the new Dataset_Alger_For_IA.xlsx into MongoDB
Splits each row into one 'profil' and one 'offre' document.
"""

from pymongo import MongoClient
from dotenv import load_dotenv
import pandas as pd
import os
from datetime import datetime, timezone
import uuid

load_dotenv()
client = MongoClient(os.getenv("MONGODB_URI"))
db = client[os.getenv("DATABASE_NAME")]

# Clear existing data (optional - remove if you want to keep old data)
print("Clearing old profils and offres...")
db.profils.delete_many({})
db.offres.delete_many({})

print("Reading Excel file... (this may take a few seconds)")
df = pd.read_excel("Dataset_Alger_For_IA.xlsx", sheet_name="Feuil1")

print(f"Loaded {len(df)} rows from Excel.")

profils_list = []
offres_list = []

for _, row in df.iterrows():
    # Generate unique IDs
    profil_id = f"DEM-{uuid.uuid4().hex[:8].upper()}"
    offre_id = f"OFF-{uuid.uuid4().hex[:8].upper()}"

    # === PROFIL (Demandeur) ===
    profil = {
        "id_demandeur": profil_id,
        "csp": "Personnel professionnel",   # you can improve this later with mapping
        "ni": row.get("Demandeur NI", ""),
        "diplomes": [{"niveau": row.get("Demandeur Diplomes", "")}],
        "experiences": [{"annees": row.get("Demandeur NB Annee Exp", 0)}],
        "date_debut_validite": row.get("Demande date Inscription"),
        "commune_residence": row.get("Demandeur Commune Residence", ""),
        "created_at": datetime.now(timezone.utc)
    }
    profils_list.append(profil)

    # === OFFRE ===
    offre = {
        "id_offre": offre_id,
        "csp": "Personnel professionnel",   # same for now
        "ni": row.get("Offre NI", ""),
        "diplomes": [{"niveau": row.get("Offre Diplômes", "")}],
        "nb_annee_exp": row.get("Offre NB Annee Exp", 0),
        "date_confirmation": row.get("Date Offre"),
        "commune_lieu_travail": row.get("Lieu Travail", ""),
        "statut": "Ouverte",
        "created_at": datetime.now(timezone.utc)
    }
    offres_list.append(offre)

# Insert in batches for speed
print("Inserting profils into MongoDB...")
db.profils.insert_many(profils_list)

print("Inserting offres into MongoDB...")
db.offres.insert_many(offres_list)

print(f"\n✅ SUCCESS!")
print(f"   Imported {len(profils_list)} profils")
print(f"   Imported {len(offres_list)} offres")
print(f"\nYou can now run Agent 1 or the full scoring.")