#此檔案定義用於通訊之json欄位(後端送至前端)
from pydantic import BaseModel
from datetime import datetime, timezone
import zoneinfo

#以下為傳給前端之 JSON 定義

class AskMessage(BaseModel):
    """詢問使用者任務具體細節"""
    type: str
    ask_messages: str
    sent_time: str      #傳送json當下的時間

class TaskStartMessage(BaseModel):
    """通知APP端任務開始"""
    type: str
    sent_time: str

class ReadUIAndScreenshot(BaseModel):
    """告知APP讀取UI樹與截圖"""
    type: str
    sent_time: str

class ActionCheck(BaseModel):
    """通知使用者敏感操作需確認"""
    type: str
    action_detail: str
    sensitive_reason: str
    sent_time: str

class OperateCommand(BaseModel):
    """發送操作指令給APP"""
    type: str
    current_action: Action
    sent_time: str

class TaskEndMessages(BaseModel):
    """關閉APP進程、告知使用者執行結果"""
    type: str
    task_result: str
    task_process: str    
    error_reason: str
    sent_time: str

class UserCancelMessages(BaseModel):
    """使用者取消時用"""
    type: str
    cancel_message: str
    sent_time: str

def now_timestamp() -> str:
    """回傳當下時間的函式，回傳型別為 str"""
    tz = zoneinfo.ZoneInfo("Asia/Taipei")
    return datetime.now(tz).isoformat()