from __future__ import annotations

import json
import socket
import threading

DISCOVERY_MESSAGE = b"TMUX_GENERATOR_DISCOVER"
DISCOVERY_PORT = 48765
DISCOVERY_POLL_SECONDS = 1.0


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


class DiscoveryServer:
    def __init__(
        self,
        http_port: int,
        discovery_port: int = DISCOVERY_PORT,
        socket_factory=socket.socket,
        poll_seconds: float = DISCOVERY_POLL_SECONDS,
    ) -> None:
        self.http_port = http_port
        self.discovery_port = discovery_port
        self.socket_factory = socket_factory
        self.poll_seconds = poll_seconds
        self._stop = threading.Event()
        self._sock = None

    def run(self) -> None:
        sock = self.socket_factory(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock = sock
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(self.poll_seconds)
        sock.bind(("", self.discovery_port))
        try:
            while not self._stop.is_set():
                try:
                    data, address = sock.recvfrom(4096)
                except (socket.timeout, TimeoutError):
                    continue
                except OSError:
                    if self._stop.is_set():
                        break
                    raise
                handle_discovery_packet(data, address, self.http_port, sock=sock)
        finally:
            sock.close()

    def stop(self) -> None:
        self._stop.set()
        sock = self._sock
        if sock is None:
            return
        try:
            sock.close()
        except OSError:
            pass


def run_discovery_server(http_port: int, discovery_port: int = DISCOVERY_PORT) -> None:
    DiscoveryServer(http_port, discovery_port).run()


def start_discovery_thread(http_port: int, discovery_port: int = DISCOVERY_PORT) -> threading.Thread:
    thread = threading.Thread(target=run_discovery_server, args=(http_port, discovery_port), daemon=True)
    thread.start()
    return thread


class DiscoveryThread:
    def __init__(
        self,
        http_port: int,
        discovery_port: int = DISCOVERY_PORT,
        socket_factory=socket.socket,
        poll_seconds: float = DISCOVERY_POLL_SECONDS,
    ) -> None:
        self.http_port = http_port
        self.discovery_port = discovery_port
        self.socket_factory = socket_factory
        self.poll_seconds = poll_seconds
        self.server: DiscoveryServer | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.server = DiscoveryServer(self.http_port, self.discovery_port, self.socket_factory, self.poll_seconds)
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        if not self.server:
            return
        self.server.stop()
        if self.thread:
            self.thread.join(timeout=self.poll_seconds + 0.5)

    def is_running(self) -> bool:
        return bool(self.thread and self.thread.is_alive())
