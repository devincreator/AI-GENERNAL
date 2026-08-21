from __future__ import annotations
import concurrent.futures as cf
import gzip, io, json, re, time, hashlib
from pathlib import Path
from datetime import datetime
import pandas as pd
import requests

OUT=Path('artifact'); OUT.mkdir(exist_ok=True)
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36'
SWS_URL='https://www.swsresearch.com/swindex/pdf/SwClass2021/StockClassifyUse_stock.xls'
CN_QUERY='https://www.cninfo.com.cn/new/hisAnnouncement/query'
CN_ORG='http://www.cninfo.com.cn/new/data/szse_stock.json'
CN_STATIC='https://static.cninfo.com.cn/'
HF_SEARCH='https://datasets-server.huggingface.co/search'
START='2005-01-01'; END='2026-08-21'

IDENTIFIERS=[
('000407','000407','胜利股份'),('000525','000525','红太阳'),('000553','000553','安道麦A'),('000732','000732','*ST三农'),
('001231','001231','农心科技'),('002004','002004','华邦健康'),('002018','002018','华星化工'),('002215','002215','诺普信'),
('002250','002250','联化科技'),('002258','002258','利尔化学'),('002391','002391','长青股份'),('002411','002411','必康股份'),
('002496','002496','辉丰股份'),('002513','002513','蓝丰生化'),('002734','002734','利民股份'),('002749','002749','国光股份'),
('002942','002942','新农股份'),('003042','003042','中农联合'),('300261','300261','雅本化学'),('300575','300575','中旗股份'),
('300796','300796','贝斯美'),('300804','300804','广康生化'),('301035','301035','润丰股份'),('301665','301665','泰禾股份'),
('600389','600389','江山股份'),('600486','600486','扬农化工'),('600500','600500','中化国际'),('600532','600532','华阳科技'),
('600538','600538','国发股份'),('600596','600596','新安股份'),('600731','600731','湖南海利'),('600796','600796','钱江生化'),
('600803','600803','新奥股份'),('600882','600882','大成股份'),('603086','603086','先达股份'),('603360','603360','百傲化学'),
('603585','603585','苏利股份'),('603599','603599','广信股份'),('603639','603639','海利尔'),('603810','603810','丰山集团'),
('603970','603970','中农立华'),('605033','605033','美邦股份'),('870866','LVHENG_TECH','绿亨科技'),('920866','LVHENG_TECH','绿亨科技'),
('833819','YINGTAI_BIO','颖泰生物'),('920819','YINGTAI_BIO','颖泰生物')]
CANON={'LVHENG_TECH':'920866','YINGTAI_BIO':'920819'}
for c,i,n in IDENTIFIERS: CANON.setdefault(i,c)

EVENT_RE=re.compile(r'投产|试生产|正式生产|复产|停产|停工|检修|事故|环保|处罚|环评|项目|扩建|技改|产能|装置|生产线|基地|工厂|合同|订单|中标|产品登记|登记证|价格调整|提价|降价|收购|并购|出售|转让|业绩预告|业绩快报|减值|存货|毛利率|年度报告|年报|半年度报告|半年报',re.I)
HEADER_CODE=re.compile(r'(?:证券|股票|公司)代码\s*[:：]\s*(\d{6})')

def req(method,url,**kw):
    s=kw.pop('session',None) or requests
    last=None
    for k in range(5):
        try:
            r=s.request(method,url,timeout=kw.pop('timeout',40),**kw)
            if r.status_code in (429,500,502,503,504):
                time.sleep(1.2*(k+1)); continue
            r.raise_for_status(); return r
        except Exception as e:
            last=e; time.sleep(1.2*(k+1))
    raise last

