"""Router + LLM against a fake Ollama server (checks request shape and action handling)."""
import json, os, tempfile, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
os.environ.setdefault("CAPRICORN_HOME", tempfile.mkdtemp())

from capricorn.config import Settings, ensure_user_files
from capricorn.security.permissions import Permissions

SEEN = []
REPLY = {"say": "Lo-fi incoming, choom.", "emotion": "smile",
         "action": {"name": "music_play", "args": {"query": "lofi beats"}}}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        body = json.dumps({"models": [{"name": "qwen3:4b"}]}).encode()
        self.send_response(200); self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append(req)
        body = json.dumps({"message": {"role": "assistant", "content": json.dumps(REPLY)}}).encode()
        self.send_response(200); self.end_headers(); self.wfile.write(body)

def test_llm_action_roundtrip(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    ensure_user_files("full")
    s = Settings()
    s.data["brain"]["ollama_url"] = f"http://127.0.0.1:{srv.server_port}"
    from capricorn.actions.registry import ActionRegistry
    from capricorn.brain.llm import LLM
    from capricorn.brain.router import Router
    from capricorn.actions import web
    opened = []
    monkeypatch.setattr(web, "_launch", lambda url, perms: opened.append(url))
    reg = ActionRegistry(s, Permissions())
    llm = LLM(s)
    assert llm.status()[0]
    r = Router(reg, llm).handle("I need something chill to study to")
    assert r.ok and r.say == "Lo-fi incoming, choom." and r.emotion == "smile"
    assert opened == ["https://music.youtube.com/search?q=lofi+beats"]
    req = SEEN[-1]
    assert req["think"] is False and req["stream"] is False and req["format"]["type"] == "object"
    assert "music_play" in req["messages"][0]["content"]
    srv.shutdown()
