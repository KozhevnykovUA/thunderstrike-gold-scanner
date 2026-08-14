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


def skillup_probability(skill, thresholds):
    yellow = thresholds['yellow']
    green = thresholds['green']
    gray = thresholds['gray']

    if skill < yellow:
        return 1.0
    if skill < green:
        width = max(1, green - yellow)
        return 1.0 - 0.5 * ((skill - yellow) / width)
    if skill < gray:
        width = max(1, gray - green)
        return 0.5 * ((gray - skill) / width)
    return 0.0


def expected_cost_per_skill(craft_gold, probability):
    if craft_gold is None or probability <= 0:
        return None
    return round(craft_gold / probability, 4)


def main():
    prices = load_json(PRICES)
    recipes = load_json(RECIPES)
    rows = []

    for recipe in recipes['recipes']:
        cost, missing = craft_cost(prices, recipe['materials'])
        required_skill = recipe.get('required_skill', 0)
        skill_curve = []
        for skill in range(300, 375):
            if skill < required_skill:
                continue
            probability = skillup_probability(skill, recipe['skill'])
            if probability <= 0:
                continue
            skill_curve.append({
                'skill': skill,
                'skillup_probability': round(probability, 4),
                'expected_cost_per_skill_gold': expected_cost_per_skill(cost, probability),
            })

        rows.append({
            'name': recipe['name'],
            'required_skill': required_skill,
            'skill': recipe['skill'],
            'requirements': recipe.get('requirements'),
            'material_cost_gold': cost,
            'missing_price_item_ids': missing,
            'notes': recipe.get('notes'),
            'skill_curve': skill_curve,
        })

    report = {
        'market': prices['market'],
        'price_source': prices['source'],
        'warning': 'Seed prices are lowest-buyout snapshots, not live market-depth-adjusted prices.',
        'skillup_model': {
            'type': 'color_breakpoint_linear_heuristic',
            'orange': 1.0,
            'yellow_to_green': 'linear 1.0 -> 0.5',
            'green_to_gray': 'linear 0.5 -> 0.0',
            'note': 'Used for route comparison; exact recipe availability and reputation requirements are enforced where known.'
        },
        'recipes': rows,
    }

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

    cheapest_by_skill = []
    for skill in range(300, 375):
        candidates = []
        for row in rows:
            point = next((x for x in row['skill_curve'] if x['skill'] == skill), None)
            if not point or point['expected_cost_per_skill_gold'] is None:
                continue
            candidates.append({
                'name': row['name'],
                'craft_cost_gold': row['material_cost_gold'],
                'skillup_probability': point['skillup_probability'],
                'expected_cost_per_skill_gold': point['expected_cost_per_skill_gold'],
                'requirements': row.get('requirements'),
            })
        candidates.sort(key=lambda x: x['expected_cost_per_skill_gold'])
        if candidates:
            cheapest_by_skill.append({
                'skill': skill,
                'best': candidates[0],
                'alternatives': candidates[1:4],
            })
    report['cheapest_by_skill'] = cheapest_by_skill

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')

    for row in rows:
        print(f"{row['name']}: {row['material_cost_gold']}g")
    print('Wrote', OUT)


if __name__ == '__main__':
    main()
