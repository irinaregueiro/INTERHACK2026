import os
import logging
from pymongo import MongoClient

log = logging.getLogger(__name__)

# Fallback to None if not configured
MONGO_DB_LINK = os.getenv("MONGO_DB_LINK")

# Use MONGO_DB_NAME from env or default to InibsaProject (per user's Atlas screenshot)
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "InibsaProject")

client = None
db = None

if MONGO_DB_LINK:
    try:
        client = MongoClient(MONGO_DB_LINK, serverSelectionTimeoutMS=5000)
        # Check connection
        client.admin.command('ping')
        db = client[MONGO_DB_NAME]
        log.info(f"Successfully connected to MongoDB Atlas (Database: {MONGO_DB_NAME}).")
    except Exception as e:
        log.error("Failed to connect to MongoDB: %s. Running without persistence.", e)
        db = None


def save_signal_status(signal_id: str, status_data: dict):
    if db is None:
        return
    try:
        db.signal_statuses.update_one(
            {"_id": signal_id},
            {"$set": status_data},
            upsert=True
        )
        log.info(f"Successfully saved signal status for {signal_id} to MongoDB.")
    except Exception as e:
        log.error("Failed to save signal status to DB: %s", e)


def load_all_signal_statuses() -> dict[str, dict]:
    if db is None:
        return {}
    try:
        docs = db.signal_statuses.find()
        return {doc["_id"]: {k: v for k, v in doc.items() if k != "_id"} for doc in docs}
    except Exception as e:
        log.error("Failed to load signal statuses from DB: %s", e)
        return {}


def save_bandit_state(state: dict):
    if db is None:
        return
    try:
        db.bandit_state.update_one(
            {"_id": "global_state"},
            {"$set": state},
            upsert=True
        )
        log.info("Successfully updated global bandit state in MongoDB.")
    except Exception as e:
        log.error("Failed to save bandit state to DB: %s", e)


def get_customer_twins_count() -> int:
    if db is None:
        return 0
    try:
        return db.CustomerTwins.count_documents({})
    except Exception as e:
        log.error("Failed to count CustomerTwins: %s", e)
        return 0


def load_bandit_state() -> dict | None:
    if db is None:
        return None
    try:
        doc = db.bandit_state.find_one({"_id": "global_state"})
        if doc:
            return {k: v for k, v in doc.items() if k != "_id"}
        return None
    except Exception as e:
        log.error("Failed to load bandit state from DB: %s", e)
        return None
