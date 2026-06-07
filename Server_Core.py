import asyncio, uvicorn
from fastapi import WebSocket, FastAPI
from Connection_Manager import manager
import colorama

#----------------------------以下為通訊層-------------------------------------

#用WebSocket時，網址開頭要是 ws:// 或 wss://
#ngrok發布命令：/ngrok/ngrok.exe http --url=unannealed-controllingly-sarai.ngrok-free.dev 8002
#WebSocket 根 URL：wss://unannealed-controllingly-sarai.ngrok-free.dev/ws

app = FastAPI()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()        #建立連線

    #建立連線後先接收第一條訊息
    initial_data: dict = await websocket.receive_json()   
    print(colorama.Fore.RED + colorama.Style.BRIGHT + f"收到前端初始訊息： {initial_data.get('Initial_messages')}")

    manager.websocket = websocket
    manager.is_active = True
    manager.agent_started = False   #重置狀態

    #檢查是否已經啟動過，避免重複執行
    if not manager.agent_started:
        manager.agent_started = True
        # 啟動 LangGraph Agent
        from LangGraph_Core import run_agent
        asyncio.create_task(run_agent(manager))
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
            print(colorama.Fore.RED + f"連線已中斷: {e}")
        finally:
            # 確保最後一定會關閉 WebSocket
            await websocket.close()
            print(colorama.Fore.RED + "WebSocket 已斷開")


    await receive_loop()    #利用上面定義的無窮迴圈，讓WebSocket連線一直保持開啟


if __name__ == '__main__':      #一鍵啟動伺服器
    uvicorn.run("Server_Core:app", port=8002, reload=True)
#-------------------------------------------------------------------------------
