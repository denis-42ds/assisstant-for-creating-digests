#!/usr/bin/env python3
"""Сбор замороженного корпуса публикаций из sources.yaml в data/corpus.json.

Запуск (нужен реальный доступ в интернет — из песочницы Claude не работает,
запускать на своей машине или там же, где будет крутиться сервис):

    python tools/fetch_corpus.py
    python tools/fetch_corpus.py --per-source 20 --out data/corpus.json
    python tools/fetch_corpus.py --sources habr_infosec,securitylab

Логика:
  - для каждого источника пробует feed, затем alt_urls (как check_feeds.py);
  - берёт не более --per-source записей на источник (по умолчанию 20);
  - аннотацию чистит от HTML и обрезает до 600 символов (лимит схемы);
  - дата — в UTC ISO 8601; если фид не даёт дату, запись пропускается
    (дата обязательна по схеме, выдумывать её нельзя);
  - id — sha1(url)[:12], стабильный и уникальный;
  - дедуп по url на уровне сборки (за дедуп «одна публикация в нескольких
    источниках» отвечает следующий шаг пайплайна — dedup.py);
  - источники с optional: true пропускаются, если не сработали ни feed,
    ни alt_urls — без остановки сборки.

Результат валидируется против corpus.schema.json перед сохранением.
"""
import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import jsonschema
import requests
import yaml

import _http

TAG_RE = re.compile(r"<[^>]+>")
ROOT = Path(__file__).parent.parent


def strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", TAG_RE.sub(" ", s or "")).strip()


def entry_id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def fetch_one(url: str, timeout: int = 15):
    r = _http.get(url, timeout=timeout)
    r.raise_for_status()
    return feedparser.parse(r.content)


def collect_source(src: dict, per_source: int) -> list[dict]:
    urls = [src["feed"], *src.get("alt_urls", [])]
    feed = None
    used_url = None
    for u in urls:
        try:
            f = fetch_one(u)
            if f.entries:
                feed, used_url = f, u
                break
        except requests.RequestException:
            continue
    if feed is None:
        print(f"  [пропуск] {src['id']}: ни один URL не отдал записей")
        return []

    items = []
    for e in feed.entries[:per_source]:
        link = e.get("link")
        title = strip_html(e.get("title", ""))
        if not link or not title:
            continue
        dt = e.get("published_parsed") or e.get("updated_parsed")
        if not dt:
            continue  # дату не выдумываем — без неё запись не соответствует схеме
        published = datetime.fromtimestamp(time.mktime(dt), tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        summary = strip_html(e.get("summary", ""))[:600]
        items.append(
            {
                "id": entry_id(link),
                "title": title,
                "url": link,
                "source": src["id"],
                "published": published,
                "summary": summary,
                "lang": src.get("lang", "ru"),
            }
        )
    print(f"  [ок] {src['id']} <- {used_url}: {len(items)} записей")
    return items


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "sources.yaml"))
    ap.add_argument("--schema", default=str(ROOT / "corpus.schema.json"))
    ap.add_argument(
        "--out",
        help="путь для корпуса; по умолчанию data/<версия>.json (не перезаписывает "
        "предыдущие прогоны) + обновляется указатель data/corpus-latest.json",
    )
    ap.add_argument("--per-source", type=int, default=20)
    ap.add_argument("--sources", help="через запятую, id из sources.yaml; по умолчанию — все")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    wanted = set(args.sources.split(",")) if args.sources else None

    all_items: list[dict] = []
    seen_urls: set[str] = set()
    used_source_ids: list[str] = []

    print("Сбор корпуса:")
    for src in cfg["sources"]:
        if wanted and src["id"] not in wanted:
            continue
        items = collect_source(src, args.per_source)
        new = [it for it in items if it["url"] not in seen_urls]
        seen_urls.update(it["url"] for it in new)
        if new:
            used_source_ids.append(src["id"])
        all_items.extend(new)

    now = datetime.now(timezone.utc)
    version = f"corpus-{now:%Y%m%d-%H%M}"
    corpus = {
        "meta": {
            "version": version,
            "collected_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sources": used_source_ids,
            "note": f"Собрано автоматически из {len(used_source_ids)} источников, "
            f"до {args.per_source} записей на источник.",
        },
        "items": all_items,
    }

    schema = json.loads(Path(args.schema).read_text(encoding="utf-8"))
    jsonschema.validate(corpus, schema)

    # По умолчанию каждый прогон пишет отдельный файл data/<версия>.json —
    # предыдущие прогоны не затираются (важно для фиксации версии на подачу).
    # data/corpus-latest.json — стабильный путь для остального пайплайна.
    out_path = Path(args.out) if args.out else ROOT / "data" / f"{version}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(corpus, ensure_ascii=False, indent=2)
    out_path.write_text(body, encoding="utf-8")

    latest_path = ROOT / "data" / "corpus-latest.json"
    latest_path.write_text(body, encoding="utf-8")

    def rel(p: Path) -> str:
        try:
            return str(p.resolve().relative_to(Path.cwd().resolve()))
        except ValueError:
            return str(p)

    print(
        f"\nИтого: {len(all_items)} публикаций из {len(used_source_ids)} источников "
        f"-> {rel(out_path)} (и {rel(latest_path)})"
    )
    return 0 if all_items else 1


if __name__ == "__main__":
    sys.exit(main())
