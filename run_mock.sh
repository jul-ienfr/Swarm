#!/bin/bash
cd /home/jul/.openclaw/workspace/langgraph-swarm

# 1. Modify config to point to mock proxy
sed -i 's|"http://192.168.31.59:8045/v1"|"http://127.0.0.1:8046/v1"|g' /home/jul/.openclaw/openclaw.json

# 2. Restart gateway
openclaw gateway restart
sleep 3

# 3. Start mock proxy in background
source venv/bin/activate
python mock_proxy.py &
MOCK_PID=$!
sleep 2

# 4. Trigger the request
curl -s -X POST http://127.0.0.1:18789/v1/responses \
  -H "Authorization: Bearer $(cat /home/jul/.openclaw/openclaw.json | jq -r .gateway.auth.token)" \
  -H "Content-Type: application/json" \
  -H "x-openclaw-agent-id: dev-ops" \
  -d '{"model": "openclaw", "input": "ls -la /"}' > /dev/null

sleep 2
kill $MOCK_PID 2>/dev/null || true

# 5. Restore config
sed -i 's|"http://127.0.0.1:8046/v1"|"http://192.168.31.59:8045/v1"|g' /home/jul/.openclaw/openclaw.json
openclaw gateway restart

echo "Mock capture complete."
