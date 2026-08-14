import json
from collections import defaultdict
from pathlib import Path

PRICES = Path('data/prices.json')
RECIPES = Path('recipes/enchanting_300_375.json')
OUT = Path('data/enchanting_report.json')
AH_CUT = 0.05
SAFE_BUY_MULTIPLIER = 1.075
SUPPLY_WARN = 0.20
SUPPLY_HIGH = 0.50


def load_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def item_row(prices, item_id):
    return prices['items'].get(str(item_id))


def item_price(prices, item_id):
    row = item_row(prices, item_id)
    return None if not row else row.get('min_buyout_gold')


def craft_cost(prices, materials, multiplier=1.0):
    total = 0.0
    missing = []
    for item_id, qty in materials.items():
        price = item_price(prices, item_id)
        if price is None:
            missing.append(str(item_id))
            continue
        total += price * qty * multiplier
    return (round(total, 4) if not missing else None), missing


def sale_recovery(prices, output):
    if not output or not output.get('saleable'):
        return {'status': 'not_saleable', 'expected_recovery_gold': 0.0}
    item_id = output['item_id']
    qty = output.get('quantity', 1)
    row = item_row(prices, item_id)
    if not row:
        return {'status': 'missing_output_market_data', 'item_id': item_id, 'expected_recovery_gold': 0.0}

    sell_price = row.get('realistic_sell_price_gold', row.get('market_value_gold', row.get('min_buyout_gold')))
    p48 = row.get('sale_probability_48h')
    sold_per_day = row.get('sold_per_day')
    sale_rate = row.get('sale_rate')
    listing_loss = row.get('listing_loss_gold', 0.0)
    if sell_price is None or p48 is None:
        return {
            'status': 'demand_unknown', 'item_id': item_id,
            'sell_price_gold': sell_price, 'sale_probability_48h': p48,
            'sold_per_day': sold_per_day, 'sale_rate': sale_rate,
            'expected_recovery_gold': 0.0,
        }

    p48 = max(0.0, min(1.0, float(p48)))
    gross_after_cut = sell_price * qty * (1.0 - AH_CUT)
    recovery = max(0.0, gross_after_cut * p48 - listing_loss)
    return {
        'status': 'estimated', 'item_id': item_id, 'quantity': qty,
        'sell_price_gold': round(sell_price, 4), 'sale_probability_48h': round(p48, 4),
        'sold_per_day': sold_per_day, 'sale_rate': sale_rate, 'ah_cut': AH_CUT,
        'listing_loss_gold': listing_loss, 'expected_recovery_gold': round(recovery, 4),
    }


def skillup_probability(skill, thresholds):
    yellow, green, gray = thresholds['yellow'], thresholds['green'], thresholds['gray']
    if skill < yellow:
        return 1.0
    if skill < green:
        return 1.0 - 0.5 * ((skill - yellow) / max(1, green - yellow))
    if skill < gray:
        return 0.5 * ((gray - skill) / max(1, gray - green))
    return 0.0


def expected_cost_per_skill(cost, probability):
    if cost is None or probability <= 0:
        return None
    return round(max(0.0, cost) / probability, 4)


def build_segments(points):
    if not points:
        return []
    segments = []
    start = prev = points[0]['skill']
    current = points[0]['best']['name']
    req = points[0]['best'].get('requirements')
    for point in points[1:]:
        name, point_req = point['best']['name'], point['best'].get('requirements')
        if name != current or point_req != req or point['skill'] != prev + 1:
            segments.append({'from_skill': start, 'to_skill': prev + 1, 'recipe': current, 'requirements': req})
            start, current, req = point['skill'], name, point_req
        prev = point['skill']
    segments.append({'from_skill': start, 'to_skill': prev + 1, 'recipe': current, 'requirements': req})
    return segments


