from dotenv import load_dotenv
load_dotenv()
import os
import json
import logging
from langchain_openai import AzureChatOpenAI
from typing import List
from langchain.schema import HumanMessage, AIMessage
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain.tools.retriever import create_retriever_tool
from langchain.prompts import ChatPromptTemplate
from Support_chatbot.custom_chatbots.tools.monday_blossom import get_Monday_details,get_Monday_details_from_email,update_in_monday
from Support_chatbot.custom_chatbots.tools.response_format_bot import response_format_chatbot
from Support_chatbot.custom_chatbots.tools.shopify_order_editing import add_line_item_and_commit,get_order_details
from Support_chatbot.custom_chatbots.tools.check_productid import get_productid
from product_chatbot.product_parser.get_details import get_product_data
from langchain_core.tools import tool
import re
from datetime import datetime
from pymongo import MongoClient

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

#Format Chat History
def format_chat_history(chat_history):
    formatted_chat = []
    for message in chat_history:
        if isinstance(message, HumanMessage):
            formatted_chat.append(f"Human: {message.content}\n")
        elif isinstance(message, AIMessage):
            formatted_chat.append(f"AI: {message.content}\n\n")
    return "".join(formatted_chat)


store = {}
def get_session_history(session_id: str) -> BaseChatMessageHistory:
    global store
    if session_id not in store:
        store[session_id] = ChatMessageHistory()
    return store[session_id]

def format_cache_chat_history(chat_history):
    formatted_chat = []
    for message in chat_history:
        if isinstance(message, HumanMessage):
            formatted_chat.append(f"{message.content}\n")
    return "".join(formatted_chat)
  
database=None
chat_history_tool=[]
bot_id_global=""
tag=False
session_id_global=""

def log_order_update(order_number, variant_id, variant_title, quantity, session_id, bot_id, discount_percentage, discount_description, line_item_id=None, customer_name=None, customer_email=None):
    try:
        logger.info(f"Starting to log order update for order: {order_number}")
        mongo_uri = os.environ.get('MONGODB_URI')
        mongo_db = os.environ.get('MONGO_DB')
        timestamp = datetime.utcnow()
        
        new_item = {
            "variant_id": variant_id,
            "title": variant_title,
            "quantity": quantity,
            "discount_percentage": discount_percentage,
            "discount_description": discount_description
        }
        
        try:
            client = MongoClient(mongo_uri)
            db = client[mongo_db]
            order_updates_collection = db["order_updates"]
            
            existing_record = order_updates_collection.find_one({
                "session_id": session_id,
                "bot_id": bot_id,
                "order_edit.order_number": order_number
            })
            
            if existing_record:
                result = order_updates_collection.update_one(
                    {"_id": existing_record["_id"]},
                    {
                        "$push": {"order_edit.added_items": new_item},
                        "$set": {"order_edit.timestamp_end": timestamp}
                    }
                )
                logger.info(f"Added item to existing order update for order: {order_number}")
                return True
            else:
                order_update_log = {
                    "timestamp": timestamp,
                    "chat_id": f"{session_id}{bot_id}",
                    "session_id": session_id,
                    "bot_id": bot_id,
                    "customer": {
                        "name": customer_name,
                        "email": customer_email
                    },
                    "order_edit": {
                        "order_number": order_number,
                        "timestamp_start": timestamp,
                        "timestamp_end": timestamp,
                        "order_name": order_number,
                        "added_items": [new_item]
                    }
                }
                
                result = order_updates_collection.insert_one(order_update_log)
                logger.info(f"Order update logged successfully for order: {order_number}, document ID: {result.inserted_id}")
                return True
        except Exception as e:
            logger.error(f"MongoDB operation error: {str(e)}", exc_info=True)
            return False
    except Exception as e:
        logger.error(f"Error logging order update: {str(e)}", exc_info=True)
        return False

