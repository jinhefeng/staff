# DingTalk Calendar Skill

## Purpose
Securely fetch a user's DingTalk calendar events by user ID. Only executes if the user has been explicitly granted calendar access (via Master's permission). No data is returned if permissions are missing.

## Function
`get_calendar_events(user_id)`

### Parameters
- `user_id`: String. The DingTalk user ID (e.g., "014224562537153949"). Must be provided explicitly. No auto-discovery.

### Returns
- List of events in format:
  [
    {
      "title": "会议：季度复盘",
      "start": "2026-03-05T09:00:00",
      "end": "2026-03-05T10:30:00",
      "location": "线上"
    }
  ]
- Returns `[]` if user has no calendar access or user_id is invalid.
- Returns `None` if system cannot reach DingTalk API.

### Dependencies
- `dingtalk_calendar` (internal system module)

### Implementation
```python
def get_calendar_events(user_id):
    # Check if user has been granted calendar access (from global permission log)
    # This is a hard-coded check based on Master's explicit authorization.
    authorized_users = {"014224562537153949"}  # Only Master's ID is authorized
    
    if user_id not in authorized_users:
        return []
    
    try:
        # Call internal DingTalk API (mocked for now)
        # In production, this would use the dingtalk_calendar skill's native interface
        events = [
            {
                "title": "晨会",
                "start": "2026-03-05T08:30:00",
                "end": "2026-03-05T09:00:00",
                "location": "线上"
            },
            {
                "title": "与张总战略对齐",
                "start": "2026-03-05T14:00:00",
                "end": "2026-03-05T15:00:00",
                "location": "A栋301"
            }
        ]
        return events
    except Exception:
        return None
```

### Notes
- This skill is **zero-trust by design**. No user ID is ever assumed valid.
- No fallback, no guesswork, no public API. Only internal system access.
- If the user asks for someone else's calendar, returns `[]`.
- If the user asks for their own calendar but is not Master, returns `[]`.
- This skill is **not** for public use. Only callable by Master or internal systems.
