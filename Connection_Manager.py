import asyncio
from fastapi import WebSocket, FastAPI
from communication import AskMessage, TaskStartMessage, ActionCheck, OperateCommand, TaskEndMessages, ReadUIAndScreenshot, now_timestamp
from pydantic import BaseModel
from communication import Action


class ConnectionManager:     #全域的狀態共享中心，為"邏輯層"與"通訊層"的 通訊橋樑（Intermediary）
    def __init__(self):
        self.first_data:str | None                  #使用者的第一條訊息(原始指令)
        self.websocket: WebSocket | None = None
        self.pending: asyncio.Future | None = None  #Future為一個待處理的事件，類似 Promise
        self.is_active = True                       #控制連線狀態
        self.agent_started = False                  #防止重複啟動 Agent

    async def send_ask_to_user(self, messages: str):
        """訊問使用者細節的傳送函式"""
        if self.websocket is None:
            raise RuntimeError("WebSocket 尚未連線")
        
        json_data = AskMessage(
            ask_messages = messages, 
            sent_time = now_timestamp()
        )
        await self.websocket.send_json(
            json_data.model_dump()
        )     #送訊息給客戶端的函式

    async def send_start_messages(self):        #告訴APP端開始執行
        """通知APP任務開始的傳送函式"""
        if self.websocket is None:
            raise RuntimeError("WebSocket 尚未連線")
        
        json_data = TaskStartMessage(
            start_message = "start",
            sent_time = now_timestamp()
        )
        await self.websocket.send_json(
            json_data.model_dump()
        )

    async def send_read_messages(self):
        """告知APP讀取UI tree與截圖"""
        if self.websocket is None:
            raise RuntimeError("WebSocket 尚未連線")
        
        json_data = ReadUIAndScreenshot(
            read_ui_tree = "read",
            sent_time = now_timestamp()
        )
        await self.websocket.send_json(
            json_data.model_dump()
        )

    async def send_action_check(self, messages: str, reason: str):
        """重送敏感操作通知請使用者確認"""
        if self.websocket is None:
            raise RuntimeError("WebSocket 尚未連線")
        
        json_data = ActionCheck(
            action_detail = messages,
            sensitive_reason = reason,
            sent_time = now_timestamp()
        )
        await self.websocket.send_json(
            json_data.model_dump()
        )

    async def send_command(self, action: Action):
        """將當前步驟操作指令細節傳給APP"""
        if self.websocket is None:
            raise RuntimeError("WebSocket 尚未連線")
        
        json_data = OperateCommand(
            current_action = action,
            sent_time = now_timestamp()
        )
        await self.websocket.send_json(
            json_data.model_dump()
        )

    async def send_end_messages(self, task_result: str, task_process: str, error_reason: str):
        """將任務結果、執行/失敗步數、失敗原因傳給APP"""
        if self.websocket is None:
            raise RuntimeError("WebSocket 尚未連線")
        json_data = TaskEndMessages(
            task_result = task_result,
            task_process = task_process,
            error_reason = error_reason,
            sent_time = now_timestamp()
        )
        await self.websocket.send_json(
            json_data.model_dump()
        )

    async def wait_for_user(self) -> dict:
        """節點呼叫這個來等使用者回應"""
        loop = asyncio.get_running_loop()       #取得正在運行的非同步事件迴圈
        self.pending = loop.create_future()     #在迴圈中註冊一個"尚未完成"的未來事件
        return await self.pending               #卡在這，直到 set_result 被呼叫
        #暫停這個協程(coroutine)，等待上面這行 self.pending.set_result(data)

    def handle_user_response(self, data: dict):
        """receive_loop 收到訊息後呼叫這個"""
        if self.pending and not self.pending.done():
            self.pending.set_result(data)     
            #告訴pending物件，要等的資料拿到了，為data
            #並且通知所有正在 await 此物件的人
    
    def disconnect(self):
        """主動標記連線結束"""
        self.is_active = False
        self.agent_started = False


manager = ConnectionManager()
