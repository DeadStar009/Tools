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
from Support_chatbot.custom_chatbots.tools.monday_blossom import get_Monday_details,get_Monday_details_from_email
from Support_chatbot.custom_chatbots.tools.response_format_bot import response_format_chatbot
from langchain_core.tools import tool
import re


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
  

@tool
def Order_details_order_number_name(order_number: str,name: str) -> str:
    """Get details about a orders with order number and name
    Args:
        order_number: The order number to get details about
        name: The name of the customer
    Returns:
        A string containing the details of the order
    """
    ans=get_Monday_details(order_number)
    if ans is None:
        return "Order number or name not found"
    else:
        ans_str=""
        for i in ans:
            names=name.lower().strip()
            order_name=i.name.lower().strip()
            print(names)
            print(order_name)
            if name in order_name:
                ans_str += i.str_details()
                ans_str += "\n\n"

        if ans_str=="":
            return "Order number or name not found"
        else:
            return ans_str
        
@tool
def Order_details_email(email: str) -> str:
    """Get details about a orders with email
    Args:
        email: The email of the customer
    Returns:
        A string containing the details of the order
    """
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
        


#MAIN FUNCTION
def blossom_monday_support_Qna(question, session_id, bot_id, user_prompt, db, cache):
    logger.info("Starting QnA process for session_id: %s, bot_id: %s", session_id, bot_id)
    t0 = time.time()

    global store,format_for_chat
    
    chat_message_history = get_session_history(session_id)
    chat_history = format_chat_history(chat_message_history.messages)
    logger.debug("Formatted chat history: %s", chat_history)

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

    tools = [retriever_tool,Order_details_order_number_name,Order_details_email]
    logger.debug("Creating agent with tools: %s", tools)
    agent = create_tool_calling_agent(model, tools, prompt)
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
                a = json.loads(json_str, strict=False)
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

        # Save History and Cache
        try:
            t6 = time.time()
            ans = ("response : "+ str(a_out['response']) +'\nSuggestive_Answers: '+str(a_out['leading_queries'])).replace("{","(").replace("}",")")
            
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

        return a_out
    
    except Exception as e:
        logger.error("Agent execution error: %s", str(e), exc_info=True)
        output_data = {
                "response": "Please ask appropriate question.",
                "leading_queries":[]
            }
        return output_data


def blossom_monday_support_predifined_history(question,session_id,answer,product):

    chat_message_history = get_session_history(session_id)
    chat_message_history.add_user_message(question)
    ans=("response : "+ str(answer) + '\n Products : '+str(product) +'\nSuggestive_Answers: [] ').replace("{","(").replace("}",")")
    chat_message_history.add_ai_message(ans)
    logger.info("Added suggestive Question to chat history: %s", ans)
    return {"a":True}

format_for_chat="""
Your response must be a valid JSON object with exactly these fields
1. "response":str: A string output which should have your text response to the user's question in Markdown format. Always there in an string format.
2. "Suggestive_Answers":list[str]: A list of suggested responses or options to help maintain the conversation flow (at least 3 items). Default to empty list [] if not applicable.
"""

prompts = """
You are a polite support agent chatbot for our company who assists customers with queries about pages, usage, and more.

- You are unable to help with forwarding the user to a live agent; you can only help with query information.
- Base your answer directly on the context provided. Avoid introducing information not found in the source material.
- If you cannot find a definitive answer within the context, indicate this clearly and explain what additional information would be helpful.
- Donot make up any fake links or products that you don't have in the context.
- Provide links in the response only if it is present in the context.

When responding to product or service inquiries:
1. FIRST search the retriever tool for relevant information
2. ONLY reference products, services, and policies found in the retriever results
3. If something is NOT found in the retriever, clearly state: "We currently do not offer [specific item/service]. However, here are some alternatives we do provide: [list alternatives from retriever]"
4. NEVER create fake products, add-ons, services, policies, or links

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

IMPORTANT: Your response must be a valid JSON object with exactly these fields:
1. "response": A string output which should have your text response to the user's question in Markdown format
2. "Suggestive_Answers": A list of suggested responses or options to help maintain the conversation flow (at least 3 items)

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

{user_prompt}

YOUR FINAL RESPONSE MUST BE VALID JSON. Do not include any text before or after the JSON object.
The JSON object must have exactly this structure:
{{
  "response": "your_markdown_formatted_text_here",
  "Suggestive_Answers": ["string1", "string2", "string3"]
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
