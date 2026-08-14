import json
from pathlib import Path
from datetime import datetime, timezone

COOK=Path('data/cooking_profit.json')
PROF=Path('data/profession_profit.json')
DE=Path('data/disenchant_thresholds.json')
OUT=Path('data/top_opportunities.json')

def load(p):
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}

def main():
    rows=[]
    for x in load(COOK).get('opportunities',[]):
        if x.get('profitable'):
            rows.append({**x,'profession':'Cooking'})
    for x in load(PROF).get('opportunities',[]):
        if x.get('profitable'):
            rows.append(x)
    rows.sort(key=lambda x:(x.get('expected_profit_per_listing_gold') is not None,x.get('expected_profit_per_listing_gold') or x.get('profit_per_craft_gold',0)),reverse=True)
    payload={
      'generated_at':datetime.now(timezone.utc).isoformat(),
      'market':'classic/eu-fresh/thunderstrike-alliance',
      'ranking':'sale-rate-adjusted expected profit per listing; sold/day retained as regional liquidity context',
      'top':rows[:25],
      'disenchant_buy_rules':load(DE).get('thresholds',[]),
      'notes':['Region Avg Daily Sold is regional TSM demand, not Thunderstrike-only sales.','Recommended craft quantity should be conservative until realm-level depth is available.']
    }
    OUT.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8')
    print('TOP OPPORTUNITIES')
    for i,x in enumerate(rows[:10],1):
        print(i,x.get('profession'),x.get('output'),'profit=',x.get('profit_per_craft_gold'),'rate=',x.get('region_sale_rate'),'sold/day=',x.get('region_avg_daily_sold'),'expected=',x.get('expected_profit_per_listing_gold'))

if __name__=='__main__': main()
