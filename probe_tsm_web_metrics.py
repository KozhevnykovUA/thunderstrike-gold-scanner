import csv
import io
import json
import re
from pathlib import Path

import requests

OUT = Path('data/tsm_web_metrics_probe.json')
BASE = 'https://tradeskillmaster.com/classic/eu-fresh/thunderstrike-alliance/items/{}'
TSM_CSV = 'https://public-data.tradeskillmaster.com/classic/eu-fresh/realm/thunderstrike-alliance/items.csv'

NAMES = [
    'Ravager Dog','Blackened Trout','Broiled Bloodfin',"Kibler's Bits",'Blackened Sporefish',
    'Grilled Mudfish','Spicy Crawdad','Warp Burger','Blackened Basilisk','Poached Bluefish',
    'Spicy Hot Talbuk','Roasted Clefthoof','Golden Fish Sticks','Thistle Tea',
    'Arcane Dust','Greater Planar Essence','Large Prismatic Shard','Superior Wizard Oil'
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

s = requests.Session()
s.headers['User-Agent'] = 'Mozilla/5.0 (compatible; ThunderstrikeGoldScanner/1.0)'

csv_resp = s.get(TSM_CSV, timeout=45)
csv_resp.raise_for_status()
rows = list(csv.DictReader(io.StringIO(csv_resp.text)))
by_name = {r['name'].strip().lower(): r for r in rows}

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
        result = {
            'item_id': item_id,
            'name': name,
            'url': url,
            'status': r.status_code,
            'final_url': r.url,
            'content_length': len(r.content),
        }
        if r.status_code == 200:
            result.update(text_metrics(r.text))
        else:
            result['body_preview'] = r.text[:300]
        items[str(item_id)] = result
    except Exception as e:
        items[str(item_id)] = {'item_id': item_id, 'name': name, 'url': url, 'error': repr(e)}

payload = {
    'source': 'tsm_web_item_pages',
    'market': 'classic/eu-fresh/thunderstrike-alliance',
    'items': items,
}
OUT.parent.mkdir(exist_ok=True)
OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
print('TSM web metrics collected:', len(items))
for x in items.values():
    if isinstance(x, dict) and x.get('region_sale_rate') is not None:
        print(x['name'], 'rate=', x['region_sale_rate'], 'sold/day=', x['region_avg_daily_sold'])
