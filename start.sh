#!/bin/bash

# 设置脚本编码
export LANG=zh_CN.UTF-8

echo "========================================"
echo "哔哩哔哩关注列表批量管理工具"
echo "Bilibili Following List Batch Management Tool"
echo "========================================"
echo
echo "[免责声明] 本工具仅供学习研究使用，存在账号风险！"
echo "[风险提示] 使用本工具可能导致账号被限制或封禁！"
echo "[重要提醒] 继续使用即表示您同意承担所有风险！"
echo
echo "详细免责声明请查看: DISCLAIMER.md"
echo
read -p "是否同意免责声明并继续使用？(输入 y 继续, 其他键退出): " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "已取消启动。"
    exit 0
fi
echo

# 检查Python是否安装
if ! command -v python3 &> /dev/null; then
    echo "[错误] 未找到Python3，请先安装Python 3.8或更高版本"
    echo "Ubuntu/Debian: sudo apt-get install python3 python3-pip python3-venv"
    echo "CentOS/RHEL: sudo yum install python3 python3-pip"
    echo "macOS: brew install python3"
    exit 1
fi

echo "[信息] 检查Python版本..."
python3 --version

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "[信息] 创建虚拟环境..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "[错误] 创建虚拟环境失败"
        exit 1
    fi
fi

# 激活虚拟环境
echo "[信息] 激活虚拟环境..."
source venv/bin/activate

# 升级pip
echo "[信息] 升级pip..."
python -m pip install --upgrade pip

# 安装依赖
echo "[信息] 安装依赖包..."
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "[错误] 安装依赖失败"
    exit 1
fi

# 检查配置文件
if [ ! -f "config/config.json" ]; then
    echo "[警告] 配置文件不存在，将在首次运行时创建"
    echo "[提示] 请在设置页面配置哔哩哔哩Cookie"
    echo
fi

# 启动应用
echo "[信息] 启动应用程序..."
echo "[提示] 应用启动后将自动打开浏览器"
echo "[提示] 如果浏览器未自动打开，请手动访问: http://127.0.0.1:8080"
echo

python main.py

# 如果程序异常退出，显示错误信息
if [ $? -ne 0 ]; then
    echo
    echo "[错误] 程序异常退出"
    read -p "按任意键继续..."
fi

echo
echo "感谢使用哔哩哔哩关注列表管理工具！" 