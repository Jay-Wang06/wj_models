# 网页剪藏器

本地运行的个人网页剪藏工具：粘贴文章 URL → 自动抽取正文与图片 → 保存为 Markdown，并可导出 PDF；支持标题/正文全文搜索。类似「个人版简悦 / Pocket」。

## 功能

- 粘贴任意文章链接，抽取标题、作者、站点、正文
- 下载文中图片到本地，并写入 Markdown 相对路径
- 预览抽取结果后再确认剪藏
- 本地库列表 + 关键词搜索（标题 / 正文 / 站点 / 作者）
- 在线阅读；一键下载 Markdown / PDF
- 数据全部保存在本机 `data/` 目录

## 快速开始（Windows）

1. 安装 [Python 3.10+](https://www.python.org/downloads/)
2. 双击 `启动.bat`（首次会自动创建虚拟环境并安装依赖）
3. 浏览器打开 http://127.0.0.1:8766

手动方式：

```bash
cd demo
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

## 使用说明

1. 在输入框粘贴文章 URL
2. 可选：点「预览」先看抽取效果（不下载图片）
3. 点「剪藏」保存到本地库
4. 在「我的剪藏」中搜索、阅读、下载 Markdown/PDF，或删除

## 配置

| 环境变量 | 说明 | 默认值 |
| --- | --- | --- |
| `CLIPPER_HOST` | 监听地址 | `127.0.0.1` |
| `CLIPPER_PORT` | 监听端口 | `8766` |
| `CLIPPER_DATA_DIR` | 数据目录 | `./data` |
| `CLIPPER_PROXY` | 全局代理，如 `http://127.0.0.1:7890` | 空 |
| `CLIPPER_MAX_IMAGES` | 单篇最多下载图片数 | `40` |
| `CLIPPER_TIMEOUT` | 请求超时（秒） | `25` |

## 项目结构

```
server/    FastAPI 后端（抽取 / 存储 / 导出）
web/       前端页面
data/      剪藏数据（index.json + clips/）
```

## 说明

- 部分站点有登录墙或强反爬，可能无法抽取；可在高级选项配置代理后重试。
- PDF 导出依赖系统中文字体（Windows 一般使用微软雅黑）。
- 正文抽取基于 [trafilatura](https://github.com/adbar/trafilatura)。
