from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn, asyncio

app = FastAPI()


async def receive_loop(websocket: WebSocket):
    while True:
        data = await websocket.receive_text()
        print(f"收到: {data}")


#用WebSocket時，網址開頭要是 ws:// 或 wss://
@app.websocket('/ws')
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()    

    #開一個背景任務接收訊息，主程式可以執行其他程序，非阻塞
    asyncio.create_task(receive_loop(websocket))
    #不能同時多個地方 receive，只能有一個接收入口

    try:
        while True:     #會阻塞整個程式
            data = await websocket.receive_json()   #接收前端訊息，多種格式
            print(f"接收到前端訊息: {data.uiTree} \n{data.screenshot}")

            # 回傳給前端
            await websocket.send_text(f"後端收到: {data}")

    except WebSocketDisconnect:
        print("客戶端斷線！")
        
#--------------------------生產者/消費者模式-----------------------
"""
queue = asyncio.Queue()     #訊息佇列

async def receive_loop(ws):     #生產者：接收訊息
    while True:
        data = await ws.receive_json()
        await queue.put(data)       #將接收到的訊息放入佇列

async def process_loop():       #消費者：處理訊息
    while True:
        data = await queue.get()    #從佇列中取得訊息
        print("處理:", data)
"""
