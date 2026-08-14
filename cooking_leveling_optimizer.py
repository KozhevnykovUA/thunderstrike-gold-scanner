import csv, json, re
from pathlib import Path
from datetime import datetime, timezone
import requests

CACHE=Path('data/tsm_items.csv')
OUT=Path('data/cooking_leveling_1_300.json')
BASE='https://tradeskillmaster.com/classic/eu-fresh/thunderstrike-alliance/items/{}'
AH_CUT=0.05

# Expected crafts are conservative route estimates based on current TBC Anniversary guides.
SEGMENTS=[
 {'from':1,'to':50,'candidates':[('Brilliant Smallfish',52,{'Raw Brilliant Smallfish':1},'Recipe: Brilliant Smallfish')]},
 {'from':50,'to':100,'candidates':[('Longjaw Mud Snapper',55,{'Raw Longjaw Mud Snapper':1},'Recipe: Longjaw Mud Snapper')]},
 {'from':100,'to':175,'candidates':[('Bristle Whisker Catfish',120,{'Raw Bristle Whisker Catfish':1},'Recipe: Bristle Whisker Catfish')]},
 {'from':175,'to':225,'candidates':[
   ('Mithril Head Trout',60,{'Raw Mithril Head Trout':1},'Recipe: Mithril Head Trout'),
   ('Rockscale Cod',75,{'Raw Rockscale Cod':1},'Recipe: Rockscale Cod')]},
 {'from':225,'to':250,'candidates':[
   ('Spotted Yellowtail',25,{'Raw Spotted Yellowtail':1},'Recipe: Spotted Yellowtail'),
   ('Tender Wolf Steak',25,{'Tender Wolf Meat':1,'Soothing Spices':1},'Recipe: Tender Wolf Steak')]},
 {'from':250,'to':275,'candidates':[
   ('Spotted Yellowtail',65,{'Raw Spotted Yellowtail':1},'Recipe: Spotted Yellowtail'),
   ('Poached Sunscale Salmon',35,{'Raw Sunscale Salmon':1},'Recipe: Poached Sunscale Salmon'),
   ('Nightfin Soup',35,{'Raw Nightfin Snapper':1,'Refreshing Spring Water':1},'Recipe: Nightfin Soup')]},
 {'from':275,'to':300,'candidates':[
   ('Mightfish Steak',25,{'Large Raw Mightfish':1,'Hot Spices':1,'Soothing Spices':1},'Recipe: Mightfish Steak'),
   ('Lobster Stew',25,{'Darkclaw Lobster':1,'Refreshing Spring Water':1},'Recipe: Lobster Stew'),
   ('Baked Salmon',25,{'Raw Whitescale Salmon':1,'Soothing Spices':1},'Recipe: Baked Salmon')]}
]
QUEST={'Giant Egg':12,'Zesty Clam Meat':10,'Alterac Swiss':20}
BOOK='Expert Cookbook'

# TSM has duplicate/name-collision rows for some Classic items. Pin known canonical TBC IDs.
OUTPUT_IDS={'Mithril Head Trout':'8364'}
MAT_IDS={'Raw Mithril Head Trout':'8365'}

def g(v):
    try:return int(v)/10000
    except:return None

def price(row):
    if not row:return None
    return g(row.get('recent')) or g(row.get('marketValue')) or g(row.get('minBuyout'))

def metrics(session,item_id):
    try:
        r=session.get(BASE.format(item_id),timeout=20)
        if r.status_code!=200:return (None,None)
        text=re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',r.text))
        a=re.search(r'Region Sale Rate\s+([0-9.]+)',text,re.I)
        b=re.search(r'Region Avg Daily Sold\s+([0-9.]+)',text,re.I)
        return (float(a.group(1)) if a else None,float(b.group(1)) if b else None)
    except:return (None,None)

with CACHE.open(encoding='utf-8') as f: rows=list(csv.DictReader(f))
by={x['name'].strip().lower():x for x in rows}
byid={x['itemId']:x for x in rows}
def lookup(name, ids):
    pinned=ids.get(name)
    return byid.get(pinned) if pinned else by.get(name.lower())

s=requests.Session(); s.headers['User-Agent']='Mozilla/5.0 (compatible; ThunderstrikeGoldScanner/1.0)'
chosen=[]; all_segments=[]; shopping={}; recipes=[]
for seg in SEGMENTS:
    ranked=[]
    for name,crafts,mats,recipe in seg['candidates']:
        out=lookup(name,OUTPUT_IDS); sell=price(out)
        if sell is None: continue
        mat_cost=0; ok=True; details=[]
        for mat,qty in mats.items():
            matrow=lookup(mat,MAT_IDS)
            p=price(matrow)
            if p is None: ok=False; break
            mat_cost+=p*qty; details.append({'name':mat,'qty':qty,'unit_gold':round(p,4),'item_id':int(matrow['itemId'])})
        if not ok: continue
        rate,sold=metrics(s,int(out['itemId']))
        recovery=sell*(1-AH_CUT)*(rate if rate is not None else 0.10)
        net=max(0,mat_cost-recovery)
        ranked.append({'output':name,'output_item_id':int(out['itemId']),'expected_crafts':crafts,'materials':details,'gross_per_craft_gold':round(mat_cost,4),'sell_gold':round(sell,4),'sale_rate':rate,'sold_per_day':sold,'expected_recovery_per_craft_gold':round(recovery,4),'net_per_craft_gold':round(net,4),'segment_net_gold':round(net*crafts,2),'recipe':recipe})
    ranked.sort(key=lambda x:x['segment_net_gold'])
    if ranked:
        best=ranked[0]; chosen.append({'from':seg['from'],'to':seg['to'],**best}); all_segments.append({'from':seg['from'],'to':seg['to'],'ranked':ranked})
        for m in best['materials']: shopping[m['name']]=shopping.get(m['name'],0)+m['qty']*best['expected_crafts']
        recipes.append(best['recipe'])
for k,v in QUEST.items(): shopping[k]=shopping.get(k,0)+v
recipes.append(BOOK)

recipe_rows=[]
for name in dict.fromkeys(recipes):
    row=by.get(name.lower()); recipe_rows.append({'name':name,'ah_recent_gold':round(price(row),4) if price(row) is not None else None,'note':'Buy on AH if listed; otherwise vendor/quest source.'})

payload={'generated_at':datetime.now(timezone.utc).isoformat(),'market':'classic/eu-fresh/thunderstrike-alliance','model':'minimize expected net leveling cost after 5% AH cut and one-listing sale-rate-weighted recovery','route':chosen,'comparisons':all_segments,'shopping_list':[{'name':k,'qty':int(round(v))} for k,v in shopping.items()],'recipes_and_books':recipe_rows,'artisan_quest':QUEST,'estimated_net_material_cost_gold':round(sum(x['segment_net_gold'] for x in chosen),2),'notes':['Sale rate and sold/day are regional TSM metrics, not Thunderstrike-only sales counts.','Amounts are conservative expected-craft quantities; RNG may require a small top-up.','Smoked Desert Dumplings is excluded because its recipe is quest-earned rather than AH-buyable.','Known Classic TSM name collisions are resolved with canonical item IDs where needed.']}
OUT.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8')
print('COOKING 1-300 NET-COST ROUTE')
for x in chosen: print(x['from'],'-',x['to'],x['output'],'crafts',x['expected_crafts'],'net',x['segment_net_gold'])
print('Estimated net material cost:',payload['estimated_net_material_cost_gold'])
print('Shopping:',payload['shopping_list'])
