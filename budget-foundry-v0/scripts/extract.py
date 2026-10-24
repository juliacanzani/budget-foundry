import cv2, numpy as np, json, base64, importlib, sys, io, contextlib
from skimage.morphology import skeletonize
allg=[]
for mod in ['label_A','label_B','label_C','label_D']:
    with contextlib.redirect_stdout(io.StringIO()):
        m=importlib.import_module(mod)
    allg+=m.res
print('total',len(allg))
C=json.load(open('comps.json'))
sheet_sw={k:float(np.median([c['sw'] for c in C[k] if c['sw']>(12 if k in 'CD' else 0)])) for k in 'ABCD'}
print(sheet_sw)
DESC=set('gjpqy,;()[]{}_|Q')
labs={k:np.load(f'{k}_lab.npy') for k in 'ABCD'}
inks={k:cv2.imread(f'{k}_ink.png',0) for k in 'ABCD'}
dists={k:cv2.distanceTransform(inks[k],cv2.DIST_L2,5) for k in 'ABCD'}
# row baselines: linear fit of bottoms of non-descender glyphs (letters/digits only)
rows={}
for g in allg: rows.setdefault(g['row'],[]).append(g)
XH=float(np.median([g['h']/sheet_sw[g['sheet']] for g in allg if g['sheet']=='A' and g['ch'] in 'acemnorsuvwxz']))
print('x-height sw',XH)
for rk,gs in rows.items():
    if all(g['ch']=='q' for g in gs):
        b=float(np.median([g['y'] for g in gs]))+XH*sheet_sw[gs[0]['sheet']]
        for g in gs: g['base']=b
        continue
    pts=[(g['x']+g['w']/2,g['y']+g['h']) for g in gs if g['ch'].isalnum() and g['ch'] not in DESC]
    if len(pts)>=3:
        xs,ys=np.array(pts).T; p=np.polyfit(xs,ys,1)
        for _ in range(2):
            r=ys-np.polyval(p,xs); keep=np.abs(r)<max(2*np.std(r),5)
            if keep.sum()>=3: p=np.polyfit(xs[keep],ys[keep],1)
        base=lambda x,p=p: float(np.polyval(p,x))
    else:
        b=float(np.median([g['y']+g['h'] for g in gs])); base=lambda x,b=b:b
    for g in gs: g['base']=base(g['x']+g['w']/2)
PX=13  # display px per stroke-width unit
TOP,BOT=10.5,5.0  # frame above/below baseline in sw units
out=[]
for n,g in enumerate(allg):
    k=g['sheet']; sw=sheet_sw[k]
    lab=labs[k]; x,y,w,h=g['x'],g['y'],g['w'],g['h']
    m=np.isin(lab[y:y+h,x:x+w],g['ids'])
    sk=skeletonize(m); d=dists[k][y:y+h,x:x+w][sk]
    gsw=float(np.median(d)*2) if d.size else sw
    ys_,xs_=np.nonzero(m); xs_=xs_-xs_.mean(); ys_=ys_-ys_.mean()
    slant=float(np.degrees(np.arctan2(-(xs_*ys_).mean(),(ys_*ys_).mean()))) if h>w*0.8 else None
    # frame relative to baseline
    s=PX/sw
    fy0=int(round(g['base']-TOP*sw)); fy1=int(round(g['base']+BOT*sw))
    pad=int(0.4*sw)
    fx0=x-pad; fx1=x+w+pad
    H,W=lab.shape
    canvas=np.zeros((fy1-fy0,fx1-fx0),np.uint8)
    sy0,sy1=max(fy0,0),min(fy1,H); sx0,sx1=max(fx0,0),min(fx1,W)
    sub=np.isin(lab[sy0:sy1,sx0:sx1],g['ids'])
    canvas[sy0-fy0:sy1-fy0,sx0-fx0:sx1-fx0]=sub*255
    small=cv2.resize(canvas,(max(1,int(canvas.shape[1]*s)),int(canvas.shape[0]*s)),interpolation=cv2.INTER_AREA)
    rgba=np.zeros(small.shape+(4,),np.uint8); rgba[...,3]=small
    ok,buf=cv2.imencode('.png',rgba,[cv2.IMWRITE_PNG_COMPRESSION,9])
    out.append(dict(id=f"{k}{n:04d}",ch=g['ch'],sheet=k,
        h=round(h/sw,2),w=round(w/sw,2),wt=round(gsw/sw,3),
        top=round((g['base']-y)/sw,2),bot=round((y+h-g['base'])/sw,2),
        slant=None if slant is None else round(slant,1),
        img=base64.b64encode(buf).decode()))
json.dump(out,open('cands.json','w'))
meta={f"{g['sheet']}{n:04d}":dict(sheet=g['sheet'],ids=g['ids'],x=g['x'],y=g['y'],w=g['w'],h=g['h'],base=g['base'],ch=g['ch'],row=g['row']) for n,g in enumerate(allg)}
json.dump(dict(meta=meta,sw=sheet_sw,XH=XH),open('meta.json','w'))
print(len(out), sum(len(o['img']) for o in out)/1e6,'MB')
