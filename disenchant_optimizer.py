import json
from pathlib import Path

PRICES = Path('data/prices.json')
RULES = Path('config/disenchant_rules.json')
OUT = Path('data/disenchant_thresholds.json')
SAFE_SELL_MULTIPLIER = 0.90

# TBC conversions: 3 Lesser Planar Essence -> 1 Greater Planar Essence;
# 3 Small Prismatic Shard -> 1 Large Prismatic Shard.
DERIVED_VALUE_RULES = {
    22447: {'from_item_id': 22446, 'ratio': 1 / 3, 'name': 'Lesser Planar Essence'},
    22448: {'from_item_id': 22449, 'ratio': 1 / 3, 'name': 'Small Prismatic Shard'},
}


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def direct_price(prices, item_id):
    row = prices.get('items', {}).get(str(item_id), {})
    return row.get('realistic_sell_price_gold', row.get('market_value_gold', row.get('min_buyout_gold')))


def mat_price(prices, item_id):
    direct = direct_price(prices, item_id)
    if direct is not None:
        return direct, 'direct_market'
    rule = DERIVED_VALUE_RULES.get(item_id)
    if rule:
        parent = direct_price(prices, rule['from_item_id'])
        if parent is not None:
            return parent * rule['ratio'], f"derived_from_{rule['from_item_id']}"
    return None, 'missing'


def expected_value(prices, outcomes):
    total = 0.0
    components = []
    missing = []
    for out in outcomes:
        p, price_source = mat_price(prices, out['item_id'])
        avg_qty = (out['qty_min'] + out['qty_max']) / 2
        if p is None:
            missing.append(out['item_id'])
            continue
        contribution = out['probability'] * avg_qty * p
        total += contribution
        components.append({
            'item_id': out['item_id'],
            'name': out['name'],
            'probability': out['probability'],
            'average_quantity_if_hit': avg_qty,
            'unit_value_gold': round(p, 4),
            'unit_value_source': price_source,
            'expected_value_gold': round(contribution, 4),
        })
    return (None if missing else round(total, 4)), components, missing


def main():
    prices = load(PRICES)
    rules = load(RULES)
    rows = []
    for bracket in rules['brackets']:
        for kind in ('armor', 'weapon'):
            ev, components, missing = expected_value(prices, bracket[kind])
            conservative = None if ev is None else round(ev * SAFE_SELL_MULTIPLIER, 4)
            rows.append({
                'quality': bracket['quality'],
                'item_level_min': bracket['item_level_min'],
                'item_level_max': bracket['item_level_max'],
                'item_type': kind,
                'expected_disenchant_value_gold': ev,
                'conservative_buy_ceiling_gold': conservative,
                'break_even_buy_ceiling_gold': ev,
                'recommended_rule': (
                    None if ev is None else
                    f"DE if total acquisition cost is below {conservative:.2f}g; between {conservative:.2f}g and {ev:.2f}g only if you accept price/variance risk."
                ),
                'components': components,
                'missing_price_item_ids': missing,
            })

    report = {
        'market': prices['market'],
        'price_source': prices['source'],
        'method': 'Expected disenchant value from probability x average quantity x material value.',
        'derived_value_rules': DERIVED_VALUE_RULES,
        'conservative_sell_multiplier': SAFE_SELL_MULTIPLIER,
        'warning': 'Uses current seed material prices and expected-value math; individual disenchants are random. Vendor value and AH resale value of the gear must be compared separately. Derived lesser/small values assume free 3:1 conversion.',
        'thresholds': rows,
    }
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print('Wrote', OUT)
    for r in rows:
        print(r['item_type'], r['item_level_min'], '-', r['item_level_max'], 'EV=', r['expected_disenchant_value_gold'], 'safe buy<=', r['conservative_buy_ceiling_gold'])


if __name__ == '__main__':
    main()
