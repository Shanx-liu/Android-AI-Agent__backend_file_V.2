from dotenv import load_dotenv
from typing import Annotated, Callable
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage, message_to_dict, BaseMessage
from typing_extensions import TypedDict
import os, base64, json, asyncio
from Connection_Manager import ConnectionManager, manager
from Action import *
from FormatOutput import *
from colorama import Fore, Style, init
import time
import functools, operator
from datetime import datetime
from pathlib import Path
from copy import deepcopy
from dataclasses import is_dataclass, asdict

#----------------------以下為流程紀錄---------------------------
def logged_node(node_name: str):        #裝飾器函式
    def decorator(func: Callable):
        @functools.wraps(func)
        async def async_wrapper(state: dict):
            start = time.monotonic()
            result = await func(state)
            duration_ms = round((time.monotonic() - start) * 1000, 1)   #紀錄步驟花費時間

            # 合併出「這個節點執行完當下」的完整 state 快照
            # （state 是這個節點執行前的內容，result 是它回傳要更新的欄位）
            snapshot = {**state, **result}
            snapshot.pop("execution_log", None)  # 避免快照裡巢狀塞自己，太肥
 
            entry = {
                "node": node_name,
                "timestamp": datetime.now().isoformat(),
                "duration_ms": duration_ms,
                "output": snapshot,
            }
            # 只回傳 execution_log 的「新增這一筆」，
            # operator.add 會自動幫你 append 到 State 原本的 list 後面
            result["execution_log"] = [entry]
            return result
 
        return async_wrapper
 
    return decorator
#----------------------------------------------------------------

init(autoreset=True)   #終端機字體顏色設定
load_dotenv()

llm = init_chat_model(      #初始化模型
    "gpt-5.4-mini",
    openai_api_key=os.getenv("OPENAI_API_KEY"),     #設定API_KEY
    max_retries=5
)

class State(TypedDict):
    """狀態表，狀態機核心記憶體"""
    user_command: str | None                 # 使用者原始指令
    again_check: bool | None                 # 是否再詢問使用者一次的變數
    messages: Annotated[list, add_messages]  # 所有對話紀錄
    define_detail: bool | None               # 判斷是否有明確說明
    clarified_params: dict | None            # 補全的參數（詢問使用者或使用預設值後填入）
    user_confirm_start: bool | None          # 使用者確認 開始/取消 任務
    #上面的變數為前置處理所需
    plan: list[PlanStep]                     # 取代 total_step  
    current_step_id: str | None              # 取代 current_step（用 ID 定位，不用 index）
    current_ui_tree: dict | None             # 每步執行前讀入，步驟結束後可清除
    current_action: Action | None            # LLM 根據 UI Tree 生成，執行完後清除
    last_ui_tree: dict | None                # 最後一張螢幕截圖
    retry_count: int                         # 失敗重試次數
    is_success: bool | None                  # 當前步驟是否執行成功；成功為 True，失敗為 False 
    is_sensitive: bool | None                # 是否為敏感操作，是敏感操作時為True，否則為False
    sensitive_reason: str | None             # 該操作為敏感操作的原因
    is_confirmed: bool | None                # 使用者確認或取消，確認為True，否則為False
    not_current_step: bool | None            # 若當前操作不為步驟清單內之步驟，則為 True，並且當前步驟不計入步驟數
    exception_step_name: str | None          # not_current_step 為 True 時生成的臨時步驟名稱
    needs_replan: bool | None                # generate_action_commands 判斷「這步寫錯/做不到」時填 True
    replan_reason: str | None                # 對應原因
    #上面為主執行流程所需
    task_result: str | None                  # 任務結果
    error_reason: list[str]                  # 每次失敗原因，最多三筆
    next_round_hint: str | None              # 分析失敗後給下一輪生成操作指令的提示
    history_summary: str                     # 壓縮後的歷程摘要，取代直接塞整個 execution_log
    execution_log: Annotated[list, operator.add]   # 每個節點執行完 append 一筆紀錄；沒宣告 reducer 的話這欄位不會被正確收集

    
#-------------------------以下為 plan 存取輔助函式-------------------------
def find_step(plan: list[PlanStep], step_id: str | None) -> PlanStep | None:
    """依 step_id 在 plan 裡找出對應的 PlanStep，找不到回傳 None"""
    if not step_id:
        return None
    for s in plan:
        if s["step_id"] == step_id:
            return s
    return None
 
