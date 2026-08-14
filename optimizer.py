import json
from pathlib import Path

PRICES = Path('data/prices.json')
RECIPES = Path('recipes/enchanting_300_375.json')
OUT = Path('data/enchanting_report.json')


def load_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def item_price(prices, item_id):
    row = prices['items'].get(str(item_id))
    return None if not row else row.get('min_buyout_gold')


def craft_cost(prices, materials):
    total = 0.0
    missing = []
    for item_id, qty in materials.items():
        price = item_price(prices, item_id)
        if price is None:
            missing.append(str(item_id))
            continue
        total += price * qty
    return (round(total, 4) if not missing else None), missing


def main():
    prices = load_json(PRICES)
    recipes = load_json(RECIPES)
    rows = []
    for recipe in recipes['recipes']:
        cost, missing = craft_cost(prices, recipe['materials'])
        rows.append({
            'name': recipe['name'],
            'skill': recipe['skill'],
            'material_cost_gold': cost,
            'missing_price_item_ids': missing,
            'notes': recipe.get('notes'),
        })

    report = {
        'market': prices['market'],
        'price_source': prices['source'],
        'warning': 'Seed prices are lowest-buyout snapshots, not live market-depth-adjusted prices.',
        'recipes': rows,
    }

    # Useful direct comparison around 320-335.
    lookup = {r['name']: r for r in rows}
    armor = lookup.get('Enchant Cloak - Major Armor')
    spirit = lookup.get('Enchant Chest - Major Spirit')
    if armor and spirit and armor['material_cost_gold'] is not None and spirit['material_cost_gold'] is not None:
        a = armor['material_cost_gold']
        s = spirit['material_cost_gold']
        report['comparison_320_335'] = {
            'major_armor_cost_gold': a,
            'major_spirit_cost_gold': s,
            'major_armor_cheaper_pct': round((1 - a / s) * 100, 2) if s else None,
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')

    for row in rows:
        print(f"{row['name']}: {row['material_cost_gold']}g")
    print('Wrote', OUT)


if __name__ == '__main__':
    main()
