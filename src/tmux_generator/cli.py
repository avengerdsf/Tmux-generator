from __future__ import annotations

import argparse

import uvicorn

from .api import create_app
from .config import DEFAULT_CONFIG_PATH, load_config
from .discovery import DISCOVERY_PORT, start_discovery_thread


def main() -> None:
    file_config = load_config()
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=file_config.host)
    parser.add_argument("--port", type=int, default=file_config.port)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--no-discovery", action="store_true")
    parser.add_argument("--discovery-port", type=int, default=DISCOVERY_PORT)
    args = parser.parse_args()
    if args.config != str(DEFAULT_CONFIG_PATH):
        file_config = load_config(args.config)
        args.host = file_config.host
        args.port = file_config.port
    if not args.no_discovery:
        start_discovery_thread(args.port, args.discovery_port)
    uvicorn.run(create_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
