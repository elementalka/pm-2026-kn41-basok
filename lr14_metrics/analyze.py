"""Recalculate course metrics using only published CSV data."""
import csv, math
from pathlib import Path
from datetime import date
P=Path(__file__).resolve().parent
def load(name):
    with (P/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def quantile(values,p):return sorted(values)[math.ceil(p*len(values))-1]
if __name__=='__main__':
    rows=load('flow.csv')
    ct=[(date.fromisoformat(r['done_date'])-date.fromisoformat(r['start_date'])).days for r in rows]
    lt=[(date.fromisoformat(r['done_date'])-date.fromisoformat(r['created_date'])).days for r in rows]
    ends=[date.fromisoformat(r['done_date']) for r in rows]
    weeks=math.ceil(((max(ends)-min(ends)).days+1)/7)
    print({'N':len(rows),'weeks':weeks,'throughput':round(len(rows)/weeks,1),'cycle_P50':quantile(ct,.5),'cycle_P85':quantile(ct,.85),'lead_P85':quantile(lt,.85),'queue':quantile(lt,.85)-quantile(ct,.85),'cycle_sorted':sorted(ct)})
    for r in load('lr14_reference_cfd.csv'):
        print('week',r['week'],'WIP',int(r['started_cum'])-int(r['done_cum']),'queue',int(r['created_cum'])-int(r['started_cum']))

    source=P.parent/'lr04_kanban/flow_timestamps.csv'
    if source.exists():
        with source.open(encoding='utf-8',newline='') as f: timed=list(csv.DictReader(f))
        seconds=[int(r['elapsed_seconds']) for r in timed if r['elapsed_seconds']!='']
        print('Supplemental status intervals; not full work duration:',{'coverage':str(len(seconds))+'/'+str(len(timed)),'unit':'seconds','min':min(seconds),'max':max(seconds),'mean':round(sum(seconds)/len(seconds),2),'P50':quantile(seconds,.5),'P85':quantile(seconds,.85)})
