"""定義LLM大模型輸出格式的所有類別"""
from pydantic import BaseModel, Field
from Action import PlanStep, Action

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
    total_step: list[PlanStep] = Field(
        ...,
        description="""這個list是一個步驟清單
                    每一個PlanStep裡面裝著:

                        step_id: str;穩定 ID，例如 "s3"，不受插入/刪除影響
                        step_name: str; 步驟描述  
                        status: str; "pending" | "done" | "skipped" | "failed"
                        note: str | None; 若被 replan 過，記錄原因（例如："中餐不存在，改選台式"）
                    
                    step_id 生成一個 s+數字 的組合，從1開始，例:s1、s2、s3...
                    step_name 根據任務生成
                    status 始化為 "pending"
                    note: 初始化為 None
                    """
    )
class FormatOutput_action_command(BaseModel):
    """請LLM生成對應的操作指令"""
    command: Action = Field(
        ...,
        description="""Action類別裡包含
                    {
                        action_type
                        full_resource_id
                        resource_id
                        content_description
                        hint_text
                        text
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
    needs_replan: bool = Field(
        ...,
        description="""若目前畫面上根本找不到符合此步驟描述的元件/選項
                    （例如步驟要求選「中餐」，但畫面上只有「台式、飲料、麵食」等其他選項），
                    代表這個步驟描述本身有問題、無法照字面執行，
                    請填入 True，並且不要勉強套用其他元件硬點、也不要編造 bounds 座標；
                    若目前步驟是可以正常執行的（即使畫面上有彈窗擋住，那屬於 not_current_step，不算這裡），
                    則填 False"""
    )
    replan_reason: str =Field(
        ...,
        description="""若 needs_replan 為 True，請簡短說明這個步驟為什麼無法照字面達成，
                    供後續重新規劃步驟時參考；
                    若 needs_replan 為 False，此欄位留空字串即可"""
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
class FormatOutput_replan(BaseModel):
    """LLM規劃新步驟描述"""
    action: str = Field(
        ...,
        description="""要對此步驟做的處理方式，只能是以下四種之一：
                    "replace"：此步驟描述寫錯了，用更貼近畫面現況、仍能達成使用者目標的描述替換掉
                    "insert_before"：在此步驟之前，需要先多做一個步驟（原步驟保留，之後繼續執行）
                    "insert_after"：在此步驟之後，需要多做一個步驟（原步驟保留）
                    "skip"：此步驟其實不需要執行，直接標記為跳過
                    """  
    )    
    target_step_id: str = Field(
        ...,
        description="要處理的目標步驟的 step_id，通常就是需要重新規畫的那個步驟"
    )
    new_step_name: str | None = Field(
        ...,
        description="""action 為 replace / insert_before / insert_after 時，
                    請填入新的步驟描述；action 為 skip 時可留空（填 null）。

                    這個描述必須是「根據目前畫面，現在就能執行的單一具體動作」，
                    例如：「點擊畫面上的『事件』選項」、「點擊標題輸入框」。
                    禁止寫成「若...就...，若沒有就...」這種條件式/多分支描述，
                    也不要一次規劃好幾個畫面之後才會出現的步驟——
                    只描述當下這一頁該做的下一件事即可。"""
    )
    reason: str = Field(
        ...,
        description="簡短說明為什麼要這樣調整這個步驟，會記錄在該步驟的 note 欄位供除錯使用"
    )
