"""Generate daily video scripts with Claude."""

import json
from datetime import date
from pathlib import Path
from typing import List, Literal

import anthropic
from pydantic import BaseModel, Field

HISTORY_FILE = Path("state/history.json")
HISTORY_LIMIT = 60


class Slide(BaseModel):
    text: str = Field(description="Text on screen, max ~12 words")
    voiceover: str = Field(description="What the voice says; empty string for silent meme slides")


class VideoScript(BaseModel):
    format: Literal["meme", "pov", "story", "top_list"]
    title: str = Field(description="Internal short name of the idea")
    hook: str = Field(description="First-second hook shown in huge letters")
    slides: List[Slide] = Field(description="2-5 slides after the hook")
    cta: str = Field(description="Final call to action, mentions the brand naturally")
    caption: str = Field(description="TikTok caption, 1-2 sentences")
    hashtags: List[str] = Field(description="5-8 hashtags without #, mostly Russian-language trends")
    use_voiceover: bool


class DailyPlan(BaseModel):
    videos: List[VideoScript]


SYSTEM = """Ты — SMM-креатор, который делает короткие вертикальные ролики и мемы для TikTok \
на русскоязычную аудиторию. Твоя задача — придумать ролики, которые досматривают до конца \
и которые органично продвигают продукт, не выглядя как скучная реклама.

Правила:
- Первый кадр (hook) должен цеплять за 1 секунду: вопрос, боль, узнаваемая ситуация, интрига.
- Опирайся на узнаваемые бытовые ситуации и актуальные мем-форматы.
- Бренд упоминай в конце или вскользь, не в каждом слайде.
- Используй только факты о продукте из списка features — ничего не выдумывай \
(никаких цифр скорости, цен или гарантий, которых нет в списке).
- Никаких призывов к нарушению закона, никаких упоминаний запрещённого контента.
- Каждый ролик должен отличаться от прошлых идей по сюжету и формату.
- Текст на экране без эмодзи (они не отрисовываются), эмодзи можно только в caption."""


def _load_history() -> list:
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    return []


def save_history(plan: DailyPlan) -> None:
    history = _load_history()
    history += [{"date": date.today().isoformat(), "title": v.title, "hook": v.hook} for v in plan.videos]
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(history[-HISTORY_LIMIT:], ensure_ascii=False, indent=2), encoding="utf-8")


def generate_plan(cfg: dict) -> DailyPlan:
    brand, content = cfg["brand"], cfg["content"]
    past = "\n".join(f"- {h['title']}: {h['hook']}" for h in _load_history()) or "(пока нет)"

    prompt = f"""Сегодня {date.today().strftime('%d.%m.%Y')}. Придумай {content['videos_per_day']} ролика.

Продукт: {brand['name']}
Куда вести: {brand['cta_link']}
Промокод: {brand.get('promo_code') or 'нет'}
Факты о продукте (features):
{chr(10).join('- ' + f for f in brand['features'])}
Аудитория: {brand['audience']}
Доступные форматы: {', '.join(content['formats'])}
Пожелания по стилю: {content.get('style_notes', '')}

Уже были такие идеи, не повторяй их:
{past}

Для формата meme ставь use_voiceover=false и пустой voiceover."""

    client = anthropic.Anthropic()
    response = client.messages.parse(
        model="claude-opus-5",
        max_tokens=16000,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium"},
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        output_format=DailyPlan,
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"Claude declined the request: {response.stop_details}")
    return response.parsed_output
