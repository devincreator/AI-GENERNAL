from __future__ import annotations
import io, json, time
from pathlib import Path
from datetime import datetime
import pandas as pd
import requests, urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

OUT=Path('artifact'); OUT.mkdir(exist_ok=True)
SWS_URL='https://www.swsresearch.com/swindex/pdf/SwClass2021/StockClassifyUse_stock.xls'
START='2005-01-01'; END='2026-08-21'
IDENTIFIERS=[
('000407','000407','胜利股份'),('000525','000525','红太阳'),('000553','000553','安道麦A'),('000732','000732','*ST三农'),('001231','001231','农心科技'),('002004','002004','华邦健康'),('002018','002018','华星化工'),('002215','002215','诺普信'),('002250','002250','联化科技'),('002258','002258','利尔化学'),('002391','002391','长青股份'),('002411','002411','必康股份'),('002496','002496','辉丰股份'),('002513','002513','蓝丰生化'),('002734','002734','利民股份'),('002749','002749','国光股份'),('002942','002942','新农股份'),('003042','003042','中农联合'),('300261','300261','雅本化学'),('300575','300575','中旗股份'),('300796','300796','贝斯美'),('300804','300804','广康生化'),('301035','301035','润丰股份'),('301665','301665','泰禾股份'),('600389','600389','江山股份'),('600486','600486','扬农化工'),('600500','600500','中化国际'),('600532','600532','华阳科技'),('600538','600538','国发股份'),('600596','600596','新安股份'),('600731','600731','湖南海利'),('600796','600796','钱江生化'),('600803','600803','新奥股份'),('600882','600882','大成股份'),('603086','603086','先达股份'),('603360','603360','百傲化学'),('603585','603585','苏利股份'),('603599','603599','广信股份'),('603639','603639','海利尔'),('603810','603810','丰山集团'),('603970','603970','中农立华'),('605033','605033','美邦股份'),('870866','LVHENG_TECH','绿亨科技'),('920866','LVHENG_TECH','绿亨科技'),('833819','YINGTAI_BIO','颖泰生物'),('920819','YINGTAI_BIO','颖泰生物')]
CANON={'LVHENG_TECH':'920866','YINGTAI_BIO':'920819'}
for c,i,n in IDENTIFIERS: CANON.setdefault(i,c)


def build_sws():
    headers={'User-Agent':'Mozilla/5.0'}
    r=requests.get(SWS_URL,headers=headers,timeout=90,verify=False)
    r.raise_for_status()
    if len(r.content)<100000: raise RuntimeError(f'SWS file too small: {len(r.content)}')
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
    if not {'security_code','start_date','industry_code'}.issubset(x.columns):
        raise RuntimeError('SWS columns: '+repr(list(x.columns)))
    x['security_code']=x.security_code.astype(str).str.extract(r'(\d{6})',expand=False).fillna('')
    x['industry_code']=x.industry_code.astype(str).str.replace(r'\.0$','',regex=True).str.strip()
    x['start_date']=pd.to_datetime(x.start_date,errors='coerce')
    x=x[x.security_code.ne('') & x.start_date.notna()].sort_values(['security_code','start_date'])
    x['end_date']=x.groupby('security_code').start_date.shift(-1)
    pest=x[x.industry_code.isin({'220303','220803'})].copy()
    idmap=pd.DataFrame(IDENTIFIERS,columns=['security_code','issuer_key','seed_name'])
    pest=pest.merge(idmap[['security_code','issuer_key']],on='security_code',how='left')
    pest['issuer_key']=pest.issuer_key.fillna(pest.security_code)
    pest['canonical_code']=pest.issuer_key.map(CANON).fillna(pest.security_code)
    pest.to_csv(OUT/'sw_pesticide_intervals.csv',index=False,encoding='utf-8-sig')
    issu=pest.groupby('issuer_key').agg(canonical_code=('canonical_code','last'),first_start=('start_date','min'),last_end=('end_date','max'),security_codes=('security_code',lambda s:'|'.join(sorted(set(s))))).reset_index()
    issu.to_csv(OUT/'sw_pesticide_issuers.csv',index=False,encoding='utf-8-sig')
    return {'raw_rows':len(x),'pesticide_rows':len(pest),'issuers':issu.issuer_key.nunique(),'security_codes':pest.security_code.nunique(),'file_bytes':len(r.content)}


