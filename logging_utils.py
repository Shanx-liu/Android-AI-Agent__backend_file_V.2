"""
這個檔案集中放「跟記錄/除錯有關」但不是核心流程邏輯的東西，原本這些散在
LangGraph_Core.py 裡：
    1. logged_node          裝飾器，記錄每個節點執行了多久、輸出了什麼 state
    2. export_task_json     任務結束時把完整 state 寫成 json 檔
    3. make_jsonable        把 state 裡各種非原生型別（pydantic model、dataclass、
                             LangChain Message）轉成可以 json.dump 的東西
    4. enable_terminal_capture  把終端機的所有輸出（print、traceback...）同時
                             另存一份成純文字檔

原本還有一個 _hanging_indent_json 函式，檢查過後發現定義了但完全沒被呼叫，
是死程式碼，這次順便拿掉了。

覺得節點執行紀錄(execution_log / agent_log.json)沒什麼用的話，
把最下面的 ENABLE_EXECUTION_LOG 改成 False 就好，不用回去改
LangGraph_Core.py 裡每一個 @logged_node(...) 的地方。
"""

from typing import Callable
import functools
import json
import sys
import re
import time
from datetime import datetime
from pathlib import Path
from copy import deepcopy

from langchain_core.messages import BaseMessage, message_to_dict
from pydantic import BaseModel
from dataclasses import is_dataclass, asdict


# =========================================================================
# 開關：關掉之後 logged_node 直接回傳原函式（沒有任何額外行為），
# export_task_json 也不會真的寫檔，等於整個節點執行紀錄功能被關閉，
# 但程式碼跟每個節點上面的 @logged_node("...") 都不用動
# =========================================================================
ENABLE_EXECUTION_LOG = False


# ----------------------------- 節點執行紀錄 -----------------------------
def logged_node(node_name: str):
    """裝飾器：記錄節點執行時間與執行完當下的 state 快照，累積進 execution_log"""

    def decorator(func: Callable):

        if not ENABLE_EXECUTION_LOG:
            # 關閉時直接回傳原函式，等於沒有包裝，沒有任何額外開銷
            return func

        @functools.wraps(func)
        async def async_wrapper(state: dict):
            start = time.monotonic()
            result = await func(state)
            duration_ms = round((time.monotonic() - start) * 1000, 1)

            # 合併出「這個節點執行完當下」的完整 state 快照
            snapshot = {**state, **result}
            snapshot.pop("execution_log", None)  # 避免快照裡巢狀塞自己，太肥

            entry = {
                "node": node_name,
                "timestamp": datetime.now().isoformat(),
                "duration_ms": duration_ms,
                "output": snapshot,
            }
            result["execution_log"] = [entry]
            return result

        return async_wrapper

    return decorator


def make_jsonable(obj):
    """把 state 裡各種非原生型別轉成可以直接 json.dump 的東西"""

    if isinstance(obj, BaseMessage):
        return message_to_dict(obj)

    if isinstance(obj, BaseModel):
        return make_jsonable(obj.model_dump())

    if is_dataclass(obj):
        return make_jsonable(asdict(obj))

    if isinstance(obj, dict):
        return {k: make_jsonable(v) for k, v in obj.items()}

    if isinstance(obj, list):
        return [make_jsonable(v) for v in obj]

    return obj


def export_task_json(final_state: dict, filename: str | None = "agent_log.json") -> Path | None:
    """
    任務結束時把完整 state 寫成 json 檔。
    final_state: teardown 節點拿到的完整 state（含 execution_log）
    filename: 輸出的 .json 路徑
    """
    if not ENABLE_EXECUTION_LOG:
        return None

    state = deepcopy(final_state)  # noqa: F841  保留變數方便未來需要對 state 做處理時使用

    payload = {
        "exported_at": datetime.now().isoformat(),
        "task_result": final_state.get("task_result"),
        "step_count": len(final_state.get("execution_log", [])),
        "final_state": make_jsonable(final_state),
    }

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return Path(filename)


# ----------------------------- 終端機輸出擷取 -----------------------------
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")  # 用來把 colorama 的顏色碼從 log 檔內容中拿掉

_terminal_log_file = None  # 目前開啟中的 log 檔 handle，用來避免重複啟用/正確關閉


class _TeeStream:
    """把寫進來的內容同時輸出到「原本的 stream」（畫面上，保留顏色）
    跟「一個純文字檔」（去除 ANSI 顏色碼，方便之後開檔案看/搜尋）"""

    def __init__(self, original_stream, log_file):
        self._original = original_stream
        self._log_file = log_file

    def write(self, data: str):
        self._original.write(data)
        plain = _ANSI_ESCAPE.sub("", data)
        if plain:
            self._log_file.write(plain)
            self._log_file.flush()  # 即時寫入，程式中途 crash 時 log 也不會遺失
        return len(data)

    def flush(self):
        self._original.flush()
        self._log_file.flush()

    def __getattr__(self, name):
            # 只有「自己沒有的屬性」才會走到這裡（fileno、encoding、closed、buffer、errors...），
            # 一律轉交給原本的 stream。這樣 colorama / uvicorn 檢查 stdout 能力時，
            # 看到的跟沒包這層時完全一樣。
            # 之前沒有這段，Tee 沒有 fileno()，colorama 在 Windows 上會判斷不出終端機
            # 支援原生 ANSI，改走 win32 API 轉換顏色，這時 stdout/stderr 走不同路徑，
            # 顏色狀態容易殘留，就會整片變紅。
            return getattr(self._original, name)

    def isatty(self):
        return self._original.isatty() if hasattr(self._original, "isatty") else False


def enable_terminal_capture(log_path: str | Path = "terminal_output.txt") -> None:
    """
    啟用終端機輸出擷取：把 sys.stdout / sys.stderr 都同時導向一份純文字 txt 檔，
    等於終端機上看到的所有東西（包含 uncaught exception 的 traceback）都會
    多留一份在檔案裡。

    要在程式最一開始就呼叫（愈早愈好），這樣連後面 import 其他模組時印出來的
    東西都會被記錄到；重複呼叫會被忽略，不會疊加包裝。
    """
    global _terminal_log_file

    if _terminal_log_file is not None:
        return  # 已經啟用過了

    path = Path(log_path)
    _terminal_log_file = open(path, "a", encoding="utf-8")

    header = f"\n{'=' * 60}\n本次啟動時間：{datetime.now().isoformat()}\n{'=' * 60}\n"
    _terminal_log_file.write(header)
    _terminal_log_file.flush()

    sys.stdout = _TeeStream(sys.stdout, _terminal_log_file)
    sys.stderr = _TeeStream(sys.stderr, _terminal_log_file)


def disable_terminal_capture() -> None:
    """關閉終端機輸出擷取，還原 sys.stdout / sys.stderr 並關閉 log 檔"""
    global _terminal_log_file

    if isinstance(sys.stdout, _TeeStream):
        sys.stdout = sys.stdout._original
    if isinstance(sys.stderr, _TeeStream):
        sys.stderr = sys.stderr._original

    if _terminal_log_file is not None:
        _terminal_log_file.close()
        _terminal_log_file = None