def find_step_index(plan: list[PlanStep], step_id: str | None) -> int:
    """依 step_id 在 plan 裡找出 index，找不到回傳 -1"""
    if not step_id:
        return -1
    for i, s in enumerate(plan):
        if s["step_id"] == step_id:
            return i
    return 
 
def first_pending_step_id(plan: list[PlanStep]) -> str | None:
    """找出 plan 裡第一個狀態為 pending 的 step_id，代表下一步該做的事"""
    for s in plan:
        if s["status"] == "pending":
            return s["step_id"]
    return None
 
def get_current_step_name(state: State) -> str:
    """取得目前要顯示/紀錄用的步驟名稱：
    若目前是在處理彈窗等例外操作，用臨時步驟名稱；否則從 plan 裡查目前步驟"""
    if state.get("not_current_step") == True:
        return state.get("exception_step_name") or ""
    step = find_step(state["plan"], state["current_step_id"])
    return step["step_name"] if step else ""
 
#-------------------------以下為所有節點之函式-------------------------

#缺少具體細節
@logged_node("缺少具體細節")    #裝飾器
async def check_requirements_completeness(state: State):
    """將使用者指令丟給LLM分析是否缺少具體細節，並將詢問訊息傳給APP"""

    user_response: dict = await manager.wait_for_user("first_messages")
    print(Fore.RED + Style.BRIGHT + f"**接收到使用者指令：{user_response['first_messages']}")
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
        print(Fore.RED + Style.BRIGHT + f"**已傳送詢問訊息給前端：{result.ask_for_user}")   
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
@logged_node("詢問使用者")
async def ask_user_for_details(state: State):
    """呼叫LLM判斷使用者是否有說具體細節，還是說"你決定就好"等等的模糊指令，
    如有說明確細節則將使用者補充的細節轉換成dict格式，放進補全的參數"""

    user_response: dict = await manager.wait_for_user('detail_response')   #接收使用者回復的訊息
    print(Fore.RED + Style.BRIGHT + f"**已接收到具體細節訊息：{user_response['detail_response']}")

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
@logged_node("使用預設值")
async def apply_default_parameters(state: State):
    """使用者若沒說明確細節則進到此節點，請LLM生成預設的值填入補全參數"""
    print(Fore.RED + Style.BRIGHT + "**進入使用預設值節點")

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
@logged_node("LLM分析指令回傳步驟清單")
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

                        **步驟粒度必須精細到能用單一指令操作的程度**
                        - 例如要在搜尋欄輸入文字時，可以拆解成先點擊搜尋框取得焦點，再輸入文字
                        
                        輸出格式必須為一個 PlanStep 的 list：
                        [
                            {"step_id": "s1", "step_name": "步驟1", "status": "pending", "note": null},
                            {"step_id": "s2", "step_name": "步驟2", "status": "pending", "note": null}
                        ]

                        規則：
                        - step_id 依序命名為 s1、s2、s3...（之後執行過程中若需要插入新步驟，
                          會接續使用更大的編號，所以這裡照順序從 s1 開始即可）
                        - status 一律初始化為 "pending"
                        - note 一律初始化為 null

                        注意：
                        - 每個步驟要具體
                        - 要包含操作相關參數（例如甜度、冰量）
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
    print(Fore.RED + Style.BRIGHT + f"**步驟清單已生成：{result.total_step}")

    first_step_id = result.total_step[0]["step_id"] if result.total_step else None

    return {"plan": result.total_step,
            "current_step_id": first_step_id}

#通知APP任務開始
@logged_node("通知APP任務開始")
async def notify_task_start(state: State):
    """傳送開始訊息告訴APP端開始執行任務"""
    await manager.send_start_messages()
    print(Fore.RED + Style.BRIGHT + "**已送出任務開始訊息給前端")

    user_response: dict = await manager.wait_for_user('user_confirm_start')
    print(Fore.RED + Style.BRIGHT + f"**接收到使用者確認/取消：{user_response['user_confirm']}")

    return{"user_confirm_start": user_response["user_confirm"]}

