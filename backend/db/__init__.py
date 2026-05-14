import os

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "telesight")

client = None
db = None
customers = None
campaigns = None
action_logs = None
pipeline_status = None


def _connect_to_mongodb() -> None:
    global client, db, customers, campaigns, action_logs, pipeline_status

    if not MONGODB_URI:
        return

    client = MongoClient(MONGODB_URI)
    db = client[MONGODB_DB_NAME]
    customers = db["customers"]
    campaigns = db["campaigns"]
    action_logs = db["action_logs"]
    pipeline_status = db["pipeline_status"]


_connect_to_mongodb()
