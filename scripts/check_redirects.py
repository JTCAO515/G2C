"""Actual local HTTP redirects: the forbidden listener must receive zero requests.

Both listeners bind IPv4 loopback. `localhost` is deliberately outside the
ProbeConnection allowlist (which accepts only literal 127.0.0.1). No public target.
"""
import json
import os
from pathlib import Path
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock, Thread

binary = Path("ios/.build/debug/CJProbe").resolve()
hits = {"source": 0, "destination": 0}
lock = Lock()


class Destination(BaseHTTPRequestHandler):
    def do_GET(self):
        with lock:
            hits["destination"] += 1
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"forbidden destination reached")

    def log_message(self, *_):
        pass


class Source(BaseHTTPRequestHandler):
    def do_GET(self):
        with lock:
            hits["source"] += 1
        self.send_response(self.server.redirect_status)
        self.send_header("Location", self.server.destination)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *_):
        pass


def main():
    destination = ThreadingHTTPServer(("127.0.0.1", 0), Destination)
    source = ThreadingHTTPServer(("127.0.0.1", 0), Source)
    threads = [Thread(target=server.serve_forever) for server in (destination, source)]
    for thread in threads:
        thread.start()
    try:
        for host in ("localhost", "127.0.0.1"):
            source.destination = f"http://{host}:{destination.server_port}/forbidden"
            for status in (301, 302, 303, 307, 308):
                source.redirect_status = status
                result = subprocess.run([str(binary)], env=dict(os.environ, CJ_ENV="local",
                    CJ_API_BASE_URL=f"http://127.0.0.1:{source.server_port}"),
                    capture_output=True, text=True, timeout=20)
                assert result.returncode == 1, result.stdout
                assert result.stdout.strip() == f"FAIL HTTP {status} redirect rejected; destination not requested", result.stdout
                assert hits["destination"] == 0, hits
                print(f"PASS HTTP {status} Location={source.destination}: exit=1, rejected before follow")
        assert hits == {"source": 10, "destination": 0}, hits
        print("PASS listener counts " + json.dumps(hits, sort_keys=True))
    finally:
        for server in (source, destination):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join()
        print("Local listeners stopped and threads joined")


if __name__ == "__main__":
    main()
