import json, re, requests
from pathlib import Path

OUT = Path('data/tsm_web_metrics_probe.json')
BASE = 'https://tradeskillmaster.com/classic/eu-fresh/thunderstrike-alliance/items/{}'
ITEMS = {
    22445: 'Arcane Dust',
    27655: 'Ravager Dog',
    27657: 'Blackened Basilisk',
}

RATE_RE = re.compile(r'Region\s+Sale\s+Rate\s*</?[^>]*>?\s*([0-9.]+)', re.I)
SOLD_RE = re.compile(r'Region\s+Avg\s+Daily\s+Sold\s*</?[^>]*>?\s*([0-9.]+)', re.I)

def text_metrics(html):
    # Keep this intentionally simple: first inspect whether the values are server-rendered in HTML.
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text)
    rate = re.search(r'Region Sale Rate\s+([0-9.]+)', text, re.I)
    sold = re.search(r'Region Avg Daily Sold\s+([0-9.]+)', text, re.I)
    return {
        'region_sale_rate': float(rate.group(1)) if rate else None,
        'region_avg_daily_sold': float(sold.group(1)) if sold else None,
        'contains_sale_rate_label': 'Region Sale Rate' in text,
        'contains_daily_sold_label': 'Region Avg Daily Sold' in text,
        'text_preview': text[:1200],
    }

s = requests.Session()
s.headers['User-Agent'] = 'Mozilla/5.0 (compatible; ThunderstrikeGoldScanner/1.0)'
result = {'source': 'tsm_web_item_pages_probe', 'items': {}}
for item_id, name in ITEMS.items():
    url = BASE.format(item_id)
    try:
        r = s.get(url, timeout=30, allow_redirects=True)
        row = {'name': name, 'url': url, 'status': r.status_code, 'final_url': r.url, 'content_length': len(r.content)}
        if r.status_code == 200:
            row.update(text_metrics(r.text))
        else:
            row['body_preview'] = r.text[:500]
        result['items'][str(item_id)] = row
    except Exception as e:
        result['items'][str(item_id)] = {'name': name, 'url': url, 'error': repr(e)}

OUT.parent.mkdir(exist_ok=True)
OUT.write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
