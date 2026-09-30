#!/usr/bin/env python3
"""Предфильтр: TF-IDF-близость публикаций к профилю интересов.

Первая ступень отбора (архитектура, шаг 2 в брифе): грубый отсев по
совпадению терминов до дорогого LLM-этапа. Работает на всём корпусе
целиком, без обращения к внешним API — быстро и бесплатно.

Как модуль:
    from pipeline.prefilter import prefilter
    ranked = prefilter(corpus["items"], profile, min_score=0.05, top_n=30)
    # ranked: [{**item, "score": float, "why": [term_or_phrase, ...]}, ...]

Из командной строки (печатает топ-N с оценками и объяснением):
    python -m pipeline.prefilter --profile profiles/soc_analyst.yaml
    python -m pipeline.prefilter --profile profiles/it_director_ciso.yaml \
        --corpus data/corpus-latest.json --top-n 15

ИСТОРИЯ ФИКСОВ (реальные прогоны 29-30.09, важно для дальнейшей отладки):

  1. Предлоги в why ("на", "по", "об") - многословные keyword-фразы
     ("атака на компанию") при разбиении на отдельные слова тащили с собой
     служебные слова. Фикс: список стоп-слов STOPWORDS.

  2. После фикса №1 профиль it_director_ciso всё равно слабо отличался от
     devops_engineer - статья про Terraform держалась в топе обоих. Причина
     глубже стоп-слов: keyword "критическая информационная инфраструктура"
     и тема "Стратегия ИБ и управление рисками" при разбиении на отдельные
     слова оставляли "инфраструктура" и "управление" - формально не
     стоп-слова, но слишком общие в отрыве от фразы, чтобы быть сигналом
     профиля; они совпадали с любой статьёй про инфраструктуру/управление
     чем угодно. Фикс: однословные keywords и tech_stack по-прежнему летят
     в общий TF-IDF-мешок слов, а многословные keywords и названия тем
     (topics) больше НЕ разбираются на отдельные слова для TF-IDF - вместо
     этого они проверяются как фраза (все значимые слова фразы должны
     встретиться в тексте публикации) и дают отдельный бонус к базовой
     TF-IDF-оценке.

  3. Тот же баг оставался в tech_stack — профиль it_director_ciso содержит
     многословные записи ("корпоративная ИТ-инфраструктура", "отечественные
     решения ИБ"), которые я забыл провести через тот же unigram/фраза
     фильтр, что и keywords — "инфраструктура" продолжала течь оттуда.
     Фикс: та же логика применена к tech_stack.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Optional

import yaml
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

ROOT = Path(__file__).parent.parent
WORD_RE = re.compile(r"\w+", re.UNICODE)

STOPWORDS = frozenset(
    """
