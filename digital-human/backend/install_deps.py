#!/usr/bin/env python3
"""安装 THG 相关依赖到虚拟环境"""
import subprocess
import sys
import os

# 获取虚拟环境的 pip 路径
venv_pip = os.path.join(os.path.dirname(__file__), 'venv', 'bin', 'pip')

if not os.path.exists(venv_pip):
    print(f"❌ 虚拟环境不存在: {venv_pip}")
    sys.exit(1)

dependencies = [
    'numpy',
    'opencv-python',
    'onnxruntime-gpu',
    'kaldi-native-fbank',
    'soundfile',
    'scipy'
]

print("🔧 正在安装依赖...")
for dep in dependencies:
    print(f"  安装 {dep}...")
    result = subprocess.run([venv_pip, 'install', dep], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"  ✅ {dep} 安装成功")
    else:
        print(f"  ⚠️ {dep} 安装可能有问题: {result.stderr[:100]}")

print("\n✅ 依赖安装完成！")

# 验证安装
venv_python = os.path.join(os.path.dirname(__file__), 'venv', 'bin', 'python')
print("\n🔍 验证安装...")
try:
    result = subprocess.run([venv_python, '-c', 'import numpy; print("numpy:", numpy.__version__)'], 
                          capture_output=True, text=True, cwd=os.path.dirname(__file__))
    if result.returncode == 0:
        print(f"  ✅ {result.stdout.strip()}")
    else:
        print(f"  ❌ 验证失败: {result.stderr}")
except Exception as e:
    print(f"  ❌ 验证异常: {e}")

