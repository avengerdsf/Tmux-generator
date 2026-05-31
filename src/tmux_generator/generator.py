from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
import re
import stat


@dataclass
class QuickCommandOptions:
    enabled: bool = False
    start: str = ""
    stop: str = ""


@dataclass
class ExportOptions:
    kind: str
    directory: Path | str
    quick: QuickCommandOptions = field(default_factory=QuickCommandOptions)
    bin_dir: Path | str | None = None


@dataclass
class ExportResult:
    files: list[Path]
    quick_commands: list[Path]


def shell_quote(value: object) -> str:
    return "'" + str(value).replace("'", "'\"'\"'") + "'"


def tmux_target(value: str) -> str:
    return value if value.startswith("$") else shell_quote(value)


def sanitize_command_name(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "_", str(value or "").strip()).lstrip("_")
    return cleaned or fallback


def session_name(config: dict) -> str:
    return sanitize_command_name(str(config.get("session") or "tmux_session"), "tmux_session")


def resolve_quick_commands(config: dict, quick: QuickCommandOptions) -> QuickCommandOptions:
    start = sanitize_command_name(quick.start, session_name(config))
    stop = sanitize_command_name(quick.stop, "kill-" + start)
    return QuickCommandOptions(enabled=quick.enabled, start=start, stop=stop)


def delete_quick_command_name(quick: QuickCommandOptions) -> str:
    return "del-" + quick.start


def _pane_rects(node: dict, rect: tuple[float, float, float, float], result: list[dict]) -> list[dict]:
    if node.get("type") == "pane":
        result.append({"id": node.get("id", ""), "pane": node, "rect": rect})
        return result
    children = node.get("children") or []
    count = len(children) or 1
    x, y, w, h = rect
    for index, child in enumerate(children):
        if node.get("direction") == "row":
            _pane_rects(child, (x + w * index / count, y, w / count, h), result)
        else:
            _pane_rects(child, (x, y + h * index / count, w, h / count), result)
    return result


def ordered_panes(window: dict) -> list[dict]:
    rects = _pane_rects(window.get("layout") or {}, (0, 0, 1, 1), [])
    rects.sort(key=lambda item: (round(item["rect"][0], 6), round(item["rect"][1], 6), item["id"]))
    return [{**item, "order": index + 1} for index, item in enumerate(rects)]


def _pane_order_map(window: dict) -> dict[str, int]:
    return {item["id"]: item["order"] for item in ordered_panes(window)}


def _pane_order_label(order: int) -> str:
    return str(order).zfill(2)


def _yaml_node(node: dict, window: dict, indent: int = 0) -> list[str]:
    sp = " " * indent
    if node.get("type") == "pane":
        order = _pane_order_map(window).get(node.get("id", ""), 0)
        return [
            f"{sp}- type: pane",
            f"{sp}  order: {order}",
            f"{sp}  id: {node.get('id', '')}",
            f"{sp}  title: {json.dumps(node.get('title', ''), ensure_ascii=False)}",
            f"{sp}  command: {json.dumps(node.get('command', ''), ensure_ascii=False)}",
        ]
    lines = [
        f"{sp}- type: split",
        f"{sp}  direction: {node.get('direction', 'row')}",
        f"{sp}  ratio: {node.get('ratio', 50)}",
        f"{sp}  children:",
    ]
    for child in node.get("children") or []:
        lines.extend(_yaml_node(child, window, indent + 4))
    return lines


def generate_yaml(config: dict, quick: QuickCommandOptions | None = None) -> str:
    quick = quick or QuickCommandOptions()
    quick = resolve_quick_commands(config, quick)
    lines = [f"session: {json.dumps(session_name(config), ensure_ascii=False)}"]
    if quick.enabled:
        delete = delete_quick_command_name(quick)
        lines.extend(
            [
                "quick_commands:",
                "  enabled: true",
                f"  start: {json.dumps(quick.start, ensure_ascii=False)}",
                f"  stop: {json.dumps(quick.stop, ensure_ascii=False)}",
                f"  delete: {json.dumps(delete, ensure_ascii=False)}",
            ]
        )
    lines.append("windows:")
    for window in config.get("windows") or []:
        lines.append(f"  - name: {json.dumps(window.get('name', 'main'), ensure_ascii=False)}")
        lines.append("    layout:")
        node_lines = _yaml_node(window.get("layout") or {"type": "pane"}, window, 6)
        node_lines[0] = node_lines[0].replace("      - ", "      root:\n        - ", 1)
        lines.extend(node_lines)
    return "\n".join(lines) + "\n"


def _tmux_node(node: dict, target: str, commands: list[str], window: dict) -> None:
    if node.get("type") == "pane":
        order = _pane_order_map(window).get(node.get("id", ""), 0)
        raw_title = node.get("title") or node.get("id", "")
        title = f"[{_pane_order_label(order)}] {raw_title}"
        commands.append(f"# pane {_pane_order_label(order)} / {node.get('id', '')} / {node.get('title', '')}")
        commands.append(f"tmux set-option -p -t {tmux_target(target)} @my_title {shell_quote(raw_title)}")
        commands.append(f"tmux select-pane -t {tmux_target(target)} -T {shell_quote(title)}")
        if node.get("command"):
            commands.append(f"tmux send-keys -t {tmux_target(target)} {shell_quote(node['command'])} C-m")
        return
    children = node.get("children") or []
    if not children:
        return
    _tmux_node(children[0], target, commands, window)
    for index, child in enumerate(children[1:]):
        flag = "-h" if node.get("direction") == "row" else "-v"
        first_pane = ordered_panes({"layout": child})[0]
        child_target = "$pane_" + _pane_order_label(_pane_order_map(window).get(first_pane["id"], index + 2))
        commands.append(f"{child_target[1:]}=$(tmux split-window {flag} -t {tmux_target(target)} -P -F '#{{pane_id}}')")
        _tmux_node(child, child_target, commands, window)


