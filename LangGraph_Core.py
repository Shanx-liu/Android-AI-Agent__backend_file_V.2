from dotenv import load_dotenv
from typing import Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from typing_extensions import TypedDict
import os, base64, json
from Connection_Manager import ConnectionManager, manager
import colorama

colorama.init(autoreset=True)   #終端機字體顏色設定
load_dotenv()

llm = init_chat_model(      #初始化模型
    "gpt-5.4-mini",
    google_api_key=os.getenv("OPENAI_API_KEY"),     #設定API_KEY
    max_retries=5
)

class Step(TypedDict):      #LLM生成步驟清單的規範
    step_name: str  
    #操作指令不先寫死，而是根據該步驟的名稱、擷取到的UI tree來生成


class Action(BaseModel):        #每次根據UI tree生成的操作指令
    """操作指令細節"""
    action_type: str            # "click" / "set_text" / "scroll" / "global_back"
    target_node_id: str         # 來自 UI Tree 的 node resource-id 或 bounds
    input_text: str | None      # 僅 set_text 時使用


class State(TypedDict):
    """狀態表，狀態機核心記憶體"""
    user_command: str | None                 # 使用者原始指令
    again_check: bool | None                 # 是否再詢問使用者一次的變數
    messages: Annotated[list, add_messages]  # 所有對話紀錄
    define_detail: bool | None               # 判斷是否有明確說明
    clarified_params: dict | None            # 補全的參數（詢問使用者或使用預設值後填入）
    #上面的變數為前置處理所需
    total_step: list[Step] | None            # LLM分析的步驟清單    
    current_step: int                        # 目前執行到第幾步
    current_ui_tree: dict | None             # 每步執行前讀入，步驟結束後可清除
    current_action: Action | None            # LLM 根據 UI Tree 生成，執行完後清除
    last_screenshot: bytes | None            # 最後一張螢幕截圖
    retry_count: int                         # 失敗重試次數
    is_success: bool | None                  # 當前步驟是否執行成功；成功為 True，失敗為 False 
    is_sensitive: bool | None                # 是否為敏感操作，是敏感操作時為True，否則為False
    sensitive_reason: str | None             # 該操作為敏感操作的原因
    is_confirmed: bool | None                # 使用者確認或取消，確認為True，否則為False
    #上面為主執行流程所需
    task_result: str | None                  # 任務結果
    error_reason: list[str]                  # 每次失敗原因，最多三筆
    next_round_hint: str | None              # 分析失敗後給下一輪生成操作指令的提示
    
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
        description="""Action類別裡包含action_type、
                    target_node_id、input_text，請生成對應的值"""
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

#-------------------------以下為所有節點之函式-------------------------

#缺少具體細節
async def check_requirements_completeness(state: State):
    """將使用者指令丟給LLM分析是否缺少具體細節，並將詢問訊息傳給APP"""

    user_response: dict = await manager.wait_for_user("first_messages")
    print(colorama.Fore.RED + f"**接收到使用者指令：{user_response['first_messages']}")
    original_command = user_response["first_messages"]

    check_llm = llm.with_structured_output(FormatOutput_check_requirements)     #讓LLM依照所定義格式輸出

    result = check_llm.invoke([
        {
            "role": "system",
            "content": """請將使用者的需求分析一遍，
                       並分析出使用者遺漏的細節，
                       將使用者未提到的所有細節彙總成一句話，
                       並詢問使用者。
                       """
        },
        {"role": "user", "content": original_command}
    ])
    
    if result.again_check:      #判斷是否需要再次詢問使用者，並決定下個節點
        await manager.send_ask_to_user(result.ask_for_user) 
        print(colorama.Fore.RED + f"**已傳送詢問訊息給前端：{result.ask_for_user}")   
        #如需要詢問則將 ask_for_user 加進 state，否則不加入
        return {
            "user_command": user_response["first_messages"],
            "again_check": result.again_check,
            "messages": [
                {"role": "user", "content": original_command},
                {"role": "assistant", "content": result.ask_for_user}
            ]
        }
    
    else:
        return {
            "user_command": user_response["first_messages"],
            "again_check": result.again_check,
            "messages": [
                {"role": "user", "content": original_command},
            ]
        }

