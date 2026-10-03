#!/usr/bin/env python3
"""LLM-этап: оценка, группировка и объяснение по таксономии организаторов.

Четвёртая ступень (архитектура, шаг 4 в брифе). Принимает кластеры после
dedup.py, батчами вызывает LLM и размечает каждый кластер по таксономии
из файла-образца организаторов (01.10, Датасет_с_примерами_v4.0.xlsx):

  - аудитория "технарь" (soc_analyst, devops_engineer, profile["audience"]
    == "tech"): группа Атака/Уязвимость/Инфо + вес-приоритет по шкале ЭТОЙ
    группы + краткое объяснение релевантности профилю.
  - аудитория "менеджер" (it_director_ciso, audience == "manager"): один
    или НЕСКОЛЬКО тегов (в примерах организаторов теги множественные, не
    один на публикацию) из фиксированного списка 12 + готовый текст
    дайджеста в 3-4 строки для нетехнического руководителя.

ПРОСТАЯ ВЕРСИЯ (решение от 02.10, зафиксировано в памяти проекта): без
полного структурного извлечения 8-10 полей из Dataset 1 (атакующая
группировка, страна жертвы, CVSS-вектор, IOC и т.п.) - это отдельный
следующий шаг, если останется время. Сейчас - релевантность + категория +
объяснение, по аналогии с уже проверенной логикой prefilter.py/dedup.py.

Бэкенд переключается переменной окружения LLM_BACKEND, не веткой кода -
требование организаторов (Q&A 30.09). Четыре варианта (02.10: добавлены
gemini/openrouter - нет ключа Anthropic, нужна была универсальность):
    LLM_BACKEND=claude (по умолчанию) - нужен ANTHROPIC_API_KEY в .env
    LLM_BACKEND=ollama - нужен запущенный `ollama serve` и модель
        `ollama pull qwen3.6:35b-a3b` (рекомендуется
        OLLAMA_CONTEXT_LENGTH>=22000 - см. HANDOFF.md). Обязателен для
        финальной проверки организаторами (см. Q&A 30.09).
    LLM_BACKEND=gemini - нужны GEMINI_API_KEY и GEMINI_MODEL в .env
    LLM_BACKEND=openrouter - нужны OPENROUTER_API_KEY и OPENROUTER_MODEL
        в .env (один ключ, доступ ко многим моделям - см. openrouter.ai/models)
Любой другой провайдер с OpenAI-совместимым /chat/completions подключается
без нового класса - через OpenAICompatibleBackend(base_url, api_key, model).

НЕ ПРОВЕРЕНО ЖИВЬЁМ: ни один бэкенд не дёргался с реальными ключами - в
песочнице их нет. Проверены (см. tests в истории чата): сборка промпта,
разбор ответа (включая JSON, обёрнутый LLM в ```markdown-блок - частая
проблема), выбор бэкенда по переменной окружения, батчинг и сшивка
результата с исходными кластерами, и (02.10) сборка запроса/разбор ответа
для gemini/openrouter на подставленном HTTP-слое. Живой вызов - на твоей
стороне.

Как модуль:
    from pipeline.llm_stage import annotate
    annotated = annotate(clusters, profile)  # clusters - выход dedup()

Из командной строки:
    python -m pipeline.llm_stage --profile profiles/soc_analyst.yaml --top-n 20
    LLM_BACKEND=ollama python -m pipeline.llm_stage --profile profiles/it_director_ciso.yaml
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

from pipeline.dedup import deduplicate
from pipeline.prefilter import prefilter

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")  # не ошибка, если файла нет - тогда просто os.environ как есть

# --- Таксономия из файла организаторов (дословно, см. ИНФО_Dataset 1/2) ---

TECH_GROUP_WEIGHTS = {
    "Атака": ["Высокий (РФ, энергетический сектор)", "Средний (РФ, другие сектора)", "Низкий (не РФ)"],
    "Уязвимость": ["Высокая (есть эксплойт)", "Средняя (нет эксплойта)"],
    "Инфо": ["Новости ТГ"],
}

MANAGER_TAGS = [
    "В РФ",
    "Вне РФ",
    "Крупные финансовые потери",
    "Нарушение работы критической инфраструктуры",
    "Энергетика",
    "Промышленность",
    "Имиджевые потери",
    "Утечки чувствительной информации (ПДн, ком. тайна, гос. тайна и т.п.)",
    "Госсектор и правовое поле",
    "Уязвимый массовоиспользуемый простыми обывателями/топ-менеджерами "
    "(не техническими ИТ/ИБ специалистами) сервис",
    "Трудовой ресурс/громкие мероприятия и конференции из мира ИБ",
    "Может быть интересно (неожиданные/нестандартные/нетиповые/курьёзные события из мира ИБ)",
]

DEFAULT_BATCH_SIZE = 10


# --- Бэкенды ---------------------------------------------------------------


class LLMBackend:
    def complete(self, prompt: str) -> str:
        raise NotImplementedError


class ClaudeBackend(LLMBackend):
    """Claude API. Модель по умолчанию - Haiku: это задача классификации/
    разметки по батчам, не творческая генерация - дорогая модель здесь
    не нужна и просто сжигает бюджет впустую."""

    API_URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None, max_tokens: int = 4000):
        self.model = model or os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.max_tokens = max_tokens
        if not self.api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY не задан (нужен в .env или окружении для LLM_BACKEND=claude)"
            )

    def complete(self, prompt: str) -> str:
        import requests

        r = requests.post(
            self.API_URL,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": self.max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        return "".join(block["text"] for block in data["content"] if block.get("type") == "text")


class OllamaBackend(LLMBackend):
    """Локальная Qwen 3.6 35B-A3B через Ollama. base_url берётся из
    OLLAMA_BASE_URL (по умолчанию localhost - Ollama слушает локально)."""

    def __init__(self, model: Optional[str] = None, base_url: Optional[str] = None):
        self.model = model or os.environ.get("OLLAMA_MODEL", "qwen3.6:35b-a3b")
        self.base_url = base_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

    def complete(self, prompt: str) -> str:
        import requests

        r = requests.post(
            f"{self.base_url}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False},
            timeout=300,
        )
        r.raise_for_status()
        return r.json()["response"]


class OpenAICompatibleBackend(LLMBackend):
    """Универсальный бэкенд для ЛЮБОГО провайдера с OpenAI-совместимым
    /chat/completions (OpenRouter, большинство шлюзов-агрегаторов, и
    даже сама Ollama через свой /v1 - см. OllamaBackend выше, который
    остался на нативном /api/generate, т.к. уже проверен тестами).
    Чтобы добавить ещё одного провайдера с таким же форматом API -
    не нужен новый класс, достаточно передать свои base_url/api_key/model."""

    def __init__(self, base_url: str, api_key: Optional[str], model: str, extra_headers: Optional[dict] = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.extra_headers = extra_headers or {}

    def complete(self, prompt: str) -> str:
        import requests

        headers = {"content-type": "application/json", **self.extra_headers}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        r = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json={"model": self.model, "messages": [{"role": "user", "content": prompt}]},
            timeout=120,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


class OpenRouterBackend(OpenAICompatibleBackend):
    """https://openrouter.ai - один ключ, доступ ко множеству моделей
    (включая Gemini, GPT, Qwen и т.д.) через OpenAI-совместимый формат.
    Модель НЕ зашита по умолчанию - каталог OpenRouter меняется, подставлять
    случайную модель без проверки хуже, чем явно потребовать её в .env."""

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None):
        api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        model = model or os.environ.get("OPENROUTER_MODEL")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY не задан (нужен в .env для LLM_BACKEND=openrouter)")
        if not model:
            raise RuntimeError(
                "OPENROUTER_MODEL не задан - укажи конкретную модель в .env "
                "(каталог меняется, см. https://openrouter.ai/models)"
            )
        super().__init__(base_url="https://openrouter.ai/api/v1", api_key=api_key, model=model)


class GeminiBackend(LLMBackend):
    """Google Gemini Developer API (generativelanguage.googleapis.com) -
    формат запроса/ответа НЕ OpenAI-совместимый (contents/parts, а не
    messages), поэтому отдельный класс, не через OpenAICompatibleBackend.
    Проверено по официальной документации 02.10 (endpoint стабилен,
    classic generateContent всё ещё полностью поддерживается, хотя Google
    с июня 2026 продвигает новый Interactions API). Модель НЕ зашита по
    умолчанию - у Gemini алиасы моделей за последний год менялись и бывали
    нестабильными (см. ai.google.dev/gemini-api/docs/models за актуальным
    списком), указывай явно в .env."""

    API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None):
        self.model = model or os.environ.get("GEMINI_MODEL")
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY не задан (нужен в .env для LLM_BACKEND=gemini)")
        if not self.model:
            raise RuntimeError(
                "GEMINI_MODEL не задан - укажи конкретную модель в .env, напр. gemini-2.5-flash "
                "(см. https://ai.google.dev/gemini-api/docs/models за актуальным списком)"
            )

    def complete(self, prompt: str) -> str:
        import requests

        r = requests.post(
            f"{self.API_BASE}/{self.model}:generateContent",
            headers={"x-goog-api-key": self.api_key, "content-type": "application/json"},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)


def get_backend() -> LLMBackend:
    name = os.environ.get("LLM_BACKEND", "claude").lower()
    if name == "claude":
        return ClaudeBackend()
    if name == "ollama":
        return OllamaBackend()
    if name == "gemini":
        return GeminiBackend()
    if name == "openrouter":
        return OpenRouterBackend()
    raise ValueError(
        f"Неизвестный LLM_BACKEND: {name!r} (ожидается 'claude', 'ollama', 'gemini' или 'openrouter')"
    )


# --- Промпты и разбор ответа ------------------------------------------------


def _parse_json_response(text: str) -> list:
    """LLM иногда оборачивает JSON в ```json ... ``` - снимаем обёртку перед
    парсингом. Поднимает json.JSONDecodeError, если и это не помогло -
    вызывающий код должен сам решить, ретраить или падать."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return json.loads(text)


