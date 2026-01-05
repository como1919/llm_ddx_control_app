# --- sys.path bootstrap so absolute imports work when Streamlit sets CWD to this folder ---
from pathlib import Path
import sys
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
# -------------------------------------------------------------------------------

import os
import time
import uuid
import hashlib
from typing import List
from datetime import datetime, date

import pandas as pd
import streamlit as st

# === dependency-free auto-refresh every N ms (keeps timer live) ===
def auto_refresh(enabled: bool, interval_ms: int = 1000):
    if not enabled:
        return
    st.markdown(
        f"""
        <script>
        const __key = "st_js_autorefresh_{interval_ms}";
        if (!window[__key]) {{
          window[__key] = setInterval(() => {{
            window.parent.postMessage({{isStreamlitMessage: true, type: "rerun"}}, "*");
          }}, {interval_ms});
        }}
        </script>
        """,
        unsafe_allow_html=True,
    )

# --- app-specific imports (CONTROL) ---
from llm_ddx_control_app.config import (
    APP_TITLE,
    TIME_LIMIT_MIN,   # 이제는 사용하지 않지만, 다른 모듈 호환을 위해 그대로 import만 유지
    REQUIRE_AT_LEAST,
    REQUIRE_AT_MOST,
    AUTOSAVE_SEC,
)
from llm_ddx_control_app.data_io import read_uploaded_csv
from llm_ddx_control_app.persistence import build_row, save_progress


# ---------------------
# CSV 다운로드 헬퍼
# ---------------------
def _append_buffer(row: dict):
    """세션 버퍼에 현재 행을 누적 (배포 환경에서도 즉시 다운로드 가능)."""
    buf = st.session_state.get("result_rows", [])
    buf.append(row)
    st.session_state["result_rows"] = buf


def _local_control_path(participant_id: str) -> str:
    today = date.today().strftime("%Y%m%d")
    return os.path.join("results", f"{participant_id}_control_{today}.csv")

def render_download_button(participant_id: str):
    """로컬 CSV + 세션 버퍼를 합쳐서 후처리 후 다운로드."""
    local_path = _local_control_path(participant_id)

    dfs = []

    # 1) 로컬 CSV가 있으면 읽기
    if os.path.exists(local_path):
        try:
            df_local = pd.read_csv(local_path)
            dfs.append(df_local)
        except Exception:
            pass

    # 2) 세션 버퍼(result_rows)도 함께 사용
    rows = st.session_state.get("result_rows", [])
    if rows:
        df_buf = pd.DataFrame(rows)
        dfs.append(df_buf)

    # 3) 둘 다 없으면 빈 DF
    if dfs:
        df_src = pd.concat(dfs, ignore_index=True)
    else:
        df_src = pd.DataFrame()

    # 4) 후처리 & 중복 제거
    if not df_src.empty:
        df = df_src.copy()

        # 정렬 기준 먼저 결정: save_ns > timestamp > index
        if "save_ns" in df.columns:
            df = df.sort_values("save_ns")
        elif "timestamp" in df.columns:
            df = df.sort_values("timestamp")
        else:
            df["__order__"] = range(len(df))
            df = df.sort_values("__order__")

        df = df.drop_duplicates(
            subset=["participant_id", "file_name"],  # 또는 ["participant_id", "case_index"]
            keep="last",
        )

        # 임시 컬럼 정리
        df = df.drop(columns=["__order__"], errors="ignore")

        # 5) 로컬 파일도 최신 상태로 저장 (가능한 경우)
        try:
            os.makedirs("results", exist_ok=True)
            tmp = f"{local_path}.tmp"
            df.to_csv(tmp, index=False)
            os.replace(tmp, local_path)
            #st.success("후처리 완료: 최신 1줄만 남기고 CSV를 갱신했습니다.")
        except Exception as e:
            st.info(f"로컬 저장은 생략하고, 후처리된 데이터만 다운로드합니다. ({e})")

        csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
    else:
        # 데이터가 하나도 없을 때
        csv_bytes = pd.DataFrame().to_csv(index=False).encode("utf-8-sig")

    today = date.today().strftime("%Y%m%d")
    st.download_button(
        label="📥 결과 CSV 다운로드",
        data=csv_bytes,
        file_name=f"{participant_id}_control_{today}.csv",
        mime="text/csv",
        use_container_width=True,
    )