#詢問使用者
async def ask_user_for_details(state: State):
    """呼叫LLM判斷使用者是否有說具體細節，還是說"你決定就好"等等的模糊指令，
    如有說明確細節則將使用者補充的細節轉換成dict格式，放進補全的參數"""

    user_response: dict = await manager.wait_for_user('detail_response')   #接收使用者回復的訊息
    print(colorama.Fore.RED + f"**已接收到具體細節訊息：{user_response['detail_response']}")

    ask_llm = llm.with_structured_output(FormatOutput_ask_user)
    result = ask_llm.invoke([       #對是否有明確說明做判斷，只輸出 True 或 False
        {
            "role": "system",
            "content": """請判斷使用者最後是否有對指令缺少的細節做出明確說明，
                    如果有明確說明，則輸出 True，
                    沒有明確說明的話則輸出 False
                    """
        },
        {
            "role": "user",
            "content": user_response["detail_response"]
        }
    ])

    detail_result = None

    if result.define_detail:    #如有明確說明，則將使用者補充的細節轉換成dict格式，放進clarified_params
        detail_change_dict_llm = llm.with_structured_output(FormatOutput_change_dict)
        detail_result_raw = detail_change_dict_llm.invoke([
            {
                "role": "system",
                "content": """請將使用者補充的細節轉換成dict格式。"""
            },
            {
                "role": "user", "content": user_response["detail_response"]
            }
        ])
        detail_result = json.loads(detail_result_raw.clarified_params_json)
    
    return{"define_detail": result.define_detail,
           "clarified_params": detail_result,
           "messages": [{"role": "user", "content": user_response["detail_response"]}]}

#使用預設值
async def apply_default_parameters(state: State):
    """使用者若沒說明確細節則進到此節點，請LLM生成預設的值填入補全參數"""
    print(colorama.Fore.RED + "**進入使用預設值節點")

    original_command = state["user_command"]

    detail_completeness_llm = llm.with_structured_output(FormatOutput_change_dict)
    result = detail_completeness_llm.invoke([   #預設值補全細節，並轉換成dict格式
        {
            "role": "system",
            "content": """請幫助使用者填入他沒說到的具體細節，
                       例如：使用者沒有說要哪個平台、冰量、甜度，
                       你就幫使用者補齊一些大部分人會選的選擇，

                       範例：
                       {
                            "外送平台": "Foodpanda",
                            "甜度": "少糖",
                            "冰量": "少冰"
                       }"""
        },
        {
            "role": "user",
            "content": original_command
        }
    ])

    return{"clarified_params": result.clarified_params_json}

#LLM分析指令回傳步驟清單
async def llm_analyze_command(state: State):
    """將使用者的原始指令、補全的參數丟給LLM分析，並生成一份步驟清單"""

    params: dict = state.get("clarified_params") or {} #填入補全的參數 

    step_list_llm = llm.with_structured_output(FormatOutput_analyze)
    result = step_list_llm.invoke([
        {
            "role": "system",
            "content": """你是一個Android裝置的行動助理，
                        你的任務是將使用者的需求拆解成「操作步驟清單」。

                        請根據：
                        1. 使用者的原始需求
                        2. 已補全的參數

                        生成完整且具體的操作流程。

                        輸出格式必須為：
                        [
                            {"step_name": "步驟1"},
                            {"step_name": "步驟2"}
                        ]

                        注意：
                        - 每個步驟要具體
                        - 要包含參數相關操作（例如甜度、冰量）
                        - 不要輸出多餘說明
                        """
        },
        {
            "role": "user",
            "content": f"""
                        【使用者需求】
                        {state['user_command']}

                        【補全參數】
                        {params}
                        """
        }
    ])
    print(colorama.Fore.RED + f"**步驟清單已生成：{result.total_step}")

    return {"total_step": result.total_step}

