#執行流程(範例)
#           步驟	        |      負責人     |           狀態
#1. 呼叫 wait_for_user	    |  Agent 節點	  |   self.pending 被建立，Agent 進入休眠等待。
#2. 使用者在前端按鈕	     |   使用者	       |     資料經由 WebSocket 傳回後台。
#3. 呼叫 set_result(data)	|  receive_loop  |	self.pending 被填入資料，狀態轉為 Done。
#4. 恢復執行	            |    事件迴圈	  |   原本卡在 await self.pending 的 Agent 節點被喚醒，拿到 data 並繼續往下走。
"""
總結流程
1. Agent 節點：執行 await manager.wait_for_user() → 「我等你的好消息 (Future) 」。
2. WebSocket 接收：收到訊息 → 執行 manager.set_result("確認") → 「好消息來了！」。
3. Future 物件：狀態轉為完成。
4. Agent 節點：收到 "確認"，繼續執行 if result == "confirm": ...。
"""

#---------------------以下為邏輯層(共用物件)-------------------------------
import asyncio, uvicorn
from fastapi import WebSocket, FastAPI
from communication import AskMessage, TaskStartMessage, ActionCheck, OperateCommand, TaskEndMessages, ReadUIAndScreenshot, now_timestamp
from Connection_Manager import manager




#----------------------------以下為通訊層-------------------------------------

#用WebSocket時，網址開頭要是 ws:// 或 wss://
#ngrok發布命令：/ngrok/ngrok.exe http --url=unannealed-controllingly-sarai.ngrok-free.dev 8001
#WebSocket 根 URL：wss://unannealed-controllingly-sarai.ngrok-free.dev/ws

app = FastAPI()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()        #建立連線

    #建立連線後先接收第一條訊息
    initial_data: dict = await websocket.receive_json()   
    print(f"收到前端初始訊息： {initial_data.get('first_messages')}")
    manager.first_data = initial_data.get("first_messages")

    manager.websocket = websocket
    manager.is_active = True
    manager.agent_started = False   #重置狀態

    #檢查是否已經啟動過，避免重複執行
    if not manager.agent_started:
        manager.agent_started = True
        # 啟動 LangGraph Agent
        from LangGraph_Core import run_agent
        asyncio.create_task(run_agent(manager.first_data, manager))
    else:
        print("Agent 已經在運行中，跳過啟動。")

    #主體：一直收訊息
    async def receive_loop():
        try:
            # 檢查旗標，如果 is_active 變 False 則跳出迴圈
            while manager.is_active:
                data: dict = await websocket.receive_json()
                manager.handle_user_response(data)  # 橋接給等待中的節點
                #將收到的資料藉由 manager 共同物件轉交給 set_sult()方法
        except Exception as e:
            print(f"連線已中斷: {e}")
        finally:
            # 確保最後一定會關閉 WebSocket
            await websocket.close()
            print("WebSocket 已斷開")


    await receive_loop()    #利用上面定義的無窮迴圈，讓WebSocket連線一直保持開啟


if __name__ == '__main__':      #一鍵啟動伺服器
    uvicorn.run("Server_Core:app", port=8001, reload=True)
#-------------------------------------------------------------------------------
