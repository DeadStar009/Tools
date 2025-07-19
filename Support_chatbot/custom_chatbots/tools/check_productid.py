from dotenv import load_dotenv
load_dotenv()
import os
import json
import logging
from langchain_core.runnables import RunnablePassthrough
from langchain_openai import AzureChatOpenAI
from langchain_core.prompts import PromptTemplate
from typing import List
from langchain_community.callbacks import get_openai_callback
from langchain.schema import HumanMessage, AIMessage
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.output_parsers import StrOutputParser
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

model = AzureChatOpenAI(
    openai_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
    azure_deployment=os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"],
)

from pydantic import BaseModel, Field


class ResponseFormatter(BaseModel):
    """Response format for the Variant_id agent."""
    variant_id: str = Field(description="The variant ID of the product the customer is asking for")
    product_found: bool = Field(description="True if the product and variant are found, False otherwise",default=False)
    reason: str = Field(description="Explanation if product/variant not found", default="")

model_with_structure = model.with_structured_output(ResponseFormatter)

#MAIN FUNCTION
def get_productid(products,chat_history,product_name,variant_name):
    global chain

    print("products: ",products,"\nchat_history: ",chat_history,"\nproduct_name: ",product_name,"\nvariant_name: ",variant_name)

    # CHAINING
    
    try:
        with get_openai_callback() as cb:
            a= chain.invoke({
                "products": products,
                "chat_history": chat_history,
                "product_name": product_name,
                "variant_name": variant_name
            })
            logger.info(cb)
            print("initial answer is a: ",a,"\ntype of a is",type(a))

        logger.debug("Output Initial= %s", a)

        a_out={"variant_id":a.variant_id,"product_found":a.product_found,"reason":a.reason}

        return a_out
    
    except Exception as e:
        logger.error("Invoke error: %s", e)
        output_data = {
                "spam":False
            }
        return output_data
        


prompts = """
You are a support agent for a Shopify store. Your job is to extract the correct variant ID of the product that the customer is asking about.

Instructions:
1. If the product is found in our catalog and the customer specified the correct variant: Return the variant ID with Product_found=True
2. If the product is found but the customer didn't specify which variant: Return Product_found=False with reason "Please specify the variant of the product"
3. If the product is not in our catalog: Return Product_found=False with reason explaining the product wasn't found

Reference Information:
Products: 
{products}

Chat History between the customer and shop owner: 
{chat_history}

ShopOwner notes:
Product Name: {product_name}
Variant Name: {variant_name}
"""
prompt =PromptTemplate.from_template(prompts) 

chain = (
    {
        "products": lambda x: x["products"],
        "chat_history": lambda x: x["chat_history"],
        "product_name": lambda x: x["product_name"],
        "variant_name": lambda x: x["variant_name"]
    }
    | prompt
    | model_with_structure
)

