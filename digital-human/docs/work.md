11月24日：选型
今日计划
暂时无法在飞书文档外展示此内容
今日总结
已有模型
LiveTalking:实时交互流式数字人，文本-TTS-驱动数字人
- 特点：
  1. 支持多种数字人模型: ernerf、musetalk、wav2lip、Ultralight-Digital-Human
  2. 支持声音克隆
  3. 支持数字人说话被打断
  4. 支持webrtc、虚拟摄像头输出
  5. 支持动作编排：不说话时播放自定义视频
  6. 支持多并发

- 数字人模型：
  - Ultralight-Digital-Human
  - ernerf
  - musetalk
  - wav2lip

- TTS：
  - fish-speech 12G显存，准确率极高，但不支持流式输出（但可以考虑用分段文字生成弥补）
  - 腾讯语音
  - 豆包语音

fay：一个连通业务系统的MCP框架
- 可以把ASR、LLM、TTS等接到这个框架里进行连通
- 特色：
  - 完全开源，商用免责
  - 支持全离线使用
  - 全时流式的支持
  - 自由匹配数字人模型、大语言模型（openai 兼容接口）、ASR、TTS模型
  - 支持数字人自动播报模式（虚拟教师、虚拟主播、新闻播报）
  - 支持任意终端使用：单片机、app、网站、大屏、三方业务系统接入等
  - 支持多用户多路并发
  - 提供文字交互接口、语音交互接口、数字人驱动接口、管理控制接口、自动播报接口、意图接口
  - 支持语音指令灵活配置执行（qa.csv）
  - 支持自定义知识库、自定义问答对、自定义人设信息
  - 支持唤醒及打断对话
  - 支持服务器及单机模式
  - 支持机器人表情输出
  - 支持agent自主决策工具调用
  - 基于日程式数字人主动对话
  - 支持后台静默启动
  - 支持deepseek等thinking llm
  - 自我认知提高
  - 仿生记忆
  - 支持MCP工具管理（sse、studio）
  - 提供配置管理中心
  - 全链路交互互通
VideoChat：ASR-LLM-TTS-THG全流程
显存：20G，单张A100
- ASR : FunASR
- LLM : Qwen
- End-to-end MLLM : GLM-4-Voice
- TTS : GPT-SoVITS, CosyVoice, edge-tts
- THG (Talking Head Generation): MuseTalk

THG
- Ultralight-Digital-Human：
- MuseTalk：
- ernerf
- wav2lip

ASR
- FunASR：支持流式识别，专业知识不太足，可能需要微调


LLM
- Qwen

TTS
- ChatTTS：流式生成
- fish-speech ：12G显存，准确率极高，但不支持流式输出（但可以考虑用分段文字生成弥补）
- 腾讯语音
- 豆包语音
-  GPT-SoVITS
-  CosyVoice
-  edge-tts



总结
- ASR:FunASR ：支持流式识别语音，专业知识不太足，可能需要微调
- LLM:Qwen2.5-7B-Instruct 中文能力够强，速度快（API）
- TTS:ChatTTS ：支持流式生成语音，看看更轻量级
- THG：Ultralight-Digital-Human：可以流式将语音转换为视频
- 连通框架：fay 可以把上述架构组合到一起，形成整体or video chat，dify，百炼，扣子，n8n（确定一下）
- 所需配置：RTX 4090
- 流式生成文本与语音对接
- 考虑成本
- 支持10/20个并发要多少计算资源多少成本
- 看看工作量，跑起来多长时间

---
确定TTS，框架，每个跑一遍
11月25日：选型
今日计划
暂时无法在飞书文档外展示此内容
今日总结
连通框架
fay：可以负责音视频处理，把“数字人实时动起来”

dify：免费无限制，但需要GPU 成本，可以把“面试流程做完整”
1. GitHub 下载或 Docker-compose 一键启动
2. 打开浏览器访问本地 Dify 控制台
3. 选择大模型（OpenAI, DeepSeek, Qwen…）
4. 配置 Prompt / 工作流
5. 发布应用 → URL 或 API 使用
百炼：收费按 Token，但不用维护GPU，成本更小，
1. 注册百炼平台
2. 创建模型 API（Qwen2.5-7B、SenseVoice、TTS…）
3. 获得 API Key
4. 后端通过 HTTP/SDK 调用
5. 根据需求设计对话逻辑
n8n：本身不是 AI 平台（LLM 调用需要自己封装 API）
1. Docker 运行 n8n
2. 在网页界面创建工作流
3. 添加节点（Webhook → Qwen API → TTS → 文件输出）
4. 触发即可

---
百炼+fay
以「学生回答一段话 → 数字人追问/反馈」为例，完整链路是：
1. 学生开口说话
  - 前端把麦克风音频流，通过 WebSocket 发送给 Fay。
