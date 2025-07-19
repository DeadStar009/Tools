# cache.py
import time
from datetime import datetime, timezone
import logging
from Database.mongo_db.mongo import MongoDatabase

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class LLMCache:

    def __init__(self):
        logger.info("Initializing LLMCache")
        self.db = MongoDatabase()
        self.collection = self.db.cache_retriever()

    def generate_cache_key(self, bot_id: str, question: str, chat_history: str,language) -> str:
        logger.debug("Generating cache key for bot_id: %s", bot_id)
        return f"{bot_id}::{chat_history}::{question}::{language}"

    def check_cache(self, bot_id: str, question: str, chat_history: str, language = "multilingual"):
        logger.debug("Checking cache for bot_id: %s", bot_id)
        key = self.generate_cache_key(bot_id, question, chat_history, language)
        doc = self.collection.find_one({"cache_key": key})
        if doc:
            logger.info("[CACHE HIT] Returning cached response for key: %s", key)
            return doc.get("cached_output")
        logger.info("[CACHE MISS] No cached response found for key: %s", key)
        return None

    def insert_cache(self, bot_id: str, question: str, chat_history: str, output_data: dict,langauge = "multilingual"):
        logger.debug("Inserting into cache for bot_id: %s", bot_id)
        key = self.generate_cache_key(bot_id, question, chat_history,langauge)
        doc = {
            "bot_id":bot_id,
            "cache_key": key,
            "chat_history":chat_history,
            "cached_output": output_data,
            "language": langauge,
            "timestamp": datetime.now(timezone.utc)
        }
        self.collection.insert_one(doc)
        logger.info("[CACHE INSERT] Stored new response in cache for key: %s", key)