def supply_risk(prices, item_id, required_qty):
    row = item_row(prices, item_id) or {}
    supply = row.get('quantity')
    if supply in (None, 0):
        return {'market_quantity': supply, 'required_fraction_of_market': None, 'risk': 'unknown'}
    frac = required_qty / supply
    risk = 'high' if frac >= SUPPLY_HIGH else ('warning' if frac >= SUPPLY_WARN else 'ok')
    return {'market_quantity': supply, 'required_fraction_of_market': round(frac, 4), 'risk': risk}


def route_summary(points, row_lookup, prices):
    mats = defaultdict(float)
    total_gross = total_safe_gross = total_recovery = total_net = total_safe_net = 0.0
    expected_crafts_total = 0.0
    recipe_crafts = defaultdict(float)
    gaps = []

    for point in points:
        skill = point['skill']
        best = point['best']
        row = row_lookup[best['name']]
        p = best['skillup_probability']
        if p <= 0:
            gaps.append(skill)
            continue
        crafts = 1.0 / p
        expected_crafts_total += crafts
        recipe_crafts[row['name']] += crafts
        if row['gross_material_cost_gold'] is not None:
            total_gross += row['gross_material_cost_gold'] * crafts
            total_safe_gross += row['safe_gross_material_cost_gold'] * crafts
            total_recovery += row['sale_recovery'].get('expected_recovery_gold', 0.0) * crafts
            total_net += row['net_craft_cost_gold'] * crafts
            total_safe_net += row['safe_net_craft_cost_gold'] * crafts
        for item_id, qty in row['materials'].items():
            mats[str(item_id)] += qty * crafts

    material_rows = []
    for item_id, qty in sorted(mats.items(), key=lambda x: -x[1]):
        market = item_row(prices, item_id) or {}
        risk = supply_risk(prices, item_id, qty)
        material_rows.append({
            'item_id': int(item_id), 'name': market.get('name'),
            'expected_quantity': round(qty, 2),
            'min_buyout_gold': market.get('min_buyout_gold'),
            'safe_unit_price_gold': round(market['min_buyout_gold'] * SAFE_BUY_MULTIPLIER, 4) if market.get('min_buyout_gold') is not None else None,
            **risk,
        })

    return {
        'covered_from_skill': points[0]['skill'] if points else None,
        'covered_to_skill': points[-1]['skill'] + 1 if points else None,
        'expected_crafts': round(expected_crafts_total, 2),
        'expected_crafts_by_recipe': {k: round(v, 2) for k, v in recipe_crafts.items()},
        'expected_gross_material_cost_gold': round(total_gross, 2),
        'expected_sale_recovery_gold': round(total_recovery, 2),
        'expected_net_leveling_cost_gold': round(total_net, 2),
        'safe_7_5pct_gross_cost_gold': round(total_safe_gross, 2),
        'safe_7_5pct_net_cost_gold': round(total_safe_net, 2),
        'material_demand': material_rows,
        'gaps': gaps,
    }


