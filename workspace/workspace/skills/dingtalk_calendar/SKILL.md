# DingTalk Calendar Skill

## Description
Securely fetch user calendar events from DingTalk API using user ID. Only triggers if valid permissions are configured; no action taken if lacking access.

## Requirements
- DingTalk App Key and Secret (configured via environment variables: `DINGTALK_APP_KEY`, `DINGTALK_APP_SECRET`)
- Valid user ID (uid) provided by user
- Network access to DingTalk API endpoints

## Parameters
| Parameter | Type | Required | Description |
|----------|------|----------|-------------|
| user_id  | string | yes | DingTalk user ID (not email) |
| start_time | string | no | ISO8601 start time (default: today) |
| end_time | string | no | ISO8601 end time (default: +7 days) |

## Behavior
- If `DINGTALK_APP_KEY` or `DINGTALK_APP_SECRET` is not set: returns `error: DingTalk credentials not configured`
- If user_id is invalid or missing: returns `error: missing or invalid user_id`
- If API returns 403/401: returns `error: insufficient permissions to access calendar`
- On success: returns structured JSON with events list

## Example Usage
```bash
# Fetch today's events for user 12345
 DingTalkCalendar user_id=12345

# Fetch events for a date range
 DingTalkCalendar user_id=12345 start_time=2026-03-01T00:00:00Z end_time=2026-03-07T23:59:59Z
```

## Security Notes
- Never log or store user_id or tokens
- Uses OAuth2.0 client credentials flow
- All requests made via HTTPS
- No personal data stored locally

## Implementation Notes
- Uses `requests` library (Python)
- Token cached for 1 hour
- Rate limiting handled (100 req/min)
- Fallback to cached token if refresh fails

## Dependencies
- Python 3.8+
- requests

## Sample Output (Success)
```json
{
  "events": [
    {
      "id": "evt_abc123",
      "title": "Team Sync",
      "start_time": "2026-03-05T09:00:00Z",
      "end_time": "2026-03-05T10:00:00Z",
      "location": "会议室A",
      "attendees": ["user1@company.com"]
    }
  ]
}
```

## Sample Output (Error - No Permissions)
```json
{
  "error": "insufficient permissions to access calendar"
}
```

## Sample Output (Error - Missing Config)
```json
{
  "error": "DingTalk credentials not configured"
}
```

## Related Links
- [DingTalk OpenAPI Docs](https://open.dingtalk.com/document/orgapp-server/overview)
- [Calendar API Reference](https://open.dingtalk.com/document/orgapp-server/calendar-api)
