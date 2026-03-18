#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
pip install -r requirements.txt
echo "✅ 依赖安装完成"

