# llm_ddx_control_app/persistence.py

import os
import json
from datetime import datetime
from typing import Dict

import pandas as pd
import streamlit as st

from llm_ddx_control_app.config import SAVE_DIR
from llm_ddx_control_app.data_io import ensure_results_dir


# ---- 로컬 저장 (control 전용) ----
def _local_result_path(participant_id: str) -> str:
    ensure_results_dir(SAVE_DIR)
    fname = f"{participant_id}_control_{datetime.now().strftime('%Y%m%d')}.csv"
    return os.path.join(SAVE_DIR, fname)

def _save_local(participant_id: str, row: Dict):
    path = _local_result_path(participant_id)
    df = pd.DataFrame([row])
    if os.path.exists(path):
        df.to_csv(path, mode="a", header=False, index=False)
    else:
        df.to_csv(path, index=False)


# ---- (선택) Google Sheets 저장: 환경이 구성된 경우에만 사용 ----
def _save_gsheets(row: Dict):
    # gspread/credentials 미구성 시 조용히 실패하도록 처리
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except Exception:
        raise RuntimeError("gsheets_unavailable")

    sa_info = st.secrets.get("gcp_service_account")
    settings = st.secrets.get("gsheets")
    if not sa_info or not settings or not settings.get("sheet_name"):
        raise RuntimeError("no_secrets")

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(sa_info, scopes=scopes)
    gc = gspread.authorize(creds)

    sh = gc.open(settings["sheet_name"])
    ws = sh.worksheet(settings.get("worksheet", "submissions"))

    ordered = [
        row.get("timestamp", ""),
        row.get("session_uuid", ""),
        row.get("participant_id", ""),
        row.get("arm", ""),
        row.get("case_index", ""),
        row.get("cases_total", ""),
        row.get("file_name", ""),
        row.get("entered_ddx_list", ""),
        row.get("notes", ""),
        row.get("seconds_left", ""),
    ]
    ws.append_row(ordered, value_input_option="USER_ENTERED")


def build_row(
    session_uuid,
    participant_id,
    idx,
    total,
    seconds_left,
    file_name,
    ddx_list,
    notes,
) -> Dict:
    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "session_uuid": session_uuid,
        "participant_id": participant_id,
        "arm": "control",  # ✅ control
        "case_index": idx + 1,
        "cases_total": total,
        "file_name": file_name,
        "entered_ddx_list": json.dumps(ddx_list, ensure_ascii=False),
        "notes": notes,
        "seconds": seconds_left,
    }


def save_progress(participant_id: str, row: Dict):
    """
    원격 저장 환경(secrets)이 제대로 구성된 경우에만 Google Sheets에 저장을 시도하고,
    그 외에는 조용히 로컬 CSV로 저장합니다. (UI에 경고/로그 출력 안 함)
    """
    # 원격 저장 가능 여부 체크
    use_remote = False
    try:
        sa = st.secrets.get("gcp_service_account")
        gs = st.secrets.get("gsheets")
        use_remote = bool(sa and gs and gs.get("sheet_name"))
    except Exception:
        use_remote = False

    if use_remote:
        try:
            _save_gsheets(row)
            return
        except Exception:
            pass  # 조용히 로컬로 폴백

    # 로컬 저장 (기본)
    try:
        _save_local(participant_id, row)
    except Exception:
        # 최종 실패도 조용히 무시 (요청: 에러 안 보이도록)
        pass