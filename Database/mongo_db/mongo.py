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
from langchain_community.vectorstores.azure_cosmos_db import (
    AzureCosmosDBVectorSearch,
    CosmosDBSimilarityType,
    CosmosDBVectorSearchType,
)
from langchain_mongodb import MongoDBChatMessageHistory



class MongoDatabase:
    def __init__(self):
        self.db_name_embeddings = os.environ['MONGO_DB_EMBEDDINGS']
        self.db_uri = os.environ['MONGODB_URI']
        self.client = MongoClient(self.db_uri)
        self.db_embeddings = self.client[self.db_name_embeddings]
        self.embeddings = OpenAIEmbeddings(model="text-embedding-ada-002")

        self.db_costing= self.client[os.environ['MONGO_DB']]
        self.collection_costing = self.db_costing["llm_costing"]
        self.collection_chat_history = self.db_embeddings["Chat_history"]
        self.collection_order_update = self.db_costing["order_update_bills"]

        self.botid=""
        self.products_vector_store=""
        self.pages_vector_store=""
        self.chat_history=""

    ## Set Bot ID and Chat History

    def set_chat_history(self,sessions_id):
        self.chat_history=MongoDBChatMessageHistory(
            session_id=sessions_id,
            connection_string=self.db_uri,
            database_name=self.db_name_embeddings,
            collection_name="Chat_history",
        )
        return self.chat_history
    
    def set_botid(self,bot_id):
        self.botid=bot_id
        collection_products = self.db_embeddings[(bot_id+"_products_embeddings")]
        self.products_vector_store=AzureCosmosDBVectorSearch(
            collection=collection_products,     
            embedding=self.embeddings,
            index_name="vectorSearchIndex"
        )
        collection_pages = self.db_embeddings[(self.botid+"_embeddings")]
        self.pages_vector_store= AzureCosmosDBVectorSearch(
            collection=collection_pages,     
            embedding=self.embeddings,
            index_name="vectorSearchIndex"
        )   
        return
        
    ## MMR Retriever
    def products_mmr_retriever(self, bot_id,k):
        collection_products = self.db_embeddings[(bot_id+"_products_embeddings")]
        vector_store = AzureCosmosDBVectorSearch(
            collection=collection_products,     
            embedding=self.embeddings,
            index_name="vectorSearchIndex"
        )
        self.products_vector_store=vector_store
        retriver=vector_store.as_retriever(search_type="mmr",
                                           search_kwargs={"k":k, 'lambda_mult': 0.5})
        return vector_store,retriver
    
    def pages_mmr_retriever(self, bot_id,k):
        collection_pages = self.db_embeddings[(bot_id+"_embeddings")]
        vector_store = AzureCosmosDBVectorSearch(
            collection=collection_pages,     
            embedding=self.embeddings,
            index_name="vectorSearchIndex"
        )
        retriver=vector_store.as_retriever(search_type="mmr",
                                           search_kwargs={"k":k, 'lambda_mult': 0.5})
        return retriver
    
    ## KNN Retriever
    def pages_k_retriever(self, bot_id,k):
        collection_pages = self.db_embeddings[(bot_id+"_embeddings")]
        vector_store = AzureCosmosDBVectorSearch(
            collection=collection_pages,     
            embedding=self.embeddings,
            index_name="vectorSearchIndex"
        )
        return vector_store,vector_store.as_retriever(search_kwargs={"k":k})
    
    def products_k_retriever(self, bot_id,k):
        collection_products = self.db_embeddings[(bot_id+"_products_embeddings")]
        vector_store = AzureCosmosDBVectorSearch(
            collection=collection_products,     
            embedding=self.embeddings,
            index_name="vectorSearchIndex"
        )
        self.products_vector_store=vector_store
        return vector_store,vector_store.as_retriever(search_kwargs={"k":k})

    ## Similarity Search
    def pages_similarity_search(self, bot_id,question,k):
        collection_pages = self.db_embeddings[(bot_id+"_embeddings")]
        vector_store = AzureCosmosDBVectorSearch(
            collection=collection_pages,     
            embedding=self.embeddings,
            index_name="vectorSearchIndex"
        )      
        return vector_store.similarity_search_with_score(question, k=k)
    
    def products_similarity_search(self, bot_id,question,k):
        collection_products = self.db_embeddings[(bot_id+"_products_embeddings")]
        vector_store = AzureCosmosDBVectorSearch(
            collection=collection_products,     
            embedding=self.embeddings,
            index_name="vectorSearchIndex"  
        ) 
        self.products_vector_store=vector_store     
        return vector_store.similarity_search_with_score(question, k=k)
    
    ## Collections
    def pages_data(self,bot_id):
        collection_pages_data = self.db_embeddings[(bot_id+"_embeddings")]
        return collection_pages_data

    def products_data(self):
        collection_product_data = self.db_embeddings[("products_data")]
        return collection_product_data
   
    ## Self Similarity Search
    def self_pages_similarity_search(self,question,k):
        return self.pages_vector_store.similarity_search_with_score(question, k=k)
    
    def self_products_similarity_search(self,question,k):
        ans=self.products_vector_store.similarity_search_with_score(question, k=k)
        return ans
    
    ## Cache Retriever
    def cache_retriever(self):
        collection_cache = self.db_embeddings[("Debales_cache")]
        return collection_cache
    
    ## Costing
    def costing(self,cost_dict):
        self.collection_costing.insert_one(cost_dict)
        return
    
    def logging_order_update(self, order_update_dict):
        # Check if the chat_id already exists with order_logging=True
        existing = self.collection_order_update.find_one({
            "chat_id": order_update_dict["chat_id"],
            "order_logging": True
        })

        if existing:
            # Add the current update to the updated_order_details array
            self.collection_order_update.update_one(
                {"chat_id": order_update_dict["chat_id"], "order_logging": True},
                {"$push": {"updated_order_details": order_update_dict}}
            )
        else:
            # Create a new log document
            new_log = {
                "order_number": order_update_dict["order_number"],
                "original_order_details": order_update_dict,
                "updated_order_details": [],
                "order_logging": True,
                "chat_id": order_update_dict["chat_id"],
                "bot_id": order_update_dict["bot_id"],
                "session_id": order_update_dict["session_id"]
            }
            self.collection_order_update.insert_one(new_log)