2. Fay → 调百炼做 ASR
  - Fay 把音频片段转发给百炼的 FunASR 实时识别接口。
  - 百炼返回文本（学生的回答字幕），可以是流式 / 分句返回。
  - Fay 更新当前 Session 的“学生回答文本”。
3. Fay → 调百炼 LLM（Qwen2.5）
  - Fay 组织好 Prompt：包括面试上下文、问题、学生上一轮回答等。
  - 调用百炼的 Qwen2.5-7B-Instruct API，得到面试官要说的话（追问 / 总结 / 反馈）。
  - Fay 把这段文本存入会话状态。
4. Fay → 调百炼 TTS（CosyVoice）
  - 把 LLM 的输出文本传给 CosyVoice（流式 WebSocket 或普通 HTTP）。
  - 获得语音流 / 音频片段。
5. Fay → 调 THG（Ultralight-DH）
  - 将语音（或对齐后的音频特征）喂给 Ultralight-Digital-Human 模型，
  - 生成对应嘴型 / 表情的视频帧流（或驱动参数）。
  - Fay 把音频 + 视频流通过 WebSocket 推回给前端。
6. 前端播放
  - 学生在浏览器里看到数字人张嘴说话、听到语音，完成一轮面试反馈。
  - Fay 的状态机决定下一步是继续追问、换题还是结束。
TTS
- edge-tts：调用微软在线 TTS 服务，不用本地算力，
- CosyVoice云服务：可以直接串在百炼 LLM 后面做一体化调用，但需要API费用$0.286706 / 10,000 字符
- Matcha-TTS


跑Ultralight-Digital-Human
用colab跑

每个 cell 开头加一句：
%cd /content/drive/MyDrive/Ultralight-Digital-Human
!ls

云盘路径：/content/drive/MyDrive/

预处理已跑通，训练出了点问题
总结
- ASR:FunASR ："qwen3-asr-flash-realtime" 百炼API ￥0.21 / 15 分钟面试
- LLM:Qwen2.5-7B-Instruct 调用百炼API：￥0.010 / 1000 tokens
- TTS:CosyVoice百炼API：可以直接串在百炼 LLM 后面做一体化调用，￥2 / 10,000 tokens
- THG：Ultralight-Digital-Human：可以流式将语音转换为视频
- 连通框架：fay +百炼，FunASR、Qwen、CosyVoice托管在百炼，本地用fay调用调控
- 支持10/20个并发的计算资源与成本：每场 15 分钟面试 ≈ ￥0.34 ～ ￥0.81；10 并发 ≈ 每小时 15–30 元，20 并发 ≈ 每小时 30–60 元，不需要GPU
11月27日：跑通THG
今日计划
暂时无法在飞书文档外展示此内容
今日总结
用阿里云DSW交互式建模平台跑
Tips
训练视频要放到data_dir文件夹下
最好都用绝对路径,绝对路径在copy path后在前面加上/mnt/workspace/
用wenet
优化点1：代码syncnet.py
- DataLoader 会按照 len(dataset) 来取索引 idx，这里是 audio_feats.shape[0]-1
- 但真正拿图像的时候用的是：self.img_path_list[idx]
- 一旦 audio_feats 的帧数 > 图片张数，idx 就会超出 img_path_list 的长度，直接 IndexError
- 优化：让 Dataset 的长度不超过「图片数」和「音频帧数」中的较小值
# 截断到统一长度，避免某个列表比另一个长
        self.img_path_list = self.img_path_list[:self.length]
        self.lms_path_list = self.lms_path_list[:self.length]
        self.audio_feats = self.audio_feats[:self.length]

优化点2：比较出错
把向量和长度比较大小了，于是报错“The truth value of an array with more than one element is ambiguous.”
解决办法：
在 datasetsss.py 里把 len 改成这一行
def __len__(self):
    return min(self.audio_feats.shape[0], len(self.img_path_list))
优化点3：送进 SyncNet 的音频特征通道数不对
解决方案：窗口改为前后各 8 帧
把
    left = index - 4
    right = index + 4
改为
    left = index - 8
    right = index + 8
优化点4：卷积期望输入通道数是 128，实际输入通道数是 256，所以不匹配
解决：
if self.mode == "wenet":
    audio_feat = audio_feat.reshape(128,16,32)
改为：
if self.mode == "wenet":
    # Wenet：特征堆叠后 reshape 成 [256, 16, 32]
    audio_feat = audio_feat.reshape(256, 16, 32)
把 AudioConvWenet 的第一层改成输入 256 通道：
把
class AudioConvWenet(nn.Module):
    def __init__(self):
        super(AudioConvWenet, self).__init__()
        ch = [32, 64, 128, 256, 512]
        self.conv1 = InvertedResidual(ch[2], ch[3], stride=1, use_res_connect=False, expand_ratio=2)
        self.conv2 = InvertedResidual(ch[3], ch[3], stride=1, use_res_connect=True, expand_ratio=2)
