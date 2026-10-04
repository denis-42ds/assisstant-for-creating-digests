# ИТ/ИБ-Дайджест

ИИ-ассистент, который собирает публикации из новостных RSS-источников,
отбирает релевантные по профилю интересов читателя, группирует по темам
и формирует готовый дайджест в Markdown. Сделано для хакатона Codenrock
(задача «Ассистент для создания ИТ/ИБ-дайджестов»).

## Что делает

- собирает публикации из настраиваемого списка RSS-источников
  (`sources.yaml`), устойчиво к WAF-блокировкам отдельных сайтов
- отбирает релевантные по профилю интересов (`profiles/*.yaml`) —
  TF-IDF-предфильтр, без обращения к внешним API
- схлопывает дубли — одна и та же новость у нескольких источников
- размечает оставшиеся публикации через LLM: категория и вес-приоритет
  для технарей, теги и готовый текст для руководства — таксономия взята
  из материалов организаторов хакатона
- собирает результат в Markdown-файл дайджеста

Три готовых профиля:
- `soc_analyst`, `devops_engineer` — аудитория «технарь» (частый
  детальный дайджест, группировка по категории Атака/Уязвимость/Инфо)
- `it_director_ciso` — аудитория «менеджер» (сжатая
  бизнес-ориентированная подборка с готовым текстом на публикацию)

## Установка

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

## LLM-бэкенд

Переключается переменной `LLM_BACKEND` в `.env`, без правки кода:

| `LLM_BACKEND` | Что нужно в `.env` |
|---|---|
| `claude` | `ANTHROPIC_API_KEY` |
| `ollama` | локально: `ollama pull qwen3.6:35b-a3b` + `ollama serve` |
| `gemini` | `GEMINI_API_KEY` + `GEMINI_MODEL` (напр. `gemini-3.8-flash`) |
| `openrouter` | `OPENROUTER_API_KEY` + `OPENROUTER_MODEL` |

Для `ollama` рекомендуется `export OLLAMA_CONTEXT_LENGTH=22000` перед
`ollama serve` — промпты батчами по умолчанию (10 публикаций) этого
просят.

## Запуск

```bash
# 1. проверить доступность источников (опционально, но полезно)
python tools/check_feeds.py

# 2. собрать корпус публикаций -> data/corpus-<версия>.json + data/corpus-latest.json
python tools/fetch_corpus.py --per-source 20

# 3. собрать дайджест по профилю -> output/<профиль>-<версия корпуса>.md
python cli.py --profile profiles/soc_analyst.yaml
python cli.py --profile profiles/devops_engineer.yaml
python cli.py --profile profiles/it_director_ciso.yaml
```

Полезные флаги `cli.py`: `--top-n` (сколько публикаций брать из
предфильтра, по умолчанию 30), `--min-score` (порог релевантности, по
умолчанию 0.001 — отсекает только нулевые совпадения), `--batch-size`
(публикаций на один вызов LLM, по умолчанию 10), `--out` (свой путь для
файла).

## Веб-сервис

`app.py` — тонкая обёртка (Streamlit) поверх того же пайплайна, два режима:
- **Готовые результаты** — читает файл из `output/`, мгновенно, без
  обращения к LLM. Сформируй заранее: `python cli.py --profile ...` для
  каждого профиля.
- **Живой запуск** — прогоняет пайплайн по кнопке прямо в браузере,
  показывает демо-метрики (сколько публикаций, предфильтр, дедуп,
  LLM-бэкенд). Ограничен rate-limit'ом: по умолчанию 5 запусков за 10
  минут (переменные `LIVE_RUN_LIMIT`, `LIVE_RUN_WINDOW_MIN` в `.env`) —
  сервис будет на публичной ссылке, лимит защищает чужой API-бюджет от
  случайного трафика.

Запуск:
```bash
streamlit run app.py
```

Публичная ссылка (своя машина, без managed-хостинга):
```bash
ngrok http --domain=https://bernetta-carpological-jessie.ngrok-free.dev 8501
```

## Структура проекта

```
digest/
├── README.md            этот файл
├── HANDOFF.md            что реализовано, цифры, ограничения (для передачи)
├── requirements.txt
├── .env.example
├── sources.yaml          список источников (RSS)
├── corpus.schema.json    схема корпуса публикаций
├── cli.py                точка входа: весь пайплайн одной командой
├── app.py                веб-интерфейс (Streamlit)
├── profiles/              профили интересов (YAML)
│   ├── soc_analyst.yaml
│   ├── devops_engineer.yaml
│   └── it_director_ciso.yaml
├── pipeline/
│   ├── prefilter.py       TF-IDF-отбор по профилю
│   ├── dedup.py            дедупликация по событию
│   ├── llm_stage.py        разметка через LLM (переключаемый бэкенд)
│   └── render.py           рендер в Markdown
├── tools/
│   ├── _http.py             общий HTTP-хелпер (обход WAF-блокировок)
│   ├── check_feeds.py       проверка доступности источников
│   └── fetch_corpus.py      сбор корпуса публикаций
├── data/                  корпус публикаций (генерируется)
└── output/                готовые дайджесты (генерируется)
```

## Известные ограничения

См. раздел «Ограничения» в `HANDOFF.md`.