#讀取UI Tree
@logged_node("讀取UI Tree")
async def capture_ui_tree(state: State):
    """傳送訊息告訴APP讀取UI tree與截圖，並將收到的截圖與UI Tree放入state"""

    time.sleep(3)
    await manager.send_read_messages()
    print(Fore.RED + Style.BRIGHT + "**已送出讀取UI通知")

    #收到APP的UI Tree與截圖 -> 將收到的JSON轉為dict  
    user_response: dict = await manager.wait_for_user('ui_screen_data')   #接收APP回傳
    print(Fore.RED + Style.BRIGHT + "**接收到 UI Tree")

    ui_tree: dict = user_response["ui_tree"]
    
    return{"current_ui_tree": ui_tree}

#LLM生成操作指令
@logged_node("LLM生成操作指令")
async def generate_action_commands(state: State):
    """將當前步驟的步驟名稱、UI Tree、截圖丟給LLM生成操作指令"""

    user_command: str = state["user_command"]   
    plan: list[PlanStep] = state["plan"]
    current_step = find_step(plan, state["current_step_id"])
    step_name: str = current_step["step_name"]
    remaining_steps = [s["step_name"] for s in plan if s["status"] == "pending"]
    ui_tree = state["current_ui_tree"]
    params: dict = state["clarified_params"] or {}
    
    action_command_llm = llm.with_structured_output(FormatOutput_action_command)

    failure_content = ""        #若前一步驟執行失敗則載入 失敗原因、下一輪提示
    if state["error_reason"] and state["is_success"] == False:
        failure_content = f"""
            上一次執行失敗：
            - 失敗原因：{state["error_reason"][-1]}
            - 注意事項：{state["next_round_hint"] or "無"}
            """
        print(Fore.RED + Style.BRIGHT + "**已載入失敗原因....")
        
    messages = [
        SystemMessage(content=      #系統訊息
            """
            你是一個 Android UI 操作代理。

            你的任務是：
            - 根據目前的步驟名稱、提供的 UI Tree
            - 輸出「唯一一個」操作指令(JSON格式)

            **情況一：畫面上有東西暫時擋住操作**
            - 例如：須關閉廣告視窗、有其他阻擋畫面的彈窗
            - 則以關閉這些彈窗生成操作指令
            - 並且不將這次操作算進步驟數，並將 not_current_step 填入 True
            - 並且根據要執行的動作生成臨時的步驟名稱，填入 exception_step_name
            - needs_replan 填 False

            **情況二：目前步驟本身無法達成**
            - 例如：步驟要求選「中餐」，但畫面上根本沒有「中餐」這個選項，
              只有「台式、飲料、麵食」等其他選項；或步驟描述的元件在畫面上完全找不到
            - 這種情況「不要」勉強套用畫面上其他元件硬點，也不要編造 bounds 座標交差
            - 請將 needs_replan 填入 True，並在 replan_reason 簡短說明原因
              （這一步之後會交給重新規劃流程處理，不會真的被執行）
            - command 欄位仍需給一個形式完整的值（可以是目前最接近的猜測），
              但重點在 needs_replan 與 replan_reason

            以上兩種情況只會符合一種，不會同時成立。若步驟可以正常執行，
            not_current_step 與 needs_replan 皆填 False。

            目標節點識別規則（依序判斷）：
            1. resource_id 有值且在當前畫面唯一 → 填 resource_id
            2. resource_id 為通用值（如 "icon"）或重複 → 改填 content_description
            3. 不管前面兩者是否有填入，都要填 bounds 座標

            嚴格遵守格式：
            {
                "action_type": "click" | "set_text" | "scroll" | "global_back",
                "full_resource_id": 完整的 ViewId,
                "resource_id": "Node 的 resourceID",
                "content_description": "如有多個resourceID重複時填入",
                "hint_text": 節點的 hint,
                "text": 節點的 text,
                "bounds: BoundsXY": "resource_ID不存在時填入",
                "input_text": "<僅 set_text 時填入，其餘為 null>",
                "scroll_direction": "僅 scroll 時使用: "up"/"down"/"left"/"right"
            }
            禁止輸出任何額外說明。          
            """),
        HumanMessage(content=[      #人類訊息(放步驟名稱、UI Tree)
            {
                "type": "text",
                "text": f"""
                        使用者原始需求：{user_command}
                        補全參數：{params}
                        目前要執行的步驟：{step_name}
                        計畫中尚未完成的其他步驟：{remaining_steps}
                        {failure_content}
                        當前 UI Tree (JSON)：
                        {json.dumps(ui_tree, ensure_ascii=False, indent=2)}
                        """
            }
        ])
    ]
    response = action_command_llm.invoke(messages)
    print(Fore.RED + Style.BRIGHT + f"**已生成操作指令：{response.command}")
    if response.needs_replan:
        print(Fore.YELLOW + Style.BRIGHT + f"**此步驟需要重新規劃，原因：{response.replan_reason}")

    return{"current_action": response.command,
           "not_current_step": response.not_current_step,
           "exception_step_name": response.exception_step_name,
           "needs_replan": response.needs_replan,
           "replan_reason": response.replan_reason}
    