#通知APP任務開始
async def notify_task_start(state: State):
    """傳送開始訊息告訴APP端開始執行任務"""
    await manager.send_start_messages()
    print(colorama.Fore.RED + "**已送出任務開始訊息給前端")
    return{}

#讀取UI Tree
async def capture_ui_tree(state: State):
    """傳送訊息告訴APP讀取UI tree與截圖，並將收到的截圖與UI Tree放入state"""

    await manager.send_read_messages()
    print(colorama.Fore.RED + "**已送出讀取UI通知")

    #收到APP的UI Tree與截圖 -> 將收到的JSON轉為dict  
    user_response = await manager.wait_for_user('ui_screen_data')   #接收APP回傳
    print(colorama.Fore.RED + "**接收到 UI Tree 、 截圖")

    ui_tree: dict = user_response["ui_tree"]
    base64_str: str = user_response["screen_shot"]
    b64_clean = base64_str.split(",")[-1]           #去除base64前綴字串
    image_bytes = base64.b64decode(b64_clean)       #將base64字串轉成bytes
    
    return{"current_ui_tree": ui_tree,
           "last_screenshot": image_bytes}

#LLM生成操作指令
async def generate_action_commands(state: State):
    """將當前步驟的步驟名稱、UI Tree、截圖丟給LLM生成操作指令"""

    step_name: str = state["total_step"][state["current_step"]]["step_name"]
    ui_tree = state["current_ui_tree"]
    screenshot_bytes = state["last_screenshot"]

    #bytes轉base64
    b64_image = base64.b64encode(screenshot_bytes).decode("utf-8")
    action_command_llm = llm.with_structured_output(FormatOutput_action_command)

    failure_content = ""        #若前一步驟執行失敗則載入 失敗原因、下一輪提示
    if state["error_reason"] and state["is_success"] == False:
        failure_content = f"""
            上一次執行失敗：
            - 失敗原因：{state["error_reason"][-1]}
            - 注意事項：{state["next_round_hint"] or "無"}
            """
        print(colorama.Fore.RED + "**已載入失敗原因....")
        
    messages = [
        SystemMessage(content=      #系統訊息
            """   
            你是一個 Android UI 操作代理。

            你的任務是：
            - 根據目前的步驟名稱、提供的 UI Tree 與截圖
            - 輸出「唯一一個」操作指令(JSON格式)

            嚴格遵守格式：
            {
                "action_type": "click" | "set_text" | "scroll" | "global_back",
                "target_node_id": "<resource-id 或 bounds>",
                "input_text": "<僅 set_text 時填入，其餘為 null>"
            }
            禁止輸出任何額外說明。          
            """),
        HumanMessage(content=[      #人類訊息(放步驟名稱、截圖、UI Tree)
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{b64_image}"
                    }
            },
            {
                "type": "text",
                "text": f"""
                        目前要執行的步驟：{step_name}
                        {failure_content}
                        當前 UI Tree (JSON)：
                        {json.dumps(ui_tree, ensure_ascii=False, indent=2)}
                        """
            }
        ])
    ]
    response = action_command_llm.invoke(messages)
    print(colorama.Fore.RED + f"**已生成操作指令：{response.command}")

    return{"current_action": response.command}

#判斷是否是敏感操作
async def is_sensitive_action(state: State):
    current_action = state["current_action"]

    sensitive_llm = llm.with_structured_output(FormatOutput_sensitive_check)
    result = sensitive_llm.invoke([
        {
            "role": "system",
            "content": """你是一個Android操作安全檢查員，
                        請判斷操作指令是否屬於敏感操作。
                        敏感操作定義：付款、確認訂單、送出表單、輸入密碼、刪除資料等。
                        """
        },
        {
            "role": "user",
            "content": f"""
                        操作指令：
                        action_type: {current_action['action_type']}
                        target_node_id: {current_action['target_node_id']}
                        input_text: {current_action['input_text']}
                        """
        }
    ])
    print(colorama.Fore.RED + "**已判斷是否為敏感操作")
    print(colorama.Fore.RED + f"**是否為敏感操作：{result.is_sensitive}")
    print(colorama.Fore.RED + f"**敏感原因：{result.reason}")

    return {"is_sensitive": result.is_sensitive,
            "sensitive_reason": result.reason}

