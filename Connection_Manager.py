import asyncio
from fastapi import WebSocket, FastAPI
from communication import AskMessage, TaskStartMessage, ActionCheck, OperateCommand, TaskEndMessages, ReadUIAndScreenshot, now_timestamp
from pydantic import BaseModel
from communication import Action


class ConnectionManager:     #全域的狀態共享中心，為"邏輯層"與"通訊層"的 通訊橋樑（Intermediary）
    def __init__(self):
        self.websocket: WebSocket | None = None
        self.is_active = True                       #控制連線狀態
        self.agent_started = False                  #防止重複啟動 Agent
        self._message_queue: asyncio.Queue[dict] = asyncio.Queue()    #使用訊息佇列

    async def send_ask_to_user(self, messages: str):
        """訊問使用者細節的傳送函式"""
        if self.websocket is None:
            raise RuntimeError("WebSocket 尚未連線")
        
        json_data = AskMessage(
            type = "ask_user",
            ask_messages = messages, 
            sent_time = now_timestamp().isoformat()
        )
        await self.websocket.send_json(
            json_data.model_dump(mode='json')
        )     #送訊息給客戶端的函式

    async def send_start_messages(self):        #告訴APP端開始執行
        """通知APP任務開始的傳送函式"""
        if self.websocket is None:
            raise RuntimeError("WebSocket 尚未連線")
        
        json_data = TaskStartMessage(
            type = "task_start",
            sent_time = now_timestamp().isoformat()
        )
        await self.websocket.send_json(
            json_data.model_dump(mode='json')
        )

    async def send_read_messages(self):
        """告知APP讀取UI tree與截圖"""
        if self.websocket is None:
            raise RuntimeError("WebSocket 尚未連線")
        
        json_data = ReadUIAndScreenshot(
            type = "read_ui",
            read_ui_tree = "read",
            sent_time = now_timestamp().isoformat()
        )
        await self.websocket.send_json(
            json_data.model_dump(mode='json')
        )

    async def send_action_check(self, messages: str, reason: str):
        """重送敏感操作通知請使用者確認"""
        if self.websocket is None:
            raise RuntimeError("WebSocket 尚未連線")
        
        json_data = ActionCheck(
            type = "action_check",
            action_detail = messages,
            sensitive_reason = reason,
            sent_time = now_timestamp().isoformat()
        )
        await self.websocket.send_json(
            json_data.model_dump(mode='json')
        )

    async def send_command(self, action: Action):
        """將當前步驟操作指令細節傳給APP"""
        if self.websocket is None:
            raise RuntimeError("WebSocket 尚未連線")
        
        json_data = OperateCommand(
            type = "operate_command",
            current_action = action,
            sent_time = now_timestamp().isoformat()
        )
        await self.websocket.send_json(
            json_data.model_dump(mode='json')
        )

    async def send_end_messages(self, task_result: str, task_process: str, error_reason: str):
        """將任務結果、執行/失敗步數、失敗原因傳給APP"""
        if self.websocket is None:
            raise RuntimeError("WebSocket 尚未連線")
        
        json_data = TaskEndMessages(
            type = "task_end",
            task_result = task_result,
            task_process = task_process,
            error_reason = error_reason,
            sent_time = now_timestamp().isoformat()
        )
        await self.websocket.send_json(
            json_data.model_dump(mode='json')
        )

    async def wait_for_user(self, expected_type: str) -> dict:
        """等待指定 type 的訊息，非預期的訊息會重新放回 queue 尾端"""
        while True:
            data = await self._message_queue.get()
            if data.get("type") == expected_type:       #取出符合 type 值的訊息
                return data
            else:
                # 不是要的類型，放回去等下一個節點消費
                await self._message_queue.put(data)
                await asyncio.sleep(0.05)   # 避免 busy loop

    def handle_user_response(self, data: dict):
        """receive_loop 收到訊息後丟進 queue"""
        self._message_queue.put_nowait(data)
    
    def disconnect(self):
        """主動標記連線結束"""
        self.is_active = False
        self.agent_started = False


manager = ConnectionManager()
