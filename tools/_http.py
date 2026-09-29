"""Общий HTTP-хелпер для скриптов в tools/.

Некоторые сайты (напр. securitylab.ru) отдают HTTP 401/403 на наш обычный
User-Agent — похоже на WAF/антибот-проверку, а не на настоящую авторизацию.
get() делает вторую попытку с более «браузерными» заголовками (UA + Referer
на домен запроса) и возвращает первый успешный ответ. Если это не помогает,
возвращает исходный ответ как есть — вызывающий код увидит тот же код ошибки.
"""
from urllib.parse import urlparse

import requests

PRIMARY_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DigestPrototype/0.1; hackathon research)"}
FALLBACK_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


def get(url: str, timeout: int = 15) -> requests.Response:
    r = requests.get(url, headers=PRIMARY_HEADERS, timeout=timeout)
    if r.status_code in (401, 403):
        origin = urlparse(url)
        headers = {
            "User-Agent": FALLBACK_UA,
            "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
            "Referer": f"{origin.scheme}://{origin.netloc}/",
        }
        r2 = requests.get(url, headers=headers, timeout=timeout)
        if r2.status_code == 200:
            return r2
    return r