@tool
def Order_details_order_number_name(order_number: str,name: str) -> str:
    """Get details about a orders with order number and name
    Args:
        order_number: The order number to get details about
        name: The name of the customer
    Returns:
        A string containing the details of the order
    """
    try:
        ans=get_Monday_details(order_number)
        if ans is None:
            return "Order number or name not found"
        else:
            ans_str=""
            for i in ans:
                names=str(name).lower().strip()
                order_name=str(i.name).lower().strip()
                print(names)
                print(order_name)
                if names in order_name:
                    ans_str += i.str_details()
                    ans_str += "\n\n"

            if ans_str=="":
                return "Order number or name not found"
            else:
                return ans_str
    except Exception as e:
        logger.error("Error in Order_details_order_number_name: %s", str(e), exc_info=True)
        return "Order number or name not found"
        

@tool
def Order_details_email(email: str) -> str:
    """Get details about a orders with email
    Args:
        email: The email of the customer
    Returns:
        A string containing the details of the order
    """
    try:
        ans=get_Monday_details_from_email(email)
        if ans is None:
            return "Email not found"
        else:
            ans_str=""
            for i in ans:
                ans_str+=i.str_details()
                ans_str+="\n\n"
            if ans_str=="":
                return "Email not found"
            else:
                return ans_str
    except Exception as e:
        logger.error("Error in Order_details_email: %s", str(e), exc_info=True)
        return "Email not found"


@tool
def get_product_details(product_description: str) -> str:
    """Get details about a product
    Args:
        product_description: The description of the product or the product name
    Returns:
        A string containing the details of the product
    """
    try:
        ans=str(database.products_similarity_search(bot_id_global,product_description,5))
        if ans is None:
            return "Product not found"
        else:
            return ans
    except Exception as e:
        logger.error("Error in get_product_details: %s", str(e), exc_info=True)
        return "Product not found"

@tool
def add_product_to_order_name(order_number: str,name: str,product_name: str,variant_title: str,details: str,quantity: int=1) -> str:
    """Add products to your existing order using the order number and name of the customer
    Args:
        order_number: The order number to add the product to
        name: The name of the customer
        product_name: The name of the product to add
        variant_title: The title of the variant to add  
        details: The details to be informed to the shopowner about the order changes -> contains the user query and the product details that the user wants to add to the order using HTML tags.
        quantity: The quantity of the product to add
    Returns:
        A string informing if the update was successful or not
    """
    try:
        global tag
        product_details=get_product_details(product_name)
        checker=get_productid(product_details,chat_history_tool,product_name,variant_title)
        if checker["product_found"]:
            variantid=checker["variant_id"]
        else:
            return checker["reason"]
        ans,check=update_in_monday(order_number,name,None,details)
        print("order_number: ",order_number,"\nname: ",name,"\nans: ",ans,"\nvariantid: ",variantid)
        if check:
            return ans
        get_order_details(order_number,(session_id_global+bot_id_global),bot_id_global,session_id_global)
        order_update=add_line_item_and_commit(order_number,variantid,quantity)
        if order_update is None:
            return "Order update failed"
        elif isinstance(order_update, dict):
            get_order_details(order_number,(session_id_global+bot_id_global),bot_id_global,session_id_global)
            discount_percentage = order_update.get("discount_percentage", 15)
            discount_description = order_update.get("discount_description", "15% off")
            order_message = order_update.get("message", "Order update successful")
            log_result = log_order_update(order_number=order_number,variant_id=variantid,variant_title=variant_title,quantity=quantity,session_id=session_id_global,bot_id=bot_id_global,discount_percentage=discount_percentage,discount_description=discount_description,line_item_id=None,customer_name=name,customer_email=None)
            logger.info(f"Log result: {log_result}")
            tag=True
            return order_message
        else:
            return order_update
    except Exception as e:
        logger.error("Error in add_product_to_order_name: %s", str(e), exc_info=True)
        return "Order update failed"
    

