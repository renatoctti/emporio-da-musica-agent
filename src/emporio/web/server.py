"""A tiny HTTP server around `WebApp`. It listens on the local machine only."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer

from emporio.web.app import MAX_BODY_BYTES, WebApp

HOST = "127.0.0.1"


class _Handler(BaseHTTPRequestHandler):
    app: WebApp

    def _serve(self, method: str) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(min(length, MAX_BODY_BYTES + 1)) if length else b""
        response = self.app.handle(method, self.path, dict(self.headers.items()), body)
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(response.body)))
        for name, value in response.headers:
            self.send_header(name, value)
        if length > MAX_BODY_BYTES:
            self.send_header("Connection", "close")  # the rest of the body was not read
            self.close_connection = True
        self.end_headers()
        self.wfile.write(response.body)

    def do_GET(self) -> None:
        self._serve("GET")

    def do_POST(self) -> None:
        self._serve("POST")

    def do_PUT(self) -> None:
        self._serve("PUT")

    def do_DELETE(self) -> None:
        self._serve("DELETE")

    def log_message(self, format: str, *args: object) -> None:
        pass  # one line per request would bury the useful output


def make_server(app: WebApp, port: int) -> HTTPServer:
    handler = type("Handler", (_Handler,), {"app": app})
    server = HTTPServer((HOST, port), handler)
    app.port = server.server_address[1]
    return server
