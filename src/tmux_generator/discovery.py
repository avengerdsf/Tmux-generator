from __future__ import annotations

import json
import socket
import threading

DISCOVERY_MESSAGE = b"TMUX_GENERATOR_DISCOVER"
DISCOVERY_PORT = 48765


def discovery_response(host: str, http_port: int) -> dict:
    return {"service": "tmux_generator", "version": 1, "url": f"http://{host}:{http_port}"}


def handle_discovery_packet(data: bytes, address: tuple[str, int], http_port: int, sock=None):
    if data.strip() != DISCOVERY_MESSAGE:
        return None
    target = sock or socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    host = target.getsockname()[0]
    if host == "0.0.0.0":
        host = address[0]
    payload = json.dumps(discovery_response(host, http_port)).encode("utf-8")
    target.sendto(payload, address)
    return payload


def run_discovery_server(http_port: int, discovery_port: int = DISCOVERY_PORT) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", discovery_port))
    while True:
        data, address = sock.recvfrom(4096)
        handle_discovery_packet(data, address, http_port, sock=sock)


def start_discovery_thread(http_port: int, discovery_port: int = DISCOVERY_PORT) -> threading.Thread:
    thread = threading.Thread(target=run_discovery_server, args=(http_port, discovery_port), daemon=True)
    thread.start()
    return thread