#停在該畫面、並通知使用者
async def notify_user(state: State):
    current_action = state["current_action"]
    sensitive_reason = state["sensitive_reason"]

    messages: str
    # 組成通知訊息
    if current_action["input_text"] == None:    #不為輸入操作時不帶入 input_text 欄位
        messages = f"""偵測到敏感操作，請確認：
                操作類型：{current_action['action_type']}
                目標元件：{current_action['target_node_id']}
                """
    else:
        messages = f"""偵測到敏感操作，請確認：
                操作類型：{current_action['action_type']}
                目標元件：{current_action['target_node_id']}
                輸入內容：{current_action['input_text']}
                """
    
    # 傳送通知給APP端（含截圖與訊息）
    await manager.send_action_check(messages, sensitive_reason)
    print(colorama.Fore.RED + "**已將敏感操作通知發給前端")
    return{}

#等待使用者確認/取消
async def wait_for_user_confirm(state: State):
    user_response = await manager.wait_for_user("sensitive_confirm")   # 等待APP回傳確認或取消
    print(colorama.Fore.RED + f"**已收到敏感操作確認：{user_response["request_response"]}")
    
    # 判斷使用者回傳的是確認還是取消
    is_confirmed = user_response["request_response"]   # True = 確認, False = 取消
    
    return {"is_confirmed": is_confirmed}

#發送操作指令
async def send_action_command(state: State):
    """將當前步驟指令傳送給前端APP"""
    #Python 端序列化成 JSON，APP 端解析執行
    action = state["current_action"]
    await manager.send_command(action)
    print(colorama.Fore.RED + "**已發送操作指令給前端")

    return{}

#手機截圖後回傳、並判斷成功與否
async def screenshot_for_result(state: State):
    """手機執行操作後截圖回傳，判斷該步驟是否執行成功"""

    system_response: dict = await manager.wait_for_user("operate_screen_shot")
    print(colorama.Fore.RED + "**收到操作後之畫面截圖")

    base64_str: str = system_response["operate_screen_shot"]
    b64_clean = base64_str.split(",")[-1]       #去除base64前綴字串
    image_bytes = base64.b64decode(b64_clean)
    b64_image = base64.b64encode(image_bytes).decode("utf-8")   #bytes轉base64

    current_step_name = state["total_step"][state["current_step"]]["step_name"]
    current_action: Action = state["current_action"]

    check_llm = llm.with_structured_output(FormatOutput_chack_action_success)
    messages = [
        SystemMessage(content=
            """
            你是一個 Android UI 操作代理。

            你剛執行完一個步驟
            - 請根據目前的螢幕截圖、執行時的步驟名稱、操作指令
            - 判斷剛才的步驟是否執行成功

            成功則輸出: True
            失敗則輸出: False
            """),
        HumanMessage(content=[
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{b64_image}"
                }
            },
            {
                "type": "text",
                "text": f"""
                        剛剛執行的步驟名稱：{current_step_name}
                        執行的操作指令：{current_action}
                        """
            }
        ])
    ]
    result = check_llm.invoke(messages)
    print(colorama.Fore.RED + f"**當前步驟執行結果：{result.is_success}")

    return{"is_success": result.is_success,
           "last_screenshot": image_bytes}
    
