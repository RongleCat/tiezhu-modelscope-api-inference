# Tiezhu ModelScope API-Inference

把魔搭 ModelScope API-Inference 的免费模型变成本机可直接调用的 Agent skill / CLI。

它把模型发现、默认模型选择、流式解析、图片生成任务轮询、媒体压缩和 Uguu 临时 URL 上传都封装好。安装后，用户只需要提供 prompt、文件路径和 ModelScope token。

## 能做什么

- 文本生成：默认 `ZhipuAI/GLM-5.2`
- 图片识别输出文本：默认 `moonshotai/Kimi-K2.6`
- 视频识别输出文本：默认 `moonshotai/Kimi-K2.6`
- 文本生成图片：默认 `Tongyi-MAI/Z-Image-Turbo`
- 音频输入：使用 `audio_url`，在所选 ModelScope provider 可用时执行
- 模型列表：安装时初始化缓存，后续可用命令刷新当前 API-Inference 候选

## 复制给 Agent 的安装请求

把下面这句话复制给 Agent：

```text
帮我安装这个 skill：https://github.com/RongleCat/tiezhu-modelscope-api-inference.git
根据 skill 说明引导我完成 ModelScope token 配置。
```

Agent 会根据 `SKILL.md` 完成安装和初始化。标准执行流程是：

```bash
git clone https://github.com/RongleCat/tiezhu-modelscope-api-inference.git
cd tiezhu-modelscope-api-inference
bash scripts/install.sh
```

`scripts/install.sh` 会：

1. 创建 `.venv`
2. 安装 `tiezhu-modelscope`
3. 检查是否已有 `MODELSCOPE_API_KEY`
4. 如果没有 token，引导输入并写入本地 `.env`
5. 初始化刷新模型列表缓存
6. 运行环境检查

`.env` 已被 `.gitignore` 忽略，不会进入仓库。

## 手动安装

```bash
git clone https://github.com/RongleCat/tiezhu-modelscope-api-inference.git
cd tiezhu-modelscope-api-inference
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
python3 scripts/init_token.py
tiezhu-modelscope refresh
```

也可以直接使用环境变量：

```bash
export MODELSCOPE_API_KEY=your_modelscope_token
```

检查环境：

```bash
python3 scripts/check_env.py
```

查看命令：

```bash
tiezhu-modelscope --help
```

## 使用示例

### 文本生成

```bash
tiezhu-modelscope text \
  --prompt "用中文解释 API-Inference 适合什么场景"
```

### 图片识别

```bash
tiezhu-modelscope vision \
  --file "/path/to/image.png" \
  --prompt "请识别这张图片，描述主体、场景、可见文字和用途。"
```

### 文本生成图片

```bash
tiezhu-modelscope image \
  --prompt "儿童科普绘本风格，一个孩子透过飞船舷窗看见地球" \
  --size 1024x1024
```

### 视频识别

```bash
tiezhu-modelscope video \
  --file "/path/to/video.mp4" \
  --prompt "请做中文拉片，按时间顺序描述画面、字幕和节奏。"
```

### 音频输入

```bash
tiezhu-modelscope audio \
  --model Qwen/Qwen3-Omni-30B-A3B-Instruct \
  --file "/path/to/music.mp3" \
  --prompt "请分析这段音乐的曲风、情绪、结构、人声和配器。"
```

## 初始化和更新模型列表

安装脚本会自动执行一次：

```bash
tiezhu-modelscope refresh
```

之后需要更新本地模型列表时，重新运行同一个命令即可。它会把文本、多模态、视频、文生图、音频相关的 API-Inference 候选写入 `cache/`：

```bash
tiezhu-modelscope refresh
```

只刷新某一类：

```bash
tiezhu-modelscope refresh --preset text
tiezhu-modelscope refresh --preset multimodal
tiezhu-modelscope refresh --preset image
```

也可以使用别名：

```bash
tiezhu-modelscope update-models
tiezhu-modelscope init-models
```

## 查看模型候选

```bash
tiezhu-modelscope catalog text
tiezhu-modelscope catalog multimodal
tiezhu-modelscope catalog image
tiezhu-modelscope catalog audio
```

不传 `--model` 时，CLI 会优先使用默认模型，再结合本地模型列表缓存和偏好路由。缓存不存在时，CLI 会即时拉取对应任务的模型列表并写入 `cache/`。传入 `--model` 时，优先使用用户指定模型。

## 媒体 URL

图片、视频、音频输入会通过 Uguu 获取临时 HTTPS URL：

- API 文档入口：`https://uguu.se/api`
- 上传端点：`https://uguu.se/upload`
- 表单字段：`files[]`
- 返回字段：`files[0].url`

请只处理你有权上传的媒体文件。

## 目录结构

```text
tiezhu-modelscope-api-inference/
├── SKILL.md
├── README.md
├── pyproject.toml
├── scripts/
├── references/
└── assets/
```

说明：

- `SKILL.md`：Agent 触发、流程和输出契约。
- `scripts/`：CLI、ModelScope 调用实现、安装和本机环境检查。
- `references/`：完整输入到输出示例。
- `assets/`：默认提示词模板。

## 能力边界

- 如果模型返回 `has no provider supported`，表示该模型当前没有可用 ModelScope API-Inference provider。
- 如果媒体文件较大，视频和音频会先压缩再上传。
- 如果没有配置 token，只能执行 refresh、catalog 或 dry-run 类操作。
