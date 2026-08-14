import json
from pathlib import Path

PRICES = Path('data/prices.json')
RECIPES = Path('recipes/enchanting_300_375.json')
OUT = Path('data/enchanting_report.json')
AH_CUT = 0.05


def load_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def item_row(prices, item_id):
    return prices['items'].get(str(item_id))


def item_price(prices, item_id):
    row = item_row(prices, item_id)
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


def sale_recovery(prices, output):
    """Conservative expected AH recovery.

    We only credit recovery if an explicit sale_probability_48h is present.
    This avoids treating a listed price as guaranteed revenue when demand is unknown.
    Optional listing_loss_gold can represent deposits/relisting losses.
    """
    if not output or not output.get('saleable'):
        return {
            'status': 'not_saleable',
            'expected_recovery_gold': 0.0,
        }

    item_id = output['item_id']
    qty = output.get('quantity', 1)
    row = item_row(prices, item_id)
    if not row:
        return {
            'status': 'missing_output_market_data',
            'item_id': item_id,
            'expected_recovery_gold': 0.0,
        }

    sell_price = row.get('realistic_sell_price_gold', row.get('market_value_gold', row.get('min_buyout_gold')))
    p48 = row.get('sale_probability_48h')
    sold_per_day = row.get('sold_per_day')
    sale_rate = row.get('sale_rate')
    listing_loss = row.get('listing_loss_gold', 0.0)

    if sell_price is None or p48 is None:
        return {
            'status': 'demand_unknown',
            'item_id': item_id,
            'sell_price_gold': sell_price,
            'sale_probability_48h': p48,
            'sold_per_day': sold_per_day,
            'sale_rate': sale_rate,
            'expected_recovery_gold': 0.0,
        }

    p48 = max(0.0, min(1.0, float(p48)))
    gross_after_cut = sell_price * qty * (1.0 - AH_CUT)
    recovery = max(0.0, gross_after_cut * p48 - listing_loss)
    return {
        'status': 'estimated',
        'item_id': item_id,
        'quantity': qty,
        'sell_price_gold': round(sell_price, 4),
        'sale_probability_48h': round(p48, 4),
        'sold_per_day': sold_per_day,
        'sale_rate': sale_rate,
        'ah_cut': AH_CUT,
        'listing_loss_gold': listing_loss,
        'expected_recovery_gold': round(recovery, 4),
    }


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


def expected_cost_per_skill(net_craft_gold, probability):
    if net_craft_gold is None or probability <= 0:
        return None
    return round(max(0.0, net_craft_gold) / probability, 4)


def build_segments(points):
    if not points:
        return []
    segments = []
    start = points[0]['skill']
    prev_skill = start
    current = points[0]['best']['name']
    req = points[0]['best'].get('requirements')
    for point in points[1:]:
        name = point['best']['name']
        point_req = point['best'].get('requirements')
        contiguous = point['skill'] == prev_skill + 1
        if name != current or point_req != req or not contiguous:
            segments.append({'from_skill': start, 'to_skill': prev_skill + 1, 'recipe': current, 'requirements': req})
            start = point['skill']
            current = name
            req = point_req
        prev_skill = point['skill']
    segments.append({'from_skill': start, 'to_skill': prev_skill + 1, 'recipe': current, 'requirements': req})
    return segments


def main():
    prices = load_json(PRICES)
    recipes = load_json(RECIPES)
    rows = []

    for recipe in recipes['recipes']:
        gross_cost, missing = craft_cost(prices, recipe['materials'])
        recovery = sale_recovery(prices, recipe.get('output'))
        recovery_gold = recovery.get('expected_recovery_gold', 0.0)
        net_cost = None if gross_cost is None else round(max(0.0, gross_cost - recovery_gold), 4)
        required_skill = recipe.get('required_skill', 0)
        repeatable = recipe.get('repeatable_for_leveling', recipe['name'] != 'Runed Adamantite Rod')
        skill_curve = []

        if repeatable:
            for skill in range(300, 375):
                if skill < required_skill:
                    continue
                probability = skillup_probability(skill, recipe['skill'])
                if probability <= 0:
                    continue
                skill_curve.append({
                    'skill': skill,
                    'skillup_probability': round(probability, 4),
                    'expected_gross_cost_per_skill_gold': expected_cost_per_skill(gross_cost, probability),
                    'expected_net_cost_per_skill_gold': expected_cost_per_skill(net_cost, probability),
                })

        rows.append({
            'name': recipe['name'],
            'required_skill': required_skill,
            'skill': recipe['skill'],
            'requirements': recipe.get('requirements'),
            'gross_material_cost_gold': gross_cost,
            'sale_recovery': recovery,
            'net_craft_cost_gold': net_cost,
            'missing_price_item_ids': missing,
            'repeatable_for_leveling': repeatable,
            'notes': recipe.get('notes'),
            'skill_curve': skill_curve,
        })

    report = {
        'market': prices['market'],
        'price_source': prices['source'],
        'warning': 'Input prices are still seed snapshots. Sale recovery is only credited when explicit demand probability is available.',
        'economics_model': {
            'ranking_metric': '(material cost - expected sale recovery) / skill-up probability',
            'ah_cut': AH_CUT,
            'sale_recovery_rule': 'No demand probability = zero credited recovery',
        },
        'recipes': rows,
    }

    cheapest_by_skill = []
    baseline_by_skill = []
    conditional_by_skill = []

    for skill in range(300, 375):
        candidates = []
        baseline = []
        conditional = []
        for row in rows:
            point = next((x for x in row['skill_curve'] if x['skill'] == skill), None)
            if not point or point['expected_net_cost_per_skill_gold'] is None:
                continue
            candidate = {
                'name': row['name'],
                'gross_craft_cost_gold': row['gross_material_cost_gold'],
                'expected_sale_recovery_gold': row['sale_recovery'].get('expected_recovery_gold', 0.0),
                'net_craft_cost_gold': row['net_craft_cost_gold'],
                'sale_recovery_status': row['sale_recovery'].get('status'),
                'skillup_probability': point['skillup_probability'],
                'expected_gross_cost_per_skill_gold': point['expected_gross_cost_per_skill_gold'],
                'expected_net_cost_per_skill_gold': point['expected_net_cost_per_skill_gold'],
                'requirements': row.get('requirements'),
            }
            candidates.append(candidate)
            (conditional if row.get('requirements') else baseline).append(candidate)

        for bucket in (candidates, baseline, conditional):
            bucket.sort(key=lambda x: x['expected_net_cost_per_skill_gold'])
        if candidates:
            cheapest_by_skill.append({'skill': skill, 'best': candidates[0], 'alternatives': candidates[1:4]})
        if baseline:
            baseline_by_skill.append({'skill': skill, 'best': baseline[0]})
        if conditional:
            conditional_by_skill.append({'skill': skill, 'best': conditional[0]})

    report['cheapest_by_skill'] = cheapest_by_skill
    report['baseline_route_segments'] = build_segments(baseline_by_skill)
    report['conditional_route_segments'] = build_segments(conditional_by_skill)
    report['all_route_segments'] = build_segments(cheapest_by_skill)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print('Wrote', OUT)


if __name__ == '__main__':
    main()
