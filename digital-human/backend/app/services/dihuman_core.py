# -*- coding: utf-8 -*-
"""
数字人流式推理核心模块
使用方法: 修改文件头部的配置参数即可
"""

# ==================== 配置参数（修改这里即可）====================
# ONNX 模型文件配置
UNET_MODEL_NAME = "Veo1_wenet.onnx"  # UNet 模型文件名
ENCODER_MODEL_NAME = "encoder.onnx"  # 音频编码器模型文件名

# 数据文件夹配置
IMG_INFERENCE_DIR = "full_body_img"  # 图像文件夹名称
LMS_INFERENCE_DIR = "landmarks"  # 关键点文件夹名称

# 帧数配置
MAX_FRAMES = 500  # 最大加载帧数（根据你的训练视频长度调整，建议 500-1000）

# 图像文件格式
IMG_EXTENSION = ".jpg"  # 图像文件扩展名    
LMS_EXTENSION = ".lms"  # 关键点文件扩展名

# 音频处理配置
AUDIO_SAMPLE_RATE = 16000  # 音频采样率 (Hz)
AUDIO_FRAME_SIZE = 160  # 每帧音频采样点数 (10ms at 16kHz)

# 推理配置
USE_GPU = True  # 是否使用 GPU 加速

# 延迟优化配置
# 原值 11040 (690ms)，降低到 7200 (450ms) 以减少处理延迟
AUDIO_PROCESS_THRESHOLD = 7200  # 开始处理的音频样本阈值 (7200 = 450ms at 16kHz)

# 初始音频缓冲配置（原 32*160=5120 即 320ms，降低到 16*160=2560 即 160ms）
INITIAL_AUDIO_BUFFER_FRAMES = 16  # 初始空白音频帧数

# 静音时的微动画配置
IDLE_ANIMATION_ENABLED = True  # 是否启用静音微动画
IDLE_BREATH_AMPLITUDE = 1.5    # 呼吸动画幅度（像素）
IDLE_BREATH_SPEED = 0.15       # 呼吸动画速度

# ==================== 空闲时推理配置（关键！聆听状态）====================
# 当检测到静音时，是否继续用空音频做推理
# True: 用空音频推理 → 嘴型会闭合，但仍有自然的表情/身体动作
# False: 跳过推理 → 直接返回原始图片（可能有各种嘴型）
IDLE_INFERENCE_ENABLED = True   # 是否启用空闲时推理
IDLE_INFERENCE_FPS = 15         # 空闲时的推理帧率（降低以节省算力）
IDLE_AUDIO_PADDING_MS = 500     # 空闲时用于推理的静音音频长度（毫秒）

# 性能分析：每 N 个输出帧打印一次平均推理耗时（0=关闭）
PROFILE_EVERY_N_FRAMES = 0   # 调试时可设为 60 等

# bbox 平滑配置
BBOX_SMOOTHING_ENABLED = True  # 是否启用 bbox 平滑
BBOX_SMOOTHING_WINDOW = 5      # 平滑窗口大小

# ==================== 时序平滑配置（关键！减少嘴部抖动）====================
TEMPORAL_SMOOTHING_ENABLED = True  # 是否启用时序平滑（强烈建议开启）
TEMPORAL_SMOOTHING_WEIGHTS = [0.6, 0.25, 0.15]  # 时序平滑权重 [当前帧, 前1帧, 前2帧]
# 权重说明：
#   - 当前帧权重大 → 嘴型反应快但可能有抖动
#   - 前几帧权重大 → 更平滑但嘴型反应慢
#   - 建议值: [0.6, 0.25, 0.15] 或 [0.7, 0.2, 0.1]
TEMPORAL_BUFFER_SIZE = 3  # 缓冲帧数（与权重数量一致）
# ================================================================

import onnxruntime
import numpy as np
import os
import cv2
import math
import time
import json
import socket
import logging
import struct
import argparse
import kaldi_native_fbank as knf

opts = knf.FbankOptions()
opts.frame_opts.dither = 0
opts.mel_opts.num_bins = 80
opts.frame_opts.snip_edges = False
opts.mel_opts.debug_mel = False

fbank = knf.OnlineFbank(opts)


# from audio_encoder import AudioEncoder
# from face_processor import FaceProcessor


