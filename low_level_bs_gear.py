import csv, json
from pathlib import Path
from datetime import datetime, timezone

CACHE=Path('data/tsm_items.csv')
OUT=Path('data/low_level_bs_gear.json')

CRAFTS=[
 {'name':'Titanic Leggings','role':'ret','level':55,'score':10,'mats':{'Arcanite Bar':12,'Enchanted Thorium Bar':20,'Essence of Earth':10,'Flask of the Titans':2}},
 {'name':'Lionheart Helm','role':'ret','level':56,'score':9,'mats':{'Thorium Bar':80,'Arcanite Bar':12,'Wicked Claw':40,'Blue Sapphire':10,'Azerothian Diamond':4}},
 {'name':'Stronghold Gauntlets','role':'hybrid','level':57,'score':6,'mats':{'Arcanite Bar':15,'Enchanted Thorium Bar':20,'Essence of Earth':10,'Blue Sapphire':4,'Large Opal':4}},
 {'name':'Enchanted Thorium Helm','role':'prot','level':57,'score':7,'mats':{'Arcanite Bar':6,'Enchanted Thorium Bar':16,'Essence of Earth':6,'Large Opal':2,'Azerothian Diamond':1}},
 {'name':'Enchanted Thorium Breastplate','role':'prot','level':58,'score':7,'mats':{'Arcanite Bar':8,'Enchanted Thorium Bar':24,'Essence of Earth':4,'Essence of Water':4,'Huge Emerald':2,'Azerothian Diamond':2}},
 {'name':'Enchanted Thorium Leggings','role':'prot','level':58,'score':7,'mats':{'Arcanite Bar':10,'Enchanted Thorium Bar':20,'Essence of Water':6,'Blue Sapphire':2,'Huge Emerald':1}},
 {'name':'Arcanite Champion','role':'ret','level':58,'score':4,'mats':{'Arcanite Bar':15,'Azerothian Diamond':8,'Righteous Orb':1,'Large Opal':4,'Enchanted Leather':8,'Dense Grinding Stone':2}},
]

def g(v):
    try:return int(v)/10000
    except:return None

def pick(row):
    if not row:return None
    for k in ('recent','marketValue','minBuyout'):
        v=g(row.get(k))
        if v and v>0:return v
    return None

rows=list(csv.DictReader(CACHE.open(encoding='utf-8')))
by={r['name'].strip().lower():r for r in rows}
out=[]
for c in CRAFTS:
    cost=0; mats=[]; missing=[]
    for n,q in c['mats'].items():
        p=pick(by.get(n.lower()))
        if p is None: missing.append(n); continue
        cost+=p*q; mats.append({'name':n,'qty':q,'unit_gold':round(p,4),'cost_gold':round(p*q,2)})
    orow=by.get(c['name'].lower())
    obuy=pick(orow)
    out.append({**{k:v for k,v in c.items() if k!='mats'},'material_cost_gold':round(cost,2) if not missing else None,'output_recent_or_market_gold':round(obuy,2) if obuy else None,'cheaper_to_buy_finished':bool(obuy and not missing and obuy<cost),'materials':mats,'missing':missing})
OUT.write_text(json.dumps({'generated_at':datetime.now(timezone.utc).isoformat(),'market':'Thunderstrike EU Alliance','items':out},indent=2),encoding='utf-8')
for x in out: print(x['name'],x['role'],'mats=',x['material_cost_gold'],'finished=',x['output_recent_or_market_gold'],'buy_finished=',x['cheaper_to_buy_finished'],'missing=',x['missing'])
