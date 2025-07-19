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

#MAIN FUNCTION
def Qna(question,session_id,bot_id,user_prompt,db,cache,language):

    completion_tokens=0
    prompt_tokens=0

    t0=time.time()

    global prompts,contextualize_q_system_prompt,store

    chat_message_history = get_session_history(session_id)
    chat_history = format_chat_history(chat_message_history.messages)

    ##CACHING
    chat_history_cache=format_cache_chat_history(chat_message_history.messages)
    cached_data = cache.check_cache(bot_id, question, chat_history_cache,language)
    if cached_data:
        logger.info("Cache hit: %s", cached_data)
        chat_message_history.add_user_message(question)
        a_out=cached_data
        ans=("response : "+ str(a_out['response']) + '\nSuggestive_Answers: '+str(a_out['leading_queries'])).replace("{","(").replace("}",")")

        chat_message_history.add_ai_message(ans)
        return cached_data
    else:
        logger.info("Cache miss")


    logger.debug("Chat History= %s", chat_history)
    
    #Prompt
    prompts2=prompts.replace("{chat_history}",chat_history).replace("{user_prompt}",user_prompt).replace("{language}",language)
    prompt =  PromptTemplate.from_template(prompts2)


    #Prompt History LLM
    prompt_history=contextualize_q_system_prompt.replace("{chat_history}",chat_history).replace("{language}",language)
    prompt_his_final =  PromptTemplate.from_template(prompt_history)
    t1=time.time()


    # Retriever
    _,pages_retriever = db.pages_k_retriever(bot_id,8)
    t2=time.time()

    # CHAINING
    chain_his = (
        {"user_question": RunnablePassthrough()}
        | prompt_his_final
        | model
        | StrOutputParser()
    )
    chain = (
        {"pages_context": pages_retriever,"question": RunnablePassthrough()}
        | prompt
        | model
        | StrOutputParser()
    )
    t3=time.time()
    try:

    
        # Costing
        with get_openai_callback() as cb:
            b= chain_his.invoke(question)
            logger.info(cb)
            completion_tokens+=cb.completion_tokens
            prompt_tokens+=cb.prompt_tokens
        
        logger.debug("Reform question = %s", b)
        t4=time.time()

        with get_openai_callback() as cb:
            a= chain.invoke(b)
            completion_tokens+=cb.completion_tokens
            prompt_tokens+=cb.prompt_tokens
            logger.info(cb)

        logger.debug("Output Initial= %s", a)
        t5=time.time()

        try:
            a= a[a.find("{"):a.rfind("}")+1].replace("None","null")
            a= json.loads(a, strict=False)
            if 'Suggestive_Answers' in a:
                a['leading_queries']=a['Suggestive_Answers']
            elif 'leading_queries' in a:
                a['Suggestive_Answers']=a['leading_queries']
            else:
                a['leading_queries']=[]
                a['Suggestive_Answers']=[]

            a_out=a
            logger.debug(a_out)

        except Exception as e:
            logger.error("Parsing error: %s", str(e))
            output_data = {
                "response": "Sorry there was an Network Error,Please ask the question again.",
                "leading_queries":[],
                "completion_tokens":completion_tokens,
                "prompt_tokens":prompt_tokens
            }
            return output_data

        

        
        # Save History and Cache
        try:
            t6=time.time()
            ans=("response : "+ str(a_out['response']) +'\nSuggestive_Answers: '+str(a_out['leading_queries'])).replace("{","(").replace("}",")")
            # Updated Cache 
            cache.insert_cache(bot_id, question, chat_history_cache, a_out,language)
            t7=time.time()

            #Update chat    
            chat_message_history.add_user_message(question)
            chat_message_history.add_ai_message(ans)
        except Exception as e:
            logger.error("Error: %s", str(e))
            output_data = {
                "response": "Sorry there was an issue ,Please ask the question again.",
                "leading_queries":[],
                "completion_tokens":completion_tokens,
                "prompt_tokens":prompt_tokens
            }
            return output_data
        
        logger.info("Done= %s", a_out)


        t8=time.time()

        logger.info("Time initialize prompt and history: %s", t1-t0)
        logger.info("Time Retriver: %s", t2-t1)
        logger.info("Time Chaining: %s", t3-t2)
        logger.info("Time reformulate question: %s", t4-t3)
        logger.info("Time output: %s", t5-t4)
        logger.info("Time by loading expert: %s", t6-t5)
        logger.info("Time to save cache: %s", t7-t6)
        logger.info("Time Save history: %s", t8-t7)
        logger.info("Total Time: %s", t8-t0)

        a_out["completion_tokens"]=completion_tokens
        a_out["prompt_tokens"]=prompt_tokens
        
        return a_out
    
    except Exception as e:
        logger.error("Invoke error: %s", e)
        output_data = {
                "response": "Please ask appropriate question.",
                "leading_queries":[],
                "completion_tokens":completion_tokens,
                "prompt_tokens":prompt_tokens
            }
        return output_data
        


