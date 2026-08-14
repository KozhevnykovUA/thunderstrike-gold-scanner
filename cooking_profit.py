import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

TSM_URL = "https://public-data.tradeskillmaster.com/classic/eu-fresh/realm/thunderstrike-alliance/items.csv"
METRICS_PATH = Path("data/tsm_web_metrics_probe.json")
OUT = Path("data/cooking_profit.json")
AH_CUT = 0.05

RECIPES = [
    {"output": "Ravager Dog", "mats": {"Ravager Flesh": 1}, "heatmap_pct": 131.8},
    {"output": "Blackened Trout", "mats": {"Barbed Gill Trout": 1}, "heatmap_pct": 120.7},
    {"output": "Broiled Bloodfin", "mats": {"Bloodfin Catfish": 1}, "heatmap_pct": 117.2},
    {"output": "Kibler's Bits", "mats": {"Buzzard Meat": 1}, "heatmap_pct": 81.5},
    {"output": "Blackened Sporefish", "mats": {"Zangarian Sporefish": 1}, "heatmap_pct": 65.4},
    {"output": "Grilled Mudfish", "mats": {"Figluster's Mudfish": 1}, "heatmap_pct": 40.5},
    {"output": "Spicy Crawdad", "mats": {"Furious Crawdad": 1}, "heatmap_pct": 30.0},
    {"output": "Warp Burger", "mats": {"Warped Flesh": 1}, "heatmap_pct": 20.2},
    {"output": "Blackened Basilisk", "mats": {"Chunk o' Basilisk": 1}, "heatmap_pct": 18.1},
    {"output": "Poached Bluefish", "mats": {"Icefin Bluefish": 1}, "heatmap_pct": 6.9},
    {"output": "Spicy Hot Talbuk", "mats": {"Talbuk Venison": 1}, "heatmap_pct": -1.3},
    {"output": "Roasted Clefthoof", "mats": {"Clefthoof Meat": 1}, "heatmap_pct": -9.9},
    {"output": "Golden Fish Sticks", "mats": {"Golden Darter": 1}, "heatmap_pct": -10.9},
    {"output": "Thistle Tea", "mats": {"Swiftthistle": 1}, "heatmap_pct": -17.3},
]

def gold(copper):
    if copper in (None, ""):
        return None
    return int(copper) / 10000.0


def main():
    r = requests.get(TSM_URL, timeout=45, headers={"User-Agent": "ThunderstrikeGoldScanner/1.0"})
    r.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(r.text)))
    by_name = {x["name"].strip().lower(): x for x in rows}
    metrics_payload = json.loads(METRICS_PATH.read_text(encoding="utf-8")) if METRICS_PATH.exists() else {"items": {}}
    metrics_by_name = {x.get("name", "").lower(): x for x in metrics_payload.get("items", {}).values() if isinstance(x, dict)}

    results = []
    missing = []
    for recipe in RECIPES:
        out = by_name.get(recipe["output"].lower())
        if not out:
            missing.append(recipe["output"])
            continue
        sell = gold(out.get("recent")) or gold(out.get("marketValue"))
        min_buyout = gold(out.get("minBuyout"))
        market = gold(out.get("marketValue"))
        historical = gold(out.get("historical"))

        mat_cost = 0.0
        mats_detail = []
        ok = True
        for mat, qty in recipe.get("mats", {}).items():
            row = by_name.get(mat.lower())
            if not row:
                missing.append(mat)
                ok = False
                break
            buy = gold(row.get("recent")) or gold(row.get("marketValue")) or gold(row.get("minBuyout"))
            if buy is None:
                ok = False
                missing.append(mat)
                break
            cost = buy * qty
            mat_cost += cost
            mats_detail.append({"name": mat, "qty": qty, "unit_buy_gold": round(buy, 4), "cost_gold": round(cost, 4)})
        if not ok or sell is None:
            continue

        net_sale = sell * (1 - AH_CUT)
        profit = net_sale - mat_cost
        roi = (profit / mat_cost * 100) if mat_cost > 0 else None
        margin = (profit / net_sale * 100) if net_sale > 0 else None
        metrics = metrics_by_name.get(recipe["output"].lower(), {})
        sale_rate = metrics.get("region_sale_rate")
        sold_day = metrics.get("region_avg_daily_sold")
        expected_profit_per_listing = profit * sale_rate if sale_rate is not None else None
        regional_demand_profit_index = profit * sold_day if sold_day is not None else None
        results.append({
            "output": recipe["output"],
            "tsm_recent_sell_gold": round(sell, 4),
            "tsm_min_buyout_gold": round(min_buyout, 4) if min_buyout is not None else None,
            "tsm_market_value_gold": round(market, 4) if market is not None else None,
            "tsm_historical_gold": round(historical, 4) if historical is not None else None,
            "heatmap_pct": recipe.get("heatmap_pct"),
            "materials": mats_detail,
            "material_cost_gold": round(mat_cost, 4),
            "net_sale_after_5pct_gold": round(net_sale, 4),
            "profit_per_craft_gold": round(profit, 4),
            "profit_per_stack20_gold": round(profit * 20, 2),
            "roi_pct": round(roi, 1) if roi is not None else None,
            "margin_pct": round(margin, 1) if margin is not None else None,
            "region_sale_rate": sale_rate,
            "region_avg_daily_sold": sold_day,
            "expected_profit_per_listing_gold": round(expected_profit_per_listing, 4) if expected_profit_per_listing is not None else None,
            "regional_demand_profit_index": round(regional_demand_profit_index, 2) if regional_demand_profit_index is not None else None,
            "profitable": profit > 0,
        })

    results.sort(key=lambda x: (x["expected_profit_per_listing_gold"] is not None, x["expected_profit_per_listing_gold"] or x["profit_per_craft_gold"]), reverse=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "TSM public pricing + TSM server-rendered regional sale metrics + TSM Gold heatmap snapshot",
        "market": "classic/eu-fresh/thunderstrike-alliance",
        "pricing_model": "recent prices; 5% AH cut; region sale rate used for per-listing expected-profit ranking",
        "note": "region_avg_daily_sold is a regional TSM demand metric, not a Thunderstrike-only daily sales forecast.",
        "opportunities": results,
        "missing_names": sorted(set(missing)),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Top cooking opportunities by sale-rate-adjusted profit:")
    for x in results[:10]:
        print(x["output"], "profit=", x["profit_per_craft_gold"], "rate=", x["region_sale_rate"], "sold/day=", x["region_avg_daily_sold"], "expected/listing=", x["expected_profit_per_listing_gold"])

if __name__ == "__main__":
    main()