_LEADING_NUMBER_RE = re.compile(r"^\s*\d+[.)]\s*")


def _normalize_tags(tags: list[str]) -> list[str]:
    """Защита сверх фикса промпта: если модель всё же вернула тег с
    цифрой впереди ("1. В РФ") - снимаем её. Тег, которого после этого
    всё равно нет в MANAGER_TAGS, оставляем как есть, но печатаем
    предупреждение - не валим весь прогон из-за одного тега."""
    out = []
    for t in tags:
        clean = _LEADING_NUMBER_RE.sub("", t).strip()
        if clean not in MANAGER_TAGS:
            print(f"[llm_stage] предупреждение: тег не из списка организаторов: {clean!r}")
        out.append(clean)
    return out


def _normalize_weight(group: str, weight: str) -> str:
    """Защита, аналогичная _normalize_tags: на реальном прогоне 03.10
    нашли, что LLM (Gemini) иногда обрезает вес до первого слова
    ("Высокая" вместо "Высокая (есть эксплойт)") - это ломало и отображение
    (теряется пояснение), и сортировку в render.py (точное совпадение не
    находилось, элементы оставались в исходном порядке вместо группировки
    по весу). Сопоставляем по началу строки, возвращаем канонический
    вариант из TECH_GROUP_WEIGHTS; если соответствия нет - оставляем как
    есть и предупреждаем, не падаем."""
    candidates = TECH_GROUP_WEIGHTS.get(group, [])
    weight = weight.strip()
    if weight in candidates:
        return weight
    for c in candidates:
        c_head = c.split(" (")[0].strip()
        if weight == c_head or c.startswith(weight) or weight.startswith(c_head):
            return c
    print(f"[llm_stage] предупреждение: вес не из шкалы категории {group!r}: {weight!r}")
    return weight