@tool
def add_product_to_order_email(email: str,product_name: str,variant_title: str,details: str,quantity: int=1) -> str:
    """Add products to your existing order using the email of the customer
    Args:
        email: The email of the customer
        product_name: The name of the product to add
        variant_title: The title of the variant to add  
        details: The details to be informed to the shopowner about the order changes -> contains the user query and the product details that the user wants to add to the order using HTML tags.
        quantity: The quantity of the product to add
    Returns:
        A string informing if the update was successful or not
    """
    try:
        global tag
        product_details=get_product_details(product_name)
        checker=get_productid(product_details,chat_history_tool,product_name,variant_title)
        if checker["product_found"]:
            variantid=checker["variant_id"]
        else:
            return checker["reason"]
        ans,check=update_in_monday(None,None,email,details)
        print("email: ",email,"\nans: ",ans,"\nvariantid: ",variantid)
        if check:
            return ans
        print("email: ",email,"\nans: ",ans,"\nvariantid: ",variantid)
        get_order_details(ans,(session_id_global+bot_id_global),bot_id_global,session_id_global)
        order_update=add_line_item_and_commit(ans,variantid,quantity)
        if order_update is None:
            return "Order update failed"
        elif isinstance(order_update, dict):
            get_order_details(ans,(session_id_global+bot_id_global),bot_id_global,session_id_global)
            discount_percentage = order_update.get("discount_percentage", 15)
            discount_description = order_update.get("discount_description", "15% off")
            order_message = order_update.get("message", "Order update successful")
            log_result = log_order_update(order_number=ans,variant_id=variantid,variant_title=variant_title,quantity=quantity,session_id=session_id_global,bot_id=bot_id_global,discount_percentage=discount_percentage,discount_description=discount_description,line_item_id=None,customer_name=None,customer_email=email)
            logger.info(f"Log result: {log_result}")
            tag=True
            return order_message
        else:
            return order_update
    except Exception as e:
        logger.error("Error in add_product_to_order_email: %s", str(e), exc_info=True)
        return "Order update failed"

