@echo off
chcp 65001 >nul
echo ========================================
echo 哔哩哔哩关注列表批量管理工具
echo Bilibili Following List Batch Management Tool
echo ========================================
echo.

REM 检查Python是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到Python，请先安装Python 3.8或更高版本
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [信息] 检查Python版本...
python --version

REM 检查虚拟环境
if not exist "venv" (
    echo [信息] 创建虚拟环境...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [错误] 创建虚拟环境失败
        pause
        exit /b 1
    )
)

REM 激活虚拟环境
echo [信息] 激活虚拟环境...
call venv\Scripts\activate.bat

REM 升级pip
echo [信息] 升级pip...
python -m pip install --upgrade pip

REM 安装依赖
echo [信息] 安装依赖包...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [错误] 安装依赖失败
    pause
    exit /b 1
)

REM 检查配置文件
if not exist "config\config.json" (
    echo [警告] 配置文件不存在，将在首次运行时创建
    echo [提示] 请在设置页面配置哔哩哔哩Cookie
    echo.
)

REM 启动应用
echo [信息] 启动应用程序...
echo [提示] 应用启动后将自动打开浏览器
echo [提示] 如果浏览器未自动打开，请手动访问: http://127.0.0.1:8080
echo.

python main.py

REM 如果程序异常退出，暂停以查看错误信息
if %errorlevel% neq 0 (
    echo.
    echo [错误] 程序异常退出，错误代码: %errorlevel%
    pause
)

echo.
echo 感谢使用哔哩哔哩关注列表管理工具！
pause 