改成：
class AudioConvWenet(nn.Module):
    def __init__(self):
        super(AudioConvWenet, self).__init__()
        ch = [32, 64, 128, 256, 512]
        # 输入通道改为 256，匹配 audio_feat 的 C=256
        self.conv1 = InvertedResidual(ch[3], ch[3], stride=1, use_res_connect=False, expand_ratio=2)
        self.conv2 = InvertedResidual(ch[3], ch[3], stride=1, use_res_connect=True, expand_ratio=2)

优化点5：推理时通道数不匹配
解决：
把inference.py按照优化点3，4一样改



12月1日：跑流式推理
今日计划
在百炼的应用开发里拉工作流 ，模型推理用PAI的EAS部署暴露出来 先把核心路径跑通
几个问题 1.怎么把整个服务暴露出来 也就是输入和输出怎么对接到你的做的工作流上 2. 哪些环节要进一步调优 3. 这个技术路径我们原始视频怎么生成，最好不要真人录，但是要保障质量和真实感
暂时无法在飞书文档外展示此内容
今日总结
转ONNX格式
ONNX：一种模型文件格式，PyTorch、TensorFlow、JAX 的模型都可以转为ONNX文件
ONNX Runtime（ORT）：用来跑ONNX文件的引擎，专为部署场景服务，速度快，兼容性好，跨平台，易于集成
把unet转为onnx格式
流式推理
流式推理代码：dihumna_run.py
输入：一小段10ms音频=160个采样
状态变量：
- self.audio_queue_get_feat：缓存还没处理完的原始音频
- self.audio_play_list：作为“输出端的播放缓冲”
- self.using_feat：已经从 wenet 提取出来的特征缓存
- self.index / self.step：决定当前用哪一张底图、做往返摆动
- self.empty_audio_counter / self.silence：用于静音检测，连续空音频就走“无口型只摇头”的逻辑
当：
- self.audio_queue_get_feat.shape[0] >= 11040（= 690ms 音频）
- 并且 self.using_feat.shape[0] >= 8（8 帧音频特征）
才会真正跑一次 onnx UNet，合成一帧新图像。
返回值：
- return_img: 可能是 None（这次不输出图像），也可能是 BGR 一帧图像
- playing_audio: 一段 10ms 的音频（长度 160），要么是之前累积的音频，要么是全 0
- check_img: 1 表示这次有图像帧可用，0 表示没有





推理前的准备工作
1. 把unet模型转为ONNX文件，放在stream_data下
2. 在stream_data下创建img_inference和lms_inference，分别放之前提取出的静音图片与关键点信息
3. 把要推理的音频文件和encoder.onnx也放在stream_data下
4. stream_data目录内容如下：
[图片]

Bug
1.生成的mp4文件损坏，而且没有test_audio.pcm文件
还是维度问题，把
if self.using_feat.shape[0]>=8: # 音频特征攒够8帧 开始输出图片 下面的逻辑和inference里的一样
                
    xmin,ymin,xmax,ymax = bbox
    ...
    img_onnx_in = np.concatenate((img_real_ex, img_masked), axis=1)
    audio_feat = self.using_feat.reshape(1,128,16,32)
改成：
if self.using_feat.shape[0]>=16: # 音频特征攒够16帧 开始输出图片 ，为了使数据量跟上下面的变动
                
    xmin,ymin,xmax,ymax = bbox
    ...
    img_onnx_in = np.concatenate((img_real_ex, img_masked), axis=1)
    audio_feat = self.using_feat.reshape(1,256,16,32)#128改成256
2.一次性把 5291 张 1080p 大图全读进内存，会内存爆了
其实十四秒的视频不需要那么多帧图像，只加载前300帧也够
      # 可以先限制加载前 300 帧
        MAX_FRAMES = 300   
        n = min(n, MAX_FRAMES)

        
        for i in range(n):
而且少加载不会影响效果，因为没有大幅度的动作（这一点要注意如果后续的模板视频有大幅度动作就要考虑内存问题）
对于嘴型合成，只要存在：
- 一组稳定的 bbox
- 一组干净的人脸模板
就足够训练/推理。
3.视频生成失败
是因为VideoWriter 尺寸 / 编码器不匹配：
尺寸部分代码改为
h, w, _ = processor.full_body_img_list[0].shape  # 用真实帧尺寸
fourcc = cv2.VideoWriter_fourcc(*'mp4v')
video_writer = cv2.VideoWriter("./test_video.mp4", fourcc, 20, (w, h))

