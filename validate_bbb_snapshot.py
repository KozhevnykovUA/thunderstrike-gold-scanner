import json
from pathlib import Path

SNAPSHOT = Path('data/bbb_snapshot.json')
CONFIG = Path('config/items.json')


def main():
    if not SNAPSHOT.exists():
        print('No BBB snapshot to validate')
        return

    snap = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
    cfg = json.loads(CONFIG.read_text(encoding='utf-8'))
    errors = []
    warnings = []

    if snap.get('schema_version') != 1:
        errors.append('schema_version must be 1')
    if snap.get('market') != cfg.get('market'):
        errors.append('snapshot market does not match config market')
    if snap.get('source') != 'bootybaybroker_browser_session':
        warnings.append(f"unexpected source: {snap.get('source')}")

    wanted = {str(x['id']): x['name'] for x in cfg.get('items', [])}
    rows = snap.get('items', {})
    ok_count = 0
    plausible_count = 0
    for item_id, row in rows.items():
        if item_id not in wanted:
            warnings.append(f'unconfigured item {item_id}')
        if not row.get('ok'):
            continue
        ok_count += 1
        price = row.get('min_buyout_gold')
        if not isinstance(price, (int, float)) or not (0 < price < 100000):
            errors.append(f'{item_id}: invalid min_buyout_gold={price!r}')
        else:
            plausible_count += 1
        for field in ('market_value_gold', 'sale_rate', 'sold_per_day', 'quantity', 'auction_count'):
            v = row.get(field)
            if v is not None and (not isinstance(v, (int, float)) or v < 0):
                errors.append(f'{item_id}: invalid {field}={v!r}')

    if rows and ok_count == 0:
        errors.append('snapshot has zero successful item rows')
    if ok_count and plausible_count / ok_count < 0.8:
        errors.append('fewer than 80% of successful rows have plausible prices')
    if ok_count < min(5, len(wanted)):
        warnings.append(f'only {ok_count} successful rows; snapshot is partial')

    print(f'BBB snapshot: {ok_count} successful rows, {len(errors)} errors, {len(warnings)} warnings')
    for w in warnings:
        print('WARNING:', w)
    if errors:
        for e in errors:
            print('ERROR:', e)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
