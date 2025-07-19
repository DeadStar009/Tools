import os
import os
from dotenv import load_dotenv
from pathlib import Path



# Build the full path to the .env in the parent directory of this file
env_path = Path(__file__).resolve().parent.parent / ".env"
print(env_path)

load_dotenv(dotenv_path=env_path)
from pymongo import MongoClient
from langchain_community.vectorstores.azure_cosmos_db import (
    AzureCosmosDBVectorSearch,
)
from langchain_openai import OpenAIEmbeddings

class Events_MongoDatabase:
    def __init__(self):
        self.client = MongoClient(os.environ['MONGODB_URI'])
        self.db = self.client[os.environ['MONGO_DB']]
        self.collection_events = self.db["behavioral-events"]

    def insert_events(self,events_dict):
        self.collection_events.insert_one(events_dict)
        return
        
