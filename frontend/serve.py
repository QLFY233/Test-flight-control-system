#!/usr/bin/env python3
"""
High-concurrency static file server for the flight control frontend.

Default Python http.server uses TCPServer.request_queue_size = 5,
which causes TCP RST (connection refused) when 40+ ES modules load
concurrently from browsers. This server uses a backlog of 128.

Usage:
    python3 serve.py [port] [bind_addr]
    python3 serve.py 8080 0.0.0.0
"""

import http.server
import socket
import socketserver
import sys
import os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
BIND = sys.argv[2] if len(sys.argv) > 2 else "0.0.0.0"

# Serve from the directory containing this script
os.chdir(os.path.dirname(os.path.abspath(__file__)))


class HighBacklogTCPServer(socketserver.ThreadingTCPServer):
    """TCPServer with larger accept queue to handle concurrent ES module loads."""
    request_queue_size = 128
    allow_reuse_address = True  # 自动设置 SO_REUSEADDR


class CORSRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Add CORS + no-cache headers."""

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def log_message(self, format, *args):
        # Quieter logging: only log errors and non-200 responses
        if hasattr(self, "send_response") and not str(args[0]).startswith("200"):
            super().log_message(format, *args)


if __name__ == "__main__":
    handler = CORSRequestHandler

    with HighBacklogTCPServer((BIND, PORT), handler) as httpd:
        print(f"✓ Frontend server listening on http://{BIND}:{PORT}")
        print(f"  Serving: {os.getcwd()}")
        print(f"  Backlog: {HighBacklogTCPServer.request_queue_size}")
        print(f"  Press Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n✗ Server stopped.")
