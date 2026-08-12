#!/usr/bin/env python3
import csv, json, urllib.parse, urllib.request, time
from pathlib import Path

SERIES = {
    'all_a_close': 'sh000985',
    'hs300_close': 'sh000300',
    'zz1000_close': 'sh000852',
}

def request_json(url, headers=None, retries=3):
    last=None
    for n in range(retries):
        try:
            req=urllib.request.Request(url,headers=headers or {'User-Agent':'Mozilla/5.0'})
            with urllib.request.urlopen(req,timeout=30) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as e:
            last=e; time.sleep(1+n)
    raise last

def get_tencent(code, beg='2026-07-20', end='2026-08-12'):
    param=f'{code},day,{beg},{end},40'
    url='https://web.ifzq.gtimg.cn/appstock/app/kline/kline?'+urllib.parse.urlencode({'param':param})
    payload=request_json(url, {'User-Agent':'Mozilla/5.0','Referer':'https://gu.qq.com/'})
    node=((payload or {}).get('data') or {}).get(code) or {}
    arr=node.get('day') or node.get('qfqday') or node.get('hfqday') or []
    out={}
    for row in arr:
        if len(row)>=3: out[row[0]]=float(row[2])
    if not out: raise RuntimeError(f'Tencent no data for {code}: {str(payload)[:500]}')
    return out

def get_eastmoney(code, beg='20260720', end='20260812'):
    secid='1.'+code[2:]
    qs=urllib.parse.urlencode({'secid':secid,'klt':'101','fqt':'0','beg':beg,'end':end,'fields1':'f1,f2,f3,f4,f5,f6','fields2':'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61'})
    payload=request_json('https://push2his.eastmoney.com/api/qt/stock/kline/get?'+qs, {'User-Agent':'Mozilla/5.0','Referer':'https://quote.eastmoney.com/'})
    out={}
    for line in ((payload or {}).get('data') or {}).get('klines') or []:
        p=line.split(','); out[p[0]]=float(p[2])
    if not out: raise RuntimeError(f'Eastmoney no data for {code}')
    return out

def get_series(code):
    errors=[]
    for fn in (get_tencent,get_eastmoney):
        try: return fn(code),fn.__name__
        except Exception as e: errors.append(f'{fn.__name__}: {e}')
    raise RuntimeError('; '.join(errors))

def main():
    series={}; sources={}
    for k,code in SERIES.items():
        series[k],sources[k]=get_series(code)
    dates=sorted(set.intersection(*(set(x) for x in series.values())))
    rows=[{'date':d,**{k:series[k][d] for k in SERIES}} for d in dates]
    if not rows or rows[-1]['date']<'2026-08-12': raise RuntimeError(f'latest row missing: {rows[-1:]}; sources={sources}')
    out=Path('site/data/latest_indices.csv'); out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['date','all_a_close','hs300_close','zz1000_close']); w.writeheader(); w.writerows(rows)
    print('sources:',sources)
    print('latest index rows:',len(rows),rows[-10:])

if __name__=='__main__': main()