# 注意: argparse 只在直接运行此文件时使用，作为模块导入时不会执行
# 避免干扰 uvicorn 等工具的启动参数解析
# if __name__ == "__main__":
#     parser = argparse.ArgumentParser()
#     parser.add_argument('--data_path', type=str, default="digital-human/backend/stream_data", help="数据存放路径")
#     arg = parser.parse_args()

class DiHumanProcessor:
    def __init__(self, data_path, use_gpu=None):
        """
        初始化数字人处理器
        
        Args:
            data_path: 数据文件路径（包含模型文件和图像文件夹）
            use_gpu: 是否使用 GPU（None 时使用全局配置 USE_GPU）
        """
        # 使用全局配置或传入参数
        if use_gpu is None:
            use_gpu = USE_GPU
        
        # 图片和关键点数据路径
        self.full_body_img_dir = os.path.join(data_path, IMG_INFERENCE_DIR)
        self.lms_dir = os.path.join(data_path, LMS_INFERENCE_DIR)
        self.full_body_img_list = []
        self.bbox_list = []
        
        # 验证路径是否存在
        if not os.path.exists(self.full_body_img_dir):
            raise FileNotFoundError(
                f"图像目录不存在: {self.full_body_img_dir}\n"
                f"请检查 data_path 配置: {data_path}\n"
                f"期望的目录结构: {data_path}/{IMG_INFERENCE_DIR}/"
            )
        if not os.path.exists(self.lms_dir):
            raise FileNotFoundError(
                f"关键点目录不存在: {self.lms_dir}\n"
                f"请检查 data_path 配置: {data_path}\n"
                f"期望的目录结构: {data_path}/{LMS_INFERENCE_DIR}/"
            )
        
        ## 数据预加载⬇️
        
        img_files = sorted(os.listdir(self.full_body_img_dir))
        lms_files = sorted(os.listdir(self.lms_dir))

        # 只保留指定扩展名的文件，并按编号排序
        img_files = [f for f in img_files if f.endswith(IMG_EXTENSION)]
        lms_files = [f for f in lms_files if f.endswith(LMS_EXTENSION)]

        n = min(len(img_files), len(lms_files))
        print(f"[INFO] found {len(img_files)} images, {len(lms_files)} lms, using {n} frames")

        # 限制加载的最大帧数（使用全局配置）
        n = min(n, MAX_FRAMES)
        print(f"[INFO] Loading first {n} frames (MAX_FRAMES={MAX_FRAMES})")

        
        for i in range(n):
            if i % 50 == 0:
                print(f"[INFO] loading frame {i}/{n}")
            full_body_img = cv2.imread(os.path.join(self.full_body_img_dir, str(i) + IMG_EXTENSION))
            self.full_body_img_list.append(full_body_img)
            lms_path = os.path.join(self.lms_dir, str(i) + LMS_EXTENSION)
            lms_list = []
            with open(lms_path, "r") as f:
                lines = f.read().splitlines()
                for line in lines:
                    arr = line.split(" ")
                    arr = np.array(arr, dtype=np.float32)
                    lms_list.append(arr)
            lms = np.array(lms_list, dtype=np.int32)
            xmin = lms[1][0]
            ymin = lms[52][1]
            xmax = lms[31][0]
            width = xmax - xmin
            ymax = ymin + width
            bbox = [xmin, ymin, xmax, ymax]
            self.bbox_list.append(bbox)

        # 平滑 bbox 列表，减少帧间抖动
        if BBOX_SMOOTHING_ENABLED and len(self.bbox_list) > BBOX_SMOOTHING_WINDOW:
            self.bbox_list = self._smooth_bbox_list(self.bbox_list, BBOX_SMOOTHING_WINDOW)
            print(f"[INFO] ✅ bbox smoothing applied with window={BBOX_SMOOTHING_WINDOW}")

        # 准备wenet推理时用到的一些数据
        self.offset = np.ones((1, ), dtype=np.int64)*100
        self.att_cache = np.zeros([3,8,16,128], dtype=np.float32)
        self.cnn_cache = np.zeros([3,1,512,14], dtype=np.float32)

        # 放一定量的空音频缓冲区 (13440 samples = 840ms at 16kHz)
        self.audio_play_list = [0] * 13440
        
        # 根据平台选择合适的执行提供程序
        import platform
        is_macos = platform.system() == "Darwin"

        # 检查可用的执行提供程序
        available_providers = onnxruntime.get_available_providers()
        print(f"[INFO] Available ONNX Runtime providers: {available_providers}")

        # 优先级：CUDA（如可用）> CoreML（macOS）> CPU
        if use_gpu:
            if "CUDAExecutionProvider" in available_providers:
                print("[INFO] Using CUDAExecutionProvider for GPU acceleration")
                providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            elif is_macos and "CoreMLExecutionProvider" in available_providers:
                # CoreML provider without custom options (avoid compatibility issues)
                print("[INFO] Using CoreMLExecutionProvider for macOS acceleration")
                providers = ["CoreMLExecutionProvider", "CPUExecutionProvider"]
            else:
                print("[WARNING] No GPU execution provider available, falling back to CPU")
                providers = ["CPUExecutionProvider"]
        else:
            print("[INFO] Using CPUExecutionProvider only (use_gpu=False)")
            providers = ["CPUExecutionProvider"]
        
        try:
            unet_path = os.path.join(data_path, UNET_MODEL_NAME)
            encoder_path = os.path.join(data_path, ENCODER_MODEL_NAME)
            print(f"[INFO] Loading ONNX models from: {data_path}")
            print(f"[INFO]   - UNet: {UNET_MODEL_NAME}")
            print(f"[INFO]   - Encoder: {ENCODER_MODEL_NAME}")
            self.ort_unet_session = onnxruntime.InferenceSession(unet_path, providers=providers)
            self.ort_ae_session = onnxruntime.InferenceSession(encoder_path, providers=providers)
            
            # 打印实际使用的执行提供程序
            actual_providers_unet = self.ort_unet_session.get_providers()
            actual_providers_ae = self.ort_ae_session.get_providers()
            print(f"[INFO] ✅ UNet model loaded with providers: {actual_providers_unet}")
            print(f"[INFO] ✅ AudioEncoder model loaded with providers: {actual_providers_ae}")
        except Exception as e:
            print(f"[ERROR] Failed to create ONNX Runtime sessions with providers {providers}: {e}")
            print("[INFO] Falling back to CPUExecutionProvider")
            providers = ["CPUExecutionProvider"]
            try:
                self.ort_unet_session = onnxruntime.InferenceSession(os.path.join(data_path, UNET_MODEL_NAME), providers=providers)
                self.ort_ae_session = onnxruntime.InferenceSession(os.path.join(data_path, ENCODER_MODEL_NAME), providers=providers)
                print("[INFO] ✅ Fallback to CPU successful")
            except Exception as e2:
                print(f"[ERROR] Failed to create ONNX Runtime sessions even with CPU: {e2}")
                raise
        # 输入到ae的音频，使用配置的初始缓冲大小（减少延迟）
        # 原 32*160 = 320ms，现使用 INITIAL_AUDIO_BUFFER_FRAMES*160
        self.audio_queue_get_feat = np.zeros([INITIAL_AUDIO_BUFFER_FRAMES * AUDIO_FRAME_SIZE], dtype=np.int16)
        print(f"[INFO] Initial audio buffer: {INITIAL_AUDIO_BUFFER_FRAMES * 10}ms")
        
        self.index = 0
        self.step = 1
        
        # 计数器
        self.counter = 0
        self.empty_audio_counter = 56
        
        self.is_processing = False
        self.return_img = None
        
        self.silence = True
        
        self.using_feat = np.zeros([4,16,512], dtype=np.float32)
        
        # 静音微动画计数器
        self.idle_frame_counter = 0
        
        # 时序平滑缓冲区（用于减少嘴部抖动）
        self.temporal_buffer = []  # 存储前几帧的嘴部预测结果
        self._profile_output_count = 0
        self._profile_sum_ms = 0.0
        if TEMPORAL_SMOOTHING_ENABLED:
            print(f"[INFO] ✅ 时序平滑已启用，权重: {TEMPORAL_SMOOTHING_WEIGHTS}")
    
    def _smooth_bbox_list(self, bbox_list, window=5):
        """对 bbox 列表做滑动平均平滑，减少帧间抖动"""
        smoothed = []
        half_window = window // 2
        for i in range(len(bbox_list)):
            start = max(0, i - half_window)
            end = min(len(bbox_list), i + half_window + 1)
            # 计算窗口内的平均值
            avg_bbox = np.mean(bbox_list[start:end], axis=0).astype(int).tolist()
            smoothed.append(avg_bbox)
        return smoothed
    
    def _apply_idle_animation(self, img):
        """在静音时对图像应用微动画（模拟呼吸/轻微晃动）"""
        if not IDLE_ANIMATION_ENABLED:
            return img
        
        # 使用正弦函数计算呼吸偏移
        breath_offset = IDLE_BREATH_AMPLITUDE * math.sin(self.idle_frame_counter * IDLE_BREATH_SPEED)
        self.idle_frame_counter += 1
        
        # 创建平移矩阵（垂直方向的轻微移动）
        rows, cols = img.shape[:2]
        M = np.float32([[1, 0, 0], [0, 1, breath_offset]])
        
        # 应用变换
        result = cv2.warpAffine(img, M, (cols, rows), borderMode=cv2.BORDER_REPLICATE)
        return result
    
    def _apply_temporal_smoothing(self, current_frame):
        """
        对嘴部预测结果应用时序平滑，减少帧间抖动
        
        原理：将当前帧与前几帧进行加权平均
        - 当前帧权重最大，保证嘴型能跟上音频
        - 前几帧有一定权重，平滑掉随机抖动
        
        Args:
            current_frame: 当前帧的嘴部预测结果 (numpy array, float32, shape: 160x160x3)
            
        Returns:
            smoothed_frame: 平滑后的结果
        """
        # 将当前帧加入缓冲区
        self.temporal_buffer.append(current_frame.copy())
        
        # 保持缓冲区大小
        while len(self.temporal_buffer) > TEMPORAL_BUFFER_SIZE:
            self.temporal_buffer.pop(0)
        
        # 如果缓冲区帧数不足，直接返回当前帧
        if len(self.temporal_buffer) < 2:
            return current_frame
        
        # 计算加权平均
        weights = TEMPORAL_SMOOTHING_WEIGHTS[:len(self.temporal_buffer)]
        
        # 归一化权重（确保权重之和为1）
        weight_sum = sum(weights)
        normalized_weights = [w / weight_sum for w in weights]
        
        # 加权平均（从最新帧开始）
        smoothed = np.zeros_like(current_frame, dtype=np.float32)
        for i, weight in enumerate(normalized_weights):
            # 索引从后往前：-1 是当前帧，-2 是前一帧...
            frame_idx = -(i + 1)
            if abs(frame_idx) <= len(self.temporal_buffer):
                smoothed += weight * self.temporal_buffer[frame_idx]
        
        return smoothed
        
    def reset(self, soft_reset: bool = False):
        """
        重置处理器状态
        
        Args:
            soft_reset: 软重置模式，只重置音频缓冲，保留帧索引和特征缓冲
                       用于状态切换时避免跳帧
        """
        self.audio_queue_get_feat = np.zeros([INITIAL_AUDIO_BUFFER_FRAMES * AUDIO_FRAME_SIZE], dtype=np.int16)
        self.audio_play_list = [0] * 13440
        self.counter = 0
        self.is_processing = True
        self.idle_frame_counter = 0
        
        if not soft_reset:
            # 完全重置：清空特征缓冲和时序平滑缓冲
            self.temporal_buffer = []
            self.using_feat = np.zeros([4,16,512], dtype=np.float32)
        # 注意：不重置 self.index 和 self.step，保持帧的连续性
    
    def process(self, audio_frame):
        # try:
        audio_frame = audio_frame.astype(np.int16)
        is_silent_frame = not np.any(audio_frame)  # 当前帧是否是静音
        
        if is_silent_frame:  # 送进来全0的语音
            if not self.silence:
                self.empty_audio_counter += 1
            if self.empty_audio_counter >= 100:
                self.silence = True
        else:
            self.empty_audio_counter = 0 # 否则重置计数器
            self.silence = False
        
        # ========== 空闲状态推理（聆听中）==========
        # 当启用空闲推理时，静音也用空音频做推理，让嘴型保持闭合
        if self.silence and IDLE_INFERENCE_ENABLED:
            # 用空音频做推理，而不是跳过推理
            if not self.is_processing:
                # 使用软重置，保留帧索引和特征缓冲，避免跳帧
                self.reset(soft_reset=True)
            
            # 计算空闲推理的帧间隔（控制帧率）
            idle_frame_interval = max(1, int(20 / IDLE_INFERENCE_FPS))  # 假设调用频率约 20fps
            self.idle_frame_counter += 1
            
            if self.idle_frame_counter % idle_frame_interval != 0:
                # 跳过这一帧以控制帧率，但仍需返回有效结果
                return None, np.zeros([AUDIO_FRAME_SIZE], dtype=np.int16), 0
            
            # 用空音频填充缓冲区（模拟静音输入）
            silence_samples = int(IDLE_AUDIO_PADDING_MS * AUDIO_SAMPLE_RATE / 1000)
            current_samples = self.audio_queue_get_feat.shape[0] if self.audio_queue_get_feat.size > 0 else 0
            if current_samples < silence_samples:
                padding_needed = silence_samples - current_samples
                if current_samples == 0:
                    self.audio_queue_get_feat = np.zeros(padding_needed, dtype=np.int16)
                else:
                    self.audio_queue_get_feat = np.concatenate([
                        self.audio_queue_get_feat, 
                        np.zeros(padding_needed, dtype=np.int16)
                    ], axis=0)
            
            # 继续执行后面的推理逻辑（不 return）
        
        # ========== 旧的静音处理逻辑（不做推理，直接返回原图）==========
        elif self.silence and not IDLE_INFERENCE_ENABLED:
            self.audio_queue_get_feat = np.array([])
            self.is_processing = False
            # 静音时每 3 帧输出一帧（原来是每 5 帧），提高流畅度
            if self.counter == 0:
                return_img = self.full_body_img_list[self.index].copy()
                # 应用静音微动画（呼吸效果）
                return_img = self._apply_idle_animation(return_img)
                self.index += self.step
                if self.index >= len(self.bbox_list)-1:
                    self.step = -1
                elif self.index <= 0:
                    self.step = 1
                check_img = 1
                self.counter += 1
            else:
                self.return_img = None
                check_img = 0
                self.counter += 1
                # 减少间隔从 5 到 3，提高静音时的帧率
                if self.counter == 3:
                    self.counter = 0
                return_img = None
            playing_audio = np.zeros([160], dtype=np.int16)
            
            return return_img, playing_audio, check_img
        
        # ========== 正常音频处理 ==========
        elif not self.silence:
            if not self.is_processing:  # 第一次推理重置参数
                # 使用软重置，保留帧索引和特征缓冲，避免跳帧
                self.reset(soft_reset=True)
            if audio_frame.shape[0] < AUDIO_FRAME_SIZE:  # 默认送进来的是10ms的音频帧
                audio_frame = np.pad(audio_frame, (0, AUDIO_FRAME_SIZE - audio_frame.shape[0]))
            self.audio_queue_get_feat = np.concatenate([self.audio_queue_get_feat, audio_frame], axis=0)  # 积攒起来，攒够一定量后开始处理
        
        # 使用可配置的处理阈值（原 11040 = 690ms，现 7200 = 450ms）
        if self.audio_queue_get_feat.shape[0] >= AUDIO_PROCESS_THRESHOLD:  # 攒够音频后开始处理
            t_block_start = time.perf_counter()
            fbank = knf.OnlineFbank(opts)
            audio_mel_feat = []

            fbank.accept_waveform(AUDIO_SAMPLE_RATE, self.audio_queue_get_feat.tolist())  # fbank
            # 将正在处理的音频加到播放列表里（使用配置的初始缓冲偏移）
            audio_offset = INITIAL_AUDIO_BUFFER_FRAMES * AUDIO_FRAME_SIZE
            self.audio_play_list.extend(self.audio_queue_get_feat[audio_offset:audio_offset+800])
            for i in range(fbank.num_frames_ready):
                audio_mel_feat.append(fbank.get_frame(i))
            audio_mel_feat = np.array([[audio_mel_feat]])  # shape: [1, 1, N, 80]
            
            # Ensure audio_mel_feat has exactly 67 frames for ONNX model input
            actual_frames = audio_mel_feat.shape[2]
            if actual_frames < 67:
                # Zero padding to 67 frames
                padding = np.zeros((1, 1, 67 - actual_frames, 80), dtype=audio_mel_feat.dtype)
                audio_mel_feat = np.concatenate([audio_mel_feat, padding], axis=2)
            elif actual_frames > 67:
                # Take only first 67 frames
                audio_mel_feat = audio_mel_feat[:, :, :67, :]
            
            ort_encoder_inputs = {'chunk': audio_mel_feat.astype(np.float32), 'offset':self.offset, 'att_cache':self.att_cache.astype(np.float32), 'cnn_cache':self.cnn_cache.astype(np.float32)}
            ort_encoder_outs = self.ort_ae_session.run(None, ort_encoder_inputs)  # wenet提取特征
            audio_feat = ort_encoder_outs[0]
            self.audio_queue_get_feat = self.audio_queue_get_feat[800:] # 丢弃处理过的音频
            
            self.using_feat = np.concatenate([self.using_feat, audio_feat], axis=0)  # 将音频特征积攒起来，攒够一定量开始处理
            img = self.full_body_img_list[self.index].copy()
            bbox = self.bbox_list[self.index]
            
            
            self.index += self.step
            if self.index >= len(self.bbox_list)-1:
                self.step = -1
            elif self.index<=0:
                self.step = 1
            
            if self.using_feat.shape[0]>=8: # 音频特征攒够8帧 开始输出图片 下面的逻辑和inference里的一样
                
                xmin,ymin,xmax,ymax = bbox
                crop_img = img[ymin:ymax, xmin:xmax]
                h, w = crop_img.shape[:2]
                crop_img = cv2.resize(crop_img, (168, 168))
                crop_img_ori = crop_img.copy()
                img_real_ex = crop_img[4:164, 4:164].copy()
                img_real_ex_ori = img_real_ex.copy()
                img_masked = cv2.rectangle(img_real_ex_ori,(5,5,150,145),(0,0,0),-1)

                img_masked = img_masked.transpose(2,0,1).astype(np.float32)/255.0
                img_real_ex = img_real_ex.transpose(2,0,1).astype(np.float32)/255.0
                img_masked = np.expand_dims(img_masked, 0)
                img_real_ex = np.expand_dims(img_real_ex, 0)
                img_onnx_in = np.concatenate((img_real_ex, img_masked), axis=1)
                audio_feat = self.using_feat[:8].reshape(1,128,16,32)  # 只使用前8帧，与训练时一致

                ort_unet_inputs = {self.ort_unet_session.get_inputs()[0].name: img_onnx_in, self.ort_unet_session.get_inputs()[1].name: audio_feat}
                ort_outs = self.ort_unet_session.run(None, ort_unet_inputs)

                pred = ort_outs[0][0]
                pred = pred.transpose(1,2,0)*255
                
                # ========== 时序平滑处理（减少嘴部抖动）==========
                if TEMPORAL_SMOOTHING_ENABLED:
                    pred = self._apply_temporal_smoothing(pred)
                # ================================================
                
                pred = pred.astype(np.uint8)

                crop_img_ori[4:164, 4:164] = pred
                crop_img_ori = cv2.resize(crop_img_ori, (w, h))
                img[ymin:ymax, xmin:xmax] = crop_img_ori
                self.using_feat = self.using_feat[1:]
                
                
            # return_img = cv2.cvtColor(img, cv2.COLOR_BGR2YUV_I420)
            return_img = img.copy()
            if PROFILE_EVERY_N_FRAMES > 0:
                self._profile_output_count += 1
                self._profile_sum_ms += (time.perf_counter() - t_block_start) * 1000
                if self._profile_output_count % PROFILE_EVERY_N_FRAMES == 0:
                    avg_ms = self._profile_sum_ms / PROFILE_EVERY_N_FRAMES
                    logging.info("[DiHuman] 推理耗时: 近 %d 帧平均 %.1f ms/帧", PROFILE_EVERY_N_FRAMES, avg_ms)
                    self._profile_sum_ms = 0.0
            self.counter = 1
            check_img = 1
        else: # 音频不够时仅返回播放列表里的音频 返回空图像
            if self.counter == 0:
                return_img =  self.full_body_img_list[self.index].copy()
                self.index += self.step
                if self.index >= len(self.bbox_list)-1:
                    self.step = -1
                elif self.index<=0:
                    self.step = 1
                # return_img = cv2.cvtColor(return_img, cv2.COLOR_BGR2YUV_I420)
                check_img = 1
                self.counter += 1
            else:
                return_img = None
                check_img = 0
                self.counter += 1
                if self.counter == 5:
                    self.counter = 0
        if not self.audio_play_list == []:
            playing_audio = np.array(self.audio_play_list[:AUDIO_FRAME_SIZE])
            self.audio_play_list = self.audio_play_list[AUDIO_FRAME_SIZE:]
        else:
            playing_audio = np.zeros([AUDIO_FRAME_SIZE], dtype=np.int16)
            
        playing_audio = playing_audio.astype(np.int16)
        return return_img, playing_audio, check_img
        # except BaseException as e:
        #     logger.error("onTransportData error: %s", e)
            
            