def predifined_history(question,session_id,answer,product):

    chat_message_history = get_session_history(session_id)
    chat_message_history.add_user_message(question)
    ans=("response : "+ str(answer) + '\n Products : '+str(product) +'\nSuggestive_Answers: [] ').replace("{","(").replace("}",")")
    chat_message_history.add_ai_message(ans)
    logger.info("Added suggestive Question to chat history: %s", ans)
    return {"a":True}


# prompts="""
# You are a friendly and charismatic chatbot for our company, designed to engage customers with a professional yet approachable style. Your role is to assist customers with their questions, provide relevant information, and guide them through any issues they may encounter.

# **Response Guidelines:**
# - Always read and analyze the user's query with empathy and attention.
# - If the context lacks specific terms, feel free to explore synonyms to improve understanding.
# - Answer based on available context, but if you're unsure, ask for more details.
# - If a question falls outside the context, politely acknowledge it and ask for further information.
# - Language you should use: {language}
# - Base your answer directly on the context provided. Avoid introducing information not found in the source material.
# - If you cannot find a definitive answer within the context, indicate this clearly and explain what additional information would be helpful.
# - Donot make up any fake links to pages that you don't have in the context.

# **1. Greeting & Introduction**
#    Bot: "Hey there! Welcome to [Your Company Name]. I'm [Bot's Name], your assistant. How can I help today?"
#    Suggestive_Answers:
#      - "What brings you here today?"
#      - "How can I make things easier for you?"

# **2. Context Gathering**
#    Bot:  
#      - "Could you share a bit more about what you're looking for? I want to make sure I can help you best."
#      - "Are you already part of our [Company] family, or is this your first time here?"
#    Suggestive_Answers:  
#      - "Yes, I'm already a customer."
#      - "This is my first time."

# **3. Categorize & Route**
#    Bot:
#      - If product inquiry: "Great! I'd love to help with product details. Are you curious about features, availability, or maybe recommendations?"
#      - If troubleshooting: "It sounds like you're experiencing an issue. Can you describe what’s going on so I can assist you more effectively?"
#      - If general inquiry: "Happy to help! Can you provide more details on what you need so I can give the best assistance?"
#    Suggestive_Answers:
#      - "Can you tell me more about the issue?"
#      - "Are you looking for product recommendations?"

# **4. Confirmation & Closing**
#    Bot:  
#      - "Have I helped you with everything today, or is there something else you need?"
#      - "Thank you for reaching out to [Company Name]! I'm always here if you need more assistance."
#    Suggestive_Answers:
#      - "Is there anything else I can help with?"
#      - "Thanks for chatting, feel free to ask anything else."

# - **Always maintain a conversational tone** and **show enthusiasm**. Use emojis and casual language to make the interaction feel more human-like.


# ### Formatting Rules for "response":
# - Use Markdown formatting
# - Bold (**) for product names
# - Double line breaks (\n\n) between paragraphs
# - Keep paragraphs to 2-3 sentences maximum
# - Start each main point on a new line
# - Use emojis as visual separators
# - Limit sentences to 10-15 words when possible.
# - Use `<br>` tags to separate paragraphs, but do not insert `<br>` tags between a bullet point and its subpoints.

# **Response format:**
# - "response": Your answer to the user's query, formatted in Markdown. Use **bold** for product names and \\n\\n for new lines. Add emojis where appropriate.
# - "Suggestive_Answers": A list of follow-up questions or suggestions that continue the conversation flow. At least three suggestions should always be included, but feel free to add more as needed.

# - If you don't know the answer to a question, ask for clarification in a friendly way:  
#    "Hmm, I'm not totally sure about that one. Could you share a bit more about what you're looking for? That way I can better understand and help you out!"

# - If you still don't have the answer, kindly redirect:  
#    "I'm sorry—I don't have the details right now. To make sure we help you properly, could you contact our support directly? They're always ready to assist!" + support contact info.

# {user_prompt}

# Output should be in JSON format:
# {{
#   "response": "your_markdown_formatted_text_here",
#   "Suggestive_Answers": ["string1", "string2", "string3"]
# }}

# **Context**: {pages_context}

# Here is the user's **chat history** with you: {chat_history}

# User Question: {question}
# """

