"""Daily run: generate scripts -> render videos -> publish.

    python -m vpnpromo            # full run
    python -m vpnpromo --dry-run  # render only, don't publish
    python -m vpnpromo --demo     # no Claude call, render a built-in sample script
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import yaml

from .ideas import DailyPlan, Slide, VideoScript, generate_plan, save_history
from .publish import full_caption, send_to_telegram, upload_to_tiktok
from .render import render_video

DEMO = VideoScript(
    format="pov",
    title="Демо: YouTube тормозит",
    hook="POV: ты хотел посмотреть одно видео перед сном",
    slides=[
        Slide(text="Видео грузится 10 минут", voiceover="Видео грузится десять минут."),
        Slide(text="Качество 144p как в 2007", voiceover="Качество сто сорок четыре пэ, как в две тысячи седьмом."),
        Slide(text="Подключил за один клик — и всё летает", voiceover="Подключил за один клик, и всё летает."),
    ],
    cta="Пробный период бесплатно — ссылка в профиле",
    caption="Знакомо? 😅",
    hashtags=["жиза", "ютуб", "рекомендации", "fyp"],
    use_voiceover=True,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--dry-run", action="store_true", help="render only, don't publish")
    parser.add_argument("--demo", action="store_true", help="skip Claude, render a built-in sample")
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    out_dir = Path("output") / date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)

    plan = DailyPlan(videos=[DEMO]) if args.demo else generate_plan(cfg)
    (out_dir / "plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")

    failures = 0
    for i, script in enumerate(plan.videos, 1):
        video = out_dir / f"{i:02d}_{script.format}.mp4"
        try:
            render_video(cfg, script, video)
            (video.with_suffix(".txt")).write_text(full_caption(script), encoding="utf-8")
            print(f"[ok] rendered {video}")
            if args.dry_run:
                continue
            if cfg["publish"].get("telegram"):
                send_to_telegram(video, script)
                print("     sent to Telegram")
            if cfg["publish"].get("tiktok"):
                pid = upload_to_tiktok(video, script, cfg["publish"].get("tiktok_privacy", "SELF_ONLY"))
                print(f"     posted to TikTok, publish_id={pid}")
        except Exception as e:  # keep going with the other videos
            failures += 1
            print(f"[fail] {script.title}: {e}", file=sys.stderr)

    if not args.demo:
        save_history(plan)
    print(json.dumps({"rendered": len(plan.videos) - failures, "failed": failures}))
    sys.exit(1 if failures == len(plan.videos) else 0)


if __name__ == "__main__":
    main()
