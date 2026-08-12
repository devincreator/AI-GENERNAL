#!/usr/bin/env python3
import argparse, csv, heapq, json, math, os, struct, urllib.request, zipfile
from bisect import bisect_left
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

TDX_URLS = [
    'https://data.tdx.com.cn/vipdoc/hsjday.zip',
    'https://www.tdx.com.cn/products/data/data/vipdoc/hsjday.zip',
]
UPSTREAM_URLS = [
    'https://a-share-top-monitor.netlify.app/data/dashboard.json',
    'https://6a72ef4b5ab7ceed7c6b46fc--a-share-top-monitor.netlify.app/data/dashboard.json',
]
START_DATE = date(2011, 8, 2)
MODEL_START = date(2014, 11, 14)
RECORD_SIZE = 32
FORMAT = '<IIIIIfII'


def parse_date(s):
    return datetime.strptime(str(s)[:10], '%Y-%m-%d').date()


def get_json(urls):
    last = None
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode('utf-8-sig')), url
        except Exception as e:
            last = e
    raise RuntimeError(f'upstream dashboard unavailable: {last}')


def download(urls, dest):
    last = None
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=180) as r, open(dest,'wb') as f:
                while True:
                    b=r.read(8*1024*1024)
                    if not b: break
                    f.write(b)
            if os.path.getsize(dest) < 100_000_000:
                raise RuntimeError('archive unexpectedly small')
            return url
        except Exception as e:
            last=e
            try: os.remove(dest)
            except OSError: pass
    raise RuntimeError(f'TDX download failed: {last}')


def stock_code(member):
    name=member.replace('\\','/').split('/')[-1].lower()
    if not name.endswith('.day'): return None
    base=name[:-4]
    if len(base)!=8 or base[:2] not in {'sh','sz'} or not base[2:].isdigit(): return None
    market, code=base[:2], base[2:]
    if market=='sh' and code.startswith('6'): return code+'.SH'
    if market=='sz' and (code.startswith('00') or code.startswith('30')): return code+'.SZ'
    return None


INDEX_MEMBERS = {
    'sh000985.day': 'all_a_close',
    'sh000300.day': 'hs300_close',
    'sh000852.day': 'zz1000_close',
}

def indices_from_tdx(zip_path):
    series={v:{} for v in INDEX_MEMBERS.values()}
    found={}
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            base=member.replace('\\','/').split('/')[-1].lower()
            col=INDEX_MEMBERS.get(base)
            if not col:
                continue
            found[col]=member
            raw=zf.read(member)
            usable=len(raw)-len(raw)%RECORD_SIZE
            for off in range(0,usable,RECORD_SIZE):
                di,op,hi,lo,cl,amount,vol,res=struct.unpack_from(FORMAT,raw,off)
                if di < 20110802 or di > 21000101 or cl <= 0:
                    continue
                d=datetime.strptime(str(di),'%Y%m%d').date()
                series[col][d]=cl/100.0
    missing=[col for col in INDEX_MEMBERS.values() if col not in found]
    if missing:
        raise RuntimeError(f'TDX index files missing: {missing}; found={found}')
    common=sorted(set(series['all_a_close']) & set(series['hs300_close']) & set(series['zz1000_close']))
    return [
        {'date':d,'all_a_close':series['all_a_close'][d],
         'hs300_close':series['hs300_close'][d],
         'zz1000_close':series['zz1000_close'][d]}
        for d in common
    ]

