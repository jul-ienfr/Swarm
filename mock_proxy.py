import json
from http.server import BaseHTTPRequestHandler, HTTPServer

class MockProxyHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        payload = json.loads(post_data.decode('utf-8'))

        print("\n" + "="*50)
        print(f"INTERCEPTED REQUEST to {self.path}")
        print("="*50)
        print(json.dumps(payload, indent=2))
        print("="*50 + "\n")

        # Append payload to a file so we can inspect all turns
        with open("/tmp/intercepted_payload.jsonl", "a") as f:
            f.write(json.dumps(payload) + "\n")

        # Send dummy response
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()

        response = {
            "id": "mock-response",
            "object": "chat.completion",
            "created": 123456789,
            "model": "gemini-3.1-pro-high",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_mock123",
                            "type": "function",
                            "function": {
                                "name": "execute_shell",
                                "arguments": "{\"command\": \"echo 'hello world'\"}"
                            }
                        }
                    ]
                },
                "finish_reason": "tool_calls"
            }]
        }
        
        # We need to simulate a tool call so that OpenClaw will execute it and send back the result in the second turn!
        # If the payload already contains a tool response, we just return a normal message to end it.
        messages = payload.get("messages", [])
        has_tool_response = any(m.get("role") == "tool" for m in messages)
        
        if has_tool_response:
            response["choices"][0]["message"] = {
                "role": "assistant",
                "content": "J'ai bien reçu le résultat de l'outil !"
            }
            response["choices"][0]["finish_reason"] = "stop"

        self.wfile.write(json.dumps(response).encode('utf-8'))

def run(port=8046):
    server_address = ('127.0.0.1', port)
    httpd = HTTPServer(server_address, MockProxyHandler)
    print(f"Mock proxy listening on port {port}...")
    try:
        httpd.serve_forever()  # Keep alive to catch multiple requests
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    run()
