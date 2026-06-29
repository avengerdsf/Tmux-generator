from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import load_ui_config, save_ui_config
from .generator import (
    ExportOptions,
    QuickCommandOptions,
    close_commands,
    export_files,
    generate_script,
    generate_yaml,
    import_script,
    session_name,
    tmux_commands,
)
from .lifecycle import PageLifecycle


class PageRequest(BaseModel):
    page_id: str


class QuickRequest(BaseModel):
    enabled: bool = False
    start: str = ""
    stop: str = ""


class PreviewRequest(BaseModel):
    config: dict
    directory: str = "."
    quick: QuickRequest = Field(default_factory=QuickRequest)


class ExportRequest(PreviewRequest):
    kind: str = "yaml"
    bin_dir: str | None = None
    previous_quick: QuickRequest | None = None


class ImportShRequest(BaseModel):
    script: str


class TmuxRequest(BaseModel):
    config: dict


class ConfigCacheRequest(BaseModel):
    config: dict
    preferences: dict = Field(default_factory=dict)


def preview_payload(config: dict, directory: str, quick: QuickCommandOptions | None = None) -> dict:
    quick = quick or QuickCommandOptions()
    return {
        "yaml": generate_yaml(config, quick),
        "script": generate_script(config, directory, quick),
        "commands": "\n".join([*tmux_commands(config), "", *close_commands(config)]),
    }


def export_payload(
    config: dict,
    kind: str,
    directory: str,
    quick: QuickCommandOptions,
    bin_dir: str | None = None,
    previous_quick: QuickCommandOptions | None = None,
) -> dict:
    result = export_files(config, ExportOptions(kind=kind, directory=directory, quick=quick, bin_dir=bin_dir, previous_quick=previous_quick))
    return {
        "files": [str(path) for path in result.files],
        "quick_commands": [str(path) for path in result.quick_commands],
        "quick": {"enabled": result.quick.enabled, "start": result.quick.start, "stop": result.quick.stop},
    }


def import_sh_payload(script: str) -> dict:
    try:
        return import_script(script)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _quick(value: QuickRequest) -> QuickCommandOptions:
    return QuickCommandOptions(enabled=value.enabled, start=value.start, stop=value.stop)


def _model_data(model: BaseModel) -> dict:
    model_dump = getattr(model, "model_dump", None)
    if model_dump:
        return model_dump()
    return model.dict()


def list_directory(path: str) -> dict:
    target = Path(path).expanduser()
    while not target.exists() and target != target.parent:
        target = target.parent
    if not target.is_dir():
        raise HTTPException(status_code=404, detail="directory not found")
    entries = [{"name": item.name, "type": "dir"} for item in sorted(target.iterdir()) if item.is_dir()]
    return {"path": str(target), "parent": str(target.parent if target != target.parent else target), "entries": entries}


def open_terminal(command: str) -> dict:
    terminals = [
        ("x-terminal-emulator", ["x-terminal-emulator", "-e", "bash", "-lc", command]),
        ("gnome-terminal", ["gnome-terminal", "--", "bash", "-lc", command]),
        ("konsole", ["konsole", "-e", "bash", "-lc", command]),
        ("xfce4-terminal", ["xfce4-terminal", "--command", "bash -lc " + subprocess.list2cmdline([command])]),
        ("xterm", ["xterm", "-e", "bash", "-lc", command]),
    ]
    for name, args in terminals:
        if shutil.which(name):
            subprocess.Popen(args)
            return {"opened": True, "terminal": name}
    return {"opened": False, "terminal": ""}


def start_tmux_session(config: dict) -> dict:
    script = generate_script(config, ".", QuickCommandOptions())
    terminal = open_terminal(script)
    return {"returncode": 0 if terminal["opened"] else 1, "terminal_opened": terminal["opened"], "terminal": terminal["terminal"]}


def stop_tmux_session(config: dict) -> dict:
    command = close_commands(config)[1]
    process = subprocess.run(["bash", "-lc", command], text=True, capture_output=True, check=False)
    return {"returncode": process.returncode, "stdout": process.stdout, "stderr": process.stderr, "session": session_name(config)}


def create_app(discovery=None) -> FastAPI:
    app = FastAPI(title="tmux-generator")
    static_dir = Path(__file__).with_name("static")
    lifecycle = PageLifecycle(
        on_active=discovery.start if discovery else None,
        on_idle=discovery.stop if discovery else None,
    )
    app.state.page_lifecycle = lifecycle

    @app.get("/")
    def index():
        return FileResponse(static_dir / "index.html")

    @app.get("/api/health")
    def health():
        return {"ok": True, "service": "tmux_generator"}

    @app.get("/api/page/status")
    def page_status():
        return lifecycle.status()

    @app.post("/api/page/heartbeat")
    def page_heartbeat(request: PageRequest):
        return lifecycle.heartbeat(request.page_id)

    @app.post("/api/page/leave")
    def page_leave(request: PageRequest):
        return lifecycle.leave(request.page_id)

    @app.get("/api/fs/list")
    def fs_list(path: str = "/"):
        return list_directory(path)

    @app.get("/api/config")
    def get_config():
        return load_ui_config()

    @app.post("/api/config")
    def save_config(request: ConfigCacheRequest):
        return save_ui_config(_model_data(request))

    @app.post("/api/preview")
    def preview(request: PreviewRequest):
        return preview_payload(request.config, request.directory, _quick(request.quick))

    @app.post("/api/export")
    def export(request: ExportRequest):
        previous_quick = _quick(request.previous_quick) if request.previous_quick else None
        return export_payload(request.config, request.kind, request.directory, _quick(request.quick), request.bin_dir, previous_quick)

    @app.post("/api/import/sh")
    def import_sh(request: ImportShRequest):
        return import_sh_payload(request.script)

    @app.post("/api/tmux/start")
    def start_tmux(request: TmuxRequest):
        return start_tmux_session(request.config)

    @app.post("/api/tmux/stop")
    def stop_tmux(request: TmuxRequest):
        return stop_tmux_session(request.config)

    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    return app
