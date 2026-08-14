// Thunderstrike Gold Scanner — BootyBayBroker rendered-browser collector v2
// Run in DevTools Console on https://bootybaybroker.com/ after the site loads normally.
// Uses same-origin iframes with the normal browser session. No Cloudflare bypassing.

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
    for(const tr of doc.querySelectorAll('table tr')){
      const cells=[...tr.querySelectorAll('td')].map(x=>(x.innerText||x.textContent||'').trim());
      if(cells.length<3) continue;
      const p=money(cells[0]); const q=number(cells[1]); const listings=number(cells[2]);
      if(p&&q!=null) levels.push({unit_price_gold:p,quantity:q,listings:listings});
    }
    levels.sort((a,b)=>a.unit_price_gold-b.unit_price_gold);
    return levels;
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
      source:'rendered_dom'
    };
  }
  async function waitForData(frame,timeoutMs=9000){
    const start=Date.now(); let last=null;
    while(Date.now()-start<timeoutMs){
      try{
        const doc=frame.contentDocument;
        if(doc){
          last=parseRendered(doc);
          const body=doc.body?.innerText||'';
          if(/Market Depth/i.test(body)&&(last.order_book.length||last.quantity!=null||last.market_value_gold!=null)) return last;
        }
      }catch(_){ }
      await sleep(500);
    }
    return last;
  }
  async function renderItem(id,name){
    const url=`/tbc-classic/item/${id}/${slugify(name)}?${qs}`;
    const frame=document.createElement('iframe');
    frame.style.cssText='position:fixed;width:1px;height:1px;opacity:0;pointer-events:none;left:-9999px;top:-9999px';
    document.body.appendChild(frame);
    try{
      const loaded=new Promise((resolve,reject)=>{frame.onload=()=>resolve();frame.onerror=()=>reject(new Error('iframe_load_failed'));});
      frame.src=url; await loaded;
      const row=await waitForData(frame);
      const doc=frame.contentDocument; const body=doc?.body?.innerText||'';
      if(/Just a moment|challenge-platform|cf-chl/i.test(body)) return {id,name,url,ok:false,error:'blocked_or_challenge'};
      if(!row||(!row.min_buyout_gold&&!row.market_value_gold)) return {id,name,url,ok:false,error:'price_not_parsed',...(row||{})};
      return {id,name,url,ok:true,http_status:200,...row};
    }finally{frame.remove();}
  }

  const snapshot={schema_version:2,source:'bootybaybroker_rendered_browser_session',generated_at:new Date().toISOString(),market:MARKET,items:{}};
  console.log(`[Gold Scanner v2] collecting ${ITEMS.length} items with rendered DOM…`);
  for(let i=0;i<ITEMS.length;i++){
    const [id,name]=ITEMS[i];
    try{snapshot.items[String(id)]=await renderItem(id,name);}catch(e){snapshot.items[String(id)]={id,name,ok:false,error:String(e)};}
    console.log(`[${i+1}/${ITEMS.length}] ${name}`,snapshot.items[String(id)]);
    await sleep(400);
  }
  const json=JSON.stringify(snapshot,null,2);
  const blob=new Blob([json],{type:'application/json'}); const href=URL.createObjectURL(blob);
  const a=document.createElement('a'); a.href=href; a.download='bbb_snapshot.json'; document.body.appendChild(a); a.click(); a.remove(); setTimeout(()=>URL.revokeObjectURL(href),1000);
  try{await navigator.clipboard.writeText(json);}catch(_){ }
  console.log('[Gold Scanner v2] done',snapshot); return snapshot;
})();
