from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()  # reads .env file

uri = os.getenv("MONGODB_URI")
client = MongoClient(uri)

db_name = os.getenv("DATABASE_NAME")
db = client[db_name]

db.profils.create_index("csp")
db.profils.create_index("id_demandeur", unique=True)
db.profils.create_index([("csp", 1), ("score_employabilite", -1)])  # top profiles per CSP

# Offres
db.offres.create_index("csp")
db.offres.create_index("wilaya")

# Placements - for historical averages
db.placements.create_index("csp")
db.placements.create_index("date_placement")

# Referentiels - small collection
db.referentiels.create_index([("type", 1), ("code", 1)], unique=True)

print("Indexes created!")