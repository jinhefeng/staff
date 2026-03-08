
import os
import re
from pathlib import Path

# 使用工作区相对路径，避免硬编码
BASE_DIR = Path(__file__).parent
GUESTS_DIR = BASE_DIR / "workspace" / "memory" / "guests"

def patch_file(p):
    if p.name == "guest_template.md" or p.suffix != ".md":
        return
    
    content = p.read_text(encoding="utf-8")
    
    # 1. Patch YAML (Add LastSyncDate if missing)
    if "LastSyncDate" not in content:
        header_match = re.match(r'^(---\n.*?\n---)', content, re.DOTALL)
        if header_match:
            header = header_match.group(1)
            new_header = header.replace("\n---", "\nLastSyncDate: \"\"\n---")
            content = content.replace(header, new_header)
        else:
            # Fallback for files without header
            content = "---\nTrustScore: 50\nLastSyncDate: \"\"\n---\n\n" + content

    # 2. Patch DeptPath anchor (Careful fix for existing messy injections)
    # Remove any broken injections like line 10 in previously messed up files
    content = re.sub(r'^- \*\*DeptPath \(组织架构\)\*\*: \(每日同步获取\) \(Persona & Basic Info\)$', '', content, flags=re.MULTILINE)
    
    # Clean up duplicate anchors if any
    content = re.sub(r'^- \*\*DeptPath \(组织架构\)\*\*:.*?\n', '', content)
    
    # Properly inject DeptPath under the section header
    if "DeptPath (组织架构)" not in content:
        section_pattern = r'(### 🎭 基本特质与履历.*?\n)'
        content = re.sub(section_pattern, r'\1- **DeptPath (组织架构)**: (每日同步获取)\n', content)

    p.write_text(content, encoding="utf-8")
    print(f"Verified and Patched {p.name}")

if __name__ == "__main__":
    if GUESTS_DIR.exists():
        for f in GUESTS_DIR.glob("*.md"):
            patch_file(f)
    else:
        print(f"Error: Directory not found: {GUESTS_DIR}")
