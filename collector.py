import csv
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

CONFIG_PATH = Path("config/items.json")
DIAG_PATH = Path("data/diagnostics.json")
PRICES_PATH = Path("data/prices.json")

TSM_CANDIDATES = [
    # User-confirmed realm URL on TSM website:
    # https://tradeskillmaster.com/classic/eu-fresh/thunderstrike-alliance
    # TSM docs say public-data slugs are copied directly from the realm page URL.
    "https://public-data.tradeskillmaster.com/classic/eu-fresh/realm/thunderstrike-alliance/items.csv",
    "https://public-data.tradeskillmaster.com/classic/eu-fresh/realm/thunderstrike/items.csv",
    # Older guesses kept only as diagnostics/fallbacks.
    "https://public-data.tradeskillmaster.com/classic/eu/realm/thunderstrike/items.csv",
    "https://public-data.tradeskillmaster.com/classic-progression/eu/realm/thunderstrike/items.csv",
    "https://public-data.tradeskillmaster.com/classic-anniversary/eu/realm/thunderstrike/items.csv",
    "https://public-data.tradeskillmaster.com/anniversary/eu/realm/thunderstrike/items.csv",
]

# market.thunderstrikemarket.org currently presents an SSL/Cloudflare 525 to GitHub-hosted runners.
# Search engines index the alternate horde.* origin, including Alliance-scoped reports, so probe both.
THUNDERSTRIKE_MARKET_PAGES = [
    "https://horde.thunderstrikemarket.org/report/alliance/raw-materials-enchanting/",
    "https://horde.thunderstrikemarket.org/auction-house/compare/",
    "https://horde.thunderstrikemarket.org/report/",
    "https://market.thunderstrikemarket.org/realms/thunderstrike/alliance/",
]

PRICE_RE = re.compile(r"(?:(\d+)g\s*)?(?:(\d+)s\s*)?(\d+)c", re.I)
ITEM_ID_RE = re.compile(r"\((\d+)\)")
NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def parse_csv(text):
    return list(csv.DictReader(io.StringIO(text)))


def find_item(rows, item_id):
    wanted = str(item_id)
    for row in rows:
        for key in ("itemId", "itemID", "id"):
            if row.get(key) == wanted:
                return row
    return None


def parse_gold(text):
    text = " ".join(text.replace("\xa0", " ").split())
    m = PRICE_RE.search(text)
    if not m:
        return None
    g, s, c = m.groups()
    return round(int(g or 0) + int(s or 0) / 100 + int(c or 0) / 10000, 4)


def parse_number(text):
    m = NUMBER_RE.search(text.replace(",", ""))
    return float(m.group()) if m else None


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


def normalize_header(text):
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")


