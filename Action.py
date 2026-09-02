"""操作指令類別定義、步驟名稱類別"""
from pydantic import BaseModel
from typing_extensions import TypedDict

class PlanStep(TypedDict):      #LLM生成步驟清單的規範
    step_id: str                # 穩定 ID，例如 "s3"，不受插入/刪除影響
    step_name: str              # 步驟描述
    status: str                 # "pending" | "done" | "skipped" | "failed"
    note: str | None            # 若被 replan 過，記錄原因（例如："中餐不存在，改選台式"）

class BoundsXY(BaseModel):
    x: int      # 元件中心點 X（node.x + node.width // 2）
    y: int      # 元件中心點 Y（node.y + node.height // 2）     

class Action(BaseModel):            #每次根據UI tree生成的操作指令
    """操作指令細節"""
    action_type: str                # "click" / "set_text" / "scroll" / "global_back"
    full_resource_id: str | None    # 完整 ViewId
    resource_id: str | None         # 優先使用，來自 UiNode.resourceId
    content_description: str | None # 次選：桌面圖示、無障礙標籤場景
    hint_text: str | None           # 節點的 hint 與 content_description 分開
    text: str | None                # 節點的 text
    bounds: BoundsXY | None         # resource_id 不存在時的 fallback
    input_text: str | None          # 僅 set_text 時使用
    scroll_direction: str | None    # 僅 scroll 時使用："up"/"down"/"left"/"right"