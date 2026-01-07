import os
import json
from datetime import datetime
from typing import Dict
import pandas as pd

from llm_ddx_case_app.config import SAVE_DIR
from llm_ddx_case_app.data_io import ensure_results_dir


def result_path(participant_id: str) -> str:
    ensure_results_dir(SAVE_DIR)
    fname = f"{participant_id}_case_{datetime.now().strftime('%Y%m%d')}.csv"
    return os.path.join(SAVE_DIR, fname)


def build_row(
    session_uuid: str,
    participant_id: str,
    idx: int,
    total: int,
    seconds_left: int,
    file_name: str,
    ddx_list: list,
    notes: str,
) -> Dict:
    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "session_uuid": session_uuid,
        "participant_id": participant_id,
        "arm": "case",
        "case_index": idx + 1,
        "cases_total": total,
        "file_name": file_name,
        "entered_ddx_list": json.dumps(ddx_list, ensure_ascii=False),
        "notes": notes,
        "seconds": seconds_left,
    }


def save_progress(participant_id: str, row: Dict):
    path = result_path(participant_id)
    df = pd.DataFrame([row])
    if os.path.exists(path):
        df.to_csv(path, mode="a", header=False, index=False)
    else:
        df.to_csv(path, index=False)