и в во не что он на я с со как а то все она так его но да ты к у же вы за бы
по только ее мне было вот от меня еще нет о из ему теперь когда даже ну вдруг
ли если уже или ни быть был него до вас нибудь опять уж вам ведь там потом
себя ничего ей может они тут где есть надо ней для мы тебя их чем была сам
чтоб без будто чего раз тоже себе под будет ж тогда кто этот того потому
этого какой совсем ним здесь этом один почти мой тем чтобы нее сейчас были
куда зачем всех никогда можно при наконец два об другой хоть после над
больше тот через эти нас про всего них какая много разве три эту моя
впрочем хорошо свою этой перед иногда лучше чуть том нельзя такой им более
всегда конечно всю между это которые который которая которых чем является
также ru com
the a an of to in for on with and or is are was were be by at from as this
that it its has have
""".split()
)

MIN_WORD_LEN = 2
PHRASE_BONUS = 0.06  # вклад одного полностью совпавшего keyword'а-фразы
TOPIC_BONUS = 0.05   # вклад одной полностью совпавшей темы (масштабируется её weight)


def _item_text(item: dict) -> str:
    return f"{item['title']} {item['summary']}"


def _significant_words(phrase: str) -> list[str]:
    words = [w.lower() for w in WORD_RE.findall(phrase)]
    return [w for w in words if w not in STOPWORDS and len(w) >= MIN_WORD_LEN]


def _profile_signals(profile: dict) -> tuple[str, list[tuple[str, list[str], float]], set[str]]:
    """Возвращает (текст для TF-IDF-вектора запроса, список фраз-бонусов).

    Фразы-бонусы - тройки (имя, значимые слова, вес): многословные keywords
    (вес 1.0) и названия topics (вес = их weight)."""
    unigrams: list[str] = []
    phrases: list[tuple[str, list[str], float]] = []

    for kw in profile.get("keywords", []):
        if len(kw.split()) == 1:
            unigrams.append(kw)
        else:
            sig = _significant_words(kw)
            if sig:
                phrases.append((kw, sig, 1.0))

    topic_names = set()
    for t in profile.get("topics", []):
        sig = _significant_words(t["name"])
        if sig:
            phrases.append((t["name"], sig, float(t.get("weight", 1.0))))
            topic_names.add(t["name"])

    # tech_stack пострадал от того же бага, что раньше keywords/topics:
    # многословные записи ("корпоративная ИТ-инфраструктура") резались на
    # отдельные слова и утекали как generic-шум ("инфраструктура"). Та же
    # логика unigram-vs-фраза, что и для keywords выше.
    for tech in profile.get("tech_stack", []):
        if len(tech.split()) == 1:
            unigrams.append(tech)
        else:
            sig = _significant_words(tech)
            if sig:
                phrases.append((tech, sig, 1.0))

    return " ".join(unigrams), phrases, topic_names


def _matched_terms(vectorizer, query_vec, item_vec, top_k: int = 4) -> list[str]:
    features = vectorizer.get_feature_names_out()
    q = query_vec.toarray().ravel()
    it = item_vec.toarray().ravel()
    shared = q * it
    top_idx = shared.argsort()[::-1][:top_k]
    return [features[i] for i in top_idx if shared[i] > 0]


def prefilter(
    items: list[dict],
    profile: dict,
    min_score: float = 0.0,
    top_n: Optional[int] = None,
) -> list[dict]:
    """Ранжирует публикации по близости к профилю: база - TF-IDF-косинус по
    однословным keywords/tech_stack, плюс бонус за полное совпадение
    многословных keyword-фраз и тем. Возвращает копии items с полями score
    (float) и why (термины и/или «фразы» в кавычках), по убыванию score.
    min_score отсеивает нерелевантное; top_n режет выдачу сверху."""
    if not items:
        return []

    query_text, phrases, topic_names = _profile_signals(profile)
    texts = [_item_text(it) for it in items] + [query_text]
    vec = TfidfVectorizer(lowercase=True, min_df=1, stop_words=list(STOPWORDS))
    X = vec.fit_transform(texts)
    item_vecs, query_vec = X[:-1], X[-1]
    base_scores = cosine_similarity(item_vecs, query_vec).ravel()

    deprioritize = [d.lower() for d in profile.get("deprioritize", [])]

    ranked = []
    for i, (it, base) in enumerate(zip(items, base_scores)):
        text_lower = _item_text(it).lower()

        bonus = 0.0
        matched_phrases: list[str] = []
        for name, sig_words, weight in phrases:
            if all(w in text_lower for w in sig_words):
                is_topic = name in topic_names
                bonus += (TOPIC_BONUS if is_topic else PHRASE_BONUS) * weight
                matched_phrases.append(name)

        score = base + bonus
        if any(d in text_lower for d in deprioritize):
            score *= 0.5

        why = _matched_terms(vec, query_vec, item_vecs[i])
        why += [f'\u00ab{p}\u00bb' for p in matched_phrases[:2]]

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
        why = ", ".join(r["why"]) or "-"
        print(f"{r['score']:.3f}  [{r['source']}] {r['title']}")
        print(f"        почему: {why}")
        snippet = r["summary"][:120].replace("\n", " ")
        if snippet:
            print(f"        текст: {snippet}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
