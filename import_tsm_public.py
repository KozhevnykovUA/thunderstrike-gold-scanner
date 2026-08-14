import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

CONFIG = Path('config/items.json')
PRICES = Path('data/prices.json')
TSM_URL = 'https://public-data.tradeskillmaster.com/classic/eu-fresh/realm/thunderstrike-alliance/items.csv'


def copper_to_gold(value):
    if value in (None, ''):
        return None
    try:
        return round(int(value) / 10000, 4)
    except (TypeError, ValueError):
        return None


def main():
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    current = json.loads(PRICES.read_text(encoding='utf-8')) if PRICES.exists() else {
        'market': config['market'], 'items': {}
    }

    r = requests.get(TSM_URL, timeout=45, headers={'User-Agent': 'ThunderstrikeGoldScanner/1.0'})
    r.raise_for_status()
    rows = {row['itemId']: row for row in csv.DictReader(io.StringIO(r.text))}

    imported = 0
    latest_updated = None
    for item in config['items']:
        row = rows.get(str(item['id']))
        if not row:
            continue

        market = copper_to_gold(row.get('marketValue'))
        min_buyout = copper_to_gold(row.get('minBuyout'))
        recent = copper_to_gold(row.get('recent'))
        historical = copper_to_gold(row.get('historical'))
        updated_at = row.get('updatedAt')
        if updated_at and (latest_updated is None or updated_at > latest_updated):
            latest_updated = updated_at

        dst = current.setdefault('items', {}).setdefault(str(item['id']), {})
        dst.update({
            'name': item['name'],
            'market_value_gold': market,
            'min_buyout_gold': min_buyout,
            'recent_gold': recent,
            'historical_gold': historical,
            # DBRecent is our primary automated buy proxy: fresher and less fragile than one cheapest listing.
            'effective_buy_gold': recent or market or min_buyout,
            'realistic_sell_price_gold': market or recent or min_buyout,
            'tsm_updated_at': updated_at,
            'data_source': 'tsm_public_csv',
        })
        imported += 1

    current['generated_at'] = datetime.now(timezone.utc).isoformat()
    current['source'] = 'tsm_public_csv_thunderstrike_alliance'
    current['tsm_url'] = TSM_URL
    current['tsm_items_imported'] = imported
    current['tsm_latest_updated_at'] = latest_updated
    current['notes'] = [
        'Official TSM Public Pricing Data for classic/eu-fresh/thunderstrike-alliance.',
        'Prices in source CSV are copper and are converted to gold.',
        'effective_buy_gold uses TSM recent when available, then marketValue, then minBuyout.',
        'minBuyout is retained as the current floor; marketValue and historical are retained for context.',
        'Public realm CSV does not expose market depth, sale rate, sold/day, or quantity, so those remain separate future inputs.',
    ]

    PRICES.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding='utf-8')
    print('Imported', imported, 'TSM items from', TSM_URL, 'latest', latest_updated)


if __name__ == '__main__':
    main()
