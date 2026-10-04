#!/usr/bin/env python3
"""Веб-интерфейс дайджеста (Streamlit).

Обёртка поверх уже готового пайплайна (pipeline/*.py + cli.py) - никакой
новой бизнес-логики, только UI и лимит на «живой запуск».

Два режима:
  - "Готовые результаты" - читает файл из output/, сформированный заранее
    через `python cli.py --profile ...`. Мгновенно, не тратит LLM-бюджет.
  - "Живой запуск" - прогоняет весь пайплайн (предфильтр -> дедуп -> LLM ->
    рендер) прямо сейчас, с видимыми демо-метриками (архитектура, раздел 6
    брифа). Ограничен простым rate-limit'ом (LIVE_RUN_LIMIT запросов за
    LIVE_RUN_WINDOW_MIN минут, файл data/live_run_log.json) - сервис будет
    висеть на публичной ngrok-ссылке, и случайный трафик не должен жечь
    чужой API-бюджет.

Запуск:
    streamlit run app.py
    # затем в отдельном терминале: ngrok http --domain=<твой-домен> 8501
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import streamlit as st
import yaml

from pipeline.dedup import deduplicate
from pipeline.llm_stage import annotate, get_backend
from pipeline.prefilter import prefilter
from pipeline.render import render_markdown

ROOT = Path(__file__).parent
VERSION = "v1.0"
LIVE_RUN_LIMIT = int(os.environ.get("LIVE_RUN_LIMIT", "5"))
LIVE_RUN_WINDOW_MIN = int(os.environ.get("LIVE_RUN_WINDOW_MIN", "10"))
RATE_LOG_PATH = ROOT / "data" / "live_run_log.json"


# --- Логика без UI (тестируется отдельно от Streamlit) ---------------------


def load_profiles(profiles_dir: Path) -> dict:
    profiles = {}
    for p in sorted(profiles_dir.glob("*.yaml")):
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        profiles[data["id"]] = data
    return profiles


def load_corpus(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _read_log(path: Path) -> list[float]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def check_rate_limit(path: Path = RATE_LOG_PATH, limit: int = LIVE_RUN_LIMIT, window_min: int = LIVE_RUN_WINDOW_MIN):
    """Возвращает (разрешено: bool, остаток_в_окне: int)."""
    window_start = time.time() - window_min * 60
    recent = [t for t in _read_log(path) if t > window_start]
    return len(recent) < limit, max(0, limit - len(recent))


def record_live_run(path: Path = RATE_LOG_PATH, window_min: int = LIVE_RUN_WINDOW_MIN) -> None:
    window_start = time.time() - window_min * 60
    recent = [t for t in _read_log(path) if t > window_start]
    recent.append(time.time())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(recent), encoding="utf-8")


def run_pipeline(
    profile: dict,
    corpus: dict,
    top_n: int = 30,
    min_score: float = 0.001,
    batch_size: int = 10,
    backend=None,
) -> tuple[str, dict]:
    """Прогоняет весь пайплайн и возвращает (markdown, демо-метрики)."""
    ranked = prefilter(corpus["items"], profile, min_score=min_score, top_n=top_n)
    clusters = deduplicate(ranked)
    backend = backend or get_backend()
    annotated = annotate(clusters, profile, batch_size=batch_size, backend=backend)
    md = render_markdown(annotated, profile)
    metrics = {
        "profile": profile["id"],
        "audience": profile.get("audience", "tech"),
        "corpus_items": len(corpus["items"]),
        "corpus_version": corpus["meta"]["version"],
        "prefilter_matched": sum(1 for r in ranked if r.get("score", 0) > 0),
        "prefilter_taken": len(ranked),
        "dedup_clusters": len(clusters),
        "dedup_merged": sum(1 for c in clusters if c.get("merged_count", 1) > 1),
        "llm_backend": backend.__class__.__name__,
        "llm_model": getattr(backend, "model", "?"),
        "final_count": len(annotated),
    }
    return md, metrics


# --- UI (streamlit) ---------------------------------------------------------


def main() -> None:
    st.set_page_config(page_title="ИТ/ИБ-Дайджест", page_icon="🛡️", layout="wide")
    st.title("🛡️ ИТ/ИБ-Дайджест")
    st.caption(f"Codenrock · задача «Ассистент для создания ИТ/ИБ-дайджестов» · версия {VERSION}")

    profiles = load_profiles(ROOT / "profiles")
    corpus = load_corpus(ROOT / "data" / "corpus-latest.json")

    if not profiles:
        st.error("Профили не найдены в `profiles/` — проверь установку.")
        st.stop()
    if corpus is None:
        st.error(
            "Корпус публикаций не найден (`data/corpus-latest.json`). "
            "Запусти `python tools/fetch_corpus.py` перед стартом сервиса."
        )
        st.stop()

    with st.sidebar:
        st.header("Настройки")
        profile_id = st.selectbox(
            "Профиль интересов",
            options=list(profiles.keys()),
            format_func=lambda pid: profiles[pid].get("role", pid),
        )
        profile = profiles[profile_id]
        st.caption(f"Аудитория: **{profile.get('audience', 'tech')}**")
        st.divider()
        mode = st.radio("Режим", ["Готовые результаты", "Живой запуск (LLM)"])
        top_n = st.slider("Сколько публикаций брать из предфильтра", 10, 50, 30)
        st.divider()
        st.caption(f"Корпус: {len(corpus['items'])} публикаций")
        st.caption(f"Собран: {corpus['meta'].get('collected_at', '?')}")
        st.caption(f"Версия корпуса: `{corpus['meta'].get('version', '?')}`")

    if mode == "Готовые результаты":
        candidates = sorted((ROOT / "output").glob(f"{profile_id}-*.md"), reverse=True)
        if not candidates:
            st.warning(
                f"Готового дайджеста для профиля `{profile_id}` нет в `output/`. "
                "Сформируй заранее (`python cli.py --profile ...`) или выбери «Живой запуск»."
            )
        else:
            md_text = candidates[0].read_text(encoding="utf-8")
            st.caption(f"Файл: `{candidates[0].name}`")
            st.download_button("Скачать .md", md_text, file_name=candidates[0].name)
            st.markdown(md_text)
    else:
        allowed, remaining = check_rate_limit()
        st.caption(f"Живых запусков доступно: {remaining}/{LIVE_RUN_LIMIT} за {LIVE_RUN_WINDOW_MIN} мин")
        if not allowed:
            st.error(
                f"Лимит живых запусков исчерпан ({LIVE_RUN_LIMIT} за {LIVE_RUN_WINDOW_MIN} мин). "
                "Попробуй позже или посмотри «Готовые результаты»."
            )
        elif st.button("Сформировать дайджест сейчас", type="primary"):
            record_live_run()
            with st.spinner("Предфильтр → дедупликация → LLM → рендер..."):
                try:
                    md_text, metrics = run_pipeline(profile, corpus, top_n=top_n)
                except RuntimeError as e:
                    st.error(f"Не настроен LLM-бэкенд: {e}")
                    st.stop()
                except ValueError as e:
                    st.error(f"LLM вернула неожиданный ответ: {e}")
                    st.stop()
                except Exception as e:  # noqa: BLE001 - демо не должно падать без объяснения
                    st.error(f"Ошибка при формировании дайджеста: {e}")
                    st.stop()

            cols = st.columns(4)
            cols[0].metric("Публикаций в корпусе", metrics["corpus_items"])
            cols[1].metric("После предфильтра", f"{metrics['prefilter_matched']}/{metrics['prefilter_taken']}")
            cols[2].metric(
                "Кластеров после дедупа",
                metrics["dedup_clusters"],
                delta=f"-{metrics['dedup_merged']} слито" if metrics["dedup_merged"] else None,
            )
            cols[3].metric("В дайджесте", metrics["final_count"])
            st.caption(f"LLM-бэкенд: **{metrics['llm_backend']}** ({metrics['llm_model']})")

            st.download_button("Скачать .md", md_text, file_name=f"{profile_id}-live.md")
            st.markdown(md_text)


if __name__ == "__main__":
    main()
