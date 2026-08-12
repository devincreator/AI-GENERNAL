#!/usr/bin/env python3
import csv, json, urllib.parse, urllib.request
from pathlib import Path

SERIES = {
    'all_a_close': '1.000985',
    'hs300_close': '1.000300',
    'zz1000_close': '1.000852',
}
BASE='https://push2his.eastmoney.com/api/qt/stock/kline/get'

def get_series(secid, beg='20260720', end='20260812'):
    qs=urllib.parse.urlencode({
        'secid':secid,'klt':'101','fqt':'0','beg':beg,'end':end,
        'fields1':'f1,f2,f3,f4,f5,f6',
        'fields2':'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
    })
    req=urllib.request.Request(BASE+'?'+qs, headers={'User-Agent':'Mozilla/5.0','Referer':'https://quote.eastmoney.com/'})
    with urllib.request.urlopen(req,timeout=30) as r:
        payload=json.loads(r.read().decode('utf-8'))
    data=(payload or {}).get('data') or {}
    out={}
    for line in data.get('klines') or []:
        p=line.split(',')
        out[p[0]]=float(p[2])
    if not out:
        raise RuntimeError(f'no klines for {secid}: {payload}')
    return out

def main():
    series={k:get_series(v) for k,v in SERIES.items()}
    dates=sorted(set.intersection(*(set(x) for x in series.values())))
    rows=[]
    for d in dates:
        rows.append({'date':d,**{k:series[k][d] for k in SERIES}})
    out=Path('site/data/latest_indices.csv'); out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['date','all_a_close','hs300_close','zz1000_close']); w.writeheader(); w.writerows(rows)
    print('latest index rows:', len(rows), rows[-10:])

if __name__=='__main__': main()
