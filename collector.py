import csv
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import requests

CONFIG_PATH = Path("config/items.json")
OUT_PATH = Path("data/diagnostics.json")

TSM_CANDIDATES = [
    "https://public-data.tradeskillmaster.com/classic/eu/realm/thunderstrike/items.csv",
    "https://public-data.tradeskillmaster.com/classic-progression/eu/realm/thunderstrike/items.csv",
    "https://public-data.tradeskillmaster.com/classic-anniversary/eu/realm/thunderstrike/items.csv",
    "https://public-data.tradeskillmaster.com/anniversary/eu/realm/thunderstrike/items.csv",
]

PRICE_RE = re.compile(r"(?:(\d+)g\s*)?(?:(\d+)s\s*)?(\d+)c", re.I)


def parse_csv(text):
    return list(csv.DictReader(io.StringIO(text)))


def find_item(rows, item_id):
    wanted = str(item_id)
    for row in rows:
        for key in ("itemId", "itemID", "id"):
            if row.get(key) == wanted:
                return row
    return None


def money_candidates(text):
    out = []
    for m in PRICE_RE.finditer(text.replace(" ", "")):
        g, s, c = m.groups()
        value = round(int(g or 0) + int(s or 0) / 100 + int(c or 0) / 10000, 4)
        if value > 0 and value not in out:
            out.append(value)
    return out[:50]


def request_probe(session, url, item_name=None):
    r = session.get(url, timeout=45, allow_redirects=True)
    text = r.text
    result = {
        "url": url,
        "http_status": r.status_code,
        "final_url": r.url,
        "content_type": r.headers.get("content-type"),
        "content_length": len(r.content),
        "server": r.headers.get("server"),
        "body_preview": text[:600],
    }
    if item_name:
        result["item_found"] = item_name.lower() in text.lower()
        result["money_candidates_gold"] = money_candidates(text)
        for token in ("market depth", "realm price comparison", "current price", "lowest buyout", "price levels"):
            result[token.replace(" ", "_")] = token in text.lower()
    return result, text


def bbb_urls(item, market):
    slug = item["name"].lower().replace("'", "").replace(" ", "-")
    qs = urlencode({
        "realmId": market["realm_id"],
        "auctionHouseId": market["auction_house_id"],
        "faction": market["faction"],
        "region": market["region"],
        "realm": market["realm"],
    })
    return [
        f"https://bootybaybroker.com/tbc-classic/item/{item['id']}/{slug}?{qs}",
        f"https://bootybaybroker.com/item/{item['id']}/{slug}?version=tbc-classic&{qs}",
    ]


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    market = config["market"]
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market": market,
        "tsm": [],
        "bootybaybroker": [],
    }

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/142.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    })

    # 1) Official TSM static CSV probe.
    for url in TSM_CANDIDATES:
        probe, text = request_probe(session, url)
        if probe["http_status"] == 200 and text.lstrip().lower().startswith(("item", "id")):
            rows = parse_csv(text)
            probe["row_count"] = len(rows)
            probe["columns"] = list(rows[0].keys()) if rows else []
            probe["items"] = []
            for item in config["items"]:
                probe["items"].append({
                    "id": item["id"],
                    "name": item["name"],
                    "row": find_item(rows, item["id"]),
                })
            result["selected_tsm_url"] = url
            result["tsm"].append(probe)
            break
        result["tsm"].append(probe)

    # 2) BootyBayBroker item-page probe. Their public item pages are indexed by search
    # engines even though the /ah route is Cloudflare-protected. We are only testing
    # normal public GETs here; no challenge bypass or cookie automation.
    for item in config["items"]:
        item_result = {"id": item["id"], "name": item["name"], "probes": []}
        for url in bbb_urls(item, market):
            try:
                probe, _ = request_probe(session, url, item["name"])
                item_result["probes"].append(probe)
                if probe["http_status"] == 200 and probe.get("item_found"):
                    break
            except Exception as exc:
                item_result["probes"].append({"url": url, "error": repr(exc)})
        result["bootybaybroker"].append(item_result)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    arcane = next(x for x in result["bootybaybroker"] if x["id"] == 22445)
    print("TSM statuses:", [(x["url"], x.get("http_status")) for x in result["tsm"]])
    print("Arcane Dust BBB probes:")
    for p in arcane["probes"]:
        print(p.get("http_status"), p.get("server"), p.get("url"))
        print("candidates:", p.get("money_candidates_gold"))


if __name__ == "__main__":
    main()
