from dotenv import load_dotenv
load_dotenv()
import os
import json
import time
from langchain_core.runnables import RunnablePassthrough
from langchain_openai import AzureChatOpenAI
from langchain_core.prompts import PromptTemplate
from typing import List
from langchain_community.callbacks import get_openai_callback
from langchain_core.output_parsers import StrOutputParser


model = AzureChatOpenAI(
    openai_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
    azure_deployment=os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"],
)
#MAIN FUNCTION
def response_format_chatbot(format_for_chat,chatbot_response):

    try:
        global prompts

        prompts2=prompts.replace("{Format}",format_for_chat)
        prompt =  PromptTemplate.from_template(prompts2)


        # CHAINING
        chain = (
            {"response": RunnablePassthrough()}
            | prompt
            | model
            | StrOutputParser()
        )    
        with get_openai_callback() as cb:
            a= chain.invoke(chatbot_response)
        a= a[a.find("{"):a.rfind("}")+1].replace("None","null").replace("\\n","\n")
        a= json.loads(a, strict=False)
        return a
                
    except Exception as e:
        print(e)
        return None




prompts = """
You are a formatter that formats the response into json format.

Format the response into json format.
{Format}

-----------------------------------------------------
Response to format: 
{response}
"""

