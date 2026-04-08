import json
from openclaw_client import OpenClawClient

client = OpenClawClient()
try:
    res = client.chat_with_agent("dev-ops", "dev-ops", [{"role": "user", "content": "ls -la /"}])
    print("RESULT:", json.dumps(res, indent=2))
except Exception as e:
    print("ERROR:", e)
