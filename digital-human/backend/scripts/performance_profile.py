#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数字人推理与渲染性能分析脚本

用于定位「渲染帧率不足 20」的瓶颈：单帧推理耗时、Encoder/UNet、JPEG 编码、
以及算法上限（每 8 个特征帧才输出 1 帧图像）。

用法（在 backend 目录下）:
  python scripts/performance_profile.py
  python scripts/performance_profile.py --seconds 15 --warmup 2
"""

from __future__ import print_function

import os
import sys
import time
import argparse
import numpy as np

# 确保能导入 app
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# 在导入 dihuman_core 前可切到 CPU 测试（环境变量）
# USE_CPU=1 python scripts/performance_profile.py


def resolve_data_path():
    data_path = os.path.join(BACKEND_DIR, "stream_data")
    if not os.path.isdir(data_path):
        raise SystemExit("stream_data 目录不存在: %s" % data_path)
    return data_path


def run_profile(data_path: str, seconds: float = 10.0, warmup_seconds: float = 2.0, use_gpu: bool = True):
    from app.services.dihuman_core import (
        DiHumanProcessor,
        AUDIO_FRAME_SIZE,
        AUDIO_SAMPLE_RATE,
    )

    print("[性能分析] 加载 DiHumanProcessor (data_path=%s, use_gpu=%s) ..." % (data_path, use_gpu))
    t0 = time.perf_counter()
    processor = DiHumanProcessor(data_path, use_gpu=use_gpu)
    print("[性能分析] 加载耗时: %.2f s" % (time.perf_counter() - t0))

    chunk_size = AUDIO_FRAME_SIZE  # 10ms
    sample_rate = AUDIO_SAMPLE_RATE

    # 生成非静音合成音频（避免走静音/空闲分支）
    np.random.seed(42)
    synthetic_audio = (np.random.randn(chunk_size * 100).astype(np.float32) * 8000).astype(np.int16)

    # Warmup：让 pipeline 越过 AUDIO_PROCESS_THRESHOLD，进入稳定输出
    warmup_calls = max(100, int(warmup_seconds * sample_rate / chunk_size))
    print("[性能分析] Warmup: %d 次 process() ..." % warmup_calls)
    for i in range(warmup_calls):
        idx = (i * chunk_size) % (synthetic_audio.size - chunk_size)
        if idx + chunk_size > synthetic_audio.size:
            idx = 0
        frame = synthetic_audio[idx : idx + chunk_size].copy()
        processor.process(frame)
    print("[性能分析] Warmup 完成")

    # 正式计时
    total_calls = int(seconds * sample_rate / chunk_size)
    process_times_ms = []
    output_frame_times_ms = []  # 仅当 check_img==1 时记录
    jpeg_times_ms = []
    output_count = 0
    first_output_img = None

    import cv2

    print("[性能分析] 计时: %d 次 process() (~%.1f s 音频) ..." % (total_calls, total_calls * chunk_size / sample_rate))
    t_start = time.perf_counter()

    for i in range(total_calls):
        idx = (i * chunk_size) % (synthetic_audio.size - chunk_size)
        if idx + chunk_size > synthetic_audio.size:
            idx = 0
        frame = synthetic_audio[idx : idx + chunk_size].copy()

        t0 = time.perf_counter()
        return_img, _playing_audio, check_img = processor.process(frame)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        process_times_ms.append(elapsed_ms)

        if check_img == 1 and return_img is not None:
            output_count += 1
            output_frame_times_ms.append(elapsed_ms)
            if first_output_img is None:
                first_output_img = return_img.copy()
            # JPEG 编码耗时（每 10 帧测一次，减少对整体时长的影响）
            if output_count <= 20 or output_count % 10 == 0:
                tj0 = time.perf_counter()
                cv2.imencode(".jpg", return_img, [cv2.IMWRITE_JPEG_QUALITY, 95])
                jpeg_times_ms.append((time.perf_counter() - tj0) * 1000)

    wall_seconds = time.perf_counter() - t_start
    actual_fps = output_count / wall_seconds if wall_seconds > 0 else 0

    # 统计
    process_times_ms = np.array(process_times_ms)
    p50 = float(np.percentile(process_times_ms, 50))
    p95 = float(np.percentile(process_times_ms, 95))
    p99 = float(np.percentile(process_times_ms, 99))
    mean_process = float(np.mean(process_times_ms))

    print("")
    print("========== 性能分析结果 ==========")
    print("  总 process() 调用: %d" % total_calls)
    print("  输出帧数 (check_img==1): %d" % output_count)
    print("  实际墙钟时间: %.2f s" % wall_seconds)
    print("  实测输出帧率: %.2f FPS" % actual_fps)
    print("")
    print("  process() 耗时 (ms):")
    print("    平均: %.2f" % mean_process)
    print("    P50:  %.2f" % p50)
    print("    P95:  %.2f" % p95)
    print("    P99:  %.2f" % p99)
    print("")

    if output_frame_times_ms:
        out_ms = np.array(output_frame_times_ms)
        print("  仅「有输出帧」的 process() 耗时 (ms): 平均 %.2f, P95 %.2f" % (float(np.mean(out_ms)), float(np.percentile(out_ms, 95))))
        print("")

    if jpeg_times_ms:
        jpeg_ms = np.array(jpeg_times_ms)
        print("  JPEG 编码 (quality=95) 耗时 (ms): 平均 %.2f, P95 %.2f" % (float(np.mean(jpeg_ms)), float(np.percentile(jpeg_ms, 95))))
        print("")

    # 与 20 FPS 目标对比
    target_fps = 20
    if actual_fps < target_fps:
        print("  结论: 当前输出帧率 %.2f < 目标 %d FPS，瓶颈可能来自：" % (actual_fps, target_fps))
        if mean_process > 1000.0 / target_fps:
            print("    - 单次 process() 过慢 (平均 %.1f ms > %.0f ms/帧)" % (mean_process, 1000.0 / target_fps))
        print("    - 算法设计：每积累 8 个音频特征才输出 1 帧，理论上限约 2.5~5 FPS（取决于 encoder 步长）")
        print("    - 若单次 process() 含 ONNX 推理且 >50ms，会进一步拉低端到端 FPS")
    else:
        print("  结论: 当前输出帧率 %.2f >= 目标 %d FPS，后端推理非主瓶颈。" % (actual_fps, target_fps))
    print("===================================")
    return {
        "output_fps": actual_fps,
        "output_count": output_count,
        "mean_process_ms": mean_process,
        "p95_process_ms": p95,
        "jpeg_mean_ms": float(np.mean(jpeg_times_ms)) if jpeg_times_ms else None,
    }


def main():
    parser = argparse.ArgumentParser(description="数字人推理与渲染性能分析")
    parser.add_argument("--seconds", type=float, default=10.0, help="正式计时时长（秒）")
    parser.add_argument("--warmup", type=float, default=2.0, help="预热时长（秒）")
    parser.add_argument("--cpu", action="store_true", help="强制使用 CPU（不选则使用 dihuman_core 的 USE_GPU）")
    parser.add_argument("--data-path", type=str, default=None, help="stream_data 路径（默认 backend/stream_data）")
    args = parser.parse_args()

    data_path = args.data_path or resolve_data_path()
    use_gpu = not args.cpu
    run_profile(data_path, seconds=args.seconds, warmup_seconds=args.warmup, use_gpu=use_gpu)


if __name__ == "__main__":
    main()
