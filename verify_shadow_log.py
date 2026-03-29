import sys
from pathlib import Path
import json

# Add project root to path
sys.path.append(str(Path.cwd()))

from nanobot.utils.helpers import ensure_dir

def _log_raw_history(workspace: Path, session_key: str, message: dict) -> None:
    raw_history_dir = ensure_dir(workspace / "sessions" / "raw_history")
    from nanobot.utils.helpers import safe_filename
    safe_key = safe_filename(session_key.replace(":", "_"))
    path = raw_history_dir / f"{safe_key}.jsonl"
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(message, ensure_ascii=False) + "\n")

# Mock data
workspace = Path("workspace")
session_key = "dingtalk:014224562537153949"
message = {"role": "user", "content": "Hello, Staff! Verification in progress."}

_log_raw_history(workspace, session_key, message)
print(f"Shadow log verified at {workspace}/sessions/raw_history/")
