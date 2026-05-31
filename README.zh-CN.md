# tmux-generator

用于创建、预览、导出、启动和关闭 tmux session 脚本的 Web 工具。

## 功能

- 在浏览器中编辑 session、window、pane、pane 标题、启动命令和标签。
- 预览生成的 YAML 和 shell 脚本。
- 将 YAML、shell 脚本或两者导出到服务端目录。
- 可选安装启动、关闭、删除三个短命令。
- 将界面配置缓存到 `.codex/tmux-generator-ui.json`。
- 从 Web 页面启动 tmux 时打开本地终端，关闭时终止对应 tmux session。
- 支持 UDP 广播发现服务。

## 环境要求

- Python 3.9+
- tmux
- 后台服务启动 tmux 时，本机需要存在以下终端命令之一：`x-terminal-emulator`、`gnome-terminal`、`konsole`、`xfce4-terminal`、`xterm`

## 安装

```bash
pip install -e .
```

## 启动

```bash
tmux-generator
```

默认服务地址：

```text
0.0.0.0:6060
```

浏览器打开：

```text
http://127.0.0.1:6060
```

## 服务配置

可选配置文件路径：

```text
~/.tmux-generator/config.json
```

示例：

```json
{
  "host": "0.0.0.0",
  "port": 6060
}
```

## 测试

```bash
PYTHONPATH=src python -m unittest
```
