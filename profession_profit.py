import csv, json
from pathlib import Path
from datetime import datetime, timezone

CACHE=Path('data/tsm_items.csv')
METRICS=Path('data/tsm_web_metrics_probe.json')
OUT=Path('data/profession_profit.json')
AH_CUT=0.05

RECIPES=[
 {'profession':'Enchanting','output':'Superior Wizard Oil','mats':{'Arcane Dust':3,'Nightmare Vine':1},'vendor_cost_gold':0.32},
 {'profession':'Blacksmithing','output':'Fel Weightstone','mats':{'Fel Iron Bar':1,'Netherweave Cloth':1}},
 {'profession':'Blacksmithing','output':'Lesser Rune of Warding','mats':{'Adamantite Bar':1}},
 {'profession':'Blacksmithing','output':'Lesser Ward of Shielding','mats':{'Adamantite Bar':1}},
 {'profession':'Blacksmithing','output':'Adamantite Weightstone','mats':{'Adamantite Bar':1,'Netherweave Cloth':2},'requirements':'Cenarion Expedition - Honored'},
 {'profession':'Blacksmithing','output':'Khorium Belt','mats':{'Khorium Bar':3,'Primal Water':2,'Primal Mana':2},'requirements':'Plans: Khorium Belt'},
]

def gold(v):
    if v in (None,''): return None
    return int(v)/10000

def main():
    rows=list(csv.DictReader(CACHE.open(encoding='utf-8')))
    by_name={r['name'].strip().lower():r for r in rows}
    metrics=json.loads(METRICS.read_text(encoding='utf-8')) if METRICS.exists() else {'items':{}}
    metrics_by_name={v.get('name','').lower():v for v in metrics.get('items',{}).values() if isinstance(v,dict)}
    results=[]
    for rec in RECIPES:
        out=by_name.get(rec['output'].lower())
        if not out: continue
        sell=gold(out.get('recent')) or gold(out.get('marketValue')) or gold(out.get('minBuyout'))
        if sell is None: continue
        cost=float(rec.get('vendor_cost_gold',0))
        mats=[]; ok=True
        for name,qty in rec['mats'].items():
            r=by_name.get(name.lower())
            if not r: ok=False; break
            buy=gold(r.get('recent')) or gold(r.get('marketValue')) or gold(r.get('minBuyout'))
            if buy is None: ok=False; break
            mats.append({'name':name,'qty':qty,'unit_buy_gold':round(buy,4),'cost_gold':round(buy*qty,4)})
            cost+=buy*qty
        if not ok: continue
        net=sell*(1-AH_CUT); profit=net-cost
        m=metrics_by_name.get(rec['output'].lower(),{})
        rate=m.get('region_sale_rate'); sold=m.get('region_avg_daily_sold')
        results.append({
          'profession':rec['profession'],'output':rec['output'],'requirements':rec.get('requirements'),
          'materials':mats,'material_cost_gold':round(cost,4),'sell_recent_gold':round(sell,4),
          'net_sale_after_5pct_gold':round(net,4),'profit_per_craft_gold':round(profit,4),
          'roi_pct':round(profit/cost*100,1) if cost else None,'region_sale_rate':rate,'region_avg_daily_sold':sold,
          'expected_profit_per_listing_gold':round(profit*rate,4) if rate is not None else None,
          'regional_demand_profit_index':round(profit*sold,2) if sold is not None else None,
          'profitable':profit>0
        })
    results.sort(key=lambda x:(x['expected_profit_per_listing_gold'] is not None,x['expected_profit_per_listing_gold'] or x['profit_per_craft_gold']),reverse=True)
    OUT.write_text(json.dumps({'generated_at':datetime.now(timezone.utc).isoformat(),'source':'TSM realm prices + TSM regional sale metrics','opportunities':results},indent=2),encoding='utf-8')
    for x in results:
        print(x['profession'],x['output'],'profit=',x['profit_per_craft_gold'],'rate=',x['region_sale_rate'],'sold/day=',x['region_avg_daily_sold'])

if __name__=='__main__': main()
