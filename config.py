from datetime import timedelta

APP_TITLE = "LLM-DDx Control App"
TIME_LIMIT_MIN = 70
REQUIRE_AT_LEAST = 3
REQUIRE_AT_MOST = 5
AUTOSAVE_SEC = 10
SAVE_DIR = "results"

# Expected CSV schema
REQUIRED_COLS = [
    "file_name",
    "현병력-Free Text#13"
]