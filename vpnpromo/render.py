"""Render a VideoScript into a vertical 9:16 mp4 (text slides + voice-over + background)."""

import asyncio
import random
import re
import subprocess
from pathlib import Path

import edge_tts
import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

from .ideas import VideoScript

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv"}
AUDIO_EXT = {".mp3", ".m4a", ".wav", ".ogg"}

# Colour schemes for the fallback gradient background: (top, bottom, accent)
PALETTES = [
    ((20, 20, 60), (120, 30, 160), (255, 214, 0)),
    ((5, 40, 60), (0, 150, 140), (255, 255, 255)),
    ((40, 0, 30), (220, 40, 90), (255, 230, 120)),
    ((10, 10, 10), (60, 60, 70), (0, 255, 170)),
]


def _run(args: list) -> subprocess.CompletedProcess:
    proc = subprocess.run([FFMPEG, "-hide_banner", "-y", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{proc.stderr[-2000:]}")
    return proc


def _duration(path: Path) -> float:
    out = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", out)
    if not m:
        raise RuntimeError(f"Cannot read duration of {path}")
    h, mnt, s = m.groups()
    return int(h) * 3600 + int(mnt) * 60 + float(s)


def _font(cfg: dict, size: int) -> ImageFont.FreeTypeFont:
    path = Path(cfg["render"]["font"])
    if not path.exists():
        path = Path(cfg["render"]["fallback_font"])
    return ImageFont.truetype(str(path), size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list:
    lines, line = [], ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_w or not line:
            line = candidate
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def _text_overlay(cfg: dict, text: str, out: Path, *, color, size: int, band: bool = False) -> None:
    """Transparent PNG with centred, outlined text that shrinks until it fits."""
    w, h = cfg["render"]["width"], cfg["render"]["height"]
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    max_w, max_h = int(w * 0.86), int(h * 0.55)

    while True:
        font = _font(cfg, size)
        lines = _wrap(draw, text, font, max_w)
        line_h = int(size * 1.2)
        if (len(lines) * line_h <= max_h and all(draw.textlength(l, font=font) <= max_w for l in lines)) or size <= 40:
            break
        size -= 6

    total_h = len(lines) * line_h
    y = (h - total_h) // 2
    if band:
        draw.rounded_rectangle((w * 0.04, y - 50, w * 0.96, y + total_h + 40), radius=40, fill=(0, 0, 0, 150))
    for line in lines:
        lw = draw.textlength(line, font=font)
        draw.text(((w - lw) / 2, y), line, font=font, fill=color,
                  stroke_width=max(4, size // 14), stroke_fill=(0, 0, 0))
        y += line_h
    img.save(out)


def _gradient(cfg: dict, top, bottom, out: Path) -> None:
    w, h = cfg["render"]["width"], cfg["render"]["height"]
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        draw.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    img.save(out)


async def _tts(text: str, voice: str, out: Path) -> None:
    await edge_tts.Communicate(text, voice, rate="+8%").save(str(out))


def _pick(folder: str, exts: set):
    files = [p for p in Path(folder).glob("*") if p.suffix.lower() in exts]
    return random.choice(files) if files else None


def render_video(cfg: dict, script: VideoScript, out_path: Path) -> Path:
    r = cfg["render"]
    w, h, fps = r["width"], r["height"], r["fps"]
    work = out_path.with_suffix("")
    work.mkdir(parents=True, exist_ok=True)
    top, bottom, accent = random.choice(PALETTES)

    # slide list: (text, voiceover, colour, base font size)
    slides = [(script.hook, script.hook if script.use_voiceover else "", accent, 120)]
    slides += [(s.text, s.voiceover if script.use_voiceover else "", (255, 255, 255), 96) for s in script.slides]
    slides.append((script.cta, script.cta if script.use_voiceover else "", accent, 100))

    # 1. overlays + per-slide audio of exact slide length
    durations, audio_parts = [], []
    for i, (text, voice_text, color, size) in enumerate(slides):
        _text_overlay(cfg, text, work / f"ov_{i}.png", color=color, size=size, band=True)
        dur = r["seconds_per_slide"]
        seg = work / f"a_{i}.wav"
        mp3 = work / f"v_{i}.mp3"
        if voice_text.strip():
            try:
                asyncio.run(_tts(voice_text, r["voice"], mp3))
            except Exception as e:  # TTS is a free unofficial endpoint; don't lose the video over it
                print(f"     TTS failed, slide {i} will be silent: {e}")
                mp3.unlink(missing_ok=True)
        if voice_text.strip() and mp3.exists() and mp3.stat().st_size > 0:
            dur = max(dur, _duration(mp3) + 0.35)
            _run(["-i", str(mp3), "-af", "apad", "-t", f"{dur:.3f}", "-ar", "44100", "-ac", "2", str(seg)])
        else:
            _run(["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{dur:.3f}", str(seg)])
        durations.append(dur)
        audio_parts.append(seg)
    total = sum(durations)

    concat_list = work / "audio.txt"
    concat_list.write_text("".join(f"file '{p.resolve()}'\n" for p in audio_parts))
    voice_track = work / "voice.wav"
    _run(["-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(voice_track)])

    # 2. background: random clip from assets/backgrounds, or a gradient
    bg = _pick("assets/backgrounds", VIDEO_EXT)
    if bg:
        bg_in = ["-stream_loop", "-1", "-i", str(bg)]
        bg_filter = f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps={fps},eq=brightness=-0.08[bg]"
    else:
        grad = work / "bg.png"
        _gradient(cfg, top, bottom, grad)
        bg_in = ["-loop", "1", "-i", str(grad)]
        # slow zoom so the frame isn't completely static
        bg_filter = (f"[0:v]scale={w * 2}:{h * 2},zoompan=z='min(zoom+0.0006,1.15)':d=1:"
                     f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps},setsar=1[bg]")

    inputs = bg_in[:]
    for i in range(len(slides)):
        inputs += ["-loop", "1", "-i", str(work / f"ov_{i}.png")]
    inputs += ["-i", str(voice_track)]
    voice_idx = len(slides) + 1

    filters, last, t = [bg_filter], "bg", 0.0
    for i, dur in enumerate(durations):
        filters.append(f"[{last}][{i + 1}:v]overlay=0:0:enable='between(t,{t:.3f},{t + dur:.3f})'[v{i}]")
        last, t = f"v{i}", t + dur

    music = _pick("assets/music", AUDIO_EXT)
    if music:
        inputs += ["-stream_loop", "-1", "-i", str(music)]
        music_vol = 0.12 if script.use_voiceover else 0.6
        filters.append(f"[{voice_idx + 1}:a]volume={music_vol}[m];[{voice_idx}:a][m]amix=inputs=2:duration=first:normalize=0[a]")
        audio_map = "[a]"
    else:
        audio_map = f"{voice_idx}:a"

    _run([*inputs, "-filter_complex", ";".join(filters), "-map", f"[{last}]", "-map", audio_map,
          "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out_path)])
    return out_path