def build_sws():
    r=req('GET',SWS_URL,headers={'User-Agent':UA},timeout=60)
    (OUT/'StockClassifyUse_stock.xls').write_bytes(r.content)
    x=pd.read_excel(io.BytesIO(r.content),dtype=str).fillna('')
    cmap={}
    for c in x.columns:
        s=str(c)
        if '股票代码' in s: cmap[c]='security_code'
        elif '计入日期' in s: cmap[c]='start_date'
        elif '行业代码' in s: cmap[c]='industry_code'
        elif '更新日期' in s: cmap[c]='update_time'
        elif '股票名称' in s or '证券简称' in s: cmap[c]='name'
    x=x.rename(columns=cmap)
    need={'security_code','start_date','industry_code'}
    if not need.issubset(x.columns): raise RuntimeError(f'SWS columns not recognized: {list(x.columns)}')
    x['security_code']=x['security_code'].astype(str).str.extract(r'(\d{6})',expand=False).fillna('')
    x['industry_code']=x['industry_code'].astype(str).str.replace(r'\.0$','',regex=True).str.strip()
    x['start_date']=pd.to_datetime(x['start_date'],errors='coerce')
    x=x[x.security_code.ne('') & x.start_date.notna()].sort_values(['security_code','start_date'])
    x['end_date']=x.groupby('security_code')['start_date'].shift(-1)
    pest=x[x.industry_code.isin({'220303','220803'})].copy()
    idmap=pd.DataFrame(IDENTIFIERS,columns=['security_code','issuer_key','name'])
    pest=pest.merge(idmap[['security_code','issuer_key']],on='security_code',how='left')
    pest['issuer_key']=pest['issuer_key'].fillna(pest['security_code'])
    pest['canonical_code']=pest['issuer_key'].map(CANON).fillna(pest['security_code'])
    pest.to_csv(OUT/'sw_pesticide_intervals.csv',index=False,encoding='utf-8-sig')
    issu=pest.groupby('issuer_key').agg(canonical_code=('canonical_code','last'),first_start=('start_date','min'),last_end=('end_date','max'),security_codes=('security_code',lambda s:'|'.join(sorted(set(s))))).reset_index()
    issu.to_csv(OUT/'sw_pesticide_issuers.csv',index=False,encoding='utf-8-sig')
    return {'rows':len(pest),'issuers':issu.issuer_key.nunique(),'codes':pest.security_code.nunique()}

def fetch_prices():
    import akshare as ak
    rows=[]; fails=[]
    def one(t):
        code,issuer,name=t
        try:
            d=ak.stock_zh_a_hist(symbol=code,period='daily',start_date=START.replace('-',''),end_date=END.replace('-',''),adjust='qfq')
            if d is None or d.empty: return None,(issuer,CANON[issuer],code,'EMPTY')
            d=d.rename(columns={'日期':'trade_date','开盘':'open','收盘':'close','最高':'high','最低':'low','成交量':'volume','成交额':'amount','涨跌幅':'pct_change','换手率':'turnover'})
            d['security_code']=code; d['issuer_key']=issuer; d['code']=CANON[issuer]
            keep=['trade_date','code','issuer_key','security_code','open','high','low','close','volume','amount','pct_change','turnover']
            return d[[c for c in keep if c in d.columns]],None
        except Exception as e: return None,(issuer,CANON[issuer],code,f'{type(e).__name__}:{e}')
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for d,f in ex.map(one,IDENTIFIERS):
            if d is not None: rows.append(d)
            if f: fails.append(f)
    if rows:
        x=pd.concat(rows,ignore_index=True); x['trade_date']=pd.to_datetime(x.trade_date,errors='coerce'); x=x.dropna(subset=['trade_date'])
        x['is_canon']=(x.security_code.astype(str)==x.code.astype(str)).astype(int)
        x=x.sort_values(['issuer_key','trade_date','is_canon','security_code']).drop_duplicates(['issuer_key','trade_date'],keep='last').drop(columns='is_canon')
        x.to_csv(OUT/'prices_daily.csv.gz',index=False,encoding='utf-8-sig',compression='gzip')
        pd.DataFrame({'trade_date':sorted(x.trade_date.dt.strftime('%Y-%m-%d').unique())}).to_csv(OUT/'trading_calendar.csv',index=False)
    pd.DataFrame(fails,columns=['issuer_key','code','security_code','reason']).to_csv(OUT/'price_failures.csv',index=False,encoding='utf-8-sig')
    return {'rows':sum(len(d) for d in rows),'consolidated_rows':len(x) if rows else 0,'fail_identifiers':len(fails)}

