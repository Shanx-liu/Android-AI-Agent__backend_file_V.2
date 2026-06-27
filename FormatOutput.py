"""定義LLM大模型輸出格式的所有類別"""
from pydantic import BaseModel, Field
from Action import Step, Action

#以下為讓LLM根據格式輸出的    結構化輸出類別
class FormatOutput_check_requirements(BaseModel):
    """詢問使用者需求具體細節的類別"""
    again_check: bool = Field(
        ...,        #省略號代表此變數必填
        description="""請判斷使用者的指令是否缺少具體細節，
                    例如：使用者想點一杯珍珠奶茶，卻沒有說要用哪個平台、糖度、冰的還是熱的，
                    如有缺少，請回答True，沒有缺少的話請回答False。
                    """
    )
    ask_for_user: str = Field(
        ...,
        description="""你是一個Android裝置的行動助理，
                    你的工作是協助使用者完成他指定的任務。
                    請你先判斷使用者的任務是否有缺少具體細節，
                    例如：使用者想點一杯珍珠奶茶，卻沒有說要用哪個平台、糖度、冰的還是熱的，
                    你需要將使用者沒說到的細節彙總成一段話再問使用者一次。
                    例如：你要使用Foodpanda嗎，微糖少冰可以嗎。
                    """
    )
class FormatOutput_ask_user(BaseModel):
    """判斷使用者是明確說明還是含糊帶過"""
    define_detail: bool = Field(
        ...,
        description="""如果明確說明就填入 True，
                    沒有明確說明則填入 False。
                    """
    )
class FormatOutput_change_dict(BaseModel):  
    """將使用者補充的具體細節轉換成 dictory"""
    clarified_params_json: str = Field(
        ...,
        description="""請將所有需要用到的細節列出來，並用合法 JSON 字串格式輸出，不要加任何說明
                    例如：
                    {"外送平台": "Foodpanda", "糖分": "半糖", "冰量": "少冰"}
                    """
    )    
class FormatOutput_analyze(BaseModel):
    """請LLM分析完整步驟清單的類別"""
    total_step: list[Step] = Field(
        ...,
        description="""這個list是一個步驟清單，
                    每一個dict裡面只裝著一個步驟名稱。
                    範例：{"step_name": "開啟Foodpanda應用程式"}。
                    """
    )
class FormatOutput_action_command(BaseModel):
    """請LLM生成對應的操作指令"""
    command: Action = Field(
        ...,
        description="""Action類別裡包含
                    {
                        action_type
                        resource_id
                        content_description
                        bounds
                        input_text
                        scroll_direction
                    }
                    請生成對應的值"""
    )
    not_current_step: bool = Field(
        ...,
        description="""若當前須執行的操作不在步驟清單裡
                    例如：
                    - 關閉廣告彈窗
                    - 須關閉其他不相關彈窗

                    若符合則填入 True
                    """
    )
    exception_step_name: str = Field(
        ...,
        description="""若不在步驟清單裡，則針對此步驟要執行的動作生成臨時的步驟名稱"""
    )
class FormatOutput_sensitive_check(BaseModel):
    """判斷是否為敏感操作"""
    is_sensitive: bool = Field(
        ...,
        description="""請判斷以下操作指令是否屬於敏感操作，
                    敏感操作包含：付款、確認訂單、送出、輸入密碼、刪除資料等，
                    如果是敏感操作請回答True，否則回答False。
                    """
    )
    reason: str = Field(
        ...,
        description="簡短說明為什麼這個操作是或不是敏感操作"
    )
class FormatOutput_chack_action_success(BaseModel):
    """請LLM判斷當前步驟是否執行成功"""
    is_success: bool = Field(
        ...,
        description="步驟成功填入True，失敗False"
    )
class FormatOutput_error_reason(BaseModel):
    """LLM分析填入：失敗原因、下一輪之提示"""
    error_reason: str = Field(      
        ...,
        description="""填入失敗原因"""
    )
    next_round_hint: str = Field(
        ...,
        description="""填入下一輪提示"""
    )