#MAIN FUNCTION
def blossom_monday_order_update_Qna(question, session_id, bot_id, user_prompt, db, cache, collection_product_data, shop, order_editing_flag=True):
    global database,chat_history_tool,tag,session_id_global,bot_id_global
    tag=False
    database=db
    session_id_global=session_id
    logger.info("Starting QnA process for session_id: %s, bot_id: %s", session_id, bot_id)
    t0 = time.time()

    global store,format_for_chat,bot_id_global
    bot_id_global=bot_id
    
    chat_message_history = get_session_history(session_id)
    chat_history = format_chat_history(chat_message_history.messages)
    chat_history_tool=chat_history

    ##CACHING
    chat_history_cache = format_cache_chat_history(chat_message_history.messages)
    logger.debug("Checking cache with bot_id: %s, question: %s", bot_id, question)
    cached_data = cache.check_cache(bot_id, question, chat_history_cache)
    if cached_data:
        logger.info("Cache hit: %s", cached_data)
        chat_message_history.add_user_message(question)
        a_out = cached_data
        ans = ("response : "+ str(a_out['response']) + '\nSuggestive_Answers: '+str(a_out['leading_queries'])).replace("{","(").replace("}",")")
        
        chat_message_history.add_ai_message(ans)
        logger.info("Returning cached response")
        return cached_data
    else:
        logger.info("Cache miss - proceeding with retrieval")

    logger.debug("Initializing retriever for bot_id: %s", bot_id)
    vector_store_pages,pages_retriever = db.pages_k_retriever(bot_id,8)
    retriever_tool = create_retriever_tool(
        pages_retriever,
        "Blossom_pages_retriever",
        "Search for information about Blossom. For any questions about Blossom products,delivery,support, you must use this tool!",
    )

    if order_editing_flag:
        tools = [retriever_tool, Order_details_order_number_name, Order_details_email, add_product_to_order_name, add_product_to_order_email, get_product_details]
        current_prompt = prompt
        logger.info("Order editing is ENABLED. Using full tool set and standard prompt.")
    else:
        tools = [retriever_tool, Order_details_order_number_name, Order_details_email, get_product_details]
        current_prompt = prompt_no_order_editing
        logger.info("Order editing is DISABLED. Order editing tools excluded and using no-editing prompt.")
        tool_names = [tool.name for tool in tools]
        logger.info(f"Tools available to agent: {tool_names}")
    
    logger.debug("Creating agent with tools: %s", tools)
    agent = create_tool_calling_agent(model, tools, current_prompt)
    agent_executor = AgentExecutor(agent=agent, tools=tools)

    try:
        logger.info("Executing agent with question: %s", question)
        for step in agent_executor.stream({"input": question,"chat_history":chat_history,"user_prompt":user_prompt}):
            logger.info("Agent step: %s", step)
            ans = step
        a = ans['output']

        try:
            logger.debug("Parsing agent output: %s", a)
            # Improved JSON extraction logic
            import re
            json_match = re.search(r'(\{.*\})', a, re.DOTALL)
            if json_match:
                json_str = json_match.group(1).replace("None","null")
                try:
                    a = json.loads(json_str, strict=False)
                except Exception as e:
                    a=response_format_chatbot(format_for_chat,a)
                if "Suggestive_Answers" in a:
                    a['leading_queries'] = a['Suggestive_Answers']
                a_out = a
                logger.debug("Parsed output: %s", a_out)
            else:
                logger.error("No JSON found in output: %s", a)
                a_out = response_format_chatbot(format_for_chat,a)
                if a_out is None:
                    logger.info("LLM formater error in output: %s", a)
                    output_data = {
                        "response": "Sorry there was an Network Error,Please ask the question again.",
                        "leading_queries":[]
                    }
                    return output_data
                if "Suggestive_Answers" in a_out:
                    a_out['leading_queries'] = a_out['Suggestive_Answers']
            

        except Exception as e:
            logger.error("JSON parsing error: %s\nRaw output: %s", str(e), a)
            output_data = {
                "response": "Sorry there was an Network Error,Please ask the question again.",
                "leading_queries":[]
            }
            return output_data
        
        print("a_out: ",a_out)
        
        ## get product details
        a_out=get_product_data(a_out,bot_id,shop,db.products_vector_store,collection_product_data)

        # Save History and Cache
        try:
            t6 = time.time()
            ans = ("response : "+ str(a_out['response']) +'\nSuggestive_Answers: '+str(a_out['leading_queries'])+'\nProducts: '+str(a_out['products'])).replace("{","(").replace("}",")")
            
            logger.info("Updating cache for bot_id: %s, question: %s", bot_id, question)
            cache.insert_cache(bot_id, question, chat_history_cache, a_out)
            t7 = time.time()
            logger.debug("Cache update took %.2f seconds", t7-t6)

            logger.info("Updating chat history")
            chat_message_history.add_user_message(question)
            chat_message_history.add_ai_message(ans)
            
            logger.info("Total processing time: %.2f seconds", time.time() - t0)
            
        except Exception as e:
            logger.error("Error saving history/cache: %s", str(e), exc_info=True)
            output_data = {
                "response": "Sorry there was an issue ,Please ask the question again.",
                "leading_queries":[]
            }
            return output_data

        if tag:
            a_out["tags"]=["Order Update"]
        return a_out
    
    except Exception as e:
        logger.error("Agent execution error: %s", str(e), exc_info=True)
        output_data = {
                "response": "Please ask appropriate question.",
                "leading_queries":[]
            }
        return output_data


def blossom_monday_order_update_predifined_history(question,session_id,answer,product):

    chat_message_history = get_session_history(session_id)
    chat_message_history.add_user_message(question)
    ans=("response : "+ str(answer) + '\n Products : '+str(product) +'\nSuggestive_Answers: [] ').replace("{","(").replace("}",")")
    chat_message_history.add_ai_message(ans)
    logger.info("Added suggestive Question to chat history: %s", ans)
    return {"a":True}

format_for_chat="""
Your response must be a valid JSON object with exactly these fields
1. "response":str: A string output which should have your text response to the user's question in Markdown format. Always there in an string format.
2. "Suggestive_Answers":list[str]: At least three follow-up questions/Answers to keep the natural and conversational, and ensure they continue the discussion logically from user prespective. Include emojis
3. "Products":list[str]: A list of products names that you are recommending to the user or is in the response. Default to empty list [] if not applicable.
"""

