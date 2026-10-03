#!/usr/bin/env python3
"""Точка входа: прогоняет весь пайплайн (предфильтр -> дедуп -> LLM -> рендер)
для одного профиля и пишет готовый дайджест в Markdown.

Печатает демо-метрики, которые архитектура (раздел 6 брифа) явно просит
показывать на экране во время презентации: сколько источников опрошено и
рабочих, сколько публикаций на входе, сколько отсеяно предфильтром, сколько
слито как дубли, сколько попало в дайджест, какой бэкенд LLM использован,
какая аудитория выбрана.

Использование:
    python cli.py --profile profiles/soc_analyst.yaml
    python cli.py --profile profiles/it_director_ciso.yaml --top-n 20 --out output/cio.md
    LLM_BACKEND=ollama python cli.py --profile profiles/devops_engineer.yaml

Перед запуском нужен реальный корпус (tools/fetch_corpus.py) и ключ
нужного LLM-бэкенда в .env (см. .env.example) - сам cli.py их не создаёт.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from pipeline.dedup import deduplicate
from pipeline.llm_stage import annotate, get_backend
from pipeline.prefilter import prefilter
from pipeline.render import render_markdown

ROOT = Path(__file__).parent


def main() -> int:
    ap = argparse.ArgumentParser(description="Собрать дайджест по профилю из уже готового корпуса.")
    ap.add_argument("--corpus", default=str(ROOT / "data" / "corpus-latest.json"))
    ap.add_argument("--sources", default=str(ROOT / "sources.yaml"))
    ap.add_argument("--profile", required=True)
    ap.add_argument("--top-n", type=int, default=30, help="сколько публикаций брать из предфильтра перед дедупом/LLM")
    ap.add_argument(
        "--min-score",
        type=float,
        default=0.001,
        help="исключает публикации с нулевым score (вообще не совпали с профилем) - "
        "не агрессивный порог релевантности, см. HANDOFF: 03.10 без него в дайджест "
        "CIO попадало 22/30 заведомо нерелевантных публикаций",
    )
    ap.add_argument("--batch-size", type=int, default=10)
    ap.add_argument("--out", help="путь для .md; по умолчанию output/<профиль>-<версия корпуса>.md")
    args = ap.parse_args()

    corpus = json.loads(Path(args.corpus).read_text(encoding="utf-8"))
    profile = yaml.safe_load(Path(args.profile).read_text(encoding="utf-8"))
    all_sources = yaml.safe_load(Path(args.sources).read_text(encoding="utf-8"))["sources"]

    ranked = prefilter(corpus["items"], profile, min_score=args.min_score, top_n=args.top_n)
    clusters = deduplicate(ranked)

    backend = get_backend()
    annotated = annotate(clusters, profile, batch_size=args.batch_size, backend=backend)

    md = render_markdown(annotated, profile)

    out_path = Path(args.out) if args.out else ROOT / "output" / f"{profile['id']}-{corpus['meta']['version']}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")

    merged_count = sum(1 for c in clusters if c.get("merged_count", 1) > 1)
    absorbed = len(ranked) - len(clusters)
    matched = sum(1 for r in ranked if r.get("score", 0) > 0)

    print("=" * 60)
    print(f"Профиль:        {profile['id']} ({profile.get('audience', 'tech')})")
    print(f"Источники:      {len(corpus['meta'].get('sources', []))}/{len(all_sources)} рабочих (из sources.yaml)")
    print(f"Корпус:         {len(corpus['items'])} публикаций (версия {corpus['meta']['version']})")
    print(f"Предфильтр:     {matched} с ненулевым score, взято топ-{len(ranked)}")
    print(f"Дедупликация:   {len(clusters)} кластеров ({merged_count} слитых, поглощено {absorbed} публикаций)")
    print(f"LLM-бэкенд:     {backend.__class__.__name__} ({getattr(backend, 'model', '?')})")
    print(f"В дайджесте:    {len(annotated)} публикаций")
    print(f"Файл:           {out_path}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
