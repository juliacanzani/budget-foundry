import cv2, numpy as np, json
C=json.load(open('comps.json'))
thin={'A':0,'B':0,'C':12,'D':10}
mina={'A':400,'B':400,'C':350,'D':250}
def glyphs(k,bands,xr=(0,99999)):
    cs=[dict(c) for c in C[k] if c['sw']>=thin[k] and c['a']>=mina[k] and xr[0]<=c['x']+c['w']/2<xr[1]]
    rows=[[] for _ in bands[:-1]]
    for c in cs:
        cy=c['y']+c['h']/2
        for i in range(len(bands)-1):
            if bands[i]<=cy<bands[i+1]: rows[i].append(c)
    out=[]
    for r in rows:
        r.sort(key=lambda c:c['x'])
        groups=[]
        for c in r:
            merged=False
            for g in groups[-3:]:
                x0=max(g['x'],c['x']); x1=min(g['x']+g['w'],c['x']+c['w'])
                if x1-x0>0.5*min(g['w'],c['w']):
                    nx=min(g['x'],c['x']); ny=min(g['y'],c['y'])
                    g['w']=max(g['x']+g['w'],c['x']+c['w'])-nx; g['h']=max(g['y']+g['h'],c['y']+c['h'])-ny
                    g['x'],g['y']=nx,ny; g['ids'].append(c['id']); merged=True; break
            if not merged:
                groups.append(dict(x=c['x'],y=c['y'],w=c['w'],h=c['h'],ids=[c['id']]))
        groups.sort(key=lambda g:g['x'])
        out.append(groups)
    return out
def apply(k,bands,specs,xr=(0,99999)):
    rows=glyphs(k,bands,xr); res=[]; ok=True
    for ri,(r,spec) in enumerate(zip(rows,specs)):
        spec=[t if len(t)==3 else (t[0],t[1],1) for t in spec]
        n=sum(c*m for _,c,m in spec)
        if n!=len(r):
            ok=False; print(f'{k} row{ri}: spec {n} vs found {len(r)}: x=',[g['x'] for g in r])
            continue
        i=0
        for ch,cnt,m in spec:
            for _ in range(cnt):
                if ch=='SKIP': i+=m; continue
                parts=r[i:i+m]; i+=m
                x0=min(p['x'] for p in parts); y0=min(p['y'] for p in parts)
                g=dict(x=x0,y=y0,w=max(p['x']+p['w'] for p in parts)-x0,h=max(p['y']+p['h'] for p in parts)-y0,
                       ids=sum([p['ids'] for p in parts],[]),ch=ch,sheet=k,row=f'{k}{xr[0]}-{bands[ri]}')
                res.append(g)
    return res,ok
def strips(k,bands,rowsel,fname,xr=(0,99999)):
    rows=glyphs(k,bands,xr); ink=255-cv2.imread(f'{k}_ink.png',0)
    outs=[]
    for ri in rowsel:
        r=rows[ri]
        if not r: continue
        y0=max(0,min(g['y'] for g in r)-60); y1=max(g['y']+g['h'] for g in r)+10
        x1=max(g['x']+g['w'] for g in r)+20
        s=cv2.cvtColor(ink[y0:y1,:],cv2.COLOR_GRAY2BGR).copy()
        for j,g in enumerate(r):
            cv2.rectangle(s,(g['x'],g['y']-y0),(g['x']+g['w'],g['y']+g['h']-y0),(0,0,255),3)
            cv2.putText(s,str(j),(g['x'],50),cv2.FONT_HERSHEY_SIMPLEX,1.6,(255,0,0),4)
        cv2.putText(s,f'R{ri}',(10,50),cv2.FONT_HERSHEY_SIMPLEX,1.6,(0,128,0),4)
        outs.append(s)
    W=max(o.shape[1] for o in outs)
    img=np.vstack([cv2.copyMakeBorder(o,0,8,0,W-o.shape[1],cv2.BORDER_CONSTANT,value=(200,200,200)) for o in outs])
    sc=1900/img.shape[1]; img=cv2.resize(img,None,fx=sc,fy=sc,interpolation=cv2.INTER_AREA)
    cv2.imwrite(fname,img)
