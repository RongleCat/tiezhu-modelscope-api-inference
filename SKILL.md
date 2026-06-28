---
name: tiezhu-modelscope-api-inference
description: >-
  Install and call ModelScope/魔搭 API-Inference free models with minimal setup,
  including token setup, model-list initialization/update, text generation,
  multimodal image/video/audio-to-text, and text-to-image generation. Trigger
  keywords: 安装这个 skill, 魔搭, ModelScope, API-Inference, 免费模型, 初始化模型列表,
  更新模型列表, 文本生成, 文生图, 图片识别, 视频拉片, 多模态, audio_url, video_url. Do not
  trigger for non-ModelScope providers, pure evaluation/ranking tasks, or tasks
  that only need local media conversion.
---

# Tiezhu ModelScope API-Inference

## 1. 目标是什么

让用户不用研究 ModelScope API-Inference 的接口细节，也能直接调用魔搭免费模型完成：

- 文本生成。
- 多模态识别输出文本，包括图片识别、视频拉片和音频/音乐分析。
- 文本生成图片。

Skill 负责模型发现、模型列表缓存、默认模型选择、流式解析、图片生成任务轮询、媒体压缩、Uguu 临时 URL 上传和清晰错误输出。

## 2. 什么情况下触发

当用户表达以下意图时触发：

- “用魔搭/ModelScope 跑一个模型”
- “帮我安装这个 skill”
- “根据 skill 说明配置 ModelScope token”
- “调用 API-Inference”
- “找一个免费的魔搭模型生成文本/图片”
- “识别这张图片”
- “视频拉片/视频内容分析”
- “把音频发给魔搭模型分析”
- “列一下当前可用的 API-Inference 模型”
- “初始化/更新魔搭模型列表”

正确触发示例：

```text
用魔搭免费模型识别这张图，输出中文描述。
```

## 3. 什么情况下不要触发

以下情况不要触发本 skill：

- 用户明确要使用 OpenAI、Gemini、Claude、百炼、火山、硅基流动等非 ModelScope provider。
- 用户只需要本地 ffmpeg 压缩、转码、抽音轨，不需要调用 ModelScope。
- 用户只想做纯评测排行、学术评测或成本对比，不需要实际调用模型。
- 用户没有授权上传本地媒体文件，但任务需要 `image_url`、`video_url` 或 `audio_url`。

错误触发示例：

```text
把这个 MP4 转成 720p，不要调用任何云服务。
```

这应使用本地媒体处理，不触发本 skill。

## 4. 开始前先收集什么信息

开始调用前先确认这些信息：

- 任务类型：`install`、`refresh`、`catalog`、`text`、`vision`、`image`、`video`、`audio`。
- Prompt：用户想让模型输出什么。
- 模型：用户是否指定 `--model`。
- 文件路径：图片、视频或音频任务必须有本地文件路径。
- Token：环境变量 `MODELSCOPE_API_KEY` / `MODELSCOPE_TOKEN` 或本地 `.env` 是否已设置。
- 媒体授权：需要上传到 Uguu 时，确认文件是用户提供或明确授权处理的。

如果缺少 token：

- 先运行 `python3 scripts/init_token.py` 进入初始化流程。
- 可以继续做 `--dry-run`、`refresh` 或 `catalog` 查询。
- 只把 token 写入本地 `.env`；该文件必须保持在 `.gitignore` 中。

如果缺少媒体文件路径：

- 直接向用户要路径。
- 不要猜测目录里的文件。

## 5. 按什么顺序干活

### 5.1 选择命令

- 安装和初始化：用 `bash scripts/install.sh`。
- 初始化/更新模型列表：用 `tiezhu-modelscope refresh`。
- 文本生成：用 `tiezhu-modelscope text`。
- 图片识别输出文本：用 `tiezhu-modelscope vision`。
- 文本生成图片：用 `tiezhu-modelscope image`。
- 视频识别输出文本：用 `tiezhu-modelscope video`。
- 音频/音乐分析：用 `tiezhu-modelscope audio`。
- 查看模型候选：用 `tiezhu-modelscope catalog <preset>`。

如果用户是在安装 skill：

```bash
git clone https://github.com/RongleCat/tiezhu-modelscope-api-inference.git
cd tiezhu-modelscope-api-inference
bash scripts/install.sh
```

如果 `scripts/install.sh` 提示输入 token，引导用户提供 ModelScope token。输入会写入本地 `.env`，用于后续调用。

安装脚本会自动执行一次 `tiezhu-modelscope refresh`。如果用户后续说“更新模型列表”，运行：

```bash
tiezhu-modelscope refresh
```

如果只更新某个分类：

```bash
tiezhu-modelscope refresh --preset text
tiezhu-modelscope refresh --preset multimodal
tiezhu-modelscope refresh --preset image
```

安装完成摘要或模型列表表格只列三类：文本生成、多模态识别、文本生成图片。不要把图片识别、视频拉片、音频/音乐分析拆成独立模型池；它们都属于多模态识别。

也可以使用别名：

