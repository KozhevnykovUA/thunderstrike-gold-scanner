// Thunderstrike Gold Scanner — BootyBayBroker rendered-browser collector v3
// Run in DevTools Console on https://bootybaybroker.com/ after the site loads normally.
// Uses ONE same-origin popup window and navigates it through item pages sequentially.
// This avoids BBB's CSP frame-ancestors 'none' rule that blocks iframes.

(async () => {
  const MARKET = {region:'eu', realm:'thunderstrike', realm_id:6409, faction:'alliance', auction_house_id:2};
  const ITEMS = [
    [16203,'Greater Eternal Essence'],[16204,'Illusion Dust'],[14344,'Large Brilliant Shard'],[25843,'Fel Iron Rod'],
    [22445,'Arcane Dust'],[22446,'Greater Planar Essence'],[22447,'Lesser Planar Essence'],[22448,'Small Prismatic Shard'],
    [22449,'Large Prismatic Shard'],[22522,'Superior Wizard Oil'],[22792,'Nightmare Vine'],[23427,'Eternium Ore'],
    [23445,'Fel Iron Bar'],[23446,'Adamantite Bar'],[23447,'Eternium Bar'],[23448,'Felsteel Bar'],[23449,'Khorium Bar'],
    [23571,'Primal Might'],[21877,'Netherweave Cloth'],[22578,'Mote of Water'],[21885,'Primal Water'],[22457,'Primal Mana'],
    [25844,'Adamantite Rod']
  ];

  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const slugify = s => s.toLowerCase().replace(/'/g,'').replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'');
  const qs = new URLSearchParams({realmId:String(MARKET.realm_id),auctionHouseId:String(MARKET.auction_house_id),faction:MARKET.faction,region:MARKET.region,realm:MARKET.realm}).toString();

  function money(s){
    if(!s) return null;
    const t=String(s).replace(/\u00a0/g,' ');
    const m=t.match(/(?:(\d+(?:[.,]\d+)?)\s*g)?\s*(?:(\d+)\s*s)?\s*(?:(\d+)\s*c)?/i);
    if(!m||(!m[1]&&!m[2]&&!m[3])) return null;
    const v=Number((m[1]||'0').replace(',','.'))+Number(m[2]||0)/100+Number(m[3]||0)/10000;
    return v>0 ? +v.toFixed(4) : null;
  }
  function number(s){
    if(s==null) return null;
    const m=String(s).replace(/[,%]/g,'').replace(/\s/g,'').match(/-?\d+(?:\.\d+)?/);
    return m?Number(m[0]):null;
  }
  function textMatch(body,label,pattern){
    const re=new RegExp(label+'\\s*[:\\n]?\\s*('+pattern+')','i');
    const m=body.match(re); return m?m[1]:null;
  }

  function parseDepth(doc){
    const levels=[];
    const tables=[...doc.querySelectorAll('table')];
    for(const table of tables){
      const txt=(table.innerText||'');
      if(!/Market Depth|Price|Quantity|Listings/i.test(txt)) continue;
      for(const tr of table.querySelectorAll('tr')){
        const cells=[...tr.querySelectorAll('td')].map(x=>(x.innerText||x.textContent||'').trim());
        if(cells.length<2) continue;
        let p=null,q=null,listings=null;
        for(const c of cells){ if(p==null) p=money(c); }
        const nums=cells.map(number).filter(x=>x!=null);
        if(nums.length){ q=nums[nums.length>1?1:0]; listings=nums.length>2?nums[2]:null; }
        if(p&&q!=null) levels.push({unit_price_gold:p,quantity:q,listings});
      }
    }
    const uniq=[]; const seen=new Set();
    for(const x of levels.sort((a,b)=>a.unit_price_gold-b.unit_price_gold)){
      const k=`${x.unit_price_gold}|${x.quantity}|${x.listings}`;
      if(!seen.has(k)){seen.add(k);uniq.push(x);}
    }
    return uniq;
  }

  function parseRendered(doc){
    const body=(doc.body?.innerText||'').replace(/\r/g,'');
    const depth=parseDepth(doc);
    const available=number(textMatch(body,'Available supply','[\\d, .]+')) ?? number(textMatch(body,'Total quantity','[\\d, .]+'));
    const auctions=number(textMatch(body,'Active auctions','[\\d, .]+')) ?? number(textMatch(body,'Total listings','[\\d, .]+'));
    const saleRateRaw=textMatch(body,'(?:Regional )?Sale Rate','[\\d.,]+%?');
    const soldRaw=textMatch(body,'(?:Regional )?Sold(?:\\s*/\\s*| Per )Day','[\\d.,]+');
    const marketRaw=textMatch(body,'Market (?:Value|Avg|Average)','(?:(?:\\d+(?:[.,]\\d+)?)\\s*g\\s*)?(?:\\d+\\s*s\\s*)?(?:\\d+\\s*c)?');
    const currentRaw=textMatch(body,'(?:Current Price|Lowest Buyout)','(?:(?:\\d+(?:[.,]\\d+)?)\\s*g\\s*)?(?:\\d+\\s*s\\s*)?(?:\\d+\\s*c)?');
    const minDepth=depth.length?depth[0].unit_price_gold:null;
    let saleRate=number(saleRateRaw); if(saleRateRaw&&/%/.test(saleRateRaw)&&saleRate!=null) saleRate/=100;
    return {
      min_buyout_gold:minDepth ?? money(currentRaw),
      market_value_gold:money(marketRaw),
      quantity:available,
      auction_count:auctions,
      sale_rate:saleRate,
      sold_per_day:number(soldRaw),
      order_book:depth,
      price_levels:depth.length,
      source:'rendered_popup_dom'
    };
  }

  function openCollectorWindow(){
    const w=window.open('about:blank','bbb_gold_scanner_window','popup=yes,width=1200,height=900');
    if(!w) throw new Error('popup_blocked: allow popups for bootybaybroker.com and run again');
    try{w.document.title='BBB Gold Scanner';w.document.body.innerHTML='<h2>Gold Scanner is starting…</h2><p>Do not close this window.</p>'; }catch(_){ }
    return w;
  }

  async function navigateAndWait(w,url,timeoutMs=15000){
    const absolute=new URL(url,location.origin).href;
    w.location.href=absolute;
    const start=Date.now();
    while(Date.now()-start<timeoutMs){
      if(w.closed) throw new Error('collector_window_closed');
      try{
        const href=w.location.href;
        const doc=w.document;
        if(href.startsWith(location.origin) && doc && doc.readyState==='complete' && href.includes('/tbc-classic/item/')) return doc;
      }catch(_){ }
      await sleep(250);
    }
    throw new Error('page_load_timeout');
  }

  async function waitForRenderedData(w,timeoutMs=12000){
    const start=Date.now(); let last=null;
    while(Date.now()-start<timeoutMs){
      if(w.closed) throw new Error('collector_window_closed');
      try{
        const doc=w.document;
        last=parseRendered(doc);
        const body=doc.body?.innerText||'';
        if(/Just a moment|challenge-platform|cf-chl/i.test(body)) return {blocked:true,row:last};
        if(last.order_book.length || last.quantity!=null || last.market_value_gold!=null || last.min_buyout_gold!=null){
          // Give client-side widgets another moment to populate Market Depth.
          await sleep(1200);
          return {blocked:false,row:parseRendered(w.document)};
        }
      }catch(_){ }
      await sleep(500);
    }
    return {blocked:false,row:last};
  }

  async function renderItem(w,id,name){
    const url=`/tbc-classic/item/${id}/${slugify(name)}?${qs}`;
    await navigateAndWait(w,url);
    const {blocked,row}=await waitForRenderedData(w);
    if(blocked) return {id,name,url,ok:false,error:'blocked_or_challenge',...(row||{})};
    if(!row||(!row.min_buyout_gold&&!row.market_value_gold&&!row.order_book?.length)) return {id,name,url,ok:false,error:'price_not_parsed',...(row||{})};
    return {id,name,url,ok:true,http_status:200,...row};
  }

  const popup=openCollectorWindow();
  const snapshot={schema_version:3,source:'bootybaybroker_rendered_popup_session',generated_at:new Date().toISOString(),market:MARKET,items:{}};
  console.log(`[Gold Scanner v3] collecting ${ITEMS.length} items using one popup…`);

  try{
    for(let i=0;i<ITEMS.length;i++){
      const [id,name]=ITEMS[i];
      try{snapshot.items[String(id)]=await renderItem(popup,id,name);}catch(e){snapshot.items[String(id)]={id,name,ok:false,error:String(e)};}
      console.log(`[${i+1}/${ITEMS.length}] ${name}`,snapshot.items[String(id)]);
      await sleep(400);
    }
  } finally {
    try{popup.close();}catch(_){ }
  }

  const json=JSON.stringify(snapshot,null,2);
  const blob=new Blob([json],{type:'application/json'}); const href=URL.createObjectURL(blob);
  const a=document.createElement('a'); a.href=href; a.download='bbb_snapshot.json'; document.body.appendChild(a); a.click(); a.remove(); setTimeout(()=>URL.revokeObjectURL(href),1000);
  try{await navigator.clipboard.writeText(json);}catch(_){ }
  console.log('[Gold Scanner v3] done',snapshot); return snapshot;
})();
