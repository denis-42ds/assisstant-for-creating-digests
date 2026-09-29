#!/usr/bin/env python3
"""Проверка доступности RSS-фидов из sources.yaml.

Запуск:
    python tools/check_feeds.py                  # проверить все источники
    python tools/check_feeds.py --config x.yaml  # другой конфиг
    python tools/check_feeds.py --json out.json  # сохранить отчёт

Для каждого источника пробует feed, затем alt_urls. Печатает: HTTP-статус,
число записей, дату самой свежей, долю записей с аннотацией, среднюю длину
аннотации. Код возврата 0, если рабочих источников >= --min-ok (по умолч. 5).
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

import feedparser
import requests
import yaml

import _http

TAG_RE = re.compile(r"<[^>]+>")


def strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", TAG_RE.sub(" ", s or "")).strip()


def check_url(url: str, timeout: int = 15) -> dict:
    res = {"url": url, "ok": False}
    t0 = time.time()
    try:
        r = _http.get(url, timeout=timeout)
    except requests.RequestException as e:
        res["error"] = f"{type(e).__name__}: {e}"[:200]
        return res
    res["status"] = r.status_code
    res["ms"] = int((time.time() - t0) * 1000)
    if r.status_code != 200:
        res["error"] = f"HTTP {r.status_code}"
        return res
    feed = feedparser.parse(r.content)
    entries = feed.entries
    if not entries:
        res["error"] = "0 записей (не RSS/Atom или пустой фид)"
        return res
    summaries = [strip_html(e.get("summary", "")) for e in entries]
    with_sum = [s for s in summaries if s]
    dates = [e.get("published_parsed") or e.get("updated_parsed") for e in entries]
    dates = [d for d in dates if d]
    res.update(
        ok=True,
        entries=len(entries),
        newest=time.strftime("%Y-%m-%d %H:%M", max(dates)) if dates else None,
        oldest=time.strftime("%Y-%m-%d %H:%M", min(dates)) if dates else None,
        with_summary=f"{len(with_sum)}/{len(entries)}",
        avg_summary_chars=int(sum(map(len, with_sum)) / len(with_sum)) if with_sum else 0,
    )
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(Path(__file__).parent.parent / "sources.yaml"))
    ap.add_argument("--json", help="путь для JSON-отчёта")
    ap.add_argument("--min-ok", type=int, default=5)
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    report, n_ok = [], 0
    for src in cfg["sources"]:
        tried = []
        for url in [src["feed"], *src.get("alt_urls", [])]:
            r = check_url(url)
            tried.append(r)
            if r["ok"]:
                break
        best = tried[-1]
        n_ok += best["ok"]
        status = "OK  " if best["ok"] else "FAIL"
        print(f"[{status}] {src['id']:<16} {best['url']}")
        if best["ok"]:
            print(f"        записей: {best['entries']}, свежая: {best['newest']}, "
                  f"старая: {best['oldest']}, аннотации: {best['with_summary']}, "
                  f"ср. длина: {best['avg_summary_chars']} симв.")
        else:
            for t in tried:
                print(f"        {t['url']} -> {t.get('error')}")
        report.append({"id": src["id"], "optional": src.get("optional", False), "attempts": tried})

    print(f"\nРабочих источников: {n_ok}/{len(cfg['sources'])}")
    if args.json:
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if n_ok >= args.min_ok else 1


if __name__ == "__main__":
    sys.exit(main())
