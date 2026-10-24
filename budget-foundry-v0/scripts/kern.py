import numpy as np, json
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
from PIL import Image, ImageDraw, ImageChops
import cv2
tt=TTFont('JuliaMarker-Regular.otf'); gs=tt.getGlyphSet(); go=tt.getGlyphOrder(); hm=tt['hmtx'].metrics
U=110; SC=0.25; Y0=-400; Y1=1100; H=int((Y1-Y0)*SC)
class Poly(BasePen):
    def __init__(s,g): super().__init__(g); s.polys=[]; s.cur=[]
    def _moveTo(s,p): s.cur=[p]
    def _lineTo(s,p): s.cur.append(p)
    def _curveToOne(s,a,b,c):
        p0=s.cur[-1]
        for t in np.linspace(0.1,1,10):
            mt=1-t; s.cur.append((mt**3*p0[0]+3*mt*mt*t*a[0]+3*mt*t*t*b[0]+t**3*c[0],mt**3*p0[1]+3*mt*mt*t*a[1]+3*mt*t*t*b[1]+t**3*c[1]))
    def _closePath(s): s.polys.append(s.cur); s.cur=[]
VB=int(0.3*U*SC)  # vertical blur radius px
def profile(name):
    p=Poly(gs); gs[name].draw(p); W=int((hm[name][0]+800)*SC)
    m=Image.new('1',(W,H),0)
    for poly in p.polys:
        t=Image.new('1',(W,H),0); ImageDraw.Draw(t).polygon([((x+400)*SC,(Y1-y)*SC) for x,y in poly],fill=1); m=ImageChops.logical_xor(m,t)
    a=np.array(m).astype(np.uint8)
    a=cv2.dilate(a,np.ones((2*VB+1,1),np.uint8))
    L=np.full(H,np.nan); R=np.full(H,np.nan)
    for y in range(H):
        xs=np.nonzero(a[y])[0]
        if xs.size: L[y]=xs[0]/SC-400; R[y]=xs[-1]/SC-400
    return L,R,hm[name][0]
chars={}
for n in go:
    if n.startswith('uni'):
        cp=int(n[3:7],16); chars.setdefault(chr(cp),[]).append(n)
P={n:profile(n) for c in chars for n in chars[c]}
def kind(c): return 'U' if (c.isupper() or c.isdigit()) else ('L' if c.islower() else 'P')
def metric(a,b):
    vals=[];mins=[]
    for na in chars[a]:
        _,Ra,adv=P[na]
        for nb in chars[b]:
            Lb,_,_=P[nb]; g=adv-Ra+Lb; ok=~np.isnan(g)
            if ok.sum()<4: return None,None
            vals.append(np.mean(np.minimum(g[ok],4*U))); mins.append(np.min(g[ok]))
    return float(np.mean(vals)),float(np.min(mins))
rep=lambda c:{'U':'H','L':'n'}.get(kind(c),c)
REF={}
def ref(a,b):
    k=(rep(a),rep(b))
    if k not in REF: REF[k]=metric(*k)[0]
    return REF[k]
KC=[c for c in chars if c not in ' ·•']
pairs={}
for a in KC:
    for b in KC:
        if kind(a)=='P' and kind(b)=='P': continue
        act,mn=metric(a,b)
        if act is None: continue
        r=ref(a,b)
        if r is None: continue
        k=-0.6*(act-r) if act>r else -0.3*(act-r)
        k=max(k,0.22*U-mn)          # never let ink collide
        k=min(k,0.3*U)
        k=int(round(k/5)*5)
        if abs(k)>=30: pairs[(a,b)]=k
cls={c:'@k_'+'%04X'%ord(c) for c in KC}
used=set(x for p in pairs for x in p)
lines=[f"{cls[c]} = [{' '.join(chars[c])}];" for c in KC if c in used]
lines.append("feature kern {\n  lookup kernpairs {")
for (a,b),k in sorted(pairs.items(),key=lambda x:x[1]):
    lines.append(f"    pos {cls[a]} {cls[b]} {k};")
lines.append("  } kernpairs;\n} kern;")
open('kern.fea','w').write("\n".join(lines))
print(len(pairs),'pairs')
for t in ['To','Ta','Va','Yo','LT','AV','P.','T.','F,','r.','y.','“A','A”','Tr','Wo','ff','fo','av']:
    if len(t)==2: print(t,pairs.get((t[0],t[1]),0),end=' | ')