4.视频开头没有声音但是嘴在动
可以按照源代码作者说的“拍摄训练视频的时候前面20秒不说话，这20秒就可以作为流式推理时的素材”
12月2日：EAS部署（OSS版）
今日计划
在百炼的应用开发里拉工作流 ，模型推理用PAI的EAS部署暴露出来 先把核心路径跑通
几个问题 1.怎么把整个服务暴露出来 也就是输入和输出怎么对接到你的做的工作流上 2. 哪些环节要进一步调优 3. 这个技术路径我们原始视频怎么生成，最好不要真人录，但是要保障质量和真实感
暂时无法在飞书文档外展示此内容
今日总结
原始视频怎么生成（方案1）
HeyGen：
1. 通义万相生成原始人物形象图片
2. 用图片在HeyGen生成Avatar
3. 在 HeyGen 创建视频 → 选择 Avatar
4. 上传： silent_20s.wav（一个 20 秒静音音频）
5. 在 script 文本框中粘贴“正式讲话部分”，不要填前 20 秒，保持空白。
你好，我是今天的面试官。接下来我们会围绕你的背景、项目经历、能力特长以及未来规划做一次比较全面的沟通，希望你可以尽量放轻松，把真实的想法展现出来。

我们先从一个常规问题开始。请你做一个简短的自我介绍，重点讲讲你最有代表性的学习或项目经验。如果你有跨专业的经历，也可以简单说一下你是如何适应并找到方向的。

好的，那接下来我想进一步了解一下你在团队协作中的表现。在你最近参与的项目里，你通常承担什么样的角色？当团队出现分歧，或者任务推进不顺利的时候，你一般会怎么处理？你可以举一个你亲身经历的实际例子。

另外，我比较看重候选人对问题的分析能力。当你遇到一个新的任务，信息不够完整，或者没有现成的方法可以直接参考时，你通常会怎么思考？你是如何拆解问题、制定计划，并最终推进落地的？我想听听你具体的做法和过程。

接下来，我们聊聊你的学习能力和自我驱动。请你回想一下，过去一年里让你成长最快的一件事情是什么？你从中获得了哪些经验，或者培养了哪些新的能力？这些能力对你未来的职业发展有什么帮助？

然后是一个比较现实的问题。每个人都会遇到压力，比如截止时间紧、任务多、或者对结果不确定。在这种情况下，你是如何调整节奏、管理情绪，并保持效率的？你有没有一些具体的方法或者习惯？

最后，我想听听你未来一到两年的职业规划。你希望在新的环境里获得哪些成长？你最想提升的能力是什么？你觉得我们这个岗位或者团队能为你带来什么样的帮助？也可以说一下你对职业发展的长期设想。

好的，你可以稍微整理一下思路，然后按照你自己的节奏回答我这些问题。

6. 打开 Timeline
  前 0–20s：放置 silent_20s.wav
  从 20s 起：放置选择的 TTS 语音（HeyGen 会自动生成）
7. 导出视频即可生成“前 20 秒自然动作 + 后 40 秒讲话”的统一视频
模型推理用EAS部署
- dihuman_core.py封装DiHumanProcessor 类
- offline_demo.py：离线测试脚本
- server.py：在一个进程里常驻多个 DiHumanProcessor 实例，每个 session 一个，提供一个 /stream_step 接口，每次调用都相当于“往这个 session 里喂一小段音频”。
- 打包为dh_stream_service.zip：
ultralight_service/
    dihuman_core.py       # 内核（你的 DiHumanProcessor）
    server.py             # FastAPI 服务壳
    requirements.txt

    stream_data/          # 你 inference 用的数据路径（和 __main__ 里保持一致）
        unet.onnx
        encoder.onnx
        img_inference/
            0.jpg
            1.jpg
            ...
        lms_inference/
            0.lms
            1.lms
            ...
        # test_16k.wav 只是本地 demo 用，服务器用不到

    # 其他你需要的配置文件 / 日志目录等
- 创建OSSBucket（资源组选择xuniversity资源组）
- 把zip上传到digital-human-thg2/zipped这个bucket中
- 在EAS中挂载OSS
暂时无法在飞书文档外展示此内容
  - 注意Uri不要写到确切文件，写到上一层的文件夹即可
- 运行命令：
set -e

