import csv, json, math
from pathlib import Path
from datetime import datetime, timezone

TSM=Path('data/tsm_items.csv')
PROFIT=Path('data/cooking_profit.json')
OUT=Path('data/cooking_recipe_roi.json')

OWNED={
 'Recipe: Warp Burger','Recipe: Blackened Basilisk','Recipe: Golden Fish Sticks',
 'Recipe: Grilled Mudfish','Recipe: Roasted Clefthoof','Recipe: Ravager Dog',
 'Recipe: Spicy Crawdad','Recipe: Poached Bluefish'
}

# Only tradeable / AH-buyable recipes here. BoP/daily recipes are excluded from AH recommendations.
CANDIDATES={
 'Recipe: Blackened Trout':'Blackened Trout',
 'Recipe: Feltail Delight':'Feltail Delight',
 'Recipe: Blackened Sporefish':'Blackened Sporefish',
 'Recipe: Talbuk Steak':'Talbuk Steak',
 'Recipe: Warp Burger':'Warp Burger',
 'Recipe: Blackened Basilisk':'Blackened Basilisk',
 'Recipe: Golden Fish Sticks':'Golden Fish Sticks',
 'Recipe: Grilled Mudfish':'Grilled Mudfish',
 'Recipe: Roasted Clefthoof':'Roasted Clefthoof',
 'Recipe: Ravager Dog':'Ravager Dog',
 'Recipe: Spicy Crawdad':'Spicy Crawdad',
 'Recipe: Poached Bluefish':'Poached Bluefish',
}

def g(v):
    try:return int(v)/10000
    except:return None

rows=list(csv.DictReader(TSM.open(encoding='utf-8')))
by={r['name'].strip().lower():r for r in rows}
profit=json.load(PROFIT.open(encoding='utf-8'))
byout={x['output']:x for x in profit.get('opportunities',[])}

result=[]
for recipe,output in CANDIDATES.items():
    rr=by.get(recipe.lower())
    p=byout.get(output)
    recipe_price=(g(rr.get('recent')) or g(rr.get('marketValue')) or g(rr.get('minBuyout'))) if rr else None
    owned=recipe in OWNED
    row={'recipe':recipe,'output':output,'owned':owned,'recipe_ah_recent_gold':round(recipe_price,4) if recipe_price is not None else None}
    if p:
        prof=p.get('profit_per_craft_gold')
        rate=p.get('region_sale_rate')
        sold=p.get('region_avg_daily_sold')
        expected=p.get('expected_profit_per_listing_gold')
        row.update({'profit_per_craft_gold':prof,'region_sale_rate':rate,'region_avg_daily_sold':sold,'expected_profit_per_listing_gold':expected})
        if prof is not None and prof>0 and recipe_price is not None:
            row['crafts_to_payback_if_sold']=math.ceil(recipe_price/prof)
        else: row['crafts_to_payback_if_sold']=None
        if expected is not None and expected>0 and recipe_price is not None:
            row['listing_attempts_to_expected_payback']=math.ceil(recipe_price/expected)
        else: row['listing_attempts_to_expected_payback']=None
        # Max sensible recipe price for a modest 100-craft commercial horizon.
        row['max_recipe_price_for_100_crafts_gold']=round(max(prof or 0,0)*100,2)
        if owned: verdict='OWNED'
        elif prof is None or prof<=0: verdict='SKIP_CURRENTLY_UNPROFITABLE'
        elif recipe_price is None: verdict='CHECK_AH_MANUALLY'
        elif recipe_price <= max(prof,0)*50: verdict='BUY_STRONG'
        elif recipe_price <= max(prof,0)*100: verdict='BUY_IF_YOU_WILL_SELL_100'
        else: verdict='SKIP_TOO_EXPENSIVE'
        row['verdict']=verdict
    else:
        row.update({'profit_per_craft_gold':None,'region_sale_rate':None,'region_avg_daily_sold':None,'expected_profit_per_listing_gold':None,'crafts_to_payback_if_sold':None,'listing_attempts_to_expected_payback':None,'max_recipe_price_for_100_crafts_gold':None,'verdict':'NEEDS_PROFIT_MODEL' if not owned else 'OWNED'})
    result.append(row)

ranked=sorted(result,key=lambda x:(x['owned'], -(x.get('expected_profit_per_listing_gold') or -999)))
payload={
 'generated_at':datetime.now(timezone.utc).isoformat(),
 'market':'classic/eu-fresh/thunderstrike-alliance',
 'owned_recipes':sorted(OWNED),
 'method':'Recipe AH cost versus current food profit after 5% AH cut; sale-rate-adjusted expected listing profit shown separately.',
 'recommendations':ranked,
 'excluded_bop_or_daily':['Recipe: Crunchy Serpent','Recipe: Mok\'Nathal Shortribs','Recipe: Kibler\'s Bits','Recipe: Spicy Hot Talbuk','Recipe: Broiled Bloodfin','Recipe: Skullfish Soup','Recipe: Stormchops','Recipe: Delicious Chocolate Cake']
}
OUT.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8')
print('COOKING RECIPE ROI')
for x in ranked:
    if not x['owned']:
        print(x['recipe'],'price=',x['recipe_ah_recent_gold'],'profit=',x['profit_per_craft_gold'],'rate=',x['region_sale_rate'],'payback=',x['crafts_to_payback_if_sold'],'verdict=',x['verdict'])