def _items_json(batch: list[dict]) -> str:
    return json.dumps(
        [
            {"index": i, "title": c["title"], "summary": c["summary"][:500], "published": c.get("published", "")}
            for i, c in enumerate(batch)
        ],
        ensure_ascii=False,
        indent=2,
    )


def _build_tech_prompt(profile: dict, batch: list[dict]) -> str:
    groups_desc = "\n".join(f'- "{g}": вес — {" / ".join(w)}' for g, w in TECH_GROUP_WEIGHTS.items())
    return f"""Ты помогаешь специалисту с профилем "{profile.get('role', profile['id'])}" отобрать и
разметить публикации для дайджеста.

Профиль интересов: {profile.get('description', '').strip()}

Для КАЖДОЙ публикации ниже определи:
1. group - ровно одна из категорий: {list(TECH_GROUP_WEIGHTS.keys())}
2. weight - вес, строго из шкалы ВЫБРАННОЙ категории:
{groups_desc}
3. explanation - 1-2 предложения, почему это релевантно профилю (по-русски)

Публикации (JSON, поле index - для сопоставления с ответом):
{_items_json(batch)}

Верни ТОЛЬКО JSON-массив, без markdown-обёртки и пояснений вокруг, вида:
[{{"index": 0, "group": "...", "weight": "...", "explanation": "..."}}, ...]
Длина массива должна точно совпадать с числом публикаций на входе ({len(batch)})."""