def parse_market_tables(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = {}
    for table in soup.find_all("table"):
        header_row = table.find("tr")
        if not header_row:
            continue
        headers = [normalize_header(x.get_text(" ", strip=True)) for x in header_row.find_all(["th", "td"])]
        if not headers:
            continue
        for tr in table.find_all("tr")[1:]:
            cells = tr.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            texts = [c.get_text(" ", strip=True) for c in cells]
            id_match = ITEM_ID_RE.search(texts[0])
            if not id_match:
                continue
            item_id = int(id_match.group(1))
            row = {headers[i]: texts[i] for i in range(min(len(headers), len(texts)))}
            row["_texts"] = texts
            rows[item_id] = row
    return rows


def get_any(row, keys):
    for key in keys:
        if key in row and row[key] not in (None, "", "-"):
            return row[key]
    return None


def row_to_market_data(row):
    price_text = get_any(row, ["current_price", "alliance_price", "price", "lowest_buyout", "buyout"])
    avg_text = get_any(row, ["market_avg", "market_average", "average", "dbmarket"])
    qty_text = get_any(row, ["on_sale", "alliance_on_sale", "quantity", "qty", "supply"])
    auctions_text = get_any(row, ["auctions", "auction_count", "listings"])
    sold_text = get_any(row, ["regional_sold_day", "regional_sold_per_day", "sold_day", "sold_per_day"])
    rate_text = get_any(row, ["regional_sales_rate", "regional_sale_rate", "sale_rate", "sales_rate"])

    return {
        "min_buyout_gold": parse_gold(price_text or ""),
        "market_value_gold": parse_gold(avg_text or ""),
        "quantity": int(parse_number(qty_text)) if qty_text and parse_number(qty_text) is not None else None,
        "auction_count": int(parse_number(auctions_text)) if auctions_text and parse_number(auctions_text) is not None else None,
        "sold_per_day": parse_number(sold_text or ""),
        "sale_rate": parse_number(rate_text or ""),
    }


def merge_live_prices(seed, live_rows, config):
    out = json.loads(json.dumps(seed))
    out["generated_at"] = datetime.now(timezone.utc).isoformat()
    updated = 0
    for item in config["items"]:
        item_id = item["id"]
        row = live_rows.get(item_id)
        if not row:
            continue
        live = row_to_market_data(row)
        if live.get("min_buyout_gold") is None:
            continue
        dst = out.setdefault("items", {}).setdefault(str(item_id), {"name": item["name"]})
        dst.update({k: v for k, v in live.items() if v is not None})
        dst["name"] = item["name"]
        dst["realistic_sell_price_gold"] = live.get("market_value_gold") or live.get("min_buyout_gold")
        if live.get("sale_rate") is not None:
            dst["sale_probability_48h"] = max(0.0, min(1.0, live["sale_rate"]))
        dst["data_source"] = "thunderstrikemarket.org"
        updated += 1
    if updated:
        out["source"] = "thunderstrikemarket_live_with_seed_fallback"
        out["live_items_updated"] = updated
        out["notes"] = [
            "Realm/faction prices and supply come from Thunderstrike Market pages when reachable.",
            "Regional sold/day and sale rate are TSM-derived demand metrics exposed by Thunderstrike Market.",
            "Seed values remain only for items not found in a live page.",
            "sale_probability_48h conservatively equals the exposed regional sale_rate; sold/day is informational only.",
        ]
    return out, updated


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    market = config["market"]
    seed_prices = json.loads(PRICES_PATH.read_text(encoding="utf-8")) if PRICES_PATH.exists() else {
        "generated_at": None, "source": "empty", "market": market, "items": {}
    }
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market": market,
        "tsm": [],
        "thunderstrike_market": [],
        "bootybaybroker": [],
    }

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; ThunderstrikeGoldScanner/1.0; +https://github.com/KozhevnykovUA/thunderstrike-gold-scanner)",
        "Accept-Language": "en-US,en;q=0.9",
    })

    for url in TSM_CANDIDATES:
        probe, text = request_probe(session, url)
        result["tsm"].append(probe)
        if probe["http_status"] == 200 and text.lstrip().lower().startswith(("item", "id")):
            rows = parse_csv(text)
            probe["row_count"] = len(rows)
            probe["columns"] = list(rows[0].keys()) if rows else []
            probe["items"] = [{"id": i["id"], "name": i["name"], "row": find_item(rows, i["id"])} for i in config["items"]]
            result["selected_tsm_url"] = url
            break

    live_rows = {}
    for url in THUNDERSTRIKE_MARKET_PAGES:
        try:
            probe, text = request_probe(session, url)
            parsed = parse_market_tables(text) if probe["http_status"] == 200 else {}
            probe["parsed_item_count"] = len(parsed)
            probe["wanted_items_found"] = [i["id"] for i in config["items"] if i["id"] in parsed]
            result["thunderstrike_market"].append(probe)
            for item_id, row in parsed.items():
                live_rows.setdefault(item_id, row)
        except Exception as exc:
            result["thunderstrike_market"].append({"url": url, "error": repr(exc)})

    merged, updated = merge_live_prices(seed_prices, live_rows, config)
    if updated:
        PRICES_PATH.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
        result["prices_updated"] = updated
        result["selected_source"] = "thunderstrikemarket.org"

    for item in config["items"][:2]:
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

    DIAG_PATH.parent.mkdir(parents=True, exist_ok=True)
    DIAG_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print("Thunderstrike Market parsed live rows:", len(live_rows), "wanted prices updated:", updated)
    for item in config["items"]:
        if item["id"] in live_rows:
            print(item["name"], row_to_market_data(live_rows[item["id"]]))


if __name__ == "__main__":
    main()
