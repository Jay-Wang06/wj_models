# wj_models

本地小工具集合。

## 推荐入口

先启动统一启动台，再从网页里启停 / 打开其它工具：

| 目录 | 说明 | 端口 |
| --- | --- | --- |
| [`launcher`](launcher/) | **统一启动台**（总入口） | `8764` |

进入 `launcher/`，双击 `启动.bat`，浏览器打开 http://127.0.0.1:8764 。

## 项目

| 目录 | 说明 | 端口 |
| --- | --- | --- |
| [`video_dl`](video_dl/) | 视频下载助手（B 站等） | `8765` |
| [`web_clipper`](web_clipper/) | 网页剪藏器（正文抽取 / Markdown / PDF / 搜索） | `8766` |
| [`snap_ocr`](snap_ocr/) | OCR 截图翻译（粘贴识字 / 中英对照） | `8767` |
| [`local_notes`](local_notes/) | 本地笔记 / 闪念（Markdown · 标签 · 全文搜索） | `8768` |
| [`focus_todo`](focus_todo/) | 番茄钟 · 今日待办 | `8769` |

也可进入对应目录，双击 `启动.bat` 或执行 `python run.py` 单独启动。
