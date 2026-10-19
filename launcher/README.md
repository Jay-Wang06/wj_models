# 统一启动台

本地小工具的总入口：查看各服务是否在线，一键启动 / 停止，并在浏览器中打开。

## 功能

- 卡片展示 `video_dl` / `web_clipper` / `snap_ocr` / `local_notes` / `focus_todo`
- 自动检测端口占用与 `/api/health`
- 启动：弹出独立控制台（优先走各目录 `启动.bat`，首次可自动建 venv）
- 停止：结束占用对应端口的进程
- 全部启动、定时刷新状态

## 快速开始（Windows）

1. 安装 [Python 3.10+](https://www.python.org/downloads/)
2. 双击 `启动.bat`
3. 浏览器打开 http://127.0.0.1:8764

手动方式：

```bash
cd launcher
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

## 配置

| 环境变量 | 说明 | 默认值 |
| --- | --- | --- |
| `LAUNCHER_HOST` | 监听地址 | `127.0.0.1` |
| `LAUNCHER_PORT` | 监听端口 | `8764` |

## 项目结构

```
server/   FastAPI 后端（状态检测 / 启停）
web/      前端页面
```

## 说明

- 启动台本身不会代替各工具的依赖安装；某个工具第一次启动时，控制台里可能会跑一段时间 `pip install`。
- 「停止」只结束对应端口进程，不会删除任何数据。
- 工具目录列表写在 `server/config.py` 的 `TOOLS` 中，以后加新工具改这里即可。
