from pymongo import MongoClient
from app.config.settings import MONGO_URL, DB_NAME

client = MongoClient(MONGO_URL)
db = client[DB_NAME]
