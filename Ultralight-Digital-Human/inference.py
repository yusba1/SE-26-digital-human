import argparse
import os
import cv2
import torch
import numpy as np
import torch.nn as nn
from torch import optim
from tqdm import tqdm
from torch.utils.data import DataLoader
from unet import Model
# from unet2 import Model
# from unet_att import Model

import time
parser = argparse.ArgumentParser(description='Train',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)

parser.add_argument('--asr', type=str, default="hubert")
parser.add_argument('--dataset', type=str, default="")  
parser.add_argument('--audio_feat', type=str, default="")
parser.add_argument('--save_path', type=str, default="")     # end with .mp4 please
parser.add_argument('--checkpoint', type=str, default="")
parser.add_argument('--start_frame', type=int, default=0, help="起始帧编号")
parser.add_argument('--end_frame', type=int, default=-1, help="结束帧编号（-1 表示最后一帧）")
args = parser.parse_args()

checkpoint = args.checkpoint
save_path = args.save_path
dataset_dir = args.dataset
audio_feat_path = args.audio_feat
mode = args.asr

device = 'cuda' if torch.cuda.is_available() else 'cpu'

def get_audio_features(features, index): # 这个逻辑跟datasets里面的逻辑相同
    left = index - 4
    right = index + 4
    pad_left = 0
    pad_right = 0
    if left < 0:
        pad_left = -left
        left = 0
    if right > features.shape[0]:
        pad_right = right - features.shape[0]
        right = features.shape[0]
    auds = torch.from_numpy(features[left:right])
    if pad_left > 0:
        auds = torch.cat([torch.zeros_like(auds[:pad_left]), auds], dim=0)
    if pad_right > 0:
        auds = torch.cat([auds, torch.zeros_like(auds[:pad_right])], dim=0) # [8, 16]
    return auds

audio_feats = np.load(audio_feat_path)
img_dir = os.path.join(dataset_dir, "full_body_img/")
lms_dir = os.path.join(dataset_dir, "landmarks/")
len_img = len(os.listdir(img_dir)) - 1
exm_img = cv2.imread(img_dir+"0.jpg")
h, w = exm_img.shape[:2]

if mode=="hubert":
    video_writer = cv2.VideoWriter(save_path, cv2.VideoWriter_fourcc('M','J','P', 'G'), 25, (w, h))
if mode=="wenet":
    video_writer = cv2.VideoWriter(save_path, cv2.VideoWriter_fourcc('M','J','P', 'G'), 20, (w, h))

start_frame = max(0, min(args.start_frame, len_img))
if args.end_frame >= 0:
    end_frame = max(start_frame, min(args.end_frame, len_img))
else:
    end_frame = len_img

print(f"[推理] 使用帧范围: {start_frame} ~ {end_frame}")
if end_frame > start_frame:
    step_stride = 1
    img_idx = start_frame - 1
else:
    step_stride = 0
    img_idx = start_frame

net = Model(6, mode).to(device)
net.load_state_dict(torch.load(checkpoint, map_location=device))
net.eval()
for i in range(audio_feats.shape[0]):
    if end_frame > start_frame:
        if img_idx >= end_frame:
            step_stride = -1  # 在设定区间内来回滚动，不越界到其他帧
        if img_idx < start_frame:
            step_stride = 1
        img_idx += step_stride
    else:
        img_idx = start_frame
    img_path = img_dir + str(img_idx)+'.jpg'
    lms_path = lms_dir + str(img_idx)+'.lms'
    
    img = cv2.imread(img_path)
    lms_list = []
    with open(lms_path, "r") as f:
        lines = f.read().splitlines()
        for line in lines:
            arr = line.split(" ")
            arr = np.array(arr, dtype=np.float32)
            lms_list.append(arr)
    lms = np.array(lms_list, dtype=np.int32)  # 这个关键点检测模型之后之后可能会改掉
    xmin = lms[1][0]
    ymin = lms[52][1]

    xmax = lms[31][0]
    width = xmax - xmin
    ymax = ymin + width
    crop_img = img[ymin:ymax, xmin:xmax]
    h, w = crop_img.shape[:2]
    crop_img = cv2.resize(crop_img, (168, 168), cv2.INTER_AREA)
    crop_img_ori = crop_img.copy()
    img_real_ex = crop_img[4:164, 4:164].copy()
    img_real_ex_ori = img_real_ex.copy()
    img_masked = cv2.rectangle(img_real_ex_ori,(5,5,150,145),(0,0,0),-1)
    
    img_masked = img_masked.transpose(2,0,1).astype(np.float32)
    img_real_ex = img_real_ex.transpose(2,0,1).astype(np.float32)
    
    img_real_ex_T = torch.from_numpy(img_real_ex / 255.0).to(device)
    img_masked_T = torch.from_numpy(img_masked / 255.0).to(device)  
    img_concat_T = torch.cat([img_real_ex_T, img_masked_T], axis=0)[None]
    # 这个地方逻辑和dataset里面完全一样，只是不需要另外取一张参考图 而是用要推理的这张图片即可
    
    audio_feat = get_audio_features(audio_feats, i)
    if mode=="hubert":
        audio_feat = audio_feat.reshape(16,32,32)
    if mode=="wenet":
        audio_feat = audio_feat.reshape(128,16,32)
    audio_feat = audio_feat[None]
    audio_feat = audio_feat.to(device)
    img_concat_T = img_concat_T.to(device)
    
    with torch.no_grad():
        pred = net(img_concat_T, audio_feat)[0]
        
    pred = pred.cpu().numpy().transpose(1,2,0)*255
    pred = np.array(pred, dtype=np.uint8)
    crop_img_ori[4:164, 4:164] = pred
    crop_img_ori = cv2.resize(crop_img_ori, (w, h))
    img[ymin:ymax, xmin:xmax] = crop_img_ori
    video_writer.write(img)
video_writer.release()

# ffmpeg -i test_video.mp4 -i test_audio.pcm -c:v libx264 -c:a aac result_test.mp4