# 1. 安装 OpenCV 需要的系统依赖
apt-get update && \
apt-get install -y libgl1 libglib2.0-0 && \
rm -rf /var/lib/apt/lists/*

# 2. 把 OSS 挂载里的代码拷到本地目录
mkdir -p /root/app
cp -r /mnt/data/server.py /root/app/
cp -r /mnt/data/requirements.txt /root/app/
cp -r /mnt/data/dihuman_core.py /root/app/
cp -r /mnt/data/.ipynb_checkpoints/ /root/app/ || true

# 3. 安装 Python 依赖
pip install --index-url https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    --disable-pip-version-check \
    -r /root/app/requirements.txt --no-cache-dir

# 4. 启动服务
cd /root/app
python -m uvicorn server:app --host 0.0.0.0 --port 8000


- 环境变量：
DIHUMAN_DATA_PATH=/mnt/data/stream_data
Bug
- 修改文件路径bug，注意挂载的Uri是要挂载一个文件夹，然后从文件夹里拿文件，而不是直接把需要的文件挂载进去
- 压缩包解压后不会包一层压缩包名称，而是压缩包下的文件直接全都放进根目录了
- 可以把压缩包传入OSS特定文件夹后自动解压
- 把解压后的文件夹挂载到EAS里，可以只在OSS存储图像这些数据，代码要放到EAS本地

12月4日：训练视频生成
今日计划
暂时无法在飞书文档外展示此内容
今日总结
原始视频生成（方案2）
录制一段视频+AI换脸
录制视频要求：
- 口型清晰
- 脸正对屏幕
- 不要戴眼镜，不要有刘海
- 光线均匀，不要有强阴影
- 分辨率1080p（不要4k，太大了）
- 屏幕比例3:4
- 别离镜头太近，可以坐在桌子前，头上方有一些留白，视野到肩膀下面
- 不要有手部动作，不要挡脸
- 录制的前20秒不要说话，可以微笑或头稍微动一动，眼睛动一动（不要一直直视镜头，自然一些，比如眼睛看左下角思考之类的），20秒后读下面这段话，语速适中，可以适当慢一些，只保证口型清楚即可，别的五官不用在意，注意动作幅度不要太大就好
你好，我是今天的面试官。接下来我们会围绕你的背景、项目经历、能力特长以及未来规划做一次比较全面的沟通，希望你可以尽量放轻松，把真实的想法展现出来。

我们先从一个常规问题开始。请你做一个简短的自我介绍，重点讲讲你最有代表性的学习或项目经验。如果你有跨专业的经历，也可以简单说一下你是如何适应并找到方向的。

好的，那接下来我想进一步了解一下你在团队协作中的表现。在你最近参与的项目里，你通常承担什么样的角色？当团队出现分歧，或者任务推进不顺利的时候，你一般会怎么处理？你可以举一个你亲身经历的实际例子。

另外，我比较看重候选人对问题的分析能力。当你遇到一个新的任务，信息不够完整，或者没有现成的方法可以直接参考时，你通常会怎么思考？你是如何拆解问题、制定计划，并最终推进落地的？我想听听你具体的做法和过程。

接下来，我们聊聊你的学习能力和自我驱动。请你回想一下，过去一年里让你成长最快的一件事情是什么？你从中获得了哪些经验，或者培养了哪些新的能力？这些能力对你未来的职业发展有什么帮助？

然后是一个比较现实的问题。每个人都会遇到压力，比如截止时间紧、任务多、或者对结果不确定。在这种情况下，你是如何调整节奏、管理情绪，并保持效率的？你有没有一些具体的方法或者习惯？

最后，我想听听你未来一到两年的职业规划。你希望在新的环境里获得哪些成长？你最想提升的能力是什么？你觉得我们这个岗位或者团队能为你带来什么样的帮助？也可以说一下你对职业发展的长期设想。

好的，你可以稍微整理一下思路，然后按照你自己的节奏回答我这些问题。

换脸：
- face-swap-ai：收费，试了一下免费额度里的发现发际线处理不太好，会跳来跳去
暂时无法在飞书文档外展示此内容
- roopunleashed:生成太慢，四个半小时还没生成完
- picsi.ai：收费，开源代码都被下架了，不过效果应该很不错$9.99 / month，每日可获得 200 点积分，替换视频中单个角色的脸，视频时长不超过 10 秒。（文件大小上限 20MB，帧率 30 FPS，每天最多 5 个视频或 50 秒）。每 5 秒 20 个积分。
- SimSwap：有开源代码可以跑代码实现
见gpt
- akool:用来换脸
暂时无法在飞书文档外展示此内容

12月8日:EAS调用
今日计划
暂时无法在飞书文档外展示此内容
今日总结
训练视频生成
方案见12.4更新
EAS调用
调用信息-->得到公网调用地址（称为EAS_ENDPOINT）和Token
- 请求方法（Method）： 最常用的是POST、GET。
- 请求路径(URL)：由基础地址<EAS_ENDPOINT>和具体的接口路径拼接而成。
- 请求头（Headers）：通常至少需要认证信息Authorization: <Token>。
- 请求体（Body）：其格式（比如JSON）由具体部署的模型接口决定。
12月9日：git同步、接口测试、EAS部署git版
今日计划
暂时无法在飞书文档外展示此内容
今日总结
代码git管理
已同步代码到仓库https://github.com/mirror1717/AI-Interviewer-THG
代码接口测试
输入要求：
是合法的 base64 字符串，且解码后的原始字节长度是偶数
因为调用时FastAPI是通过HTTP和JSON把音频传进来的，而HTTP的JSON不能直接塞原始的二进制数组，只能传输base64字符串，所以做法是：
- 客户端：int16 PCM → bytes → base64字符串（把用户传入的音频转为base64）
- 服务器：base64字符串 → bytes → np.int16（把base64再转回原来格式进行处理）
tips:需要在客户端/工作流里多加一层「音频 → int16 → bytes → base64」的预处理
阿里云 PAI 的「工作流」节点本质也是跑一段代码，你只要：
- 在 Python 节点 或 自定义算子 里写上述「音频 → int16 → bytes → base64」这几行；
- 把生成的 audio_b64 塞进 HTTP 请求的 audio_chunk 字段；
- 其他的跟普通 HTTP 调用没区别。
关键记住这条约定：
接口的 audio_chunk 必须是：
base64( int16 PCM 的原始字节流 )，且每帧长度最好是 160 个采样（10ms）。


在DSW服务器里面测试
在terminal里跑
cd /mnt/workspace/content/drive/MyDrive/Ultralight-Digital-Human/EAS_service
export DIHUMAN_DATA_PATH=/mnt/workspace/content/drive/MyDrive/Ultralight-Digital-Human/EAS_service/stream_data
python -m uvicorn server:app --host 0.0.0.0 --port 8000
然后再另开一个terminal，跑：
curl http://127.0.0.1:8000/health
如果出现{"status":"ok"}说明服务可以成功连接
输出处理：
需要把输出的json数据再转换成图片和音频，最后把音频和视频进行合成得到最终视频
客户端代码：
import soundfile as sf
import numpy as np
import base64
import requests
import math
import cv2
from scipy.io import wavfile

wav_path = "/mnt/workspace/content/drive/MyDrive/Ultralight-Digital-Human/test_16k.wav"
audio, sr = sf.read(wav_path)

if audio.ndim > 1:
    audio = audio[:, 0]

audio = audio.astype(np.float32)
if audio.max() <= 1.0 and audio.min() >= -1.0:
    audio = audio * 32767.0
pcm_int16 = audio.astype(np.int16)

print("audio len:", len(pcm_int16), "sr:", sr)

# FastAPI / EAS 地址
url = "http://127.0.0.1:8000/stream_step"   # EAS 上改成 http://.../api/predict/xxx/stream_step
session_id = "test-session-1"

# 视频帧和音频片段缓存
frames = []
audio_chunks = []

# 先告诉后端 reset 一下（清空内部状态）
def call_step(chunk_int16, reset=False):
    # chunk_int16: np.int16 一维数组
    pcm_bytes = chunk_int16.tobytes()
    audio_b64 = base64.b64encode(pcm_bytes).decode("ascii")
    payload = {
        "session_id": session_id,
        "audio_chunk": audio_b64,
        "reset": reset,
    }
    r = requests.post(url, json=payload)
    r.raise_for_status()
    return r.json()

# 第一次调用，顺便 reset
first_chunk = pcm_int16[:160] if len(pcm_int16) >= 160 else pcm_int16
resp0 = call_step(first_chunk, reset=True)
print("first resp:", resp0)

# 把第一次的结果也存下来
audio_chunks.append(base64.b64decode(resp0["audio"]))
if resp0["check_img"] == 1 and resp0["frame"] is not None:
    img_bytes = base64.b64decode(resp0["frame"])
    img_arr = np.frombuffer(img_bytes, dtype=np.uint8)
    frame = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
    frames.append(frame)

# 后续流式发送
num_chunks = math.ceil(len(pcm_int16) / 160)
for i in range(1, num_chunks):
    start = i * 160
    end = min((i + 1) * 160, len(pcm_int16))
    chunk = pcm_int16[start:end]

    # 不足 160 的补零，和你原来的逻辑一致
    if len(chunk) < 160:
        padding = np.zeros(160 - len(chunk), dtype=np.int16)
        chunk = np.concatenate([chunk, padding])

    resp = call_step(chunk, reset=False)

    audio_chunks.append(base64.b64decode(resp["audio"]))

    if resp["check_img"] == 1 and resp["frame"] is not None:
        img_bytes = base64.b64decode(resp["frame"])
        img_arr = np.frombuffer(img_bytes, dtype=np.uint8)
        frame = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
        frames.append(frame)

print("得到视频帧数：", len(frames))
print("得到音频片段数：", len(audio_chunks))

# 把帧写成视频（可选）
if frames:
    h, w, _ = frames[0].shape
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter("test_http_video.mp4", fourcc, 20, (w, h))
    for f in frames:
        if f.shape[:2] != (h, w):
            f = cv2.resize(f, (w, h))
        writer.write(f)
    writer.release()

# 把音频写成 pcm（注意：这里写的是 16kHz，和你原来的逻辑一致）
audio_bytes_all = b"".join(audio_chunks)
audio_np = np.frombuffer(audio_bytes_all, dtype=np.int16)
wavfile.write("test_http_audio.pcm", 16000, audio_np)
print("最终音频采样点数：", audio_np.shape)
ffmpeg -y -i test_http_video.mp4 -f s16le -ar 16000 -ac 1 -i test_http_audio.pcm \
       -c:v libx264 -c:a aac result_http_test.mp4
EAS部署（git版）
set -e

# 1. 安装 OpenCV 需要的系统依赖
apt-get update && \
apt-get install -y libgl1 libglib2.0-0 git && \
rm -rf /var/lib/apt/lists/*

# -------------------------------
# 2. 克隆 GitHub 项目到本地
# -------------------------------
mkdir -p /root/app
cd /root/app

# 你自己的 GitHub 仓库
REPO_URL="https://github.com/mirror1717/AI-Interviewer-THG.git"

# 如果目录为空则直接 clone，否则先清空再 clone
if [ -d ".git" ]; then
    echo "仓库已存在，拉取最新代码..."
    git pull
else
    echo "开始克隆 GitHub 仓库..."
    git clone $REPO_URL .
fi

# -------------------------------
# 3. 安装 Python 依赖
# -------------------------------
pip install --index-url https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    --disable-pip-version-check \
    -r requirements.txt --no-cache-dir

# -------------------------------
# 4. 启动 FastAPI 服务
# -------------------------------
python -m uvicorn server:app --host 0.0.0.0 --port 8000


import soundfile as sf
import numpy as np
import base64
import requests
import math
import cv2
from scipy.io import wavfile

wav_path = "/mnt/workspace/content/drive/MyDrive/Ultralight-Digital-Human/test_16k.wav"
audio, sr = sf.read(wav_path)

if audio.ndim > 1:
    audio = audio[:, 0]

audio = audio.astype(np.float32)
if audio.max() <= 1.0 and audio.min() >= -1.0:
    audio = audio * 32767.0
pcm_int16 = audio.astype(np.int16)

print("audio len:", len(pcm_int16), "sr:", sr)

# EAS 地址
url = "http://1577983101063836.cn-hangzhou.pai-eas.aliyuncs.com/api/predict/digital_human_thg2/stream_step" 
session_id = "test-session-1"

EAS_TOKEN = "ZDViOGY5YjlmZDU3NjM0MWNlZTBhYWYzMGY0NjNhZGE5M2ZjZTYwZg=="
headers = {
    "Authorization": EAS_TOKEN,
    "Content-Type": "application/json"
}


# 视频帧和音频片段缓存
frames = []
audio_chunks = []

# 先告诉后端 reset 一下（清空内部状态）
def call_step(chunk_int16, reset=False):
    # chunk_int16: np.int16 一维数组
    pcm_bytes = chunk_int16.tobytes()
    audio_b64 = base64.b64encode(pcm_bytes).decode("ascii")
    payload = {
        "session_id": session_id,
        "audio_chunk": audio_b64,
        "reset": reset,
    }
    r = requests.post(url, json=payload, headers=headers)
    r.raise_for_status()
    return r.json()

# 第一次调用，顺便 reset
first_chunk = pcm_int16[:160] if len(pcm_int16) >= 160 else pcm_int16
resp0 = call_step(first_chunk, reset=True)
print("first resp:", resp0)

# 把第一次的结果也存下来
audio_chunks.append(base64.b64decode(resp0["audio"]))
if resp0["check_img"] == 1 and resp0["frame"] is not None:
    img_bytes = base64.b64decode(resp0["frame"])
    img_arr = np.frombuffer(img_bytes, dtype=np.uint8)
    frame = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
    frames.append(frame)

# 后续流式发送
num_chunks = math.ceil(len(pcm_int16) / 160)
for i in range(1, num_chunks):
    start = i * 160
    end = min((i + 1) * 160, len(pcm_int16))
    chunk = pcm_int16[start:end]

    # 不足 160 的补零，和你原来的逻辑一致
    if len(chunk) < 160:
        padding = np.zeros(160 - len(chunk), dtype=np.int16)
        chunk = np.concatenate([chunk, padding])

    resp = call_step(chunk, reset=False)

    audio_chunks.append(base64.b64decode(resp["audio"]))

    if resp["check_img"] == 1 and resp["frame"] is not None:
        img_bytes = base64.b64decode(resp["frame"])
        img_arr = np.frombuffer(img_bytes, dtype=np.uint8)
        frame = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
        frames.append(frame)

print("得到视频帧数：", len(frames))
print("得到音频片段数：", len(audio_chunks))

# 把帧写成视频（可选）
if frames:
    h, w, _ = frames[0].shape
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter("test_http_video.mp4", fourcc, 20, (w, h))
    for f in frames:
        if f.shape[:2] != (h, w):
            f = cv2.resize(f, (w, h))
        writer.write(f)
    writer.release()

# 把音频写成 pcm（注意：这里写的是 16kHz，和你原来的逻辑一致）
audio_bytes_all = b"".join(audio_chunks)
audio_np = np.frombuffer(audio_bytes_all, dtype=np.int16)
wavfile.write("test_http_audio.pcm", 16000, audio_np)
print("最终音频采样点数：", audio_np.shape)

!ffmpeg -y -i test_http_video.mp4 -f s16le -ar 16000 -ac 1 -i test_http_audio.pcm \
       -c:v libx264 -c:a aac result_http_test.mp4

12月11日：拉工作流
今日计划
在百炼的应用开发里拉工作流 
暂时无法在飞书文档外展示此内容
今日总结
排查EAS慢的原因
减少 HTTP 请求次数
把 160 点 → 3200 点 / 16000 点

在百炼的应用开发里拉工作流 


EAS部署（docker版）
EAS部署跑了四天还没跑好，一直在解压文件，因为OSS的压缩包挂载后在服务器解压完的文件还要存回OSS，太慢了于是被程序杀掉重启了于是陷入死循环：
尝试用docker容器打包镜像然后上传到EAS：







12月15日：THG提速+拉工作流
今日计划
暂时无法在飞书文档外展示此内容
今日总结
THG提速
缺少一个依赖cuDNN，应该是初始镜像里没有带，所以导致跑的时候是用CPU跑的，需要重构镜像
工作流
前端 (React + TypeScript + Vite)
    ↓ WebSocket (实时双向通信)
后端 (FastAPI + Python)
    ↓
流式处理流程
ASR → LLM → TTS → THG
system prompt：
你是一个专业、冷静、严肃、不太友好、喜欢刨根问底的面试官。

你的主要职责是：
1. 与用户进行自然、清晰、有引导性的对话；
2. 根据用户的回答进行追问、评价或引导下一步交流；
3. 在技术面试、学习交流或一般问答场景中，给出结构清楚、逻辑严谨的回应。

你需要遵守以下行为规范：

【角色与风格】
- 始终以“AI 面试官 / AI 对话引导者”的身份回答；
- 语气专业但不生硬，友好但不过度热情；
- 避免口语化过强的表达，不使用网络流行语；
- 不使用表情符号、不使用颜文字、不使用 Markdown。

【输入理解】
- 用户输入来自语音识别（ASR），可能存在错别字、语序不完整或口语省略；
- 在不影响原意的前提下，你可以自动纠正明显的识别错误；
- 如果用户表达不清晰，应先合理推断其意图，再进行回应；
- 如果无法判断意图，应礼貌地请求用户澄清。

【输出要求】
- 输出内容将被用于语音合成（TTS）和数字人驱动；
- 回复应以完整、自然的口语化书面中文为主；
- 单次回复长度建议控制在 2–5 句以内；
- 避免非常长的复合句，尽量使用清晰的短句；
- 不输出代码块、不输出列表符号、不输出特殊格式。

【对话目标】
- 如果是面试场景：逐步引导用户展示其思考过程、经验和能力；
- 如果是问答场景：给出清晰、有层次的解释；
- 在合适时机主动提出下一步问题或交流方向，而不是被动结束对话。

【安全与边界】
- 不生成违法、不当或具有误导性的内容；
- 对于不确定或专业性很强的问题，应明确说明限制，不编造事实。


user prompt：
以下是用户通过语音输入的内容，由语音识别系统转写，可能存在个别错误或口语省略：

“{{ASR_TEXT}}”

请你完成以下任务：
1. 理解并纠正可能的语音识别错误（仅在不改变原意的情况下）；
2. 判断用户当前的交流意图；
3. 以 AI 面试官的身份给出清晰、自然、有引导性的回应。

注意：你的回复将被用于语音合成和数字人视频生成，请保持表达自然、简洁、口语化。


后端技术栈
- FastAPI: 现代、快速的 Python Web 框架
- WebSocket: 实时双向通信
- Python 3.8+: 编程语言
- 异步处理: 支持流式处理和并行执行
tips
cd ~/digital-human/digital-human
chmod +x stop.sh
dos2unix stop.sh
./stop.sh
用WSL：
conda activate digital-human

cd ~/digital-human/digital-human/backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8001


cd ~/digital-human/digital-human/frontend
npm run dev
systemctl list-units --type=service | grep -i snap
systemctl list-units --type=service | grep -i proxy

sudo ss -lntp | grep ':8000'

sudo systemctl stop snap.snap-store-proxy.snapdevicegw.service(上一步输出的名称)
#验证是否成功释放
sudo ss -lntp | grep ':8000' || echo "8000 free"


12月16日:写工作流代码LLM节点
今日计划
暂时无法在飞书文档外展示此内容
今日总结
BUG
- 8000端口被系统占用了，改成8001端口
后端
asyns:设定并发异步函数
yield：返回结果但不终止
with:用完某实体后自动清理回收
FastAPI：@app.get("/chat")表示当进入该URL并发出get请求时，调用此装饰词后边的函数
LLM节点