def write_indices_csv(rows,path):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    fields=['date','all_a_close','hs300_close','zz1000_close']
    with open(path,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for r in rows:
            x=dict(r); x['date']=r['date'].isoformat(); w.writerow(x)

def concentration_from_tdx(zip_path):
    total={}; count={}; positive={}; heaps={}
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            code=stock_code(member)
            if not code: continue
            raw=zf.read(member)
            usable=len(raw)-len(raw)%RECORD_SIZE
            for off in range(0,usable,RECORD_SIZE):
                di,op,hi,lo,cl,amount,vol,res=struct.unpack_from(FORMAT,raw,off)
                if di < 20110802 or di > 21000101 or not math.isfinite(amount) or amount < 0: continue
                d=datetime.strptime(str(di),'%Y%m%d').date()
                total[d]=total.get(d,0.0)+float(amount)
                count[d]=count.get(d,0)+1
                if amount>0: positive[d]=positive.get(d,0)+1
                h=heaps.setdefault(d,[])
                item=(float(amount), code)
                if len(h)<50: heapq.heappush(h,item)
                elif item>h[0]: heapq.heapreplace(h,item)
    rows=[]
    for d in sorted(total):
        top=sum(v for v,_ in heaps[d])
        rows.append({'date':d,'total_amount_yuan':total[d],'eligible_stock_count':count[d],
                     'positive_amount_stock_count':positive.get(d,0),'top50_amount_yuan':top,
                     'top50_stock_count':len(heaps[d]),'top50_share':top/total[d] if total[d] else None,
                     'top50_share_pct':top/total[d]*100 if total[d] else None})
    return rows


def read_concentration_csv(path):
    rows=[]
    with open(path,encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            rows.append({'date':parse_date(r['date']), 'total_amount_yuan':float(r['total_amount_yuan']),
                         'eligible_stock_count':int(float(r['eligible_stock_count'])),
                         'positive_amount_stock_count':int(float(r['positive_amount_stock_count'])),
                         'top50_amount_yuan':float(r['top50_amount_yuan']),
                         'top50_stock_count':int(float(r['top50_stock_count'])),
                         'top50_share':float(r['top50_share']), 'top50_share_pct':float(r['top50_share_pct'])})
    return rows


def write_concentration_csv(rows,path):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    fields=['date','total_amount_yuan','eligible_stock_count','positive_amount_stock_count','top50_amount_yuan','top50_stock_count','top50_share','top50_share_pct']
    with open(path,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for r in rows:
            x=dict(r); x['date']=r['date'].isoformat(); w.writerow(x)


def percentile(history, x):
    vals=[v for v in history if v is not None and math.isfinite(v)]
    if not vals or x is None or not math.isfinite(x): return None
    return sum(v<=x for v in vals)/len(vals)


def add_features(rows):
    share=[r['top50_share'] for r in rows]
    d20=[None]*len(rows); d40=[None]*len(rows); p20=[None]*len(rows); p40=[None]*len(rows)
    for i in range(len(rows)):
        if i>=20: d20[i]=share[i]-share[i-20]
        if i>=40: d40[i]=share[i]-share[i-40]
        if d20[i] is not None: p20[i]=percentile(d20[max(0,i-504):i],d20[i])
        if d40[i] is not None: p40[i]=percentile(d40[max(0,i-252):i],d40[i])
        rows[i].update({'d20':d20[i],'d40':d40[i],'p20_504':p20[i],'p40_252':p40[i]})
    return rows


def next_index(dates,d):
    return bisect_left(dates,d)


def overlay_indices(rows, end_date, threshold=.90, confirm_days=3, cooldown=45):
    dates=[r['date'] for r in rows]; start=next_index(dates,MODEL_START); end=max(i for i,d in enumerate(dates) if d<=end_date)
    streak=0; last=-10**9; out=[]
    for i in range(start,end+1):
        ok=rows[i]['p20_504'] is not None and rows[i]['p20_504']>=threshold
        streak=streak+1 if ok else 0
        if streak>=confirm_days and i-last>=cooldown:
            out.append(i); last=i
    return out


def gate_indices(rows, base_signals, threshold=.50, wait_days=10):
    dates=[r['date'] for r in rows]; out=[]; audit=[]
    for sig in base_signals:
        raw=parse_date(sig['signal_date']); si=next_index(dates,raw)
        if si>=len(dates): continue
        conf=None
        for j in range(si,min(si+wait_days,len(rows))):
            p=rows[j]['p40_252']
            if p is not None and p>=threshold:
                conf=j; break
        if conf is not None: out.append(conf)
        audit.append({'base_signal_date':raw.isoformat(),'path':sig.get('path'),'status':'confirmed' if conf is not None else 'filtered',
                      'confirmation_date':rows[conf]['date'].isoformat() if conf is not None else None,
                      'confirmation_percentile':rows[conf]['p40_252'] if conf is not None else None,
                      'wait_days':(conf-si) if conf is not None else None})
    return out,audit


def evaluate(rows, signal_indices, tops, asof):
    dates=[r['date'] for r in rows]; top_dates=[parse_date(t['top_date']) for t in tops]
    top_idx=[next_index(dates,d) for d in top_dates]; asof_idx=max(i for i,d in enumerate(dates) if d<=asof)
    hits=mature=0; covered=set(); leads=[]; details=[]
    for si in signal_indices:
        matches=[(k,ti) for k,ti in enumerate(top_idx) if si<=ti<=si+63]
        if matches:
            hits+=1; mature+=1; leads.append(matches[0][1]-si)
            for k,ti in matches: covered.add(k)
            k,ti=matches[0]
            details.append({'signal_date':dates[si].isoformat(),'status':'命中','matched_top':top_dates[k].isoformat(),'lead_trading_days':ti-si})
        elif si+63<=asof_idx:
            mature+=1; details.append({'signal_date':dates[si].isoformat(),'status':'误报','matched_top':None,'lead_trading_days':None})
    p=hits/mature if mature else None; r=len(covered)/len(tops) if tops else None
    f1=2*p*r/(p+r) if p is not None and r is not None and p+r else None
    return {'signals':mature,'hits':hits,'precision':p,'tops':len(tops),'covered':len(covered),'recall':r,'f1':f1,
            'median_lead_trading_days':sorted(leads)[len(leads)//2] if leads else None,'signal_details':details}


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--site-dir',default='site'); ap.add_argument('--skip-tdx-download',action='store_true'); args=ap.parse_args()
    site=Path(args.site_dir); site.mkdir(parents=True,exist_ok=True); (site/'data').mkdir(parents=True,exist_ok=True)
    upstream=os.environ.get('UPSTREAM_DASHBOARD_URL')
    urls=[upstream] if upstream else UPSTREAM_URLS
    try:
        base,source=get_json(urls)
    except Exception:
        fallback=site/'data/base-dashboard.json'
        if not fallback.exists(): fallback=site/'data/dashboard.json'
        base=json.load(open(fallback,encoding='utf-8-sig')); source='local file'
    if args.skip_tdx_download:
        rows=read_concentration_csv(site/'data/concentration.csv'); tdx_source='cached concentration.csv'
    else:
        z=site.parent/'hsjday.zip'; tdx_source=download(TDX_URLS,z); rows=concentration_from_tdx(z); write_concentration_csv(rows,site/'data/concentration.csv'); index_rows=indices_from_tdx(z); write_indices_csv(index_rows,site/'data/tdx_indices.csv')
    rows=add_features(rows)
    asof=parse_date(base['meta']['data_asof'])
    tops=base['backtest']['tops']; mature_base=base['backtest']['signals']
    gate,audit=gate_indices(rows,mature_base); overlay=overlay_indices(rows,asof)
    union=sorted(set(gate)|set(overlay)); summary=evaluate(rows,union,tops,asof); gate_eval=evaluate(rows,gate,tops,asof); overlay_eval=evaluate(rows,overlay,tops,asof)
    dates=[r['date'] for r in rows]; latest=len(rows)-1
    last_base=base.get('backtest',{}).get('pending_signals',[])
    last_base=(last_base[-1:] or mature_base[-1:])[0]
    _,cur_audit=gate_indices(rows,[last_base])
    oa=overlay_indices(rows,rows[-1]['date']); last_overlay=dates[oa[-1]].isoformat() if oa else None
    streak=0
    for r in reversed(rows):
        if r['p20_504'] is not None and r['p20_504']>=.9: streak+=1
        else: break
    hist=[{'date':r['date'].isoformat(),'top50_share':r['top50_share'],'p20_504':r['p20_504'],'p40_252':r['p40_252']} for r in rows if r['date']>=date(2023,1,1)]
    base['meta']['generated_at_enhanced']=datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')
    base['meta']['upstream_dashboard']=source; base['meta']['enhancement_source']=tdx_source
    base['enhancement']={'version':'C50-gate50-overlay90-v1','data_source':'TDX official hsjday.zip','concentration_data_asof':rows[-1]['date'].isoformat(),
      'rules':{'concentration':'C50=当日沪深普通A股成交额前50只合计/普通A股总成交额','gate':'B/C预警后最多10个A股交易日；40日C50升幅在过去252日分位≥50%时确认，否则过滤','overlay':'20日C50升幅在过去504日分位≥90%，连续3个交易日；补充信号冷却45个交易日','combination':'确认后的B/C信号 ∪ 20日集中度补充信号'},
      'current':{'concentration':{'date':dates[latest].isoformat(),'top50_share':rows[latest]['top50_share'],'top50_share_pct':rows[latest]['top50_share_pct'],'d20_change':rows[latest]['d20'],'d20_change_pp':rows[latest]['d20']*100 if rows[latest]['d20'] is not None else None,'p20_504':rows[latest]['p20_504'],'d40_change':rows[latest]['d40'],'d40_change_pp':rows[latest]['d40']*100 if rows[latest]['d40'] is not None else None,'p40_252':rows[latest]['p40_252']},
                 'gate':cur_audit[0] if cur_audit else None,'overlay':{'threshold':.9,'confirm_days':3,'current_streak':streak,'triggered_now':bool(oa and oa[-1]==latest),'latest_signal_date':last_overlay}},
      'backtest':{'verified_for':base['meta'].get('model_version'),'period':{'start':MODEL_START.isoformat(),'mature_negative_end':base['backtest']['period']['mature_negative_end'],'data_end':asof.isoformat()},'summary':summary,'gate_only':gate_eval,'overlay_only':overlay_eval,'gate_audit':audit,'note':'按当前网页B/C版本重新回测；与此前31次基线版本的80.5%/88.2%不可直接混用。'},'history':hist}
    json.dump(base,open(site/'data/dashboard.json','w',encoding='utf-8'),ensure_ascii=False,separators=(',',':'))

if __name__=='__main__': main()
