#!/usr/bin/env python3
"""Дедупликация: схлопывает публикации об одном и том же событии.

Вторая ступень отбора (архитектура, шаг 3 в брифе). Работает на выходе
prefilter() - то есть уже на публикациях, прошедших предфильтр для
конкретного профиля, а не на всём сыром корпусе.

ВАЖНО (найдено на синтетическом тесте по мотивам реальных данных
30.09-01.10): два РАЗНЫХ CISA-advisory с разными CVE, но общим шаблоном
("CISA has added two new vulnerabilities... based on evidence of active
exploitation.") дают косинус 0.826 - а два источника, честно пересказавших
СВОИМИ словами ОДНУ и ту же новость ("Додо Пицца"), дают всего 0.498.
То есть у шаблонных источников ложное сходство систематически ВЫШЕ, чем
у настоящих дублей с естественной русской словоформой. Простой общий
порог косинуса тут принципиально не работает - высокий порог пропустит
настоящие дубли, низкий порог схлопнет CISA-кейс. Поэтому дедуп:
  1. использует порог пониже (0.45 по умолчанию) - достаточно, чтобы
     ловить настоящие дубли вроде "Додо Пиццы";
  2. ОБЯЗАТЕЛЬНО сверяет множества CVE-номеров, упомянутых в тексте -
     если у обеих публикаций есть CVE и множества НЕ пересекаются,
     публикации считаются РАЗНЫМИ независимо от косинуса. Это не
     подстраховка "на всякий случай" - без неё CISA-кейс гарантированно
     схлопнется при любом пороге, достаточно низком, чтобы ловить
     настоящие дубли;
  3. окно по датам публикации (по умолчанию ±2 дня) - одно и то же
     реальное событие освещается в пределах нескольких дней.

НАЙДЕНО (реальные данные 02.10, профиль it_director_ciso): CVE-защита
покрывает только публикации про уязвимости. На Хабре статья "Сканер
152-ФЗ выписал нарушения..." ложно схлопнулась с двумя совершенно
не связанными статьями ("Купил мини-ПК с приставкой AI...", "Вскрываем
5G на iPhone") - косинус перепрыгнул порог, видимо, из-за общих
шаблонных фраз/вёрстки в RSS-описании Хабра, а не из-за реального
смыслового совпадения. Фикс - 4-я защита:
  4. требуется минимум MIN_SHARED_TERMS (по умолчанию 3) РЕАЛЬНО общих
     значимых слов между текстами (после стоп-слов), а не только
     близость в векторном пространстве - общий шаблон/вёрстка редко
     даёт 3+ содержательных пересечения на пустом месте.
Это общая защита (в отличие от CVE-проверки работает для любой
категории), но не абсолютная гарантия - два события одного типа с
богатым случайным пересечением лексики в теории всё ещё могут
схлопнуться. Снижает риск, не устраняет полностью.

Как модуль:
    from pipeline.dedup import deduplicate
    clusters = deduplicate(ranked_items)  # ranked_items - выход prefilter()
    # clusters: [{**primary_item, "sources": [...], "merged_count": int}, ...]

Из командной строки (предфильтр + дедуп в одном прогоне):
    python -m pipeline.dedup --profile profiles/soc_analyst.yaml --top-n 30
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from pipeline.prefilter import STOPWORDS, prefilter

ROOT = Path(__file__).parent.parent
CVE_RE = re.compile(r"CVE-\d{4}-\d{4,7}", re.IGNORECASE)

DEFAULT_SIMILARITY_THRESHOLD = 0.45
DEFAULT_DATE_WINDOW_DAYS = 2


def _item_text(item: dict) -> str:
    return f"{item['title']} {item['summary']}"


def _cve_set(text: str) -> set[str]:
    return {m.upper() for m in CVE_RE.findall(text)}


def _parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")


MIN_SHARED_TERMS = 3  # см. докстринг: найдено на реальных данных 02.10


def _should_link(a: dict, b: dict, date_window_days: int, analyzer) -> bool:
    """Доп. проверки поверх порога косинуса - см. докстринг модуля."""
    try:
        da, db = _parse_date(a["published"]), _parse_date(b["published"])
        if abs((da - db).days) > date_window_days:
            return False
    except (ValueError, KeyError):
        pass  # не можем распарсить дату - не блокируем по этому признаку

    cve_a, cve_b = _cve_set(_item_text(a)), _cve_set(_item_text(b))
    if cve_a and cve_b and cve_a.isdisjoint(cve_b):
        return False

    # Общая защита (не только для CVE-кейса): на реальных данных 02.10
    # нашли, что "Сканер 152-ФЗ..." схлопнулся с "Купил мини-ПК с
    # приставкой AI..." и "Вскрываем 5G на iPhone" - три РАЗНЫЕ статьи
    # Хабра, у которых нет ничего общего по смыслу, но косинус всё равно
    # перепрыгнул порог (вероятно, из-за общих шаблонных фраз/вёрстки в
    # RSS-описании Хабра). Требуем реальное пересечение значимых слов, а
    # не только близость в векторном пространстве.
    terms_a = {t for t in analyzer(_item_text(a))}
    terms_b = {t for t in analyzer(_item_text(b))}
    if len(terms_a & terms_b) < MIN_SHARED_TERMS:
        return False

    return True


def deduplicate(
    items: list[dict],
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    date_window_days: int = DEFAULT_DATE_WINDOW_DAYS,
) -> list[dict]:
    """Группирует похожие публикации в кластеры "одно событие". Внутри
    кластера primary - публикация с наивысшим prefilter score; поле
    sources перечисляет ВСЕ источники/ссылки кластера (включая primary),
    отсортированные по дате - требование брифа "сохранять ссылки на
    источники" не теряется при слиянии. merged_count == 1 означает, что
    публикация ни с кем не слилась."""
    if not items:
        return []

    texts = [_item_text(it) for it in items]
    vec = TfidfVectorizer(lowercase=True, min_df=1, stop_words=list(STOPWORDS))
    X = vec.fit_transform(texts)
    sim = cosine_similarity(X)

    n = len(items)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    analyzer = vec.build_analyzer()
    for i in range(n):
        for j in range(i + 1, n):
            if sim[i, j] >= similarity_threshold and _should_link(items[i], items[j], date_window_days, analyzer):
                union(i, j)

    groups: dict[int, list[int]] = {}
    for idx in range(n):
        groups.setdefault(find(idx), []).append(idx)

    clusters = []
    for idxs in groups.values():
        cluster_items = [items[i] for i in idxs]
        cluster_items.sort(key=lambda it: it.get("score", 0), reverse=True)
        primary = cluster_items[0]
        by_date = sorted(cluster_items, key=lambda it: it.get("published", ""))
        clusters.append(
            {
                **primary,
                "sources": [
                    {
                        "source": it["source"],
                        "url": it["url"],
                        "title": it["title"],
                        "published": it["published"],
                    }
                    for it in by_date
                ],
                "merged_count": len(cluster_items),
            }
        )

    clusters.sort(key=lambda c: c.get("score", 0), reverse=True)
    return clusters


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=str(ROOT / "data" / "corpus-latest.json"))
    ap.add_argument("--profile", required=True)
    ap.add_argument("--top-n", type=int, default=30, help="сколько публикаций брать из предфильтра перед дедупом")
    ap.add_argument("--min-score", type=float, default=0.0)
    ap.add_argument("--similarity-threshold", type=float, default=DEFAULT_SIMILARITY_THRESHOLD)
    ap.add_argument("--date-window-days", type=int, default=DEFAULT_DATE_WINDOW_DAYS)
    args = ap.parse_args()

    corpus = json.loads(Path(args.corpus).read_text(encoding="utf-8"))
    profile = yaml.safe_load(Path(args.profile).read_text(encoding="utf-8"))

    ranked = prefilter(corpus["items"], profile, min_score=args.min_score, top_n=args.top_n)
    clusters = deduplicate(
        ranked,
        similarity_threshold=args.similarity_threshold,
        date_window_days=args.date_window_days,
    )

    print(
        f"Профиль: {profile['id']} | после предфильтра: {len(ranked)} | "
        f"после дедупа: {len(clusters)} кластеров\n"
    )
    for c in clusters:
        tag = f"  [СЛИТО {c['merged_count']}]" if c["merged_count"] > 1 else ""
        print(f"{c['score']:.3f}  [{c['source']}] {c['title']}{tag}")
        if c["merged_count"] > 1:
            for s in c["sources"]:
                print(f"        + [{s['source']}] {s['title']}")
                print(f"          {s['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
