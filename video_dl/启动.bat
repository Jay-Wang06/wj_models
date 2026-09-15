@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动 视频下载助手 ...
if not exist ".venv" (
    echo 首次运行，正在创建虚拟环境并安装依赖...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)
python run.py
pause