# ---------------------
# Utils
# ---------------------
def elapsed_seconds() -> int:
    """세션 시작 이후 경과 시간(초)만 기록 (제한시간 없음)."""
    start_ts = st.session_state.get("start_ts")
    if not start_ts:
        return 0
    elapsed = (datetime.now() - start_ts).total_seconds()
    return max(0, int(elapsed))

def disabled() -> bool:
    """시간 제한 없이, 세션이 종료(finalized)된 경우에만 입력 비활성화."""
    return st.session_state.get("finalized", False)

def init_order(df_len: int, randomize: bool):
    if "order" not in st.session_state:
        idxs = list(range(df_len))
        if randomize:
            import random
            random.Random(42).shuffle(idxs)
        st.session_state.order = idxs
        st.session_state.case_idx = 0
        st.session_state["notes"] = ""

def _ddx_key(i: int, row) -> str:
    """file_name 기반 해시로 케이스별 위젯 키 충돌 방지."""
    fid = str(row.get("file_name", ""))
    h = hashlib.md5(fid.encode("utf-8")).hexdigest()[:8]
    return f"ddx_{i}_{h}"

def collect_inputs(row) -> List[str]:
    return [st.session_state.get(_ddx_key(i, row), "").strip() for i in range(1, REQUIRE_AT_MOST + 1)]


# ---------------------
# Center pane (CONTROL): Editable HPI only (NO Model Suggestions)
# ---------------------
def render_center_hpi_only(row: pd.Series):
    st.subheader("환자 초진 기록")
    fid = str(row.get("file_name", ""))
    h = hashlib.md5(fid.encode("utf-8")).hexdigest()[:8]
    hkey = f"hpi_{h}"
    default_hpi = row.get("원본 초진기록", row.get("현병력-Free Text#13", ""))

    if hkey not in st.session_state:
        st.session_state[hkey] = str(default_hpi)

    st.text_area(
        "raw_visit",
        key=hkey,
        height=460,
        label_visibility="collapsed",
    )


