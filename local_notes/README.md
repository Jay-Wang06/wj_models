# 本地笔记 / 闪念

本地运行的 Markdown 笔记工具：写笔记、打标签、全文搜索；支持「粘贴即存」——粘贴 URL 存书签，粘贴文字存闪念。

## 功能

- Markdown 笔记编辑与预览
- 标签管理与筛选
- 标题 / 正文 / 标签全文搜索
- 粘贴即存：URL → 书签；文本 → 闪念
- 笔记类型：笔记 / 闪念 / 书签
- 数据全部保存在本机 `data/`

## 快速开始（Windows）

1. 安装 [Python 3.10+](https://www.python.org/downloads/)
2. 双击 `启动.bat`
3. 浏览器打开 http://127.0.0.1:8768

手动方式：

```bash
cd demo
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

## 快捷操作

| 操作 | 说明 |
| --- | --- |
| 粘贴区 `Ctrl+Enter` | 立即保存闪念/书签 |
| 编辑区 `Ctrl+S` | 保存当前笔记 |
| 预览按钮 | 分栏预览 Markdown |

## 配置

| 环境变量 | 说明 | 默认值 |
| --- | --- | --- |
| `NOTES_HOST` | 监听地址 | `127.0.0.1` |
| `NOTES_PORT` | 监听端口 | `8768` |
| `NOTES_DATA_DIR` | 数据目录 | `./data` |

## 项目结构

```
server/   FastAPI 后端
web/      前端页面
data/     笔记数据（index.json + notes/*.md）
```
