import json, numpy as np, base64
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.basePen import BasePen
from PIL import Image, ImageDraw, ImageChops
tt=TTFont('JuliaMarker-Regular.otf'); gs=tt.getGlyphSet(); cmap=tt.getBestCmap()
picks=json.load(open('picks.json'))
order="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,:;…!?'\"“”‘’-–—_()[]{}<>«»/\\|+=×÷%*#@&~"
XH=465; CAP=700
class Poly(BasePen):
    def __init__(s,g): super().__init__(g); s.polys=[]; s.cur=[]
    def _moveTo(s,p): s.cur=[p]
    def _lineTo(s,p): s.cur.append(p)
    def _curveToOne(s,a,b,c):
        p0=s.cur[-1]
        for t in np.linspace(0.1,1,10):
            mt=1-t; s.cur.append((mt**3*p0[0]+3*mt*mt*t*a[0]+3*mt*t*t*b[0]+t**3*c[0],mt**3*p0[1]+3*mt*mt*t*a[1]+3*mt*t*t*b[1]+t**3*c[1]))
    def _closePath(s): s.polys.append(s.cur); s.cur=[]
def raster(name,sc=0.2):
    p=Poly(gs); gs[name].draw(p); W=int(1400*sc); H=int(1600*sc)
    m=Image.new('1',(W,H),0)
    for poly in p.polys:
        t=Image.new('1',(W,H),0); ImageDraw.Draw(t).polygon([(x*sc+100*sc,(1100-y)*sc) for x,y in poly],fill=1); m=ImageChops.logical_xor(m,t)
    a=np.array(m); ys,xs=np.nonzero(a)
    return a,ys,xs,sc
def slant(name):
    a,ys,xs,sc=raster(name)
    if len(xs)<10: return None
    h=np.ptp(ys); w=np.ptp(xs)
    if h<w*0.8: return None
    x=xs-xs.mean(); y=ys-ys.mean()
    return float(np.degrees(np.arctan2(-(x*y).mean(),(y*y).mean())))
def svg(name):
    pen=SVGPathPen(gs); gs[name].draw(pen); adv=gs[name].width
    return adv,pen.getCommands()
data=[]; allsl=[]
rows=[]
for ch in order:
    base='uni%04X'%ord(ch)
    n=len([g for g in tt.getGlyphOrder() if g==base or g.startswith(base+'.alt')])
    vs=[]
    for s in range(n):
        name=base if s==0 else f'{base}.alt{s}'
        adv,d=svg(name)
        bp=gs[name]; 
        from fontTools.pens.boundsPen import BoundsPen
        b=BoundsPen(gs); gs[name].draw(b); bb=b.bounds
        sl=slant(name) if ch.isalnum() else None
        if sl is not None: allsl.append(sl)
        src=picks[ch][s] if ch in picks else None
        vs.append(dict(slot=s,id=src,adv=adv,d=d,ymin=bb[1],sl=sl))
    rows.append((ch,vs))
GS=float(np.median(allsl)); print('global slant',GS)
ROUND=set('OCGSQUJ0368935ocesuvwg'); DESC=set('gjpqyQ')
for ch,vs in rows:
    mw=np.median([v['adv'] for v in vs])
    for v in vs:
        sc=abs(v['adv']-mw)/mw*3
        if v['sl'] is not None: sc+=abs(v['sl']-GS)/10
        if ch.isalnum() and ch not in DESC: sc+=abs(v['ymin']-(-12 if ch in ROUND else 0))/25
        if v['id']=='A0023': sc+=5   # the a that reads as a 2
        v['score']=round(sc,3); v['sl']=None if v['sl'] is None else round(v['sl'],1)
    best=min(vs,key=lambda v:v['score'])['slot']
    data.append(dict(ch=ch,best=best,vs=vs))
json.dump(data,open('defaults_data.json','w'),ensure_ascii=False,separators=(',',':'))
print(len(data),'chars; changed from current default:',sum(1 for d in data if d['best']!=0))