# ---------------------
# Main
# ---------------------
def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")

    # Auto-refresh: 이제는 제한시간이 아니라,
    # 경과 시간/자동저장을 위한 주기적 rerun 용도로만 사용.
    auto_refresh(
        enabled=st.session_state.get("active") and not st.session_state.get("finalized", False),
        interval_ms=1000,
    )

    # Sidebar
    with st.sidebar:
        st.header("CONTROL 설정 (대조군)")
        uploaded = st.file_uploader("CSV 업로드", type=["csv"], accept_multiple_files=False)
        participant_id = st.text_input("참가자 ID", value=st.session_state.get("participant_id", ""))
        #randomize_order = st.checkbox("증례 순서 무작위", value=False)
        st.session_state["participant_id"] = participant_id

        st.markdown("---")
        # 더 이상 '총 시간 제한'은 없음 → 안내 문구만 간단히 변경
        st.caption("세션 시작 시점부터의 경과 시간만 기록합니다. (시간 제한 없음)")

        c1, c2 = st.columns(2)
        with c1:
            if st.button("세션 시작/재개", use_container_width=True):
                if not participant_id:
                    st.error("참가자 ID를 입력하세요.")
                    st.stop()
                if "start_ts" not in st.session_state:
                    st.session_state.start_ts = datetime.now()
                if "session_uuid" not in st.session_state:
                    st.session_state.session_uuid = str(uuid.uuid4())
                st.session_state.active = True
                st.session_state.finalized = False
        with c2:
            if st.button("세션 종료", use_container_width=True):
                st.session_state.finalized = True

        #st.markdown("---")
        #st.subheader("자동 저장")
        #st.caption(f"{AUTOSAVE_SEC}초마다 결과 저장 (페이지가 열려 있는 동안)")
        #st.write("최근 저장:", st.session_state.get("last_saved_ts", "(없음)"))


    if not uploaded:
        st.title(APP_TITLE)
        st.info("좌측에서 CSV를 업로드하세요.")
        return

    df = read_uploaded_csv(uploaded)
    init_order(len(df), randomize=False)

    # Header
    order = st.session_state.order
    ci = st.session_state.case_idx
    total = len(order)
    sec = elapsed_seconds()

    top_left, top_right = st.columns([3, 1])
    with top_left:
        st.title(APP_TITLE)
        st.progress((ci / max(1, total)), text=f"진행도: {ci}/{total}")
    with top_right:
        # 남은 시간 → 경과 시간 표시로 변경
        st.metric("경과 시간", f"{sec//60:02d}:{sec%60:02d}")

    if not st.session_state.get("active"):
        st.warning("좌측에서 '세션 시작/재개'를 눌러 시작하세요.")
        return

    if disabled():
        st.error("세션이 종료되었습니다. 입력이 비활성화되었습니다.")

    row = df.iloc[order[ci]]

    st.markdown(f"### 증례 {ci+1} / {total} — `{row['file_name']}`")

    # Layout: center(HPI only) | right(inputs)
    col_center, col_right = st.columns([5, 3])

    with col_center:
        render_center_hpi_only(row)

    with col_right:
        st.subheader("감별진단 입력 (3–5개)")
        for i in range(1, REQUIRE_AT_MOST + 1):
            st.text_input(f"감별진단 {i}", key=_ddx_key(i, row), disabled=disabled())
        st.text_area("메모(선택)", key="notes", disabled=disabled())

        #if st.button("입력 초기화", disabled=disabled(), use_container_width=True):
            #for i in range(1, REQUIRE_AT_MOST + 1):
            #    st.session_state[_ddx_key(i, row)] = ""
            #st.session_state["notes"] = ""
            #st.rerun()

    # Validate & collect
    inputs = collect_inputs(row)
    non_empty = [d for d in inputs if d]
    valid = REQUIRE_AT_LEAST <= len(non_empty) <= REQUIRE_AT_MOST

    # 현재 시점 경과 시간 (로그용)
    current_elapsed = elapsed_seconds()

    # Navigation
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        prev_disabled = ci == 0 or disabled()
        if st.button("⬅️ 이전", disabled=prev_disabled):
            row_out = build_row(
                st.session_state.session_uuid,
                participant_id,
                ci,
                total,
                current_elapsed,  # seconds_left 대신 경과 시간 저장
                str(row["file_name"]),
                non_empty,
                st.session_state.get("notes", ""),
            )
            save_progress(participant_id, row_out)
            _append_buffer(row_out)   # ✅ download buffer
            st.session_state.case_idx -= 1
            st.rerun()

    with c2:
        next_disabled = ci == total - 1 or disabled() or not valid
        if st.button("다음 ➡️", disabled=next_disabled):
            if not valid:
                st.warning(f"감별진단을 {REQUIRE_AT_LEAST}–{REQUIRE_AT_MOST}개 입력하세요.")
            else:
                row_out = build_row(
                    st.session_state.session_uuid,
                    participant_id,
                    ci,
                    total,
                    current_elapsed,  # seconds_left 대신 경과 시간
                    str(row["file_name"]),
                    non_empty,
                    st.session_state.get("notes", ""),
                )
                save_progress(participant_id, row_out)
                _append_buffer(row_out)   # ✅ download buffer
                st.session_state.case_idx += 1
                st.rerun()

    with c3:
        submit_disabled = ci != total - 1 or disabled() or not valid
        if st.button("✅ 마지막 증례 저장", disabled=submit_disabled):
            row_out = build_row(
                st.session_state.session_uuid,
                participant_id,
                ci,
                total,
                current_elapsed,  # seconds_left 대신 경과 시간
                str(row["file_name"]),
                non_empty,
                st.session_state.get("notes", ""),
            )
            save_progress(participant_id, row_out)
            _append_buffer(row_out)   # ✅ download buffer
            st.session_state.finalized = True
            st.success("세션이 종료되었습니다. 좌측 하단의 결과 csv 다운로드 버튼을 클릭하세요.")

    # Autosave heartbeat (제한시간 없이, 경과 시간을 로그로 저장)
    if not disabled():
        row_out = build_row(
            st.session_state.session_uuid,
            participant_id,
            ci,
            total,
            elapsed_seconds(),
            str(row["file_name"]),
            non_empty,
            st.session_state.get("notes", ""),
        )
        save_progress(participant_id, row_out)
        _append_buffer(row_out)
        st.session_state["last_saved_ts"] = datetime.now().strftime("%H:%M:%S")

    with st.sidebar:
        st.markdown("---")
        st.subheader("결과 다운로드")
        render_download_button(participant_id)


if __name__ == "__main__":
    main()