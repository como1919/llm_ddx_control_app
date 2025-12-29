import json
import ast
import re
import pandas as pd
from typing import List, Optional

def _clean_token(t: str) -> str:
    return t.strip().strip("'\"")

def parse_listish(val: Optional[str]) -> List[str]:
    """Robustly parse list-like strings into a list of strings.
    Supports: JSON arrays, Python list literals, bracketed strings,
    and newline/pipe/semicolon/comma/tab-separated values.
    """
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return []
    if isinstance(val, list):
        return [_clean_token(str(x)) for x in val if str(x).strip()]

    s = str(val).strip()
    if not s:
        return []

    # 1) JSON array
    try:
        obj = json.loads(s)
        if isinstance(obj, list):
            return [_clean_token(str(x)) for x in obj if str(x).strip()]
        if isinstance(obj, dict) and "name" in obj:
            return [_clean_token(str(obj["name"]))]
    except Exception:
        pass

    # 2) Python list literal (e.g., ['A'\n'B'])
    try:
        obj = ast.literal_eval(s)
        if isinstance(obj, list):
            return [_clean_token(str(x)) for x in obj if str(x).strip()]
    except Exception:
        pass

    # 3) Strip surrounding brackets if present (but don't leave empty charclass!)
    s2 = s
    if s2.startswith("[") and s2.endswith("]"):
        s2 = s2[1:-1]

    # 4) Safe split on newlines / pipes / semicolons / commas / tabs
    tokens = re.split(r"[\n\r\t]+|\||;|,", s2)
    out = [_clean_token(t) for t in tokens if _clean_token(t)]
    return out