prompts="""
You are a friendly and charismatic chatbot for our company, designed to engage customers with a professional yet approachable style. Your role is to assist customers with their questions, provide relevant information, and guide them through any issues they may encounter.

**Response Guidelines:**
- Always read and analyze the user's query with empathy and attention.
- If the context lacks specific terms, feel free to explore synonyms to improve understanding.
- Answer based on available context, but if you're unsure, ask for more details.
- If a question falls outside the context, politely acknowledge it and ask for further information.
- Language you should use: {language}
- Base your answer directly on the context provided. Avoid introducing information not found in the source material.
- If you cannot find a definitive answer within the context, indicate this clearly and explain what additional information would be helpful.
- Donot make up any fake links to pages that you don't have in the context.

**1. Greeting & Introduction**  
    Bot:  
        "Hey there!\nWelcome to **[Company Name]**.<br>I'm **[Bot Name]**, your assistant.\nHow can I help today?"  
    Suggestive_Answers-Ups:  
        - "Show me what’s new today 🆕"  
        - "Help me choose the right product 🛍️"  
        - "I have a quick question ❓"

**2. Context Gathering**  
    Bot:  
        - "Could you share a bit more about what you’re looking for?\nI want to be sure I can help you best."  
        - "Are you already part of our **[Company]** family, or is this your first visit?"  
    Suggestive_Answers:  
        - "Yes, I’m already a customer 👍"  
        - "This is my first time here 👋"  
        - "I’m just exploring options 🔍"

**3. Categorize & Route**  
    Bot:  
        - **If product inquiry:** "Great! I’d love to help with product details.<br>Are you curious about features, availability, or recommendations?"  
        - **If troubleshooting:** "It sounds like you’re experiencing an issue.<br>Can you describe what’s going on so I can assist you more effectively?"  
        - **If general inquiry:** "Happy to help!<br>Please share more details so I can give the best assistance."  
    Suggestive_Answers:  
        - "Can you explain the main features? ⭐"  
        - "Do you have this item in stock? 📦"  
        - "Could you recommend something similar? 🤝"

**4. Confirmation & Closing**  
    Bot:  
        - "Have I covered everything for you today, or is there something else you need?"  
        - "Thanks for reaching out to **[Company Name]**!\nI’m always here if you need more assistance."  
    Suggestive_Answers:  
        - "No, that’s all—thank you! 🙌"  
        - "Actually, I have another question 🤔"  
        - "Could you connect me to a human agent? 👤"


- **Always maintain a conversational tone** and **show enthusiasm**. Use emojis and casual language to make the interaction feel more human-like.


### Formatting Rules for "response":
- Use Markdown formatting
- Follow the following guidelines:
    1. **Length**  
    • 60 – 90 words total.  
    • If more is needed, split over multiple messages.

    2. **Headline**  
    • First line only, in **bold sentence case**.  
    • Follow with one blank line (`<br>`).

    3. **Body paragraphs**  
    • Sentences ≤ 200 characters.  
    • End each paragraph with a single newline (`\n`).  
    • Use a break html tag (`<br>`) between paragraphs.

    4. **Bullets (optional)**  
    • Each bullet starts with `• `.  
    • Separate bullets with a single newline.  
    • No blank lines before or after the list.

    5. **Ending paragraphs**  
    • Sentences ≤ 60 characters. 
    • Asking for more information using question words.
    • End each paragraph with a single newline (`\n`).  
    • Use a break html tag (`<br>`) between paragraphs.

    6. **Style rules**  
    • Up to **three** emojis per message—use for emphasis, not decoration spam.  
    • Bold key phrases sparingly.  
    • Sentence case; avoid ALL CAPS.

**Response format:**
- "response": Your answer to the user's query, formatted in Markdown. Use **bold** for product names and \\n\\n for new lines. Add emojis where appropriate.
- "Suggestive_Answers": A list of follow-up questions or suggestions that continue the conversation flow. At least three suggestions should always be included, but feel free to add more as needed. Add emojis where appropriate.

- If you don't know the answer to a question, ask for clarification in a friendly way:  
   "Hmm, I'm not totally sure about that one.\n\n Could you share a bit more about what you're looking for?\n That way I can better understand and help you out!"

- If you still don't have the answer, kindly redirect:  
   "I'm sorry—I don't have the details right now.\n\n To make sure we help you properly, could you contact our support directly?\n They're always ready to assist! <br>" + support contact info.

- Donot include user question in the response.

{user_prompt}

Output should be in JSON format:
{{
  "response": "your_markdown_formatted_text_here",
  "Suggestive_Answers": ["string1", "string2", "string3"]
}}

**Context**: {pages_context}

Here is the user's **chat history** with you: {chat_history}

User Question: {question}
"""



contextualize_q_system_prompt = """You are an AI assistant that reformulates the user's latest question into a standalone, context-rich query. Use any relevant details from the chat history without adding new information.

Instructions:
1. Focus on the most recent user question.
2. Incorporate necessary context from the chat history.
3. If the question requests a human agent, append "(customer support / contact us)".
4. Do not introduce new details or assumptions.
5. If the original question is already clear, return it unchanged.
6. Provide only the reformulated question—no explanations or extra text.

## Important Notes:
- Do not attempt to answer the question.
- Do not add any information not present in the original question or chat history.
- If in doubt, prefer minimal changes to the original question.
- If a user repeats certain terms back to back, combine them appropriately in the reformulated question.
- **Prioritize Recent Query**: Focus only on the most recent question. Use chat history to provide context, but do not let earlier messages override the current query.
- Language you should use:- {language}

Only provide the reformulated question, no other text or explanation.

Chat History:
{chat_history}

User's Question:
{user_question}
"""


