#!/usr/bin/env python3
"""Рендер дайджеста в Markdown.

Пятая, финальная ступень пайплайна (архитектура, шаг 5 в брифе). Принимает
размеченные кластеры (выход llm_stage.annotate()) и профиль, возвращает
готовый Markdown. Формат подогнан под аудиторию профиля:

  - tech (soc_analyst, devops_engineer): группировка по категории
    (Атака/Уязвимость/Инфо - порядок и веса из TECH_GROUP_WEIGHTS), внутри
    группы сортировка по весу (Высокий -> Низкий), у каждой публикации -
    объяснение релевантности и ссылки на ВСЕ источники кластера (dedup.py
    сохраняет их все, даже после слияния).
  - manager (it_director_ciso): плоский пронумерованный список, у каждой
    публикации - готовый digest_text (3-4 строки) и теги, формат близкий
    к примеру организаторов (Dataset 2: заголовок/описание/ссылка).

Как модуль:
    from pipeline.render import render_markdown
    md_text = render_markdown(annotated, profile)  # annotated - выход annotate()

Из командной строки (прогоняет только сам рендер поверх уже готового
annotated-JSON - для отладки форматирования без похода к LLM):
    python -m pipeline.render --annotated /tmp/annotated.json --profile profiles/soc_analyst.yaml
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from pipeline.llm_stage import TECH_GROUP_WEIGHTS

ROOT = Path(__file__).parent.parent


def _source_links(item: dict) -> str:
    srcs = item.get("sources") or [{"source": item.get("source", ""), "url": item.get("url", "")}]
    return ", ".join(f"[{s['source']}]({s['url']})" for s in srcs if s.get("url"))


def _tech_sort_key(item: dict):
    group_order = list(TECH_GROUP_WEIGHTS.keys())
    group = item.get("group", "")
    g_idx = group_order.index(group) if group in group_order else len(group_order)
    w_list = TECH_GROUP_WEIGHTS.get(group, [])
    weight = item.get("weight", "")
    w_idx = w_list.index(weight) if weight in w_list else len(w_list)
    return (g_idx, w_idx)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def render_tech_markdown(annotated: list[dict], profile: dict) -> str:
    lines = [
        f"# Дайджест ИТ/ИБ — {profile.get('role', profile['id'])}",
        "",
        f"_Сформировано: {_now()} · профиль: `{profile['id']}` · публикаций: {len(annotated)}_",
        "",
    ]
    current_group, current_weight = None, None
    for it in sorted(annotated, key=_tech_sort_key):
        group = it.get("group", "Без категории")
        weight = it.get("weight", "—")
        if group != current_group:
            lines.append(f"## {group}")
            current_group, current_weight = group, None
        if weight != current_weight:
            lines.append(f"### {weight}")
            current_weight = weight
        lines.append(f"- **{it['title']}** — {it.get('explanation', '').strip()}")
        links = _source_links(it)
        if links:
            lines.append(f"  Источники: {links}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_manager_markdown(annotated: list[dict], profile: dict) -> str:
    lines = [
        f"# Дайджест ИБ для руководства — {profile.get('role', profile['id'])}",
        "",
        f"_Сформировано: {_now()} · публикаций: {len(annotated)}_",
        "",
    ]
    for i, it in enumerate(annotated, start=1):
        lines.append(f"### {i}. {it['title']}")
        lines.append("")
        lines.append(it.get("digest_text", "").strip())
        lines.append("")
        tags = ", ".join(it.get("tags", []))
        if tags:
            lines.append(f"**Теги:** {tags}")
        links = _source_links(it)
        if links:
            lines.append(f"**Источники:** {links}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_markdown(annotated: list[dict], profile: dict) -> str:
    if not annotated:
        return (
            f"# Дайджест — {profile.get('role', profile['id'])}\n\n"
            f"_Сформировано: {_now()}_\n\n"
            "Публикаций, прошедших отбор по текущему профилю, не найдено.\n"
        )
    audience = profile.get("audience", "tech")
    if audience == "manager":
        return render_manager_markdown(annotated, profile)
    return render_tech_markdown(annotated, profile)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--annotated", required=True, help="JSON-файл с выходом llm_stage.annotate()")
    ap.add_argument("--profile", required=True)
    ap.add_argument("--out", help="путь для .md; по умолчанию печатает в stdout")
    args = ap.parse_args()

    annotated = json.loads(Path(args.annotated).read_text(encoding="utf-8"))
    profile = yaml.safe_load(Path(args.profile).read_text(encoding="utf-8"))
    md = render_markdown(annotated, profile)

    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"Записано: {args.out}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
