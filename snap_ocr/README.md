# OCR 截图翻译

本地运行的办公小工具：粘贴截图 → OCR 识字 → 复制原文，或生成中英对照译文。

## 功能

- `Ctrl+V` 粘贴截图 / 拖拽上传 / 选择文件
- 本地 OCR（RapidOCR，中英文）
- 自动或手动翻译（中↔英）
- 一键复制原文、译文、中英对照
- 数据仅在本机处理；翻译需访问外网翻译接口

## 快速开始（Windows）

1. 安装 [Python 3.10+](https://www.python.org/downloads/)
2. 双击 `启动.bat`（首次会创建虚拟环境并安装依赖）
3. 浏览器打开 http://127.0.0.1:8767

手动方式：

```bash
cd demo
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

## 使用说明

1. 用系统截图工具截取需要识别的区域
2. 在页面虚线框内按 `Ctrl+V`（或点「从剪贴板粘贴」）
3. 查看「识别原文」，需要时切换「译文 / 中英对照」
4. 点复制按钮即可粘贴到文档、邮件、IM

## 配置

| 环境变量 | 说明 | 默认值 |
| --- | --- | --- |
| `OCR_HOST` | 监听地址 | `127.0.0.1` |
| `OCR_PORT` | 监听端口 | `8767` |
| `OCR_MAX_IMAGE_BYTES` | 单图大小上限 | `12582912`（12MB） |

## 说明

- OCR 首次运行会加载 ONNX 模型，可能稍慢。
- 翻译默认使用 Google 翻译（经 `deep-translator`），需要能访问外网；若失败仍可只使用识字结果。
- 模糊、倾斜、艺术字截图识别率会下降，尽量截清晰区域。

## 项目结构

```
server/   FastAPI 后端（OCR / 翻译）
web/      前端页面
```
