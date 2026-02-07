from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()  # reads .env file

uri = os.getenv("MONGODB_URI")
client = MongoClient(uri)

db_name = os.getenv("DATABASE_NAME")
db = client[db_name]

# Create collections (MongoDB creates them automatically on first use, but this makes it explicit)
collections = ["profils", "offres", "placements", "referentiels"]

for coll in collections:
    if coll not in db.list_collection_names():
        db.create_collection(coll)
        print(f"Created collection: {coll}")
    else:
        print(f"Collection {coll} already exists")

# Optional: print all collections to confirm
print("All collections:", db.list_collection_names())