import os
import pandas as pd
import streamlit as st
from llm_ddx_control_app.config import REQUIRED_COLS


def read_uploaded_csv(uploaded_file) -> pd.DataFrame:
    df = pd.read_csv(uploaded_file)
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        st.error(f"CSV 누락 컬럼: {missing}")
        st.stop()
    return df.copy()


def ensure_results_dir(path: str):
    os.makedirs(path, exist_ok=True)