#分析失敗原因、提供解決方法
async def analyze_error_solution(state: State):
    """步驟執行失敗後進到此節點，判斷失敗原因並記錄到 state[error_reason]"""
    #將失敗原因帶入下一輪的"生成操作指令"節點，提示LLM上次的操作失敗了，不要用重複的指令
    #寫入 retry hint（給下一輪的提示，不是指令）
    #失敗原因供teardown使用
    print(colorama.Fore.RED + "**進入到錯誤分析節點")
    retry_count = state["retry_count"]
    retry_count += 1  #重試次數+1
    current_step = state["total_step"][state["current_step"]]["step_name"]
    current_action = state["current_action"]

    screen_shot = state["last_screenshot"]      #螢幕截圖
    b64_image = base64.b64encode(screen_shot).decode("utf-8")

    solution_llm = llm.with_structured_output(FormatOutput_error_reason)
    messages = [
        SystemMessage(content=
            """
            你是一個 Android UI 操作代理。

            剛剛執行一個操作時失敗了

            請你根據提供的步驟名稱、執行後的螢幕截圖、操作指令
            判斷操作的失敗原因，並提供一個提示告訴下一輪生成指令時要注意的地方
            """),
        HumanMessage(content=[
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{b64_image}"
                }
            },
            {
                "type": "text",
                "text": f"""
                        步驟名稱：{current_step}
                        執行的操作指令：{current_action}
                        """
            }
        ])
    ]
    result = solution_llm.invoke(messages)
    print(colorama.Fore.RED + f"**當前步驟失敗原因：{result.error_reason}")
    
    error_reason = state["error_reason"]
    error_reason.append(result.error_reason)    #將LLM分析的失敗原因新增至 state 的 error_reason

    return{"retry_count": retry_count,
           "error_reason": error_reason,
           "next_round_hint": result.next_round_hint}

#判斷任務是否執行完畢     是否需要此節點(待定)
async def task_is_completed(state: State):
    """判斷執行完的步驟是否是最後一個步驟，若為最後一個步驟則進到收尾工作"""
    step_count = state["current_step"]
    step_count += 1
    print(colorama.Fore.RED + "**步驟數已加 1")
    print(colorama.Fore.RED + f"**目前步驟數：{step_count}")

    return{"current_step": step_count}

#更新狀態機並執行下個步驟
async def update_state_and_next_action(state: State):
    """清空動態欄位，繼續下一步驟"""
    print(colorama.Fore.RED + "**已清空所有動態欄位")

    return{"current_ui_tree": None,
           "last_screenshot": None,
           "current_action": None,
           "is_sensitive": None,
           "sensitive_reason": None,
           "is_confirmed": None}

#收尾工作
async def teardown_process(state: State):
    """在APP顯示執行結果、失敗原因、過程log，通知APP關閉進程"""
    print(colorama.Fore.RED + "**已進入收尾工作")
    error_messages: list = state["error_reason"].copy()

    #判斷任務結果
    task_result: str
    if state["current_step"] == len(state["total_step"]):
        task_result = "任務成功"
    elif not state.get("is_confirmed"):      #使用者主動取消任務(待定)
        task_result = "任務已取消" 
    else:
        task_result = "任務失敗"

    #過程摘要
    task_process: str = f"""
        任務總步數：{len(state['total_step'])}
        成功執行的步數：{state['current_step']}
        失敗的次數：{state['retry_count']}
        """

    #失敗原因
    error_reason: str = ""
    if state["retry_count"] > 0:        #若有失敗過則載入失敗原因
        for i, message in enumerate(error_messages, start=1):
            error_reason += f"第{i}次失敗原因：{message}\n"

    manager.send_end_messages(task_result, task_process, error_reason)
    print(colorama.Fore.RED + "**已將任務結果、執行步數、失敗原因(若失敗)，傳給APP")

    return{"current_ui_tree": None,
           "last_screenshot": None,
           "current_action": None,
           "is_sensitive": None,
           "sensitive_reason": None,
           "is_confirmed": None,
           "next_round_hint": None,
           "task_result": task_result}


#-------------------------以下為狀態圖的建構-------------------------
graph_builder = StateGraph(State)