def load_org_map():
    d=req('GET',CN_ORG,headers={'User-Agent':UA},timeout=30).json()
    return {str(s.get('code','')).zfill(6):str(s.get('orgId','')) for s in d.get('stockList',[]) if s.get('code')}

def fallback_org(code):
    if code.startswith(('92','8','4')): p='bj'
    elif code.startswith(('6','5','9')): p='sh'
    else: p='sz'
    return f'gs{p}0{code}'

def cninfo_metadata():
    orgmap=load_org_map(); allrows=[]; failures=[]
    headers={'User-Agent':UA,'Content-Type':'application/x-www-form-urlencoded','Referer':'https://www.cninfo.com.cn/new/disclosure','Origin':'https://www.cninfo.com.cn'}
    def one(t):
        code,issuer,name=t; org=orgmap.get(code) or orgmap.get(CANON[issuer]) or fallback_org(code); out=[]; seen=set(); page=1
        try:
            while True:
                payload={'stock':f'{code},{org}','tabName':'fulltext','pageSize':'30','pageNum':str(page),'column':'','category':'','plate':'','seDate':f'{START}~{END}','searchkey':'','secid':'','sortName':'','sortType':'','isHLtitle':'true'}
                d=req('POST',CN_QUERY,data=payload,headers=headers,timeout=35).json(); anns=d.get('announcements') or []
                if not anns: break
                for a in anns:
                    aid=str(a.get('announcementId') or '')
                    if not aid or aid in seen: continue
                    seen.add(aid); adjunct=a.get('adjunctUrl') or ''
                    ts=a.get('announcementTime'); pub=datetime.fromtimestamp(ts/1000).isoformat(timespec='seconds') if isinstance(ts,(int,float)) else str(ts or '')
                    out.append({'issuer_key':issuer,'code':CANON[issuer],'security_code':code,'name':name,'announcement_id':aid,'title':a.get('announcementTitle',''),'announcement_type':a.get('announcementTypeName',''),'publish_timestamp':pub,'adjunct_url':adjunct,'pdf_url':CN_STATIC+adjunct.lstrip('/') if adjunct else ''})
                total=int(d.get('totalAnnouncement') or 0); page+=1
                if total and len(seen)>=total: break
                time.sleep(.08)
            return out,None
        except Exception as e: return out,(issuer,code,f'{type(e).__name__}:{e}')
    with cf.ThreadPoolExecutor(max_workers=5) as ex:
        for r,f in ex.map(one,IDENTIFIERS): allrows.extend(r); failures.extend([f] if f else [])
    x=pd.DataFrame(allrows)
    if len(x):
        x['security_codes_returned']=x.security_code
        x=x.sort_values(['issuer_key','publish_timestamp','announcement_id']).drop_duplicates(['issuer_key','announcement_id'],keep='last')
        x.to_csv(OUT/'cninfo_metadata.csv.gz',index=False,encoding='utf-8-sig',compression='gzip')
    pd.DataFrame(failures,columns=['issuer_key','security_code','reason']).to_csv(OUT/'cninfo_failures.csv',index=False,encoding='utf-8-sig')
    return x,{'rows':len(x),'fail_identifiers':len(failures)}

def extract_pdf_text(url):
    from pypdf import PdfReader
    r=req('GET',url,headers={'User-Agent':UA,'Referer':'https://www.cninfo.com.cn/'},timeout=60)
    if len(r.content)<1000: raise RuntimeError('tiny_pdf')
    reader=PdfReader(io.BytesIO(r.content)); text='\n'.join((p.extract_text() or '') for p in reader.pages)
    return text,len(reader.pages),hashlib.sha256(r.content).hexdigest()