def market_code(code):
    if code.startswith('6'): return 'sh.'+code
    if code.startswith(('0','3')): return 'sz.'+code
    return ''


def fetch_prices_baostock():
    import baostock as bs
    lg=bs.login()
    if lg.error_code!='0': raise RuntimeError('baostock login '+lg.error_msg)
    rows=[]; fails=[]
    fields='date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,isST'
    try:
        for code,issuer,name in IDENTIFIERS:
            mc=market_code(code)
            if not mc:
                fails.append((issuer,CANON[issuer],code,'UNSUPPORTED_MARKET_BY_BAOSTOCK')); continue
            try:
                rs=bs.query_history_k_data_plus(mc,fields,start_date=START,end_date=END,frequency='d',adjustflag='2')
                if rs.error_code!='0':
                    fails.append((issuer,CANON[issuer],code,'BAOSTOCK:'+rs.error_msg)); continue
                data=[]
                while rs.next(): data.append(rs.get_row_data())
                if not data:
                    fails.append((issuer,CANON[issuer],code,'EMPTY')); continue
                d=pd.DataFrame(data,columns=fields.split(','))
                d=d.rename(columns={'date':'trade_date','turn':'turnover','pctChg':'pct_change'})
                for c in ['open','high','low','close','preclose','volume','amount','turnover','pct_change']:
                    d[c]=pd.to_numeric(d[c],errors='coerce')
                d['security_code']=code; d['issuer_key']=issuer; d['code']=CANON[issuer]; d['name']=name
                rows.append(d[['trade_date','code','issuer_key','security_code','name','open','high','low','close','preclose','volume','amount','pct_change','turnover','tradestatus','isST']])
            except Exception as e:
                fails.append((issuer,CANON[issuer],code,f'{type(e).__name__}:{e}'))
            time.sleep(.03)
    finally:
        bs.logout()
    if rows:
        x=pd.concat(rows,ignore_index=True); x['trade_date']=pd.to_datetime(x.trade_date,errors='coerce'); x=x.dropna(subset=['trade_date','close'])
        x['is_canon']=(x.security_code.astype(str)==x.code.astype(str)).astype(int)
        x=x.sort_values(['issuer_key','trade_date','is_canon','security_code']).drop_duplicates(['issuer_key','trade_date'],keep='last').drop(columns='is_canon')
        x.to_csv(OUT/'prices_daily.csv.gz',index=False,encoding='utf-8-sig',compression='gzip')
        pd.DataFrame({'trade_date':sorted(x.trade_date.dt.strftime('%Y-%m-%d').unique())}).to_csv(OUT/'trading_calendar.csv',index=False)
    else: x=pd.DataFrame()
    pd.DataFrame(fails,columns=['issuer_key','code','security_code','reason']).to_csv(OUT/'price_failures.csv',index=False,encoding='utf-8-sig')
    return {'raw_rows':sum(len(d) for d in rows),'consolidated_rows':len(x),'successful_identifiers':len(rows),'fail_identifiers':len(fails),'min_date':x.trade_date.min().strftime('%Y-%m-%d') if len(x) else None,'max_date':x.trade_date.max().strftime('%Y-%m-%d') if len(x) else None}


def main():
    s={'started_at':datetime.now().isoformat()}
    for name,fn in [('sws',build_sws),('prices',fetch_prices_baostock)]:
        try: s[name]=fn()
        except Exception as e: s[name]={'error':f'{type(e).__name__}:{e}'}
    s['finished_at']=datetime.now().isoformat()
    (OUT/'build_summary.json').write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(s,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