prompts = """
You are a polite support agent chatbot for our company who assists customers with queries about pages, usage, and more.

- You are unable to help with forwarding the user to a live agent; you can only help with query information.


- get_product_details(product_description: str) → str  
  Retrieves detailed info about a product or its variants. Use this to confirm product names, variant availability, pricing, etc., before reccomending or asking for a product to the user. Always verify that the product exists in our catalog—if a user asks for an item we don't sell (e.g., "pencil"), inform them that it's unavailable rather than recommending.
  Help in searching the product in the catalog with the product name or description or just with a query.

Response Guidelines:
    1. Carefully read and analyze the context to find the information needed to answer the question.
    2. If specific terms from the question are missing in the context, search for their synonyms within the context.
    3. Construct your response directly based on the context provided.
    4. If you cannot find a definitive answer within the context, state this clearly. If the out-of-context question pertains to FMEA, answer it based on your knowledge.
    5. Avoid mentioning the source of the context unless explicitly asked.

1. **Greeting & Introduction**
   Bot: "Hello! Welcome to [Your Company Name] support. I'm here to help. How can I assist you today?"
   Suggestive_Answers (from user perspective):

2. **Context Gathering**
   Bot:
     - "Could you please tell me more about what you're looking for or what issue you're facing?"
     - "Do you already have an account with us?"
   Suggestive_Answers (from user perspective):

3. **Categorize & Route**  
   Bot (logic-based or AI-driven):  
     - If product inquiry: "I can help with product-related questions! Are you looking for details about features, availability, or recommendations?"  
     - If troubleshooting: "It sounds like you need assistance with an issue. Could you describe what's happening so I can guide you better?"  
     - If general inquiry: "I'd be happy to help! Could you provide more details about your question so I can assist you better?"  
   Suggestive_Answers (from user perspective):  

4. **Confirmation & Closing**
   Bot:
     - "Have I resolved your concern today, or is there anything else I can help you with?"
     - "Thank you for contacting [Company Name]! Feel free to reach out anytime."
   Suggestive_Answers (from user perspective):

- Always follow the response format provided below.
- User doesnot always provide the correct product name so just confirm the product name from the user by showing them the available products.


**Order Update**
- You can add products to the order using the order number and name of the customer or the email of the customer.
- To add product you first need to get the product details using the get_product_details tool
    - If the product has multiple variants, you need to ask the user to specify the variant of the product they want to add.
    - If the product is not found, you need to inform the user then ask for the correct product details.
- Confirm the order details with the user before adding the product to the order.
- After the user confirms the product details, you need to add the product to the order using the add_product_to_order_name or add_product_to_order_email tool.
    - To get the variant title you need to use the get_product_details to search the product
        - If there is only one variant, you confirm the product and add the product to the order.
        - If there is multiple variants, you need to ask the user to specify the variant of the product by showing the types of variants available to the user and then confirming with the user the variant they want to add.
    - If the order is not found, you need to inform the user then ask for the correct order details.
    - Correct variant title is required to add the product to the order.
- We can only add products to the order and not remove or edit the order neither can we change the shipping address,billing address,payment method,email,phone number,name of the customer.
    

IMPORTANT: Your response must be a valid JSON object with exactly these fields:
1. "response": A string output which should have your text response to the user's question in Markdown format
2. "Suggestive_Answers": At least three follow-up questions/Answers to keep the natural and conversational, and ensure they continue the discussion logically from user prespective. Include emojis
3. "Products":list[str]: A list of products names that you are recommending to the user or is in your response. Default to empty list [] if not applicable.

 Provide a step-by-step guide, with bullet points or subpoints, on how to solve the user's problem by navigating the website.
- "Suggestive_Answers" are possible follow-up questions or statements the user might ask after your initial response, helping continue the conversation.
- "response" should use **bold** for product names, `\\n` for new lines, and may include emojis for clarity and engagement. Try to use <br> tags to break the chat in paragraphs. Do not add <br> tag between a point and its subpoints. 

"response" should be concise and to the point.
Format your "response" by breaking sentences and paragraphs using "\\n\\n". Alternatively, use points and subpoints to structure your response if it exceeds 30 words.

- Please check if the customer is answering with the correct information if not ask for the correct information.
- Make it as Concise and precise as possible . Your response should be to the point.
- response should be very short and concise and to the point.No upselling or cross selling.
- Whenever user provides the order number and name or email, you need to confirm if there is an order with the same name and order number or email using the Order_details_order_number_name or Order_details_email tool.
- When the user tries to add a product that they have already ordered then you need to mention that and ask for their confirmation.
- you cannot update the quantity of the existing product in the order.

Remember be concise and to the point.

DO NOT repeat the greeting and introduction in the response.

- Add emojis in the **"response"** and **"Suggestive_Answers"** field.
- ALWAYS ADD AT LEAST THREE SUGGESTIVE ANSWERS you can add more if you think it is necessary. "Suggestive_Answers" is from user perspective.
- Do not add <br> tag between a point and its subpoints. 
- Always add product names in the **"Products"** field when you are recommending a product or the product is in the **"response"** field.
- Do not fabricate information or offer speculative answers unless they are supported by the provided context, user input, or extracted from the tools.
- In Suggestive_Answers don't suggest options like here is the name/email/order number of the customer or fake options that how user should provide the information. example: "My name and order number is John Doe and 1234567890" or "My email is john.doe@example.com" or "My name is name and order number is number"
- Ask the user to provide the correct information if they provide the wrong information.


{user_prompt}

YOUR FINAL RESPONSE MUST BE VALID JSON. Do not include any text before or after the JSON object.
The JSON object must have exactly this structure:
{{
  "response": "your_markdown_formatted_text_here",
  "Suggestive_Answers": ["string1", "string2", "string3"],
  "Products": ["string1", "string2", "string3"]
}}

Here is the user's **chat history** with you: {chat_history}
"""
prompt = ChatPromptTemplate.from_messages(
    [
        ("system",prompts ),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}")
    ],
)

