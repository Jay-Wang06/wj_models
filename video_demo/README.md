# 视频下载助手

一个本地运行的视频下载网站：粘贴视频网址（如 B 站视频链接）→ 自动解析可选清晰度 → 选择后下载到本地。

后端基于 [yt-dlp](https://github.com/yt-dlp/yt-dlp)，支持 Bilibili 及大量其它网站（YouTube、抖音、微博等，视站点限制而定）。内置 `curl_cffi` Chrome TLS 指纹伪装，规避 B 站等站点对非浏览器请求的拦截。

## 功能

- 解析视频信息：标题、UP主、时长、封面、播放量
- 按分辨率列出真实可用的下载选项（4K / 1080P / 720P / …），并标注编码（AVC / HEVC / AV1）、是否 60 帧、预估文件大小
- 支持分 P / 合集选择
- 下载进度实时显示（百分比 / 速度 / 剩余时间），完成后一键保存到本地
- 下载记录管理（保存 / 删除 / 打开文件夹）
- 可选：粘贴 B 站 SESSDATA，解锁 1080P+ / 4K 等高画质

## 快速开始（Windows）

1. 安装 [Python 3.10+](https://www.python.org/downloads/)
2. 双击 `启动.bat`（首次会自动创建虚拟环境并安装依赖）
3. 浏览器打开 `http://127.0.0.1:8765`

手动方式：

```bash
pip install -r requirements.txt
python run.py
```

## ffmpeg（重要）

1080P 以上通常需要把「视频流 + 音轨」合并，这一步依赖 [ffmpeg](https://ffmpeg.org/download.html)：

- 将 `ffmpeg.exe` 放入项目根目录的 `ffmpeg/` 文件夹；或
- 安装 ffmpeg 并加入系统 PATH

没有 ffmpeg 时，界面会自动禁用需要合并的选项（仅音频、单文件选项不受影响）。

## 使用 B 站更高清晰度（可选）

登录 [bilibili.com](https://www.bilibili.com)，在浏览器开发者工具 → Application → Cookies 中找到 `SESSDATA`，粘贴到页面「高级选项」中即可。该值仅保存在本机，用于本地 yt-dlp 请求。

也可以把导出的 Netscape 格式 `cookies.txt` 放到项目根目录，程序会自动使用。

## 常见问题

**解析时提示「远程主机强迫关闭连接 / Connection was reset」（WinError 10054 / curl 35）**

先用页面上的「网络诊断」按钮确认从当前网络能否连到 B 站主站/API：

- 若诊断显示 B 站主站/API **不可连接**：说明当前网络的 IP 被 B 站拦截（常见于云服务器、机房、部分代理出口）。此时任何配置都无法绕过，请：
  1. 在本机（能正常打开 B 站的网络）运行本程序；或
  2. 在「高级选项」填写一个能访问 B 站的代理地址（如 `http://127.0.0.1:7890`），或用环境变量 `VIDEODL_PROXY` 设置全局代理
- 若诊断显示**可连接**但仍报错：多为临时风控，请：
  1. 直接重试解析（程序已自动换用 Chrome/Edge/Firefox/Safari 指纹重试）
  2. 在「高级选项」粘贴 B 站登录后的 `SESSDATA` 再试
  3. 用 `python -m yt_dlp -U` 确认 yt-dlp 已是最新

**下载 1080P 以上失败 / 提示需要 ffmpeg**

请参考上方「ffmpeg（重要）」一节安装 ffmpeg。

## 配置

| 环境变量 | 说明 | 默认值 |
| --- | --- | --- |
| `VIDEODL_HOST` | 监听地址 | `127.0.0.1` |
| `VIDEODL_PORT` | 监听端口 | `8765` |
| `VIDEODL_DOWNLOAD_DIR` | 下载文件保存目录 | `./downloads` |
| `FFMPEG_LOCATION` | ffmpeg 可执行文件路径 | 自动检测 |
| `VIDEODL_PROXY` | 全局代理地址，如 `http://127.0.0.1:7890` | 空 |
| `VIDEODL_FORCE_IPV4` | 强制 IPv4（修复部分连接被重置） | `1` |

## 项目结构

```
server/    FastAPI 后端（解析 / 下载任务）
web/       前端页面
downloads/ 下载的文件（按任务分目录）
```
