from fastapi import FastAPI
import uvicorn
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

app = FastAPI()

load_dotenv()

llm_google = init_chat_model(      #初始化模型
    "gemini-2.5-flash",
    model_provider="google_genai",                  #設定LLM提供商
    google_genai_api_key=os.getenv("GEMINI_API_KEY"),      #設定API_KEY
    max_retries=3
)

llm_openai = init_chat_model(      #初始化模型
    "gpt-4o-mini",
    model_provider="openai",                  #設定LLM提供商
    api_key=os.getenv("OPENAI_API_KEY"),      #設定API_KEY
    max_retries=3
)

class Request(BaseModel):
    prompt: str

@app.post('/test')
async def get_messages(messages: Request):

    print(messages.uiTree)
    print(messages.screenshot)
    """
    result = await llm_google.ainvoke([
        {
            "role": "user",
            "content": messages.prompt
        }
    ])
    """
    return#{"reply": result.content,
           #"test": "這是劉善行的後端傳給你的"}


if __name__ == "__main__":
    uvicorn.run("test_connect:app", port=8000, reload=True)
    
    #ngrok發布命令：/ngrok/ngrok.exe http --url=unannealed-controllingly-sarai.ngrok-free.dev 8000
    #API 根 URL：https://unannealed-controllingly-sarai.ngrok-free.dev/test/