#!/usr/bin/env python3
"""测试 THG 配置和初始化"""
import os
import sys

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(__file__))

from app.config import settings
from app.services.orchestrator import DigitalHumanOrchestrator

print("=" * 50)
print("THG 配置测试")
print("=" * 50)

print(f"\n1. 配置检查:")
print(f"   thg_data_path: {settings.thg_data_path}")
print(f"   thg_use_gpu: {settings.thg_use_gpu}")

print(f"\n2. 路径检查:")
if settings.thg_data_path:
    exists = os.path.exists(settings.thg_data_path)
    print(f"   {settings.thg_data_path}: {'✅ 存在' if exists else '❌ 不存在'}")
    if exists:
        abs_path = os.path.abspath(settings.thg_data_path)
        print(f"   绝对路径: {abs_path}")
        files = os.listdir(settings.thg_data_path)
        print(f"   包含 {len(files)} 个文件/目录")
        for f in files[:10]:
            print(f"     - {f}")
        if len(files) > 10:
            print(f"     ... 还有 {len(files) - 10} 个")
else:
    print("   thg_data_path 未配置")

# 检查相对路径
rel_path = "./stream_data"
if os.path.exists(rel_path):
    print(f"   相对路径 {rel_path}: ✅ 存在")

print(f"\n3. Orchestrator 初始化测试:")
try:
    orchestrator = DigitalHumanOrchestrator()
    service_type = type(orchestrator.thg_service).__name__
    print(f"   使用的服务: {service_type}")
    if service_type == "RealTHGService":
        print("   ✅ 成功使用 RealTHGService")
    else:
        print("   ⚠️ 使用的是 MockTHGService")
except Exception as e:
    print(f"   ❌ 初始化失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 50)