def tmux_commands(config: dict, include_comments: bool = True) -> list[str]:
    windows = config.get("windows") or [{"name": "main", "layout": {"type": "pane"}}]
    session = session_name(config)
    commands: list[str] = []
    if include_comments:
        commands.extend(["# 启动命令", "# pane order: top-to-bottom first, then left-to-right"])
    commands.append(f"tmux new-session -d -s {shell_quote(session)} -n {shell_quote(windows[0].get('name', 'main'))}")
    commands.append(f"tmux set-window-option -t {shell_quote(session)} pane-border-status top")
    commands.append(f"tmux set-window-option -t {shell_quote(session)} pane-border-format {shell_quote(' [ #{@my_title} ] ')}")
    commands.append(f"tmux set-option -t {shell_quote(session)} mouse on")
    commands.append(f"tmux set-option -t {shell_quote(session)} allow-rename off")
    for index, window in enumerate(windows):
        if index > 0:
            commands.append(f"tmux new-window -t {shell_quote(session)} -n {shell_quote(window.get('name', 'window'))}")
        _tmux_node(window.get("layout") or {"type": "pane"}, f"{session}:{index}.0", commands, window)
    commands.append(f"tmux attach -t {shell_quote(session)}")
    return commands


def close_commands(config: dict) -> list[str]:
    session = session_name(config)
    return ["# 关闭命令", f"tmux has-session -t {shell_quote(session)} 2>/dev/null && tmux kill-session -t {shell_quote(session)} || true"]


def generate_script(config: dict, export_dir: str | Path, quick: QuickCommandOptions | None = None) -> str:
    quick = quick or QuickCommandOptions()
    quick = resolve_quick_commands(config, quick)
    script_path = Path(export_dir) / f"{session_name(config)}.sh"
    lines = ["#!/usr/bin/env bash", "set -e", "", "# Generated by tmux session orchestrator demo", f"# Export dir: {export_dir}", "# Pane order: top-to-bottom first, then left-to-right"]
    if quick.enabled:
        delete = delete_quick_command_name(quick)
        lines.extend(
            [
                f"# Quick start command: {quick.start}",
                f"# Quick stop command: {quick.stop}",
                f"# Quick delete command: {delete}",
                "# Install quick commands after exporting:",
                '#   mkdir -p "$HOME/.local/bin"',
                f"#   ln -sf {shell_quote(script_path)} \"$HOME/.local/bin/{quick.start}\"",
                f"#   cat > \"$HOME/.local/bin/{quick.stop}\" <<'EOF'",
                "#   #!/usr/bin/env bash",
                "#   " + close_commands(config)[1],
                "#   EOF",
                f"#   cat > \"$HOME/.local/bin/{delete}\" <<'EOF'",
                "#   #!/usr/bin/env bash",
                f"#   rm -f \"$HOME/.local/bin/{quick.start}\" \"$HOME/.local/bin/{quick.stop}\" \"$HOME/.local/bin/{delete}\"",
                "#   EOF",
                f"#   chmod +x {shell_quote(script_path)} \"$HOME/.local/bin/{quick.stop}\" \"$HOME/.local/bin/{delete}\"",
            ]
        )
    lines.extend(["", *close_commands(config)[1:], "", *tmux_commands(config, include_comments=False)])
    return "\n".join(lines) + "\n"


def export_files(config: dict, options: ExportOptions) -> ExportResult:
    if options.kind not in {"yaml", "sh", "both"}:
        raise ValueError("kind must be yaml, sh, or both")
    directory = Path(options.directory).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    session = session_name(config)
    files: list[Path] = []
    if options.kind in {"yaml", "both"}:
        path = directory / f"{session}.yaml"
        path.write_text(generate_yaml(config, options.quick), encoding="utf-8")
        files.append(path)
    if options.kind in {"sh", "both"}:
        path = directory / f"{session}.sh"
        path.write_text(generate_script(config, directory, options.quick), encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        files.append(path)
    quick_paths = _install_quick_commands(config, files, options)
    return ExportResult(files=files, quick_commands=quick_paths)


def _install_quick_commands(config: dict, files: list[Path], options: ExportOptions) -> list[Path]:
    if not options.quick.enabled:
        return []
    script = next((path for path in files if path.suffix == ".sh"), None)
    if script is None:
        script = Path(options.directory) / f"{session_name(config)}.sh"
        script.write_text(generate_script(config, options.directory, options.quick), encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    bin_dir = Path(options.bin_dir or Path.home() / ".local" / "bin").expanduser()
    bin_dir.mkdir(parents=True, exist_ok=True)
    quick = resolve_quick_commands(config, options.quick)
    start = bin_dir / quick.start
    stop = bin_dir / quick.stop
    delete = bin_dir / delete_quick_command_name(quick)
    if start.exists() or start.is_symlink():
        start.unlink()
    start.symlink_to(script)
    if stop.exists() or stop.is_symlink():
        stop.unlink()
    stop.write_text("#!/usr/bin/env bash\n" + close_commands(config)[1] + "\n", encoding="utf-8")
    stop.chmod(stop.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    if delete.exists() or delete.is_symlink():
        delete.unlink()
    delete.write_text("#!/usr/bin/env bash\nrm -f " + " ".join(shell_quote(path) for path in [start, stop, delete]) + "\n", encoding="utf-8")
    delete.chmod(delete.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return [start, stop, delete]
