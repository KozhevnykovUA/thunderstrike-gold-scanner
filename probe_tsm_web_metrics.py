import csv
import json
import re
from pathlib import Path

import requests

OUT = Path('data/tsm_web_metrics_probe.json')
CACHE = Path('data/tsm_items.csv')
BASE = 'https://tradeskillmaster.com/classic/eu-fresh/thunderstrike-alliance/items/{}'

NAMES = [
    'Ravager Dog','Blackened Trout','Feltail Delight','Broiled Bloodfin',"Kibler's Bits",'Blackened Sporefish',
    'Grilled Mudfish','Spicy Crawdad','Warp Burger','Blackened Basilisk','Poached Bluefish',
    'Spicy Hot Talbuk','Talbuk Steak','Roasted Clefthoof','Golden Fish Sticks','Crunchy Serpent',"Mok'Nathal Shortribs",'Thistle Tea',
    'Arcane Dust','Greater Planar Essence','Large Prismatic Shard','Superior Wizard Oil',
    'Fel Weightstone','Lesser Rune of Warding','Lesser Ward of Shielding','Adamantite Weightstone','Khorium Belt'
]

def text_metrics(html):
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text)
    rate = re.search(r'Region Sale Rate\s+([0-9.]+)', text, re.I)
    sold = re.search(r'Region Avg Daily Sold\s+([0-9.]+)', text, re.I)
    return {
        'region_sale_rate': float(rate.group(1)) if rate else None,
        'region_avg_daily_sold': float(sold.group(1)) if sold else None,
        'contains_sale_rate_label': 'Region Sale Rate' in text,
        'contains_daily_sold_label': 'Region Avg Daily Sold' in text,
    }

with CACHE.open(encoding='utf-8') as f:
    rows=list(csv.DictReader(f))
by_name = {r['name'].strip().lower(): r for r in rows}

s = requests.Session()
s.headers['User-Agent'] = 'Mozilla/5.0 (compatible; ThunderstrikeGoldScanner/1.0)'
items = {}
for name in NAMES:
    row = by_name.get(name.lower())
    if not row:
        items[name] = {'name': name, 'error': 'not_found_in_tsm_csv'}
        continue
    item_id = int(row['itemId'])
    url = BASE.format(item_id)
    try:
        r = s.get(url, timeout=30, allow_redirects=True)
        result = {'item_id':item_id,'name':name,'url':url,'status':r.status_code,'final_url':r.url,'content_length':len(r.content)}
        if r.status_code == 200:
            result.update(text_metrics(r.text))
        items[str(item_id)] = result
    except Exception as e:
        items[str(item_id)] = {'item_id':item_id,'name':name,'url':url,'error':repr(e)}

payload = {'source':'tsm_web_item_pages','market':'classic/eu-fresh/thunderstrike-alliance','items':items}
OUT.parent.mkdir(exist_ok=True)
OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
print('TSM web metrics collected:', len(items))
for x in items.values():
    if isinstance(x,dict) and x.get('region_sale_rate') is not None:
        print(x['name'],'rate=',x['region_sale_rate'],'sold/day=',x['region_avg_daily_sold'])