def selected_cninfo_text(meta):
    if meta is None or meta.empty: return {'selected':0,'text_ok':0,'fail':0}
    sel=meta[meta.title.astype(str).str.contains(EVENT_RE,na=False,regex=True)].copy()
    # Keep runtime bounded but high recall: newest 250 selected docs per issuer.
    sel=sel.sort_values('publish_timestamp').groupby('issuer_key',group_keys=False).tail(250)
    results=[]
    def one(r):
        try:
            text,pages,sha=extract_pdf_text(r.pdf_url)
            return {**r._asdict(),'text':text,'page_count':pages,'sha256':sha,'char_count':len(text),'text_status':'OK' if len(text)>=200 else 'SHORT'},None
        except Exception as e: return {**r._asdict(),'text':'','page_count':'','sha256':'','char_count':0,'text_status':f'ERROR:{type(e).__name__}'},str(e)
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for a,e in ex.map(one,sel.itertuples(index=False)):
            results.append(a)
    with gzip.open(OUT/'cninfo_event_texts.jsonl.gz','wt',encoding='utf-8') as f:
        for r in results: f.write(json.dumps(r,ensure_ascii=False,default=str)+'\n')
    man=pd.DataFrame([{k:v for k,v in r.items() if k!='text'} for r in results]); man.to_csv(OUT/'cninfo_selected_manifest.csv.gz',index=False,encoding='utf-8-sig',compression='gzip')
    return {'selected':len(sel),'text_ok':int((man.text_status=='OK').sum()) if len(man) else 0,'fail':int(man.text_status.astype(str).str.startswith('ERROR').sum()) if len(man) else 0}

def fincorpus_search():
    out=[]; fails=[]
    sess=requests.Session()
    def one(t):
        code,issuer,name=t; rows=[]; offset=0
        try:
            while True:
                params={'dataset':'Duxiaoman-DI/FinCorpus','config':'default','split':'train','query':code,'offset':offset,'length':100}
                d=req('GET',HF_SEARCH,params=params,headers={'User-Agent':UA},session=sess,timeout=60).json(); batch=d.get('rows') or []
                if not batch: break
                for z in batch:
                    row=z.get('row') or {}; text=str(row.get('text') or '')
                    m=HEADER_CODE.search(text[:8000])
                    if not m or m.group(1)!=code: continue
                    rows.append({'row_idx':z.get('row_idx'),'issuer_key':issuer,'code':CANON[issuer],'security_code':code,'name':name,'text':text,'meta':row.get('meta') or {}})
                offset += len(batch); total=int(d.get('num_rows_total') or 0)
                if offset>=total or offset>=5000: break
            return rows,None
        except Exception as e: return rows,(issuer,code,f'{type(e).__name__}:{e}')
    # One session per thread is safer; run serial-ish with 4 workers by wrapping independent calls.
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        for r,f in ex.map(one,IDENTIFIERS): out.extend(r); failures=[f] if f else []; fails.extend(failures)
    # issuer+text hash dedupe handles old/new identifiers.
    seen=set(); ded=[]
    for r in out:
        h=hashlib.sha256(r['text'].encode()).hexdigest(); key=(r['issuer_key'],h)
        if key in seen: continue
        seen.add(key); r['sha256']=h; ded.append(r)
    with gzip.open(OUT/'fincorpus_matches.jsonl.gz','wt',encoding='utf-8') as f:
        for r in ded: f.write(json.dumps(r,ensure_ascii=False,default=str)+'\n')
    pd.DataFrame(fails,columns=['issuer_key','security_code','reason']).to_csv(OUT/'fincorpus_failures.csv',index=False,encoding='utf-8-sig')
    return {'raw_matches':len(out),'deduped_matches':len(ded),'fail_identifiers':len(fails)}

def main():
    summary={'started_at':datetime.now().isoformat()}
    for name,fn in [('sws',build_sws),('prices',fetch_prices)]:
        try: summary[name]=fn()
        except Exception as e: summary[name]={'error':f'{type(e).__name__}:{e}'}
    try:
        meta,st=cninfo_metadata(); summary['cninfo_metadata']=st
        summary['cninfo_selected_text']=selected_cninfo_text(meta)
    except Exception as e: summary['cninfo_metadata']={'error':f'{type(e).__name__}:{e}'}
    try: summary['fincorpus']=fincorpus_search()
    except Exception as e: summary['fincorpus']={'error':f'{type(e).__name__}:{e}'}
    summary['finished_at']=datetime.now().isoformat()
    (OUT/'build_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
