# 番茄钟 · 今日待办

本地运行的专注小工具：番茄钟计时 + 今日待办清单，数据保存在本机。

## 功能

- 专注 / 短休 / 长休三种模式，可自定义时长
- 开始 / 暂停 / 重置；结束时提示音与浏览器通知
- 专注完成后自动切换到短休（每 N 次进入长休）
- 今日待办：添加、勾选完成、删除、清除已完成
- 可把当前专注关联到某条待办（计入该条的番茄数）
- 今日统计：完成番茄数 / 专注分钟 / 未完成待办数

## 快速开始（Windows）

1. 安装 [Python 3.10+](https://www.python.org/downloads/)
2. 双击 `启动.bat`
3. 浏览器打开 http://127.0.0.1:8769

手动方式：

```bash
cd focus_todo
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

也可从仓库的 [`launcher`](../launcher/) 统一启动台启动本工具。

## 配置

| 环境变量 | 说明 | 默认值 |
| --- | --- | --- |
| `FOCUS_HOST` | 监听地址 | `127.0.0.1` |
| `FOCUS_PORT` | 监听端口 | `8769` |
| `FOCUS_DATA_DIR` | 数据目录 | `./data` |

## 项目结构

```
server/   FastAPI 后端
web/      前端页面
data/     本地 JSON（待办与今日统计）
```