```bash
tiezhu-modelscope update-models
tiezhu-modelscope init-models
```

### 5.2 选择模型

默认优先模型：

- 文本生成：`ZhipuAI/GLM-5.2`
- 多模态识别输出文本：`moonshotai/Kimi-K2.6`，用于图片、视频、音频输入。
- 文本生成图片：`Tongyi-MAI/Z-Image-Turbo`

决策分支：

- 如果用户指定了 `--model`，优先使用用户指定模型。
- 如果用户没有指定模型，使用对应任务的默认模型。
- 如果本地 `cache/` 有模型列表，先用缓存参与候选路由。
- 如果缓存不存在，自动拉取当前分类模型列表并写入 `cache/`。
- 如果默认模型额度、限流或 provider 不可用，切换到同能力候选。
- 如果错误不是额度/限流/provider 类错误，停止并输出错误，不要盲目重试。

### 5.3 处理媒体

图片识别：

- 上传图片到 Uguu。
- 把返回的 HTTPS URL 放入 `image_url`。
- 走多模态识别模型。

视频识别：

- 用压缩阶梯生成较小 MP4。
- 上传候选 MP4 到 Uguu。
- 把返回的 HTTPS URL 放入 `video_url`。
- 发送完整视频 URL。
- 走多模态识别模型。

音频分析：

- 压缩为 mono 16 kHz MP3。
- 上传 MP3 到 Uguu。
- 把返回的 HTTPS URL 放入 `audio_url`。
- 走多模态识别模型。
- 如果模型返回不支持 `audio_url` 或 `has no provider supported`，说明当前 ModelScope provider 不可用。

文本生成图片：

- 调用 `/images/generations`。
- 如果返回 `task_id`，轮询任务直到得到图片 URL 或失败。

### 5.4 命令示例

文本：

```bash
tiezhu-modelscope text --prompt "用中文解释 API-Inference 的适用场景"
```

图片识别：

```bash
tiezhu-modelscope vision \
  --file "/path/to/image.png" \
  --prompt "请识别这张图片，描述主体、场景、可见文字和用途。"
```

文生图：

```bash
tiezhu-modelscope image \
  --prompt "儿童科普绘本风格，一个孩子透过飞船舷窗看见地球" \
  --size 1024x1024
```

视频：

```bash
tiezhu-modelscope video \
  --file "/path/to/video.mp4" \
  --prompt "请做中文拉片，按时间顺序描述画面、字幕和节奏。"
```

## 6. 输出必须长什么样

CLI 输出必须是 JSON，便于 Agent 继续处理。

成功输出至少包含：

- `model`
- `response`
- `attempts`

媒体任务还应包含：

- `source`
- `input_url`
- 预处理结果，例如 `compressed` 或 `video_candidates`

失败输出必须是 JSON：

```json
{
  "ok": false,
  "error": "HTTP 400: ..."
}
```

不要输出未结构化 traceback 给用户。

## 7. 做到什么程度算完成

以下条件全部满足才算完成：

- 选对任务命令。
- 使用用户指定模型，或使用默认模型。
- 安装流程已执行模型列表初始化；用户要求更新模型列表时，已执行 `tiezhu-modelscope refresh` 并说明缓存位置。
- 需要媒体 URL 时已通过 Uguu 获取 HTTPS URL。
- ModelScope 返回了可用结果，或返回了明确 provider/额度/参数错误。
- 最终答复说明模型、输入、输出结果位置或失败原因。
- 没有把 API key、Authorization、Cookie、CSRF 写入仓库文件或回答；API key 只允许写入本地 `.env`。

可验证标准：

- `tiezhu-modelscope --help` 能看到 `catalog,refresh,text,video,vision,audio,image`。
- `tiezhu-modelscope refresh --page-size 3` 能写入 `cache/text-models.json`、`cache/multimodal-models.json`、`cache/image-models.json`。
- `--dry-run` 能显示默认模型排在候选第一位。
- 真实调用成功时，JSON 里有 `response.choices[0].message.content` 或图片 URL。

## 8. 搞不定的时候怎么处理

常见失败处理：

- `MODELSCOPE_API_KEY is not set`：运行 `python3 scripts/init_token.py` 或提示用户设置环境变量。
- `has no provider supported`：说明该模型当前没有可用 API-Inference provider，建议换模型或稍后再试。
- `quota`、`rate limit`、`429`：切换同能力候选模型。
- Uguu 上传失败：提示用户检查网络、文件大小或换一个可公开访问的 URL。
- 视频过大：降低 `--max-mb`，让压缩阶梯选择更小 MP4。
- 多模态模型不支持当前媒体类型：如实说明 provider 限制，不要伪造分析结果。

如果用户的要求必须调用外部服务，但未授权上传媒体文件，先请求授权。

## 9. 什么时候去读参考文件

- 需要完整输入到输出示例时，读取 `references/output-example.md`。
- 需要默认提示词时，读取 `assets/default-prompts.json`。
- 日常调用不需要读取参考文件；优先直接使用 CLI。
