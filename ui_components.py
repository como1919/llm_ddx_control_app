import streamlit as st
from typing import List
from llm_ddx_case_app.config import REQUIRE_AT_LEAST, REQUIRE_AT_MOST


def header(title: str, progress_frac: float, progress_text: str, seconds_left: int):
    left, right = st.columns([3, 1])
    with left:
        st.title(title)
        st.progress(progress_frac, text=progress_text)
    with right:
        st.metric("남은 시간", f"{seconds_left//60:02d}:{seconds_left%60:02d}")


def ddx_inputs(disabled: bool):
    st.markdown(":blue[감별진단 **3–5개**를 입력하세요.]")
    for i in range(1, REQUIRE_AT_MOST + 1):
        st.text_input(f"감별진단 {i}", key=f"ddx_{i}", disabled=disabled)
    st.text_area("메모(선택)", key="notes", disabled=disabled)


def assistance_panel(expected: List[str], diffs: List[str], disabled: bool):
    st.subheader("보조 패널 (중재군)")
    if expected:
        st.markdown("**Expected Dx**")
        for j, s in enumerate(expected, 1):
            if st.button(f"⭐ {s}", key=f"exp_{j}", disabled=disabled):
                _fill_first_empty(s)
    if diffs:
        st.markdown("**Differentials**")
        for j, s in enumerate(diffs, 1):
            if st.button(f"{j}. {s}", key=f"diff_{j}", disabled=disabled):
                _fill_first_empty(s)


def _fill_first_empty(value: str):
    from .config import REQUIRE_AT_MOST
    for i in range(1, REQUIRE_AT_MOST + 1):
        k = f"ddx_{i}"
        if not st.session_state.get(k):
            st.session_state[k] = value
            break