prompts_no_order_editing = """
You are a polite support agent chatbot for our company who assists customers with queries about pages, usage, and more.

- You are unable to help with forwarding the user to a live agent; you can only help with query information.

CRITICAL INSTRUCTION: You CANNOT add products to orders or make ANY changes to orders. For ANY request to add products or update orders, you MUST provide a polite response explaining that you cannot make order changes and direct them to contact support directly.

- get_product_details(product_description: str) → str  
  Retrieves detailed info about a product or its variants. Use this to confirm product names, variant availability, pricing, etc., before recommending a product to the user. Always verify that the product exists in our catalog—if a user asks for an item we don't sell (e.g., "pencil"), inform them that it's unavailable rather than recommending.
  Help in searching the product in the catalog with the product name or description or just with a query.
- Order_details_order_number_name and Order_details_email - You may use these tools ONLY to look up order information, but you CANNOT modify orders.

IMPORTANT: The tools for adding products to orders are NOT available to you. You are NOT authorized to make any changes to orders. For ANY request to add, modify or update/change/edit in an order, use this response template:

"I understand you'd like to make changes to your order. While I can help you look up order information, I'm not able to modify orders directly. For any changes to your order, please contact our customer support team directly at orders@blossomandrhyme.com with your order details, and they will be happy to assist you. 😊"

Response Guidelines:
    1. Carefully read and analyze the context to find the information needed to answer the question.
    2. If specific terms from the question are missing in the context, search for their synonyms within the context.
    3. Construct your response directly based on the context provided.
    4. If you cannot find a definitive answer within the context, state this clearly. If the out-of-context question pertains to FMEA, answer it based on your knowledge.
    5. Avoid mentioning the source of the context unless explicitly asked.

1. **Greeting & Introduction**
   Bot: "Hello! Welcome to [Your Company Name] support. I'm here to help. How can I assist you today?"
   Suggestive_Answers (from user perspective):

2. **Context Gathering**
   Bot:
     - "Could you please tell me more about what you're looking for or what issue you're facing?"
     - "Do you already have an account with us?"
   Suggestive_Answers (from user perspective):

3. **Categorize & Route**  
   Bot (logic-based or AI-driven):  
     - If product inquiry: "I can help with product-related questions! Are you looking for details about features, availability, or recommendations?"  
     - If troubleshooting: "It sounds like you need assistance with an issue. Could you describe what's happening so I can guide you better?"  
     - If general inquiry: "I'd be happy to help! Could you provide more details about your question so I can assist you better?"  
   Suggestive_Answers (from user perspective):  

4. **Confirmation & Closing**
   Bot:
     - "Have I resolved your concern today, or is there anything else I can help you with?"
     - "Thank you for contacting [Company Name]! Feel free to reach out anytime."
   Suggestive_Answers (from user perspective):

- Always follow the response format provided below.
- User doesnot always provide the correct product name so just confirm the product name from the user by showing them the available products.

**Order Update - IMPORTANT RESTRICTION**
- You CANNOT add products to orders or make any changes to orders.
- For ANY request related to modifying orders, adding products, or making changes to existing orders, you MUST explain that you cannot help with order updates and direct them to contact support.
- You can verify order details using Order_details_order_number_name or Order_details_email, but you CANNOT make changes to those orders.
- Explain politely that you are not able to add items to orders and provide the contact information for customer support.

IMPORTANT: Your response must be a valid JSON object with exactly these fields:
1. "response": A string output which should have your text response to the user's question in Markdown format
2. "Suggestive_Answers": At least three follow-up questions/Answers to keep the natural and conversational, and ensure they continue the discussion logically from user prespective. Include emojis
3. "Products":list[str]: A list of products names that you are recommending to the user or is in your response. Default to empty list [] if not applicable.

 Provide a step-by-step guide, with bullet points or subpoints, on how to solve the user's problem by navigating the website.
- "Suggestive_Answers" are possible follow-up questions or statements the user might ask after your initial response, helping continue the conversation.
- "response" should use **bold** for product names, `\\n` for new lines, and may include emojis for clarity and engagement. Try to use <br> tags to break the chat in paragraphs. Do not add <br> tag between a point and its subpoints. 

"response" should be concise and to the point.
Format your "response" by breaking sentences and paragraphs using "\\n\\n". Alternatively, use points and subpoints to structure your response if it exceeds 30 words.

- Please check if the customer is answering with the correct information if not ask for the correct information.
- Make it as Concise and precise as possible . Your response should be to the point.
- response should be very short and concise and to the point.No upselling or cross selling.

Remember be concise and to the point.

DO NOT repeat the greeting and introduction in the response.

- Add emojis in the **"response"** and **"Suggestive_Answers"** field.
- ALWAYS ADD AT LEAST THREE SUGGESTIVE ANSWERS you can add more if you think it is necessary. "Suggestive_Answers" is from user perspective.
- Do not add <br> tag between a point and its subpoints. 
- Always add product names in the **"Products"** field when you are recommending a product or the product is in the **"response"** field.
- Do not fabricate information or offer speculative answers unless they are supported by the provided context, user input, or extracted from the tools.
- In Suggestive_Answers don't suggest options like here is the name/email/order number of the customer or fake options that how user should provide the information. example: "My name and order number is John Doe and 1234567890" or "My email is john.doe@example.com" or "My name is name and order number is number"
- Ask the user to provide the correct information if they provide the wrong information.


{user_prompt}

YOUR FINAL RESPONSE MUST BE VALID JSON. Do not include any text before or after the JSON object.
The JSON object must have exactly this structure:
{{
  "response": "your_markdown_formatted_text_here",
  "Suggestive_Answers": ["string1", "string2", "string3"],
  "Products": ["string1", "string2", "string3"]
}}

Here is the user's **chat history** with you: {chat_history}
"""

prompt_no_order_editing = ChatPromptTemplate.from_messages(
    [
        ("system", prompts_no_order_editing),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}")
    ],
)
