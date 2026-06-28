# 输入到输出示例

## 正确示例：图片识别

输入：

```bash
tiezhu-modelscope vision \
  --model moonshotai/Kimi-K2.6 \
  --file "/Users/me/Desktop/poster.png" \
  --prompt "请识别这张图片，描述主体、场景、可见文字和适合的用途。"
```

输出形态：

```json
{
  "source": "/Users/me/Desktop/poster.png",
  "input_url": "https://d.uguu.se/example.png",
  "model": "moonshotai/Kimi-K2.6",
  "attempts": [],
  "response": {
    "choices": [
      {
        "message": {
          "content": "这张图片展示了..."
        }
      }
    ]
  }
}
```

最终答复：

```text
已用 moonshotai/Kimi-K2.6 识别图片。主体是...；可见文字是...；适合用于...
```

## 错误示例：把失败说成成功

输入：

```bash
tiezhu-modelscope audio --model Qwen/Qwen3-Omni-30B-A3B-Instruct --file song.mp3
```

模型返回：

```json
{
  "ok": false,
  "error": "Model id ... has no provider supported"
}
```

错误答复：

```text
音乐分析完成，这首歌是古风抒情。
```

正确答复：

```text
这次没有完成音乐分析。文件已按 audio_url 路径提交，但该模型当前没有可用 ModelScope API-Inference provider。
```
