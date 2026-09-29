#!/usr/bin/env python3
"""Предфильтр: TF-IDF-близость публикаций к профилю интересов.

Первая ступень отбора (архитектура, шаг 2 в брифе): грубый отсев по
совпадению терминов до дорогого LLM-этапа. Работает на всём корпусе
целиком, без обращения к внешним API — быстро и бесплатно.

Как модуль:
    from pipeline.prefilter import prefilter
    ranked = prefilter(corpus["items"], profile, min_score=0.05, top_n=30)
    # ranked: [{**item, "score": float, "why": [term, ...]}, ...]

Из командной строки (печатает топ-N с оценками и объяснением):
    python -m pipeline.prefilter --profile profiles/soc_analyst.yaml
    python -m pipeline.prefilter --profile profiles/it_director_ciso.yaml \
        --corpus data/corpus-latest.json --top-n 15
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

import yaml
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

ROOT = Path(__file__).parent.parent


def _item_text(item: dict) -> str:
    return f"{item['title']} {item['summary']}"


def _profile_text(profile: dict) -> str:
    """Собирает «запрос» профиля: ключевые слова + темы (продублированные
    пропорционально весу — простой способ дать TF-IDF-вектору уклон в
    сторону более важных тем) + технологический стек."""
    parts: list[str] = list(profile.get("keywords", []))
    for t in profile.get("topics", []):
        reps = max(1, round(float(t.get("weight", 1.0)) * 3))
        parts.extend([t["name"]] * reps)
    parts.extend(profile.get("tech_stack", []))
    return " ".join(parts)


def _matched_terms(vectorizer, query_vec, item_vec, top_k: int = 4) -> list[str]:
    features = vectorizer.get_feature_names_out()
    q = query_vec.toarray().ravel()
    it = item_vec.toarray().ravel()
    shared = q * it  # ненулевое произведение = термин встречается и там, и там
    top_idx = shared.argsort()[::-1][:top_k]
    return [features[i] for i in top_idx if shared[i] > 0]


def prefilter(
    items: list[dict],
    profile: dict,
    min_score: float = 0.0,
    top_n: Optional[int] = None,
) -> list[dict]:
    """Ранжирует публикации по TF-IDF-близости к профилю. Возвращает копии
    items с полями score (0..1) и why (термины, объясняющие совпадение),
    по убыванию score. min_score отсеивает нерелевантное; top_n режет сверху."""
    if not items:
        return []

    texts = [_item_text(it) for it in items] + [_profile_text(profile)]
    vec = TfidfVectorizer(lowercase=True, min_df=1)
    X = vec.fit_transform(texts)
    item_vecs, query_vec = X[:-1], X[-1]
    scores = cosine_similarity(item_vecs, query_vec).ravel()

    deprioritize = [d.lower() for d in profile.get("deprioritize", [])]

    ranked = []
    for i, (it, score) in enumerate(zip(items, scores)):
        text_lower = _item_text(it).lower()
        if any(d in text_lower for d in deprioritize):
            score *= 0.5
        why = _matched_terms(vec, query_vec, item_vecs[i])
        ranked.append({**it, "score": round(float(score), 4), "why": why})

    ranked.sort(key=lambda r: r["score"], reverse=True)
    ranked = [r for r in ranked if r["score"] >= min_score]
    if top_n:
        ranked = ranked[:top_n]
    return ranked


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=str(ROOT / "data" / "corpus-latest.json"))
    ap.add_argument("--profile", required=True)
    ap.add_argument("--min-score", type=float, default=0.0)
    ap.add_argument("--top-n", type=int, default=20)
    args = ap.parse_args()

    corpus = json.loads(Path(args.corpus).read_text(encoding="utf-8"))
    profile = yaml.safe_load(Path(args.profile).read_text(encoding="utf-8"))

    ranked = prefilter(corpus["items"], profile, min_score=args.min_score, top_n=args.top_n)
    print(
        f"Профиль: {profile['id']} | вход: {len(corpus['items'])} | "
        f"после предфильтра: {len(ranked)}\n"
    )
    for r in ranked:
        why = ", ".join(r["why"]) or "—"
        print(f"{r['score']:.3f}  [{r['source']}] {r['title']}")
        print(f"        почему: {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
