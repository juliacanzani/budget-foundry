import json, numpy as np, math
c=json.load(open('cands.json'))
by={}
for g in c: by.setdefault(g['ch'],[]).append(g)
FREQ=set('eaonsti') ; PUN2=set('[]{}|_#@×÷…;“”«»%*\\/')
for ch,gs in by.items():
    mh=np.median([g['h'] for g in gs]); mb=np.median([g['bot'] for g in gs])
    sl=[g['slant'] for g in gs if g['slant'] is not None]; ms=np.median(sl) if sl else None
    for g in gs:
        size=g['h']/mh; rw=g['wt']/size
        flags=[]
        if size<0.82: flags.append('small')
        if size>1.2: flags.append('large')
        if rw>1.35: flags.append('heavy')
        if rw<0.75: flags.append('light')
        sd=None
        if ms is not None and g['slant'] is not None:
            sd=g['slant']-ms
            if abs(sd)>12: flags.append(f"slant {'+' if sd>0 else '−'}{abs(sd):.0f}°")
        bd=g['bot']-mb
        if abs(bd)>1.2 and ch.isalnum(): flags.append('drops' if bd>0 else 'floats')
        score=abs(math.log(size))*2+abs(math.log(rw))*2+(abs(sd)/15 if sd is not None else 0)+abs(bd)/3
        g.update(size=round(size,2),rw=round(rw,2),flags=flags,score=round(score,3))
    n=4 if ch in FREQ else (2 if ch in PUN2 else 3)
    for g in sorted(gs,key=lambda g:g['score'])[:n]: g['pick']=True
order="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,:;…!?'\"“”-–—_()[]{}<>«»/\\|+=×÷%*#@&~"
chars=[ch for ch in order if ch in by]+[ch for ch in by if ch not in order]
assert len(chars)==len(by)
for ch in by: by[ch].sort(key=lambda g:g['id'])
data=[dict(ch=ch,cands=by[ch]) for ch in chars]
json.dump(data,open('data.json','w'),ensure_ascii=False,separators=(',',':'))
print(len(chars),'chars'); print({ch:len(by[ch]) for ch in chars})
print('flagged',sum(1 for g in c if g['flags']),'picked',sum(1 for g in c if g.get('pick')))
