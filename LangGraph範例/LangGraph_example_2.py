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

class MessageClassifier(BaseModel):     #結構化輸出類別
    message_type: Literal["emotional", "logical"] = Field(
        ...,
        description="Classify if the message requires an emotional (therapist) or logical response."
        #描述:讓LLM知道messages_type這個變數該填什麼值
    )
    

class State(TypedDict):
    messages: Annotated[list, add_messages]
    message_type: str | None    #分類結果


def classify_message(state: State):
    last_message = state["messages"][-1]
    classifier_llm = llm.with_structured_output(MessageClassifier)
    #強迫LLM依照MessageClassifier的格式輸出
    
    result = classifier_llm.invoke([
        {
            "role": "system",
            "content": """將用戶訊息分類為:
            - 'emotional': 尋求情緒支持、心理諮商、處理情緒問題或個人問題
            - 'logical': 尋求事實、資訊、邏輯分析或實用解決方案
            """
        },
        {"role": "user", "content": last_message.content}
    ])
    return {"message_type": result.message_type}


def router(state: State):
    message_type = state.get("message_type", "logical")
    if message_type == "emotional":
        return {"next": "therapist"}

    return {"next": "logical"}   #輸出分類結果，會自動儲存在State狀態裡


def therapist_agent(state: State):
    last_message = state["messages"][-1]

    messages = [
        {"role": "system",
         "content": """你是一位富有同情心的治療師。請關注使用者資訊中的情感層面。
                    展現同理心，認可他們的感受，並幫助他們處理情緒。
                    提出一些啟發性的問題，幫助他們更深入地探索自己的感受。
                    除非使用者明確詢問，否則避免提供邏輯化的回覆。"""
        },
        {
            "role": "user",
            "content": last_message.content
        }
    ]
    reply = llm.invoke(messages)
    return {"messages": [{"role": "assistant", "content": reply.content}]}


def logical_agent(state: State):
    last_message = state["messages"][-1]

    messages = [
        {"role": "system",
         "content": """你是純粹的邏輯型助手。請只關注事實和資訊。
                    請根據邏輯和證據提供清晰簡潔的答案。
                    請勿涉及情緒或提供情感支持。
                    請直接、坦誠地回答問題。"""
         },
        {
            "role": "user",
            "content": last_message.content
        }
    ]
    reply = llm.invoke(messages)
    return {"messages": [{"role": "assistant", "content": reply.content}]}


graph_builder = StateGraph(State)

graph_builder.add_node("classifier", classify_message)
graph_builder.add_node("router", router)
graph_builder.add_node("therapist", therapist_agent)
graph_builder.add_node("logical", logical_agent)

graph_builder.add_edge(START, "classifier")
graph_builder.add_edge("classifier", "router")

graph_builder.add_conditional_edges(    #新增條件邊，router連到therapist或logical
    "router",
    lambda state: state.get("next"),
    {"therapist": "therapist", "logical": "logical"}
)

graph_builder.add_edge("therapist", END)
graph_builder.add_edge("logical", END)

graph = graph_builder.compile()


def run_chatbot():      #啟動系統
    state = {"messages": [], "message_type": None}  #初始化狀態

    while True:
        user_input = input("Message:")
        if user_input == "exit":    #輸入exit則退出系統
            print("Bye")
            break

        state["messages"] = state.get("messages", []) + [
            {"role": "user", "content": user_input}
        ]    #新增使用者訊息

        state = graph.invoke(state)     #開始執行狀態機

        if state.get("messages") and len(state["messages"]) > 0:
            last_message = state["messages"][-1]
            print(f"Assistant: {last_message.content}")


if __name__ == "__main__":
    run_chatbot()
    #將建構的狀態圖以png形式輸出成圖片
    from IPython.display import Image, display
    try:
        png_data = graph.get_graph().draw_mermaid_png()
        with open("graph_2.png", "wb") as f:
            f.write(png_data)
        print("已輸出 graph_2.png")
    except Exception:
        pass