#重新規劃步驟描述節點
@logged_node("重新規劃步驟描述")
async def replan_step_name(state: State):
    #這步失敗的原因」「原始需求/參數」「plan 其餘內容」丟給 LLM，讓它回傳一個修改指令
    print(Fore.RED + Style.BRIGHT + f"**已進入重新規劃步驟節點")

    step_id = state["current_step_id"]
    plan: list[PlanStep] = [dict(s) for s in state["plan"]]   #複製一份，避免直接改到舊的 reference
    target_index = find_step_index(plan, step_id)
    target_step = plan[target_index] if target_index != -1 else None
    replan_reason = state["replan_reason"]
    user_command = state["user_command"]
    clarified_params = state.get("clarified_params") or {}
    ui_tree = state.get("current_ui_tree")    #一定要給實際畫面，否則只能盲寫、寫出模糊的條件句

    print(Fore.RED + Style.BRIGHT + f"**須重規劃的步驟 {target_step}")

    replan_llm = llm.with_structured_output(FormatOutput_replan)
    result = replan_llm.invoke([
        {
            "role": "system",
            "content": """請你根據使用者的原始需求、補全的參數、需要重新規畫的原因、
                       plan的其餘內容、以及「目前畫面實際的 UI Tree」，
                       來重新規畫需要的步驟描述。

                       請優先選擇 replace（換一個更符合畫面現況、但仍能達成使用者目標的描述），
                       只有在必須「多做一步」或「這步根本不需要」時，才用 insert_before / insert_after / skip。

                       重要規則（違反這些規則會導致下一輪執行卡住）：
                       - new_step_name 必須是「當下這一步，根據目前 UI Tree 就能立刻執行的單一具體動作」，
                         例如：「點擊畫面上的『事件』選項」、「點擊標題輸入框」
                       - 絕對不要寫成條件句、多分支、或「若...就...，若沒有就...」這種涵蓋多種情境的描述，
                         這種寫法只是在延後決策，會讓下一輪的 LLM 更難判斷該做什麼、導致重複失敗
                       - 你只需要根據目前這張畫面決定「現在」要點什麼、輸入什麼，
                         不用預先規劃畫面切換後的步驟——那是之後每一輪重新讀取 UI Tree 後才需要決定的事
                       - 如果目前的 UI Tree 顯示的其實是更早的中間頁面（例如還在選單、還沒進到表單），
                         new_step_name 就只描述「這一頁該點的下一個東西」就好，不用一次規劃到最終目標
                       """
        },
        {
            "role": "user",
            "content": f"""
                        需重新規畫的步驟：{target_step}
                        使用者原始需求：{user_command}
                        補全的參數：{clarified_params}
                        需重新規畫的原因：{replan_reason}
                        plan的其餘內容：{plan}

                        目前畫面實際的 UI Tree（請以此為準，判斷現在畫面上實際有什麼）：
                        {json.dumps(ui_tree, ensure_ascii=False, indent=2)}
                        """
        }
    ])
    print(Fore.RED + Style.BRIGHT + f"**重新規劃結果：{result}")

    #依 LLM 的決定產生新的 step_id，避免跟現有步驟撞名
    existing_ids = {int(s["step_id"][1:]) for s in plan if s["step_id"][1:].isdigit()}
    next_num = (max(existing_ids) + 1) if existing_ids else (len(plan) + 1)
    def new_step_id() -> str:
        nonlocal next_num
        sid = f"s{next_num}"
        next_num += 1
        return sid

    idx = find_step_index(plan, result.target_step_id)
    if idx == -1:      #保底：LLM 回傳的 id 對不上時，退回原本要重規劃的那一步
        idx = target_index if target_index != -1 else 0

    next_step_id = step_id     #預設維持原本要執行的那一步

    if result.action == "replace":
        plan[idx] = {**plan[idx],
                     "step_name": result.new_step_name or plan[idx]["step_name"],
                     "note": result.reason}

    elif result.action == "skip":
        plan[idx] = {**plan[idx], "status": "skipped", "note": result.reason}
        if plan[idx]["step_id"] == step_id:      #被跳過的正是目前這步，往下找下一個待辦
            next_step_id = first_pending_step_id(plan)

    elif result.action == "insert_before":
        inserted: PlanStep = {"step_id": new_step_id(), "step_name": result.new_step_name,
                               "status": "pending", "note": result.reason}
        plan.insert(idx, inserted)
        next_step_id = inserted["step_id"]      #新插入的步驟變成接下來要做的事

    elif result.action == "insert_after":
        inserted: PlanStep = {"step_id": new_step_id(), "step_name": result.new_step_name,
                               "status": "pending", "note": result.reason}
        plan.insert(idx + 1, inserted)
        #原步驟仍在原位，next_step_id 維持不變

    return {"plan": plan,
            "current_step_id": next_step_id,
            "needs_replan": None,
            "replan_reason": None}

