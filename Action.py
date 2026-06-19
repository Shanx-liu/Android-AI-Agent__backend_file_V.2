"""操作指令類別定義"""
from pydantic import BaseModel

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