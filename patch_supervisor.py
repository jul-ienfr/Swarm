import re

with open("/home/jul/.openclaw/workspace/langgraph-swarm/supervisor.py", "r") as f:
    content = f.read()

new_content = re.sub(
    r"cursor\.execute\('''\s*INSERT INTO activities \(id, type, entity_type, entity_id, actor, description, data, created_at, workspace_id\)\s*VALUES \(\?, \?, \?, \?, \?, \?, \?, \?, \?\)\s*''', \(record_id, 'log', 'agent', 'supervisor', 'supervisor', f\"\[\{action\}\] \{content\}\", data, now, ws_id\)\)",
    """cursor.execute('''
                INSERT INTO activities (type, entity_type, entity_id, actor, description, data, created_at, workspace_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', ('log', 'agent', 1, 'supervisor', f"[{action}] {content}", data, int(datetime.datetime.utcnow().timestamp()), int(ws_id)))""",
    content
)

with open("/home/jul/.openclaw/workspace/langgraph-swarm/supervisor.py", "w") as f:
    f.write(new_content)