def _build_manager_prompt(profile: dict, batch: list[dict]) -> str:
    # БЕЗ нумерации (не "1. X\n2. Y") - на реальном прогоне 03.10 нашли, что
    # модель в одном батче копирует "1. В РФ" целиком как тег, в другом -
    # "В РФ" без номера. Кавычки без цифр убирают саму возможность путаницы.
    tags_list = "\n".join(f'- "{t}"' for t in MANAGER_TAGS)
    return f"""Ты готовишь дайджест по ИБ для нетехнического руководства и сотрудников
компании. Профиль: {profile.get('description', '').strip()}

Для КАЖДОЙ публикации ниже определи:
1. tags - список ПОДХОДЯЩИХ тегов (может быть несколько) из фиксированного
   списка ниже - используй ТОЛЬКО эти формулировки, дословно:
{tags_list}
2. digest_text - готовый текст для дайджеста, 3-4 строки, понятным языком
   для нетехнического руководителя, с акцентом на бизнес-последствия
   (деньги, репутация, простой, юридические риски), без технического
   жаргона и аббревиатур без расшифровки

Публикации (JSON, поле index - для сопоставления с ответом):
{_items_json(batch)}

Верни ТОЛЬКО JSON-массив, без markdown-обёртки и пояснений вокруг, вида:
[{{"index": 0, "tags": ["..."], "digest_text": "..."}}, ...]
Длина массива должна точно совпадать с числом публикаций на входе ({len(batch)})."""


# --- Оркестрация -------------------------------------------------------------


def annotate(
    clusters: list[dict],
    profile: dict,
    batch_size: int = DEFAULT_BATCH_SIZE,
    backend: Optional[LLMBackend] = None,
) -> list[dict]:
    """Размечает кластеры (выход dedup()) по таксономии организаторов.
    Возвращает копии кластеров с добавленными полями разметки (group/weight/
    explanation для tech, tags/digest_text для manager). Бросает исключение,
    если LLM вернула не тот размер массива или невалидный JSON - на этом
    этапе лучше упасть явно, чем молча потерять публикации."""
    if not clusters:
        return []

    backend = backend or get_backend()
    audience = profile.get("audience", "tech")
    build_prompt = _build_manager_prompt if audience == "manager" else _build_tech_prompt

    results: list[dict] = []
    for start in range(0, len(clusters), batch_size):
        batch = clusters[start : start + batch_size]
        raw = backend.complete(build_prompt(profile, batch))
        try:
            parsed = _parse_json_response(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM вернула невалидный JSON на батче {start}-{start + len(batch)}: {raw[:300]!r}") from e
        if len(parsed) != len(batch):
            raise ValueError(
                f"LLM вернула {len(parsed)} элементов вместо {len(batch)} на батче {start}-{start + len(batch)}"
            )
        for item, ann in zip(batch, parsed):
            extra = {k: v for k, v in ann.items() if k != "index"}
            if audience == "manager" and "tags" in extra:
                extra["tags"] = _normalize_tags(extra["tags"])
            elif audience != "manager" and "weight" in extra:
                extra["weight"] = _normalize_weight(extra.get("group", ""), extra["weight"])
            results.append({**item, **extra})
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=str(ROOT / "data" / "corpus-latest.json"))
    ap.add_argument("--profile", required=True)
    ap.add_argument("--top-n", type=int, default=20, help="сколько публикаций брать из предфильтра")
    ap.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    args = ap.parse_args()

    corpus = json.loads(Path(args.corpus).read_text(encoding="utf-8"))
    profile = yaml.safe_load(Path(args.profile).read_text(encoding="utf-8"))

    ranked = prefilter(corpus["items"], profile, top_n=args.top_n)
    clusters = deduplicate(ranked)
    annotated = annotate(clusters, profile, batch_size=args.batch_size)

    audience = profile.get("audience", "tech")
    print(f"Профиль: {profile['id']} ({audience}) | размечено: {len(annotated)}\n")
    for a in annotated:
        if audience == "manager":
            print(f"[{', '.join(a.get('tags', []))}]")
            print(f"  {a['title']}")
            print(f"  {a.get('digest_text', '')}")
        else:
            print(f"[{a.get('group', '?')} / {a.get('weight', '?')}]  {a['title']}")
            print(f"  {a.get('explanation', '')}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
