import os
import os
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime, timezone

# Build the full path to the .env in the parent directory of this file
env_path = Path(__file__).resolve().parent.parent / ".env"
print(env_path)

load_dotenv(dotenv_path=env_path)
from pymongo import MongoClient


db_uri = os.environ['MONGODB_URI']
client = MongoClient(db_uri)
db_main= client[os.environ['MONGO_DB']]
collection_chats = db_main["chats"]

import logging

def add_file_attachment(chatid, file_type, file_url,file_name):
    file_attachment = {"file_type": file_type, "file_url": file_url,"file_name":file_name,"timestamp":datetime.now(timezone.utc)}
    try:
        result = collection_chats.update_one(
            {"chatid": chatid},
            {"$push": {"file_attachment": file_attachment}}
        )
        if result.matched_count == 0:
            logging.warning(f"No chat found with chatid: {chatid}. File attachment not added.")
        elif result.modified_count == 1:
            logging.info(f"File attachment added to chatid: {chatid}.")
        else:
            logging.info(f"File attachment update attempted for chatid: {chatid}, but no changes made.")
    except Exception as e:
        logging.error(f"Error adding file attachment to chatid {chatid}: {e}")


def update_conversation_response(chatid, new_response):
    try:
        result = collection_chats.update_one(
            {"chatid": chatid},
            {"$set": {f"conversation.0.response": new_response}}
        )
        
        if result.matched_count == 0:
            logging.warning(f"No chat found with chatid: {chatid}. Response not updated.")
        elif result.modified_count == 1:
            logging.info(f"Response updated for chatid: {chatid}.")
        else:
            logging.info(f"Response update attempted for chatid: {chatid}, but no changes made.")
    except Exception as e:
        logging.error(f"Error updating response for chatid {chatid}: {e}")