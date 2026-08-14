import json
from datetime import datetime, timezone
from pathlib import Path

SNAPSHOT = Path('data/bbb_snapshot.json')
PRICES = Path('data/prices.json')


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def clean_row(row):
    allowed = {
        'min_buyout_gold', 'market_value_gold', 'quantity', 'auction_count',
        'sale_rate', 'sold_per_day'
    }
    return {k: row[k] for k in allowed if row.get(k) is not None}


def main():
    if not SNAPSHOT.exists():
        print('No data/bbb_snapshot.json; keeping existing prices.json')
        return

    snap = load(SNAPSHOT)
    prices = load(PRICES) if PRICES.exists() else {
        'generated_at': None, 'source': 'empty', 'market': snap['market'], 'items': {}
    }

    if snap.get('market') != prices.get('market'):
        raise SystemExit('Snapshot market does not match prices.json market')

    updated = 0
    rejected = []
    for item_id, row in snap.get('items', {}).items():
        if not row.get('ok'):
            rejected.append({'item_id': item_id, 'reason': row.get('error', 'not_ok')})
            continue
        clean = clean_row(row)
        if clean.get('min_buyout_gold') is None:
            rejected.append({'item_id': item_id, 'reason': 'missing_min_buyout'})
            continue
        dst = prices.setdefault('items', {}).setdefault(str(item_id), {})
        dst['name'] = row.get('name', dst.get('name'))
        dst.update(clean)
        dst['realistic_sell_price_gold'] = clean.get('market_value_gold') or clean.get('min_buyout_gold')
        # Sale rate is not blindly treated as a 48h sale probability. We store it separately.
        # A conservative p48 is only derived when sale_rate is present and <= 1.
        sr = clean.get('sale_rate')
        if sr is not None and 0 <= sr <= 1:
            dst['sale_probability_48h'] = min(1.0, float(sr))
        dst['data_source'] = 'bootybaybroker_browser_session'
        updated += 1

    prices['generated_at'] = datetime.now(timezone.utc).isoformat()
    prices['source'] = 'bootybaybroker_browser_snapshot_with_fallbacks'
    prices['live_items_updated'] = updated
    prices['snapshot_generated_at'] = snap.get('generated_at')
    prices['snapshot_import'] = {
        'updated': updated,
        'rejected': rejected,
        'rule': 'Only successful rows with a parsed min buyout overwrite existing values.'
    }
    prices['notes'] = [
        'BootyBayBroker snapshot collected inside the user browser session using same-origin requests.',
        'Market value is preferred as realistic sell price when available; min buyout is retained separately.',
        'Existing seed/fallback values remain for rows not successfully parsed.',
    ]

    PRICES.write_text(json.dumps(prices, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Imported {updated} BBB rows; rejected {len(rejected)}')


if __name__ == '__main__':
    main()
