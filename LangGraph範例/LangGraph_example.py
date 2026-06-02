from dotenv import load_dotenv
from typing import Annotated, Literal
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field
from typing_extensions import TypedDict
import os

load_dotenv()

llm = init_chat_model(      #初始化模型
    "gemini-2.5-flash",
    model_provider="google_genai",                  #設定LLM提供商
    google_api_key=os.getenv("GEMINI_API_KEY")      #設定API_KEY
)

class State(TypedDict):     #整個LangGraph的共享記憶體，每個節點都能讀取以及寫入，儲存完整歷史對話
    messages: Annotated[list, add_messages] 
    #第一個參數為型別，第二個參數讓新訊息附加到最後面，防止新訊息覆蓋掉舊訊息


graph_builder = StateGraph(State)   #建立狀態圖


def chatbot(state: State):      #新增節點時的呼叫函式
    return {"messages": [llm.invoke(state["messages"])]}


graph_builder.add_node("chatbot", chatbot)      #新增名為 'chatbot' 的節點，並指定其處理函式
graph_builder.add_edge(START, "chatbot")        #將起點與節點連接
graph_builder.add_edge("chatbot", END)      #將節點與終點連接


graph = graph_builder.compile()     #編譯狀態圖


user_input = input("請輸入你的問題：")
state = graph.invoke({"messages": [{"role": "user", "content": user_input}]}) #呼叫LLM


print(state["messages"][-1].content)    #顯示聊天內容的最後一條訊息

#將建構的狀態圖以png形式輸出成圖片
from IPython.display import Image, display
try:
    png_data = graph.get_graph().draw_mermaid_png()
    with open("graph.png", "wb") as f:
        f.write(png_data)
    print("已輸出 graph.png")
except Exception:
    pass


