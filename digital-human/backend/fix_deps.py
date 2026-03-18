#!/usr/bin/env python3
"""直接安装依赖到虚拟环境"""
import subprocess
import sys
import os

VENV_DIR = os.path.dirname(os.path.abspath(__file__))
PIP_PATH = os.path.join(VENV_DIR, 'venv', 'bin', 'pip')
PYTHON_PATH = os.path.join(VENV_DIR, 'venv', 'bin', 'python')

if not os.path.exists(PIP_PATH):
    print(f"❌ pip 不存在: {PIP_PATH}")
    sys.exit(1)

deps = ['numpy', 'opencv-python', 'onnxruntime-gpu', 'kaldi-native-fbank', 'soundfile', 'scipy']

print("🔧 安装依赖...")
for dep in deps:
    print(f"  安装 {dep}...")
    result = subprocess.run([PIP_PATH, 'install', dep], 
                          stdout=subprocess.PIPE, 
                          stderr=subprocess.PIPE,
                          text=True)
    if result.returncode == 0:
        print(f"  ✅ {dep}")
    else:
        print(f"  ⚠️ {dep}: {result.stderr[:100]}")

print("\n🔍 验证安装...")
result = subprocess.run([PYTHON_PATH, '-c', 'import numpy; print("numpy:", numpy.__version__)'],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
if result.returncode == 0:
    print(f"  ✅ {result.stdout.strip()}")
else:
    print(f"  ❌ numpy 验证失败: {result.stderr}")

print("\n🔍 验证模块导入...")
result = subprocess.run([PYTHON_PATH, '-c', 
                        'import sys; sys.path.insert(0, "."); from app.services.thg_service import DIHUMAN_AVAILABLE; print("thg_service:", DIHUMAN_AVAILABLE)'],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                       text=True, cwd=VENV_DIR)
if result.returncode == 0:
    print(f"  ✅ {result.stdout.strip()}")
else:
    print(f"  ❌ thg_service 导入失败: {result.stderr[:200]}")

print("\n✅ 完成！")

