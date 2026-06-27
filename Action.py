"""操作指令類別定義、步驟名稱類別"""
from pydantic import BaseModel
from typing_extensions import TypedDict

class Step(TypedDict):      #LLM生成步驟清單的規範
    step_name: str  
    #操作指令不先寫死，而是根據該步驟的名稱、擷取到的UI tree來生成

class BoundsXY(BaseModel):
    x: int      # 元件中心點 X（node.x + node.width // 2）
    y: int      # 元件中心點 Y（node.y + node.height // 2）     

class Action(BaseModel):            #每次根據UI tree生成的操作指令
    """操作指令細節"""
    action_type: str                # "click" / "set_text" / "scroll" / "global_back"
    resource_id: str | None         # 優先使用，來自 UiNode.resourceId
    content_description: str | None # 次選：桌面圖示、無障礙標籤場景
    bounds: BoundsXY | None         # resource_id 不存在時的 fallback
    input_text: str | None          # 僅 set_text 時使用
    scroll_direction: str | None    # 僅 scroll 時使用："up"/"down"/"left"/"right"