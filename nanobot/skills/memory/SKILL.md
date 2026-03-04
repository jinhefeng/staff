---
name: memory
description: Federated memory system (Global + Isolated Guest Sandboxes).
always: true
---

# Memory

## Structure

The memory system is divided into physical files based on identity.

**1. Core Memory (Global knowledge)**
- `memory/core/global.md` — Long-term facts, project context, relationships, overall system instructions.
  - **Access**: Master has full read/write access. Guests have read-only access to this file.

**2. Guest Sandboxes (Isolated profiles)**
- `memory/guests/{user_id}.md` — Exclusively for the external guest. Contains their individual preferences, aliases, names, history context, and a `TrustScore`.
  - **Access**: Master can access all. Guests can ONLY access their own sandbox.

**3. Dynamic Groups Cache**
- `memory/core/groups.json` — Auto-maintained mapping of group IDs to group names for cross-session messaging targeting.

**4. Append-Only Log**
- `memory/HISTORY.md` — Append-only event log. NOT loaded into context. Search it with grep. Each entry starts with [YYYY-MM-DD HH:MM].

## Search Past Events

To search through historical context, use the `exec` tool to run grep:
```bash
grep -i "keyword" memory/HISTORY.md
```

## When to Update Memory

Use `update_memory` (if available in tools) or standard file writing tools to update the memory files.

- **Global File**: Write facts that apply to the system or all users.
- **Guest Profiles**: If interacting with a Guest, actively collect and save their Name, Alias/Nickname, Company, or Purpose of visit into their specific `{user_id}.md` file. E.g., `Alias: 姜姐`. This is crucial for retrieving them later via search tools.

## Auto-consolidation

Old conversations are automatically summarized and appended to `HISTORY.md` when the session grows large. Long-term facts are extracted to the respective memory profiles. Trust Score changes and rumor detections are handled by a background `ReflectionAgent`. You don't need to manually update trust scores unless explicitly instructed.