def main():
    prices = load_json(PRICES)
    recipes = load_json(RECIPES)
    rows = []

    for recipe in recipes['recipes']:
        gross_cost, missing = craft_cost(prices, recipe['materials'])
        safe_gross, _ = craft_cost(prices, recipe['materials'], SAFE_BUY_MULTIPLIER)
        recovery = sale_recovery(prices, recipe.get('output'))
        recovery_gold = recovery.get('expected_recovery_gold', 0.0)
        net_cost = None if gross_cost is None else round(max(0.0, gross_cost - recovery_gold), 4)
        safe_net = None if safe_gross is None else round(max(0.0, safe_gross - recovery_gold), 4)
        required_skill = recipe.get('required_skill', 0)
        repeatable = recipe.get('repeatable_for_leveling', recipe['name'] != 'Runed Adamantite Rod')
        skill_curve = []
        if repeatable:
            for skill in range(300, 375):
                if skill < required_skill:
                    continue
                p = skillup_probability(skill, recipe['skill'])
                if p <= 0:
                    continue
                skill_curve.append({
                    'skill': skill, 'skillup_probability': round(p, 4),
                    'expected_gross_cost_per_skill_gold': expected_cost_per_skill(gross_cost, p),
                    'expected_net_cost_per_skill_gold': expected_cost_per_skill(net_cost, p),
                    'expected_safe_net_cost_per_skill_gold': expected_cost_per_skill(safe_net, p),
                })

        rows.append({
            'name': recipe['name'], 'required_skill': required_skill, 'skill': recipe['skill'],
            'requirements': recipe.get('requirements'), 'materials': recipe['materials'],
            'gross_material_cost_gold': gross_cost, 'safe_gross_material_cost_gold': safe_gross,
            'sale_recovery': recovery, 'net_craft_cost_gold': net_cost, 'safe_net_craft_cost_gold': safe_net,
            'missing_price_item_ids': missing, 'repeatable_for_leveling': repeatable,
            'notes': recipe.get('notes'), 'skill_curve': skill_curve,
        })

    report = {
        'market': prices['market'], 'price_source': prices['source'],
        'warning': 'Market-depth tiers are not available yet. Safe scenario applies +7.5% to input buy prices. Sale recovery is credited only with explicit demand probability.',
        'economics_model': {
            'ranking_metric': '(material cost - expected sale recovery) / skill-up probability',
            'ah_cut': AH_CUT, 'safe_buy_multiplier': SAFE_BUY_MULTIPLIER,
            'supply_warning_fraction': SUPPLY_WARN, 'supply_high_risk_fraction': SUPPLY_HIGH,
            'sale_recovery_rule': 'No demand probability = zero credited recovery',
        },
        'recipes': rows,
    }

    cheapest_by_skill, baseline_by_skill, conditional_by_skill = [], [], []
    for skill in range(300, 375):
        candidates, baseline, conditional = [], [], []
        for row in rows:
            point = next((x for x in row['skill_curve'] if x['skill'] == skill), None)
            if not point or point['expected_net_cost_per_skill_gold'] is None:
                continue
            candidate = {
                'name': row['name'], 'gross_craft_cost_gold': row['gross_material_cost_gold'],
                'expected_sale_recovery_gold': row['sale_recovery'].get('expected_recovery_gold', 0.0),
                'net_craft_cost_gold': row['net_craft_cost_gold'], 'safe_net_craft_cost_gold': row['safe_net_craft_cost_gold'],
                'sale_recovery_status': row['sale_recovery'].get('status'), 'skillup_probability': point['skillup_probability'],
                'expected_gross_cost_per_skill_gold': point['expected_gross_cost_per_skill_gold'],
                'expected_net_cost_per_skill_gold': point['expected_net_cost_per_skill_gold'],
                'expected_safe_net_cost_per_skill_gold': point['expected_safe_net_cost_per_skill_gold'],
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
    row_lookup = {r['name']: r for r in rows}
    report['baseline_route_summary'] = route_summary(baseline_by_skill, row_lookup, prices)
    report['conditional_route_summary'] = route_summary(conditional_by_skill, row_lookup, prices)
    report['all_route_summary'] = route_summary(cheapest_by_skill, row_lookup, prices)

    # Mandatory one-time tools are separated from repeatable leveling economics.
    report['mandatory_tools'] = [
        {
            'name': r['name'], 'required_skill': r['required_skill'],
            'gross_material_cost_gold': r['gross_material_cost_gold'],
            'safe_gross_material_cost_gold': r['safe_gross_material_cost_gold'],
            'missing_price_item_ids': r['missing_price_item_ids'],
        }
        for r in rows if not r['repeatable_for_leveling']
    ]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print('Wrote', OUT)
    print('Baseline:', report['baseline_route_segments'])
    print('Baseline total:', report['baseline_route_summary'])
    print('All:', report['all_route_segments'])
    print('All total:', report['all_route_summary'])


if __name__ == '__main__':
    main()
