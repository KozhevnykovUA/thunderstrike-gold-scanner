// Thunderstrike Gold Scanner — BootyBayBroker browser collector
// Run this in DevTools Console while you are on https://bootybaybroker.com/ and past Cloudflare.
// It uses same-origin fetch with your normal browser session; no challenge bypassing.
// The result is downloaded as bbb_snapshot.json and copied to the clipboard when possible.

(async () => {
  const MARKET = {
    region: 'eu', realm: 'thunderstrike', realm_id: 6409,
    faction: 'alliance', auction_house_id: 2
  };

  const ITEMS = [
    [22445, 'Arcane Dust'],
    [22446, 'Greater Planar Essence'],
    [22447, 'Lesser Planar Essence'],
    [22448, 'Small Prismatic Shard'],
    [22449, 'Large Prismatic Shard'],
    [22522, 'Superior Wizard Oil'],
    [22792, 'Nightmare Vine'],
    [23427, 'Eternium Ore'],
    [23445, 'Fel Iron Bar'],
    [23446, 'Adamantite Bar'],
    [23447, 'Eternium Bar'],
    [23448, 'Felsteel Bar'],
    [23449, 'Khorium Bar'],
    [23571, 'Primal Might'],
    [21877, 'Netherweave Cloth'],
    [22578, 'Mote of Water'],
    [21885, 'Primal Water'],
    [22457, 'Primal Mana'],
    [25844, 'Adamantite Rod']
  ];

  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const slugify = s => s.toLowerCase().replace(/'/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  const qs = new URLSearchParams({
    realmId: String(MARKET.realm_id),
    auctionHouseId: String(MARKET.auction_house_id),
    faction: MARKET.faction,
    region: MARKET.region,
    realm: MARKET.realm,
  }).toString();

  function normalizeMoney(s) {
    if (!s) return null;
    const t = String(s).replace(/\u00a0/g, ' ');
    const m = t.match(/(?:(\d+(?:[.,]\d+)?)\s*g)?\s*(?:(\d+)\s*s)?\s*(?:(\d+)\s*c)?/i);
    if (!m || (!m[1] && !m[2] && !m[3])) return null;
    const g = Number((m[1] || '0').replace(',', '.'));
    const ss = Number(m[2] || 0), c = Number(m[3] || 0);
    return +(g + ss / 100 + c / 10000).toFixed(4);
  }

  function num(s) {
    if (s == null) return null;
    const m = String(s).replace(/,/g, '').match(/-?\d+(?:\.\d+)?/);
    return m ? Number(m[0]) : null;
  }

  function collectJsonObjects(root) {
    const out = [];
    for (const script of root.querySelectorAll('script')) {
      const type = (script.type || '').toLowerCase();
      const text = script.textContent || '';
      if (!(type.includes('json') || text.trim().startsWith('{') || text.trim().startsWith('['))) continue;
      try { out.push(JSON.parse(text)); } catch (_) {}
    }
    return out;
  }

  function walk(obj, fn, seen = new Set()) {
    if (!obj || typeof obj !== 'object' || seen.has(obj)) return;
    seen.add(obj); fn(obj);
    if (Array.isArray(obj)) obj.forEach(x => walk(x, fn, seen));
    else Object.values(obj).forEach(x => walk(x, fn, seen));
  }

  function extractFromJson(jsons, itemId) {
    const candidates = [];
    const priceKeys = ['minBuyout','minimumBuyout','lowestBuyout','currentPrice','price','buyout','marketPrice'];
    const marketKeys = ['marketValue','marketAvg','marketAverage','dbMarket','avgPrice'];
    const qtyKeys = ['quantity','available','availableQuantity','supply','onSale'];
    const auctionKeys = ['auctions','auctionCount','listings','activeAuctions'];
    const saleRateKeys = ['saleRate','regionalSaleRate','regionSaleRate'];
    const soldKeys = ['soldPerDay','regionalSoldPerDay','regionSoldPerDay'];
    const first = (o, keys) => { for (const k of keys) if (o[k] != null) return o[k]; return null; };

    for (const root of jsons) {
      walk(root, o => {
        const id = o.itemId ?? o.itemID ?? o.id;
        if (String(id) !== String(itemId)) return;
        const rawPrice = first(o, priceKeys);
        const rawMarket = first(o, marketKeys);
        const row = {
          min_buyout_gold: typeof rawPrice === 'number' ? (rawPrice > 10000 ? rawPrice / 10000 : rawPrice) : normalizeMoney(rawPrice),
          market_value_gold: typeof rawMarket === 'number' ? (rawMarket > 10000 ? rawMarket / 10000 : rawMarket) : normalizeMoney(rawMarket),
          quantity: num(first(o, qtyKeys)),
          auction_count: num(first(o, auctionKeys)),
          sale_rate: num(first(o, saleRateKeys)),
          sold_per_day: num(first(o, soldKeys)),
          source: 'embedded_json'
        };
        if (Object.values(row).some(v => v != null && v !== 'embedded_json')) candidates.push(row);
      });
    }
    return candidates[0] || null;
  }

  function labelValue(doc, labels) {
    const all = [...doc.querySelectorAll('body *')];
    for (const el of all) {
      const txt = (el.textContent || '').trim();
      if (!txt || txt.length > 120) continue;
      for (const label of labels) {
        if (txt.toLowerCase() === label.toLowerCase()) {
          const parent = el.parentElement;
          const siblings = parent ? [...parent.children] : [];
          const idx = siblings.indexOf(el);
          for (const cand of [siblings[idx + 1], el.nextElementSibling, parent?.nextElementSibling]) {
            const v = cand?.textContent?.trim();
            if (v) return v;
          }
        }
      }
    }
    return null;
  }

  function extractFromDom(doc) {
    const body = doc.body?.innerText || '';
    const current = labelValue(doc, ['Current Price','Lowest Buyout','Price']);
    const market = labelValue(doc, ['Market Value','Market Avg','Market Average']);
    const qty = labelValue(doc, ['Available Supply','On Sale','Quantity','Supply']);
    const auctions = labelValue(doc, ['Active Auctions','Auctions','Listings']);
    const saleRate = labelValue(doc, ['Sale Rate','Regional Sale Rate']);
    const soldDay = labelValue(doc, ['Sold / Day','Sold Per Day','Regional Sold Per Day']);
    const fallbackMoney = [...body.matchAll(/(?:\d+g\s*)?(?:\d+s\s*)?\d+c/gi)].map(x => normalizeMoney(x[0])).filter(x => x != null);
    return {
      min_buyout_gold: normalizeMoney(current) ?? fallbackMoney[0] ?? null,
      market_value_gold: normalizeMoney(market) ?? fallbackMoney[1] ?? null,
      quantity: num(qty), auction_count: num(auctions), sale_rate: num(saleRate), sold_per_day: num(soldDay),
      source: 'dom_text'
    };
  }

  async function fetchItem(id, name) {
    const url = `/tbc-classic/item/${id}/${slugify(name)}?${qs}`;
    const r = await fetch(url, {credentials: 'include', headers: {'Accept': 'text/html,application/xhtml+xml'}});
    const html = await r.text();
    if (!r.ok || /Just a moment|challenge-platform|cf-chl/i.test(html)) {
      return {id, name, url, ok: false, http_status: r.status, error: 'blocked_or_challenge'};
    }
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const jsonRow = extractFromJson(collectJsonObjects(doc), id);
    const domRow = extractFromDom(doc);
    const merged = {...domRow, ...(jsonRow || {})};
    if (merged.min_buyout_gold == null) {
      return {id, name, url, ok: false, http_status: r.status, error: 'price_not_parsed', ...merged};
    }
    return {id, name, url, ok: true, http_status: r.status, ...merged};
  }

  const snapshot = {schema_version: 1, source: 'bootybaybroker_browser_session', generated_at: new Date().toISOString(), market: MARKET, items: {}};
  console.log(`[Gold Scanner] collecting ${ITEMS.length} items…`);
  for (let i = 0; i < ITEMS.length; i++) {
    const [id, name] = ITEMS[i];
    try {
      const row = await fetchItem(id, name);
      snapshot.items[String(id)] = row;
      console.log(`[${i + 1}/${ITEMS.length}] ${name}`, row);
    } catch (e) {
      snapshot.items[String(id)] = {id, name, ok: false, error: String(e)};
    }
    await sleep(350);
  }

  const json = JSON.stringify(snapshot, null, 2);
  const blob = new Blob([json], {type: 'application/json'});
  const href = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = href; a.download = 'bbb_snapshot.json';
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
  try { await navigator.clipboard.writeText(json); console.log('[Gold Scanner] snapshot copied to clipboard'); } catch (_) {}
  console.log('[Gold Scanner] done:', snapshot);
  return snapshot;
})();