#下面四個為前置處理節點
graph_builder.add_node("check_requirements_completeness", check_requirements_completeness)
graph_builder.add_node("ask_user_for_details", ask_user_for_details)
graph_builder.add_node("apply_default_parameters", apply_default_parameters)
graph_builder.add_node("llm_analyze_command", llm_analyze_command)
graph_builder.add_node("notify_task_start", notify_task_start)
#下面為主流程節點
graph_builder.add_node("capture_ui_tree", capture_ui_tree)
graph_builder.add_node("generate_action_commands", generate_action_commands)
graph_builder.add_node("is_sensitive_action", is_sensitive_action)
graph_builder.add_node("notify_user", notify_user)
graph_builder.add_node("wait_for_user_confirm", wait_for_user_confirm)
graph_builder.add_node("send_action_command", send_action_command)
graph_builder.add_node("screenshot_for_result", screenshot_for_result)
graph_builder.add_node("analyze_error_solution", analyze_error_solution)
graph_builder.add_node("task_is_completed", task_is_completed)
graph_builder.add_node("update_state_and_next_action", update_state_and_next_action)
graph_builder.add_node("teardown_process", teardown_process)


#以下為邊的連接---------------
graph_builder.add_edge(START, "check_requirements_completeness")
graph_builder.add_conditional_edges(
    "check_requirements_completeness",      #從缺少具體細節發出條件邊
    lambda state: state.get("again_check"),
    {True: "ask_user_for_details", False: "llm_analyze_command"}
)
graph_builder.add_conditional_edges(
    "ask_user_for_details",
    lambda state: state.get("define_detail"),
    {True: "llm_analyze_command", False: "apply_default_parameters"}
)
graph_builder.add_edge("apply_default_parameters", "llm_analyze_command")
graph_builder.add_edge("llm_analyze_command", "notify_task_start")
graph_builder.add_edge("notify_task_start", "capture_ui_tree")
#以下為主流程邊的連接----------------------------------
graph_builder.add_edge("capture_ui_tree", "generate_action_commands")
graph_builder.add_edge("generate_action_commands", "is_sensitive_action")
graph_builder.add_conditional_edges(
    "is_sensitive_action",
    lambda state: state.get("is_sensitive"),
    {True: "notify_user", False: "send_action_command"}
)
graph_builder.add_edge("notify_user", "wait_for_user_confirm")
graph_builder.add_conditional_edges(
    "wait_for_user_confirm",
    lambda state: state.get("is_confirmed"),
    {True: "send_action_command", False: "teardown_process"}
)
graph_builder.add_edge("send_action_command", "screenshot_for_result")
graph_builder.add_conditional_edges(
    "screenshot_for_result",
    lambda state: state.get("is_success"),
    {True: "task_is_completed", False: "analyze_error_solution"}
)
graph_builder.add_conditional_edges(
    "analyze_error_solution",
    lambda state: (
        "retry < 3"
        if state["retry_count"] < 3
        else "retry > 3"
    ),
    {"retry < 3": "capture_ui_tree", 
     "retry > 3": "teardown_process"}
)
graph_builder.add_conditional_edges(
    "task_is_completed",
    lambda state: (
        "finish"
        if (state["current_step"] == len(state["total_step"]))
        else "unfinished"
    ),
    {"finish": "teardown_process",
     "unfinished": "update_state_and_next_action"}
)
graph_builder.add_edge("update_state_and_next_action", "capture_ui_tree")
graph_builder.add_edge("teardown_process", END)

graph = graph_builder.compile()

#----------------------啟動系統-----------------------------------

async def run_agent(manager: ConnectionManager):
    print(colorama.Fore.RED + "**  Agent代理 已啟動  **")
    initial_state = {    #設定初始值
        "user_command": None,
        "again_check": None,
        "messages": [],
        "define_detail": None,
        "clarified_params": None,
        "total_step": None,
        "current_step": 0,
        "current_ui_tree": None,
        "current_action": None,
        "last_screenshot": None,
        "retry_count": 0,
        "is_success": None,
        "is_sensitive": None,
        "sensitive_reason": None,
        "is_confirmed": None,
        "task_result": None,
        "error_reason": [],
        "next_round_hint": None
    }

    state = graph.ainvoke(initial_state)     #初始化狀態表


#----------------------以下為圖的繪製---------------------------
if __name__ == "__main__":
    try:
        png_data = graph.get_graph().draw_mermaid_png()
        with open("graph_AI.png", "wb") as f:
            f.write(png_data)
        print("已輸出 graph_AI.png")
    except Exception:
        pass
