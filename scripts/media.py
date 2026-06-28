"""Media preprocessing for ModelScope multimodal inputs."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess


@dataclass(slots=True)
class MediaInfo:
    path: Path
    duration: float | None
    size_bytes: int
    width: int | None = None
    height: int | None = None
    codec: str | None = None


def ffprobe(path: Path) -> MediaInfo:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration,size:stream=codec_type,codec_name,width,height",
        "-of",
        "json",
        str(path),
    ]
    data = json.loads(subprocess.check_output(cmd, text=True))
    fmt = data.get("format") or {}
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    return MediaInfo(
        path=path,
        duration=float(fmt["duration"]) if fmt.get("duration") else None,
        size_bytes=int(fmt.get("size") or path.stat().st_size),
        width=video.get("width"),
        height=video.get("height"),
        codec=video.get("codec_name"),
    )


def compress_video_ladder(source: Path, output_dir: Path, *, max_mb: int = 20, stop_at_max: bool = True) -> list[Path]:
    """Create increasingly small MP4s until one is under max_mb."""

    output_dir.mkdir(parents=True, exist_ok=True)
    attempts = [
        ("720p", "scale=-2:720", "1200k", "96k"),
        ("540p", "scale=-2:540", "800k", "80k"),
        ("360p", "scale=-2:360", "450k", "64k"),
        ("240p", "scale=-2:240", "260k", "48k"),
    ]
    outputs: list[Path] = []
    for label, scale, vbitrate, abitrate in attempts:
        target = output_dir / f"{source.stem}-{label}.mp4"
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-vf",
            scale,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-b:v",
            vbitrate,
            "-c:a",
            "aac",
            "-b:a",
            abitrate,
            "-movflags",
            "+faststart",
            str(target),
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        outputs.append(target)
        if stop_at_max and target.stat().st_size <= max_mb * 1024 * 1024:
            break
    return outputs


def extract_keyframes(source: Path, output_dir: Path, *, count: int = 8, width: int = 768) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    pattern = output_dir / "frame-%03d.jpg"
    duration = ffprobe(source).duration or 1
    fps = max(count / duration, 0.01)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-vf",
        f"fps={fps},scale={width}:-2",
        "-frames:v",
        str(count),
        "-q:v",
        "3",
        str(pattern),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return sorted(output_dir.glob("frame-*.jpg"))


def compress_audio(source: Path, output_dir: Path, *, max_mb: int = 8) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"{source.stem}-mono-16k.mp3"
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-b:a",
        "64k",
        str(target),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if target.stat().st_size > max_mb * 1024 * 1024:
        shorter = output_dir / f"{source.stem}-mono-16k-first180s.mp3"
        cmd[3:3] = ["-t", "180"]
        cmd[-1] = str(shorter)
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return shorter
    return target
