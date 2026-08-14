import json
from pathlib import Path

PRICES = Path('data/prices.json')
RECIPES = Path('recipes/enchanting_300_375.json')
OUT = Path('data/enchanting_report.json')


def load_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def item_row(prices, item_id):
    return prices['items'].get(str(item_id))


def item_buy_price(prices, item_id):
    row = item_row(prices, item_id)
    if not row:
        return None
    return row.get('effective_buy_gold', row.get('safe_buy_gold', row.get('min_buyout_gold')))


def craft_cost(prices, materials):
    total = 0.0
    missing = []
    for item_id, qty in materials.items():
        price = item_buy_price(prices, item_id)
        if price is None:
            missing.append(str(item_id))
            continue
        total += price * qty
    return (round(total, 4) if not missing else None), missing


def sale_probability(row):
    """Best-effort probability that one crafted item sells in the target window.

    Preferred input is explicit sell_probability_48h. If absent, infer conservatively
    from sale_rate and sold_per_day. Missing demand data means no recovery credit.
    """
    if not row:
        return None
    explicit = row.get('sell_probability_48h')
    if explicit is not None:
        return max(0.0, min(1.0, float(explicit)))

    rate = row.get('sale_rate')
    sold = row.get('sold_per_day')
    if rate is None and sold is None:
        return None

    probs = []
    if rate is not None:
        # TSM-style sale rates are small decimals; map them conservatively to 48h sell chance.
        probs.append(max(0.0, min(1.0, float(rate) * 8.0)))
    if sold is not None:
        # One crafted unit has a good chance to move when several sell per day.
        probs.append(max(0.0, min(1.0, float(sold) / 2.0)))
    return round(sum(probs) / len(probs), 4)


def sale_recovery(prices, output):
    if not output:
        return {
            'expected_recovery_gold': 0.0,
            'sell_price_gold': None,
            'sell_probability_48h': None,
            'demand_known': False,
            'reason': 'not_saleable_output',
        }

    row = item_row(prices, output['item_id'])
    if not row:
        return {
            'expected_recovery_gold': 0.0,
            'sell_price_gold': None,
            'sell_probability_48h': None,
            'demand_known': False,
            'reason': 'missing_output_market_data',
        }

    sell_price = row.get('realistic_sell_gold', row.get('market_value_gold', row.get('min_buyout_gold')))
    probability = sale_probability(row)
    if sell_price is None or probability is None:
        return {
            'expected_recovery_gold': 0.0,
            'sell_price_gold': sell_price,
            'sell_probability_48h': probability,
            'demand_known': probability is not None,
            'reason': 'missing_sell_price_or_demand',
        }

    qty = output.get('quantity', 1)
    cut_pct = float(row.get('ah_cut_pct', 0.05))
    deposit = float(row.get('deposit_gold', 0.0))
    expected_reposts = float(row.get('expected_reposts', 0.0))
    gross = float(sell_price) * qty
    net_if_sold = gross * (1.0 - cut_pct)
    expected_deposit_loss = deposit * expected_reposts
    expected = max(0.0, probability * net_if_sold - expected_deposit_loss)

    return {
        'expected_recovery_gold': round(expected, 4),
        'sell_price_gold': round(float(sell_price), 4),
        'sell_probability_48h': round(probability, 4),
        'sale_rate': row.get('sale_rate'),
        'sold_per_day': row.get('sold_per_day'),
        'quantity_on_ah': row.get('quantity'),
        'ah_cut_pct': cut_pct,
        'expected_deposit_loss_gold': round(expected_deposit_loss, 4),
        'demand_known': True,
        'reason': 'market_recovery_applied',
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
    return round(net_craft_gold / probability, 4)


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
        raw_cost, missing = craft_cost(prices, recipe['materials'])
        recovery = sale_recovery(prices, recipe.get('output'))
        net_cost = None if raw_cost is None else max(0.0, round(raw_cost - recovery['expected_recovery_gold'], 4))
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
                    'expected_net_cost_per_skill_gold': expected_cost_per_skill(net_cost, probability),
                })

        rows.append({
            'name': recipe['name'],
            'required_skill': required_skill,
            'skill': recipe['skill'],
            'requirements': recipe.get('requirements'),
            'material_cost_gold': raw_cost,
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
        'warning': 'Ranking uses expected NET leveling cost after sale recovery where sell-price and demand data are available. Missing demand data receives zero recovery credit.',
        'recovery_model': {
            'ranking_metric': '(material cost - expected AH recovery) / skill-up probability',
            'sell_window': '48h',
            'ah_cut_default': 0.05,
            'demand_priority': 'explicit 48h sell probability, else conservative inference from sale_rate / sold_per_day',
            'rule': 'No demand data = no assumed recovery; avoids treating an expensive unsold item as free leveling.'
        },
        'skillup_model': {
            'type': 'color_breakpoint_linear_heuristic',
            'orange': 1.0,
            'yellow_to_green': 'linear 1.0 -> 0.5',
            'green_to_gray': 'linear 0.5 -> 0.0',
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
                'material_cost_gold': row['material_cost_gold'],
                'expected_recovery_gold': row['sale_recovery']['expected_recovery_gold'],
                'net_craft_cost_gold': row['net_craft_cost_gold'],
                'sell_probability_48h': row['sale_recovery'].get('sell_probability_48h'),
                'skillup_probability': point['skillup_probability'],
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

    for row in rows:
        print(row['name'], 'raw=', row['material_cost_gold'], 'recovery=', row['sale_recovery']['expected_recovery_gold'], 'net=', row['net_craft_cost_gold'])
    print('Wrote', OUT)


if __name__ == '__main__':
    main()
