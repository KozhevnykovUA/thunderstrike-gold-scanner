import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

CONFIG_PATH = Path("config/items.json")
OUT_PATH = Path("data/diagnostics.json")
REALM_API_BASES = [
    "https://realm-api.tradeskillmaster.com",
    "https://realm-api.tradeskillmaster.com/public",
]


def parse_csv(text):
    return list(csv.DictReader(io.StringIO(text)))


def find_item(rows, item_id):
    wanted = str(item_id)
    for row in rows:
        for key in ("itemId", "itemID", "id"):
            if row.get(key) == wanted:
                return row
    return None


def request_json(session, url):
    r = session.get(url, timeout=45, allow_redirects=True)
    out = {
        "url": url,
        "http_status": r.status_code,
        "content_type": r.headers.get("content-type"),
        "content_length": len(r.content),
        "body_preview": r.text[:500],
    }
    if r.status_code == 200:
        try:
            out["json"] = r.json()
        except Exception as exc:
            out["json_error"] = repr(exc)
    return out


def walk(obj):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from walk(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from walk(value)


def thunderstrike_matches(payload):
    matches = []
    for obj in walk(payload):
        text = json.dumps(obj, ensure_ascii=False).lower()
        if "thunderstrike" in text:
            matches.append(obj)
            if len(matches) >= 50:
                break
    return matches


def slugify(value):
    return str(value).strip().lower().replace("_", "-").replace(" ", "-")


def collect_slug_candidates(matches):
    games = ["classic", "classic-progression", "classic-anniversary", "anniversary"]
    regions = ["eu"]
    realms = ["thunderstrike"]

    for match in matches:
        if not isinstance(match, dict):
            continue
        for k, v in match.items():
            lk = str(k).lower()
            if isinstance(v, str):
                sv = slugify(v)
                if any(x in lk for x in ("game", "version", "type")) and len(sv) < 60:
                    games.insert(0, sv)
                if "region" in lk and len(sv) < 20:
                    regions.insert(0, sv)
                if ("slug" in lk or "realm" in lk or "name" in lk) and "thunderstrike" in sv:
                    realms.insert(0, sv)

    return list(dict.fromkeys(games)), list(dict.fromkeys(regions)), list(dict.fromkeys(realms))


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market": config["market"],
        "realm_api": {},
        "sources": [],
    }

    session = requests.Session()
    session.headers.update({"User-Agent": "thunderstrike-gold-scanner/0.3"})

    all_matches = []
    for base in REALM_API_BASES:
        block = {}
        for endpoint in ("realms", "regions"):
            response = request_json(session, f"{base}/{endpoint}")
            block[endpoint] = {k: v for k, v in response.items() if k != "json"}
            payload = response.get("json")
            if payload is not None:
                found = thunderstrike_matches(payload)
                block[f"{endpoint}_thunderstrike_matches"] = found
                all_matches.extend(found)
        result["realm_api"][base] = block

    games, regions, realms = collect_slug_candidates(all_matches)
    result["discovered"] = {
        "matches": all_matches[:50],
        "game_candidates": games,
        "region_candidates": regions,
        "realm_candidates": realms,
    }

    urls = []
    for game in games[:15]:
        for region in regions[:8]:
            for realm in realms[:8]:
                urls.append(f"https://public-data.tradeskillmaster.com/{game}/{region}/realm/{realm}/items.csv")
    urls = list(dict.fromkeys(urls))[:120]

    for url in urls:
        src = {"url": url}
        try:
            r = session.get(url, timeout=45, allow_redirects=True)
            src["http_status"] = r.status_code
            src["content_type"] = r.headers.get("content-type")
            src["content_length"] = len(r.content)
            if r.status_code == 200:
                src["body_preview"] = r.text[:300]
            if r.status_code == 200 and r.text.lstrip().lower().startswith(("item", "id")):
                rows = parse_csv(r.text)
                src["row_count"] = len(rows)
                src["columns"] = list(rows[0].keys()) if rows else []
                src["items"] = []
                for item in config["items"]:
                    found = find_item(rows, item["id"])
                    src["items"].append({"id": item["id"], "name": item["name"], "row": found})
                if rows:
                    result["selected_url"] = url
                    result["selected_columns"] = src["columns"]
                    result["selected_items"] = src["items"]
                    result["sources"].append(src)
                    break
        except Exception as exc:
            src["error"] = repr(exc)
        if src.get("http_status") != 404:
            result["sources"].append(src)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print("Thunderstrike API matches:", len(all_matches))
    print("Game candidates:", games[:10])
    print("Region candidates:", regions[:10])
    print("Realm candidates:", realms[:10])
    print("Selected TSM source:", result.get("selected_url"))
    if result.get("selected_items"):
        arcane = next((x for x in result["selected_items"] if x["id"] == 22445), None)
        print("Arcane Dust row:", arcane)


if __name__ == "__main__":
    main()
