import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://bootybaybroker.com/tbc-classic/ah"
CONFIG_PATH = Path("config/items.json")
OUT_PATH = Path("data/diagnostics.json")

PRICE_PATTERNS = [
    re.compile(r"(?:(\d+)\s*g\s*)?(?:(\d+)\s*s\s*)?(\d+)\s*c", re.I),
    re.compile(r"(?:(\d+)\s*g\s*)?(\d+)\s*s", re.I),
]
NUMERIC_KEY_RE = re.compile(
    r'"(?P<key>[^"\\]*(?:price|buyout|market)[^"\\]*)"\s*:\s*(?P<value>\d+(?:\.\d+)?)',
    re.I,
)


def money_to_gold(match):
    groups = match.groups()
    if len(groups) == 3:
        g, s, c = groups
        return (int(g or 0) + int(s or 0) / 100 + int(c or 0) / 10000)
    g, s = groups
    return int(g or 0) + int(s or 0) / 100


def scoped_url(market, item):
    params = {
        "realmId": market["realm_id"],
        "auctionHouseId": market["auction_house_id"],
        "faction": market["faction"],
        "region": market["region"],
        "realm": market["realm"],
        "q": item["name"],
        "item": item["id"],
    }
    return f"{BASE_URL}?{urlencode(params)}"


def extract_candidates(html, item_name):
    soup = BeautifulSoup(html, "html.parser")
    text = " ".join(soup.stripped_strings)
    lower = text.lower()
    idx = lower.find(item_name.lower())
    if idx >= 0:
        window = text[max(0, idx - 800): idx + 5000]
    else:
        window = text[:12000]

    money = []
    for pattern in PRICE_PATTERNS:
        for m in pattern.finditer(window):
            value = round(money_to_gold(m), 4)
            if value > 0 and value not in money:
                money.append(value)

    numeric = []
    for m in NUMERIC_KEY_RE.finditer(html):
        entry = {"key": m.group("key")[:120], "value": float(m.group("value"))}
        if entry not in numeric:
            numeric.append(entry)
        if len(numeric) >= 50:
            break

    return {
        "item_found_in_text": idx >= 0,
        "text_excerpt": window[:2500],
        "money_candidates_gold": money[:50],
        "numeric_price_key_candidates": numeric,
    }


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    market = config["market"]
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/142 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    })

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market": market,
        "items": [],
    }

    for item in config["items"]:
        url = scoped_url(market, item)
        row = {"id": item["id"], "name": item["name"], "url": url}
        try:
            response = session.get(url, timeout=30)
            row["http_status"] = response.status_code
            row["final_url"] = response.url
            row["content_length"] = len(response.text)
            row.update(extract_candidates(response.text, item["name"]))
            if "expected_validation_gold" in item:
                expected = item["expected_validation_gold"]
                row["expected_validation_gold"] = expected
                row["validation_match"] = any(
                    abs(candidate - expected) <= 0.0001
                    for candidate in row["money_candidates_gold"]
                )
        except Exception as exc:
            row["error"] = repr(exc)
        result["items"].append(row)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    arcane = next((x for x in result["items"] if x["id"] == 22445), None)
    if not arcane or arcane.get("http_status") != 200:
        raise SystemExit("Arcane Dust validation request failed")


if __name__ == "__main__":
    main()
