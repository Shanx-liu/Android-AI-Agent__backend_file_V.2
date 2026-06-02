#此檔案定義用於通訊之json欄位(後端送至前端)
from pydantic import BaseModel
from datetime import datetime, timezone
import zoneinfo

class Action(BaseModel):
    """LangGraph_Core.py的Action類別"""
    action_type: str
    target_node_id: str
    input_text: str | None

class AskMessage(BaseModel):
    """詢問使用者任務具體細節"""
    ask_messages: str
    sent_time: datetime      #傳送json當下的時間

class TaskStartMessage(BaseModel):
    """通知APP端任務開始"""
    start_message: str
    sent_time: datetime

class ReadUIAndScreenshot(BaseModel):
    """告知APP讀取UI樹與截圖"""
    read_ui_tree: str
    sent_time: datetime

class ActionCheck(BaseModel):
    """通知使用者敏感操作需確認"""
    action_detail: str
    sensitive_reason: str
    sent_time: datetime

class OperateCommand(BaseModel):
    """發送操作指令給APP"""
    current_action: Action
    sent_time: datetime

class TaskEndMessages(BaseModel):
    """關閉APP進程、告知使用者執行結果"""
    task_result: str
    task_process: str    
    error_reason: str
    sent_time: datetime

def now_timestamp() -> datetime:
    """回傳目前時間的函式"""
    tz = zoneinfo.ZoneInfo("Asia/Taipei")
    return datetime.now(tz)