#判斷是否是敏感操作
@logged_node("判斷是否是敏感操作")
async def is_sensitive_action(state: State):
    current_action = state["current_action"]
    current_step_name = get_current_step_name(state)

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
                        current_step_name: {current_step_name}
                        action_type: {current_action.action_type}
                        resource_id: {current_action.resource_id}
                        content_description: {current_action.content_description}
                        input_text: {current_action.input_text}
                        """
        }
    ])
    print(Fore.RED + Style.BRIGHT + "**已判斷是否為敏感操作")
    print(Fore.YELLOW + Style.BRIGHT + f"**是否為敏感操作：{result.is_sensitive}")
    print(Fore.YELLOW + Style.BRIGHT + f"**原因：{result.reason}")

    return {"is_sensitive": result.is_sensitive,
            "sensitive_reason": result.reason}

#停在該畫面、並通知使用者
@logged_node("通知使用者")
async def notify_user(state: State):
    current_action = state["current_action"]
    sensitive_reason = state["sensitive_reason"]
    current_step_name = get_current_step_name(state)

    messages: str
    # 組成通知訊息
    if current_action.input_text == None:    #不為輸入操作時不帶入 input_text 欄位
        messages = f"""偵測到敏感操作，請確認：
                要執行的動作名稱：{current_step_name}
                操作類型：{current_action.action_type}
                """
    else:
        messages = f"""偵測到敏感操作，請確認：
                要執行的動作名稱：{current_step_name}
                操作類型：{current_action.action_type}
                輸入內容：{current_action.input_text}
                """
    
    # 傳送通知給APP端（含截圖與訊息）
    await manager.send_action_check(messages, sensitive_reason)
    print(Fore.RED + Style.BRIGHT + "**已將敏感操作通知發給前端")
    return{}

#等待使用者確認/取消
@logged_node("等待使用者確認/取消")
async def wait_for_user_confirm(state: State):
    user_response: dict = await manager.wait_for_user("sensitive_confirm")   # 等待APP回傳確認或取消
    print(Fore.RED + Style.BRIGHT + f"**已收到敏感操作確認：{user_response['request_response']}")

    # 判斷使用者回傳的是確認還是取消
    is_confirmed = user_response["request_response"]   # True = 確認, False = 取消
    
    return {"is_confirmed": is_confirmed}

#發送操作指令
@logged_node("發送操作指令")
async def send_action_command(state: State):
    """將當前步驟指令傳送給前端APP"""
    action = state["current_action"]
    await manager.send_command(action)
    print(Fore.RED + Style.BRIGHT + "**已發送操作指令給前端")

    return{}

#手機截圖後回傳、並判斷成功與否
@logged_node("判斷成功與否")
async def screenshot_for_result(state: State):
    """手機執行操作後截圖回傳，判斷該步驟是否執行成功"""
    print(Fore.RED + Style.BRIGHT + f"進入接收 UI Tree判斷是否成功節點")

    system_response: dict = await manager.wait_for_user("ui_screen_data")
    print(Fore.RED + Style.BRIGHT + "**收到操作後之 UI Tree")

    ui_tree: dict = state["current_ui_tree"]            #操作前的 UI Tree
    last_ui_tree: dict = system_response["ui_tree"]     #操作後回傳的UI Tree
    current_action: Action = state["current_action"]
    current_step_name = get_current_step_name(state)

    check_llm = llm.with_structured_output(FormatOutput_chack_action_success)
    messages = [
        SystemMessage(content=
            """
            你是一個 Android UI 操作代理。

            你剛執行完一個步驟
            - 請根據執行前的UI Tree、執行後的UI Tree、執行時的步驟名稱、操作指令
            - 判斷剛才的步驟是否執行成功

            成功則輸出: True
            失敗則輸出: False
            """),
        HumanMessage(content=[
            {
                "type": "text",
                "text": f"""
                        剛剛執行的步驟名稱：{current_step_name}
                        執行的操作指令：{current_action}
                        執行前的 UI Tree：{ui_tree}
                        執行後的 UI Tree：{last_ui_tree}
                        """
            }
        ])
    ]
    result = check_llm.invoke(messages)
    print(Fore.RED + Style.BRIGHT + f"**當前步驟執行結果：{result.is_success}")

    return{"is_success": result.is_success,
           "last_ui_tree": last_ui_tree}
    
#分析失敗原因、提供解決方法
@logged_node("分析失敗原因、提供解決方法")
async def analyze_error_solution(state: State):
    """步驟執行失敗後進到此節點，判斷失敗原因並記錄到 state[error_reason]"""
    #將失敗原因帶入下一輪的"生成操作指令"節點，提示LLM上次的操作失敗了，不要用重複的指令
    #寫入 retry hint（給下一輪的提示，不是指令）
    #失敗原因供teardown使用
    print(Fore.RED + Style.BRIGHT + "**進入到錯誤分析節點")
    retry_count = state["retry_count"]
    retry_count += 1  #重試次數+1
    current_step_name = get_current_step_name(state)

    ui_tree: dict = state["current_ui_tree"]
    current_action = state["current_action"]
    last_ui_tree: dict = state["last_ui_tree"]

    solution_llm = llm.with_structured_output(FormatOutput_error_reason)
    messages = [
        SystemMessage(content=
            """
            你是一個 Android UI 操作代理。

            剛剛執行一個操作時失敗了

            請你根據提供的步驟名稱、執行後的UI Tree、操作指令
            判斷操作的失敗原因，並提供一個提示告訴下一輪生成指令時要注意的地方
            """),
        HumanMessage(content=[ 
            {
                "type": "text",
                "text": f"""
                        步驟名稱：{current_step_name}
                        執行的操作指令：{current_action}
                        執行前的 UI Tree：{ui_tree}
                        執行後的 UI Tree：{last_ui_tree}
                        """
            }
        ])
    ]
    result = solution_llm.invoke(messages)
    print(Fore.RED + Style.BRIGHT + f"**當前步驟失敗原因：{result.error_reason}")
    
    error_reason = state["error_reason"]
    error_reason.append(result.error_reason)    #將LLM分析的失敗原因新增至 state 的 error_reason

    return{"retry_count": retry_count,
           "error_reason": error_reason,
           "next_round_hint": result.next_round_hint,
           "replan_reason": f"連續執行失敗：{result.error_reason}"}

#判斷任務是否執行完畢     是否需要此節點(待定)
@logged_node("判斷任務是否執行完畢")
async def task_is_completed(state: State):
    """判斷執行完的步驟是否是最後一個步驟，若為最後一個步驟則進到收尾工作"""
    if state["not_current_step"] == True:   #若當前操作不在步驟清單內，則不影響 plan 進度
        print(Fore.GREEN + Style.BRIGHT + "**此步驟為額外步驟，故不標記 plan 進度")
        return{}
    else:
        plan: list[PlanStep] = [dict(s) for s in state["plan"]]
        idx = find_step_index(plan, state["current_step_id"])
        if idx != -1:
            plan[idx] = {**plan[idx], "status": "done"}
        done_count = sum(1 for s in plan if s["status"] != "pending")
        print(Fore.RED + Style.BRIGHT + f"**目前已完成/處理步驟數：{done_count} / {len(plan)}")
        return{"plan": plan}

#更新狀態機並執行下個步驟
@logged_node("更新狀態機並執行下個步驟")
async def update_state_and_next_action(state: State):
    """清空動態欄位，並將 current_step_id 指到 plan 裡下一個 pending 的步驟"""
    print(Fore.RED + Style.BRIGHT + "**已清空所有動態欄位")

    next_step_id = first_pending_step_id(state["plan"])

    return{"current_ui_tree": None,
           "last_ui_tree": None,
           "current_action": None,
           "is_sensitive": None,
           "sensitive_reason": None,
           "is_confirmed": None,
           "not_current_step": None,
           "exception_step_name": None,
           "needs_replan": None,
           "replan_reason": None,
           "current_step_id": next_step_id,
           "retry_count": 0}    #換下一個步驟了，重試次數歸零，不要沿用上一步殘留的次數

#收尾工作
@logged_node("收尾工作")
async def teardown_process(state: State):
    """在APP顯示執行結果、失敗原因、過程log，通知APP關閉進程"""
    print(Fore.RED + Style.BRIGHT + "**已進入收尾工作")
    
    if state["user_confirm_start"] == False:    #當使用者自行取消時觸發這段
        print(Fore.RED + Style.BRIGHT + "**使用者自行取消任務**")
        await manager.send_user_cancel_messages("您已取消任務！")

    error_messages: list = state["error_reason"].copy()
    plan: list[PlanStep] = state.get("plan") or []
    done_count = sum(1 for s in plan if s["status"] == "done")
    handled_count = sum(1 for s in plan if s["status"] != "pending")   #done 或 skipped 都算已處理

    #判斷任務結果
    task_result: str
    if plan and handled_count == len(plan):
        task_result = "任務成功"
    elif not state.get("is_confirmed"):      #使用者主動取消任務(待定)
        task_result = "任務已取消" 
    else:
        task_result = "任務失敗"

    #過程摘要
    task_process: str = f"""
        任務總步數：{len(plan)}
        成功執行的步數：{done_count}
        失敗的次數：{state['retry_count']}
        """

    #失敗原因
    error_reason: str = ""
    if state["retry_count"] > 0:        #若有失敗過則載入失敗原因
        for i, message in enumerate(error_messages, start=1):
            error_reason += f"第{i}次失敗原因：{message}\n"

    await manager.send_end_messages(task_result, task_process, error_reason)
    print(Fore.RED + Style.BRIGHT + "**已將任務結果、執行步數、失敗原因(若失敗)，傳給APP")

    final_updates = {
        "current_ui_tree": None,
        "last_ui_tree": None,
        "current_action": None,
        "is_sensitive": None,
        "sensitive_reason": None,
        "is_confirmed": None,
        "next_round_hint": None,
        "not_current_step": None,
        "exception_step_name": None,
        "needs_replan": None,
        "replan_reason": None,
        "task_result": task_result,
    }

    #匯出 Log Json 檔時要用「合併過 task_result 等欄位之後」的完整 state，
    #否則 export 用的還是這個節點被呼叫當下、尚未寫入 task_result 的舊 state，log 裡永遠會是 None
    export_task_json({**state, **final_updates})

    return final_updates


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
graph_builder.add_node("replan_step_name", replan_step_name)
graph_builder.add_node("is_sensitive_action", is_sensitive_action)
graph_builder.add_node("notify_user", notify_user)
graph_builder.add_node("wait_for_user_confirm", wait_for_user_confirm)
graph_builder.add_node("send_action_command", send_action_command)
graph_builder.add_node("screenshot_for_result", screenshot_for_result)
graph_builder.add_node("analyze_error_solution", analyze_error_solution)
graph_builder.add_node("task_is_completed", task_is_completed)
graph_builder.add_node("update_state_and_next_action", update_state_and_next_action)
graph_builder.add_node("teardown_process", teardown_process)


#以下為任務初始化邊的連接---------------
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
graph_builder.add_conditional_edges(
    "notify_task_start",
    lambda state: state.get("user_confirm_start"),
    {True: "capture_ui_tree", False: "teardown_process"}
)
#git commit -m "加入記錄每一步Log的功能，新增replan節點在'生成操作指令'之後，'判斷敏感操作之前'若'生成操作指令'節點判斷需要重新規劃步驟則進到replan節點，replan完後再次進入'生成操作指令'節點" 
#以下為主流程邊的連接----------------------------------
graph_builder.add_edge("capture_ui_tree", "generate_action_commands")
graph_builder.add_conditional_edges(
    "generate_action_commands",
    lambda state: state.get("needs_replan"),
    {True: "replan_step_name", False: "is_sensitive_action"}
)
graph_builder.add_edge("replan_step_name", "generate_action_commands")   #計畫改完，畫面沒變，不必重新截圖
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
        "give_up" if state["retry_count"] >= 4          #同一步驟已失敗夠多次，放棄
        else "force_replan" if state["retry_count"] >= 2  #連續失敗2次，強迫換個做法而不是重試一樣的指令
        else "retry"
    ),
    {"retry": "capture_ui_tree",
     "force_replan": "replan_step_name",
     "give_up": "teardown_process"}
)
graph_builder.add_conditional_edges(
    "task_is_completed",
    lambda state: (
        "finish"
        if all(s["status"] != "pending" for s in state["plan"])
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
    print(Fore.RED + Style.BRIGHT + "**  Agent代理 已啟動  **")
    initial_state = {    #設定初始值
        "user_command": None,
        "again_check": None,
        "messages": [],
        "define_detail": None,
        "clarified_params": None,
        "user_confirm_start": None,
        "plan": [],
        "current_step_id": None,
        "current_ui_tree": None,
        "current_action": None,
        "last_ui_tree": None,
        "retry_count": 0,
        "is_success": None,
        "is_sensitive": None,
        "sensitive_reason": None,
        "is_confirmed": None,
        "not_current_step": None,
        "exception_step_name": None,
        "needs_replan": None,
        "replan_reason": None,
        "task_result": None,
        "error_reason": [],
        "next_round_hint": None,
        "history_summary": "",
        "execution_log": []
    }

    state = await graph.ainvoke(initial_state)     #初始化狀態表


#----------------------以下為圖的繪製---------------------------
if __name__ == "__main__":
    """直接執行主程式時"""
    try:
        png_data = graph.get_graph().draw_mermaid_png()
        with open("graph_AI.png", "wb") as f:
            f.write(png_data)
        print("已輸出 graph_AI.png")
    except Exception:
        pass


#----------------------以下為匯出流程紀錄Json檔---------------------------
def export_task_json(final_state: dict, filename: str | None = "agent_log.json") -> Path:
    """
    final_state: teardown 節點拿到的完整 state（含 execution_log）
    filename: 輸出的 .json 路徑，例如 "my_agent_log".json"
    """
    state = deepcopy(final_state)

    # messages 轉換
    """
    if "messages" in state:
        state["messages"] = [
            message_to_dict(m) if hasattr(m, "type") else m
            for m in state["messages"]
        ]
    """
    
    payload = {
        "exported_at": datetime.now().isoformat(),
        "task_result": final_state.get("task_result"),
        "step_count": len(final_state.get("execution_log", [])),
        "final_state": make_jsonable(final_state) 
    }
 
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
 
    return filename

#----------------------以下為自訂Json縮排格式---------------------------
def _hanging_indent_json(obj, col: int = 0) -> str:
    if isinstance(obj, dict):
        if not obj:
            return "{}"
        inner_col = col + 1  # 對齊到 "{" 後面那一格
        parts = []
        for key, value in obj.items():
            key_str = json.dumps(key, ensure_ascii=False)
            value_str = _hanging_indent_json(value, inner_col + len(key_str) + 2)
            parts.append(f"{key_str}: {value_str}")
        sep = ",\n" + " " * inner_col
        return "{" + sep.join(parts) + "}"
 
    if isinstance(obj, list):
        if not obj:
            return "[]"
        inner_col = col + 1  # 對齊到 "[" 後面那一格
        parts = [_hanging_indent_json(item, inner_col) for item in obj]
        sep = ",\n" + " " * inner_col
        return "[" + sep.join(parts) + "]"
 
    return json.dumps(obj, ensure_ascii=False)
 #--------------------------------------------------------------------
def make_jsonable(obj):
    #LangChain Message
    if isinstance(obj, BaseMessage):
        return message_to_dict(obj)

    #pydantic BaseModel (Action、BoundsXY)
    if isinstance(obj, BaseModel):
        return make_jsonable(obj.model_dump())

    # dataclass
    if is_dataclass(obj):
        return make_jsonable(asdict(obj))

    #dict
    if isinstance(obj, dict):
        return {k: make_jsonable(v) for k, v in obj.items()}

    #list / tuple
    if isinstance(obj, list):
        return [make_jsonable(v) for v in obj]

    return obj
