import json
import os
import re
from datetime import datetime

def collect_monitor_data():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    workspace_dir = os.path.join(base_dir, "workspace")
    website_dir = os.path.join(base_dir, "website", "monitor")
    
    data = {
        "last_updated": datetime.now().isoformat(),
        "tickets": {"total_active": 0, "items": []},
        "heartbeat": {"tasks": []},
        "sessions": {"active_count": 0, "recent": []},
        "deferred_tasks": []
    }

    # 1. Collect Tickets
    tickets_path = os.path.join(workspace_dir, "tickets", "active_tickets.json")
    if os.path.exists(tickets_path):
        try:
            with open(tickets_path, 'r', encoding='utf-8') as f:
                tickets_data = json.load(f)
                data["tickets"]["total_active"] = len(tickets_data)
                for tid, tinfo in tickets_data.items():
                    item = {
                        "id": tid,
                        "guest": tinfo.get("guest_name", "Unknown"),
                        "content": tinfo.get("content", ""),
                        "created_at": tinfo.get("created_at", "")
                    }
                    data["tickets"]["items"].append(item)
                    
                    # Identify deferred tasks
                    if "[DEFERRED TASK]" in tinfo.get("content", ""):
                        data["deferred_tasks"].append(item)
        except Exception as e:
            print(f"Error reading tickets: {e}")

    # 2. Collect Heartbeat Tasks
    heartbeat_path = os.path.join(workspace_dir, "HEARTBEAT.md")
    if os.path.exists(heartbeat_path):
        try:
            with open(heartbeat_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # Simple markdown parsing for tasks
                tasks_section = re.search(r"## Active Tasks.*?(?=##|$)", content, re.DOTALL)
                if tasks_section:
                    task_lines = tasks_section.group(0).split('\n')
                    for line in task_lines:
                        match = re.match(r"- \[( |x|/|X)\] (.*)", line.strip())
                        if match:
                            status_char = match.group(1).lower()
                            status = "completed" if status_char == "x" else ("processing" if status_char == "/" else "pending")
                            data["heartbeat"]["tasks"].append({
                                "text": match.group(2).strip(),
                                "status": status
                            })
        except Exception as e:
            print(f"Error reading heartbeat: {e}")

    # 3. Collect Sessions
    sessions_dir = os.path.join(workspace_dir, "sessions")
    if os.path.exists(sessions_dir):
        try:
            sessions = []
            for entry in os.scandir(sessions_dir):
                if entry.is_file() and entry.name.endswith(".jsonl"):
                    mtime = datetime.fromtimestamp(entry.stat().st_mtime).isoformat()
                    # Counting lines as a rough estimate of message count
                    with open(entry.path, 'r', encoding='utf-8') as f:
                        msg_count = sum(1 for _ in f)
                    
                    sessions.append({
                        "name": entry.name,
                        "last_modified": mtime,
                        "msg_count": msg_count
                    })
            
            # Sort sessions by last modified
            sessions.sort(key=lambda x: x["last_modified"], reverse=True)
            data["sessions"]["active_count"] = len(sessions)
            data["sessions"]["recent"] = sessions[:10] # Top 10 recent
        except Exception as e:
            print(f"Error reading sessions: {e}")

    # Output to data.json
    output_path = os.path.join(website_dir, "data.json")
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Monitor data updated at {data['last_updated']}")
    except Exception as e:
        print(f"Error writing data.json: {e}")

if __name__ == "__main__":
    collect_monitor_data()
