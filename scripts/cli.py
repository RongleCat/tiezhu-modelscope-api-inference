"""Command line interface."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from .catalog import CatalogError, ModelRecord, ModelScopeCatalog, read_cache, write_cache
from .config import cache_dir, preference_path
from .inference import InferenceError, ModelScopeInferenceClient, audio_messages, image_messages, text_messages, video_messages
from .media import compress_audio, compress_video_ladder, ffprobe
from .router import PreferenceStore, is_quota_error, route_models
from .uploader import UguuUploader, UploadError


DEFAULT_MODELS = {
    "text": "ZhipuAI/GLM-5.2",
    "multimodal": "moonshotai/Kimi-K2.6",
    "image": "Tongyi-MAI/Z-Image-Turbo",
}


CATALOG_PRESETS = ["text", "multimodal", "image", "text-to-image"]
DEFAULT_REFRESH_PRESETS = ["text", "multimodal", "image"]


def cmd_catalog(args: argparse.Namespace) -> int:
    data = ModelScopeCatalog().fetch_preset(args.preset, page_size=args.page_size, pages=args.pages)
    output = Path(args.output) if args.output else cache_dir() / f"{args.preset}-models.json"
    write_cache(output, data)
    print(json.dumps({"output": str(output), "models": len(data["models"]), "preset": args.preset}, ensure_ascii=False, indent=2))
    return 0


def cmd_refresh(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir) if args.output_dir else cache_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    client = ModelScopeCatalog()
    outputs = []
    presets = args.preset or DEFAULT_REFRESH_PRESETS
    for preset in presets:
        data = client.fetch_preset(preset, page_size=args.page_size, pages=args.pages)
        output = output_dir / f"{preset}-models.json"
        write_cache(output, data)
        outputs.append(
            {
                "preset": preset,
                "output": str(output),
                "models": len(data["models"]),
                "task_totals": [{"task": t.get("task"), "total": t.get("total", 0)} for t in data.get("tasks", [])],
            }
        )
    print(json.dumps({"ok": True, "outputs": outputs}, ensure_ascii=False, indent=2))
    return 0


def load_catalog(capability: str, limit: int) -> dict:
    path = cache_dir() / f"{capability}-models.json"
    if path.exists():
        try:
            return read_cache(path)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    data = ModelScopeCatalog().fetch_preset(capability, page_size=max(limit, 30), pages=1)
    write_cache(path, data)
    return data


def candidate_models(capability: str, explicit_model: str | None, limit: int) -> list[ModelRecord]:
    store = PreferenceStore(preference_path())
    fetched = load_catalog(capability, limit)
    routed = route_models(fetched["models"], capability=capability, preferences=store.load())
    preferred_model = explicit_model or DEFAULT_MODELS.get(capability)
    if preferred_model:
        routed = [ModelRecord(preferred_model, capability), *[m for m in routed if m.model_id != preferred_model]]
    return routed[:limit]


def run_chat_with_fallback(capability: str, explicit_model: str | None, messages: list[dict], limit: int) -> dict:
    client = ModelScopeInferenceClient()
    attempts = []
    for model in candidate_models(capability, explicit_model, limit):
        try:
            response = client.chat(model.model_id, messages, stream=True)
            PreferenceStore(preference_path()).remember(capability, model.model_id)
            return {"model": model.model_id, "attempts": attempts, "response": response}
        except InferenceError as exc:
            attempts.append({"model": model.model_id, "error": str(exc)})
            if not is_quota_error(exc):
                raise
    raise InferenceError(f"all {capability} candidates failed: {attempts}")


def run_image_with_fallback(capability: str, explicit_model: str | None, prompt: str, size: str, limit: int) -> dict:
    client = ModelScopeInferenceClient()
    attempts = []
    for model in candidate_models(capability, explicit_model, limit):
        try:
            response = client.image(model.model_id, prompt, size=size)
            PreferenceStore(preference_path()).remember(capability, model.model_id)
            return {"model": model.model_id, "size": size, "attempts": attempts, "response": response}
        except InferenceError as exc:
            attempts.append({"model": model.model_id, "error": str(exc)})
            if not is_quota_error(exc):
                raise
    raise InferenceError(f"all {capability} candidates failed: {attempts}")


def run_video_with_fallback(explicit_model: str | None, prompt: str, videos: list[Path], limit: int, fps: float) -> dict:
    client = ModelScopeInferenceClient()
    uploader = UguuUploader()
    attempts = []
    for video in videos:
        try:
            uploaded_url = uploader.upload(video)
        except UploadError as exc:
            attempts.append({"input_video": str(video), "size_bytes": video.stat().st_size, "upload_error": str(exc)})
            continue
        messages = video_messages(prompt, uploaded_url, fps=fps)
        for model in candidate_models("multimodal", explicit_model, limit):
            try:
                response = client.chat(model.model_id, messages, stream=True)
                PreferenceStore(preference_path()).remember("multimodal", model.model_id)
                return {"model": model.model_id, "input_video": str(video), "input_url": uploaded_url, "attempts": attempts, "response": response}
            except InferenceError as exc:
                attempts.append({"model": model.model_id, "input_video": str(video), "input_url": uploaded_url, "size_bytes": video.stat().st_size, "error": str(exc)})
                if is_quota_error(exc):
                    continue
                break
    raise InferenceError(f"all multimodal candidates failed for video input: {attempts}")


def dry_run_model_ids(capability: str, explicit_model: str | None, limit: int) -> list[str]:
    return [m.model_id for m in candidate_models(capability, explicit_model, limit)]


def cmd_text(args: argparse.Namespace) -> int:
    messages = text_messages(args.prompt)
    if args.dry_run:
        print(json.dumps({"models": dry_run_model_ids("text", args.model, args.candidate_limit), "messages": messages}, ensure_ascii=False, indent=2))
        return 0
    print(json.dumps(run_chat_with_fallback("text", args.model, messages, args.candidate_limit), ensure_ascii=False, indent=2))
    return 0


def cmd_video(args: argparse.Namespace) -> int:
    source = Path(args.file)
    out = Path(args.output_dir)
    info = ffprobe(source)
    compressed = compress_video_ladder(source, out / "video", max_mb=args.max_mb, stop_at_max=False)
    video_candidates = [p for p in compressed if p.stat().st_size <= args.max_mb * 1024 * 1024]
    if source.stat().st_size <= args.max_mb * 1024 * 1024:
        video_candidates.insert(0, source)
    video_candidates = sorted(video_candidates, key=lambda p: p.stat().st_size, reverse=True)
    prompt = args.prompt or "请按时间顺序分析这段视频的画面内容，输出中文拉片摘要、镜头变化和可见文字。"
    report = {
        "source": str(source),
        "source_info": asdict(info) | {"path": str(info.path)},
        "compressed": [{"path": str(p), "size_bytes": p.stat().st_size} for p in compressed],
        "video_candidates": [{"path": str(p), "size_bytes": p.stat().st_size} for p in video_candidates],
        "models": dry_run_model_ids("multimodal", args.model, args.candidate_limit),
        "mode": "direct_video_file",
        "fps": args.fps,
    }
    if args.dry_run:
        preview_video = video_candidates[0] if video_candidates else None
        print(json.dumps(report | {"messages_preview": {"prompt": prompt, "input_video": str(preview_video) if preview_video else None}}, ensure_ascii=False, indent=2))
        return 0
    if not video_candidates:
        raise InferenceError(f"no compressed video under {args.max_mb} MB")
    response = run_video_with_fallback(args.model, prompt, video_candidates, args.candidate_limit, args.fps)
    print(json.dumps(report | response, ensure_ascii=False, indent=2))
    return 0


def cmd_vision(args: argparse.Namespace) -> int:
    source = Path(args.file)
    prompt = args.prompt or "请识别这张图片，输出中文描述、主体、文字信息和可能的用途。"
    report = {
        "source": str(source),
        "models": dry_run_model_ids("multimodal", args.model, args.candidate_limit),
        "mode": "image_to_text",
    }
    if args.dry_run:
        print(json.dumps(report | {"messages_preview": {"prompt": prompt, "input_image": str(source)}}, ensure_ascii=False, indent=2))
        return 0
    uploaded_url = UguuUploader().upload(source)
    messages = image_messages(prompt, uploaded_url)
    response = run_chat_with_fallback("multimodal", args.model, messages, args.candidate_limit)
    print(json.dumps(report | {"input_url": uploaded_url} | response, ensure_ascii=False, indent=2))
    return 0


def cmd_audio(args: argparse.Namespace) -> int:
    source = Path(args.file)
    out = Path(args.output_dir)
    compressed = compress_audio(source, out / "audio", max_mb=args.max_mb)
    prompt = args.prompt or "请分析这段音乐，输出歌词/人声线索、曲风、情绪、结构段落、配器和适合的内容标签。"
    report = {"source": str(source), "compressed": str(compressed), "models": dry_run_model_ids("multimodal", args.model, args.candidate_limit)}
    if args.dry_run:
        print(json.dumps(report | {"messages_preview": "audio payload built"}, ensure_ascii=False, indent=2))
        return 0
    uploaded_url = UguuUploader().upload(compressed)
    messages = audio_messages(prompt, uploaded_url)
    response = run_chat_with_fallback("multimodal", args.model, messages, args.candidate_limit)
    print(json.dumps(report | {"input_url": uploaded_url} | response, ensure_ascii=False, indent=2))
    return 0


def cmd_image(args: argparse.Namespace) -> int:
    sizes = args.size or ["512x512", "768x1024", "1024x768", "1024x1024"]
    if args.dry_run:
        models = dry_run_model_ids("image", args.model, args.candidate_limit)
        print(json.dumps([{"models": models, "prompt": args.prompt, "size": s} for s in sizes], ensure_ascii=False, indent=2))
        return 0
    outputs = [run_image_with_fallback("image", args.model, args.prompt, s, args.candidate_limit) for s in sizes]
    print(json.dumps(outputs, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tiezhu-modelscope")
    sub = parser.add_subparsers(dest="cmd", required=True)

    catalog = sub.add_parser("catalog")
    catalog.add_argument("preset", choices=CATALOG_PRESETS)
    catalog.add_argument("--page-size", type=int, default=30)
    catalog.add_argument("--pages", type=int, default=1)
    catalog.add_argument("--output")
    catalog.set_defaults(func=cmd_catalog)

    refresh = sub.add_parser("refresh", aliases=["init-models", "update-models"])
    refresh.add_argument("--preset", action="append", choices=CATALOG_PRESETS)
    refresh.add_argument("--page-size", type=int, default=30)
    refresh.add_argument("--pages", type=int, default=1)
    refresh.add_argument("--output-dir")
    refresh.set_defaults(func=cmd_refresh)

    text = sub.add_parser("text")
    text.add_argument("--model")
    text.add_argument("--candidate-limit", type=int, default=10)
    text.add_argument("--prompt", required=True)
    text.add_argument("--dry-run", action="store_true")
    text.set_defaults(func=cmd_text)

    video = sub.add_parser("video")
    video.add_argument("--model")
    video.add_argument("--candidate-limit", type=int, default=10)
    video.add_argument("--file", required=True)
    video.add_argument("--output-dir", default="artifacts/media-test")
    video.add_argument("--max-mb", type=int, default=20)
    video.add_argument("--fps", type=float, default=1.0)
    video.add_argument("--prompt")
    video.add_argument("--dry-run", action="store_true")
    video.set_defaults(func=cmd_video)

    vision = sub.add_parser("vision")
    vision.add_argument("--model")
    vision.add_argument("--candidate-limit", type=int, default=10)
    vision.add_argument("--file", required=True)
    vision.add_argument("--prompt")
    vision.add_argument("--dry-run", action="store_true")
    vision.set_defaults(func=cmd_vision)

    audio = sub.add_parser("audio")
    audio.add_argument("--model")
    audio.add_argument("--candidate-limit", type=int, default=10)
    audio.add_argument("--file", required=True)
    audio.add_argument("--output-dir", default="artifacts/media-test")
    audio.add_argument("--max-mb", type=int, default=8)
    audio.add_argument("--prompt")
    audio.add_argument("--dry-run", action="store_true")
    audio.set_defaults(func=cmd_audio)

    image = sub.add_parser("image")
    image.add_argument("--model")
    image.add_argument("--candidate-limit", type=int, default=10)
    image.add_argument("--prompt", required=True)
    image.add_argument("--size", action="append")
    image.add_argument("--dry-run", action="store_true")
    image.set_defaults(func=cmd_image)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (CatalogError, InferenceError, UploadError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
