import json, numpy as np, cv2, potrace, zlib
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

M=json.load(open('meta.json')); meta=M['meta']; SW=M['sw']
picks=json.load(open('picks.json'))
labs={k:np.load(f'{k}_lab.npy') for k in 'ABCD'}
UPM=1000; CAP=700
FLAT_CAPS='EFHIKLTXZ'
def top_sw(i): g=meta[i]; return (g['base']-g['y'])/SW[g['sheet']]
def bot_sw(i): g=meta[i]; return (g['base']-(g['y']+g['h']))/SW[g['sheet']]
CAP_SW=np.median([top_sw(i)-bot_sw(i) for c in FLAT_CAPS for i in picks[c]])
U=CAP/CAP_SW                       # font units per stroke width
XH=np.median([top_sw(i)-bot_sw(i) for c in 'acemnorsuvwxz' for i in picks[c]])*U
DESC_C='gjpqyQ'
print(f'stroke={U:.0f}u x-height={XH:.0f}u')

OS=12
TGT={}
for c in 'ABDEFHIJKLMNPRTVWXYZ': TGT[c]=CAP
for c in 'CGOSU': TGT[c]=CAP+2*OS
TGT['Q']=780
for c in '1247': TGT[c]=CAP
for c in '03689': TGT[c]=CAP+2*OS
for c in '5': TGT[c]=CAP+OS
for c in 'mnruvwxz': TGT[c]=XH
for c in 'aceos': TGT[c]=XH+2*OS
for c in 'bdhkl': TGT[c]=690
TGT['f']=690; TGT['t']=600; TGT['i']=600; TGT['j']=850
for c in 'gpqy': TGT[c]=XH+255
TGT.update({':':480,';':640,'!':780,'?':780,'(':760,')':760,'[':800,']':800,'{':880,'}':880,'<':470,'>':470,'«':400,'»':400,
            '/':760,'\\':760,'|':800,'+':470,'%':650,'*':450,'#':700,'@':760,'&':720})
def hu(i): g=meta[i]; return g['h']*U/SW[g['sheet']]
FACT={}
WT={c['id']:c['wt'] for c in json.load(open('cands.json'))}
for ch,ids in picks.items():
    if ch not in TGT: continue
    m=np.median([hu(i) for i in ids])
    for i in ids:
        T=TGT[ch]*(hu(i)/m)**0.5
        sw=U  # stroke in units
        FACT[i]=float(np.clip((T-sw)/(hu(i)-sw),0.55,1.7))
DOTS={'.':135,'…':140}
for ch,T0 in DOTS.items():
    m=np.median([hu(i) for i in picks[ch]])
    for i in picks[ch]: FACT[i]=T0*(hu(i)/m)**0.5/hu(i)
def mask_of(i, comp=None):
    g=meta[i]; k=g['sheet']; p=int(SW[k]); x,y,w,h=g['x'],g['y'],g['w'],g['h']
    lab=labs[k]; H,W=lab.shape
    x0,y0,x1,y1=max(x-p,0),max(y-p,0),min(x+w+p,W),min(y+h+p,H)
    ids=g['ids'] if comp is None else [comp]
    m=np.isin(lab[y0:y1,x0:x1],ids).astype(np.float32)
    f=FACT.get(i,1.0) if comp is None else 1.0
    wt=1+0.6*(float(np.clip(WT.get(i,1.0),0.85,1.15))-1)
    r=0 if g['ch'] in DOTS else SW[k]*(1/f-wt)/2
    if abs(r)>=1:
        m=np.pad(m,int(abs(r))+2); x0-=int(abs(r))+2; y0-=int(abs(r))+2
        ker=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(2*int(round(abs(r)))+1,)*2)
        m=(cv2.dilate if r>0 else cv2.erode)(m,ker)
    m=cv2.GaussianBlur(m,(0,0),SW[k]*0.06)>0.5
    return m,x0,y0,f
def trace(m):
    m=np.pad(m,4)
    return potrace.Bitmap(~m).trace(turdsize=int(4),alphamax=1.0,opticurve=True,opttolerance=0.25), 4

ROUND_BOT=set('OCGSQUJ0368935ocesuvwg'); OVERSHOOT=12
# ---- per-glyph source list: (glyph char, slot, id, optional component)
sources=[]
for ch,ids in picks.items():
    for s,i in enumerate(ids): sources.append((ch,s,i,None))
def comps_sorted(i):
    g=meta[i]; lab=labs[g['sheet']]; x,y,w,h=g['x'],g['y'],g['w'],g['h']
    out=[]
    for c in g['ids']:
        ys,xs=np.nonzero(lab[y:y+h,x:x+w]==c); out.append((xs.mean(),c,len(xs)))
    out=[o for o in out if o[2]>0.3*max(q[2] for q in out)]
    return [c for _,c,_ in sorted(out)]
for s,i in enumerate(picks['“']): sources.append(('‘',s,i,comps_sorted(i)[0]))
_pq=[i for i in picks['”'] if len(comps_sorted(i))>=2][0]
_c=comps_sorted(_pq)
_c=[c for c in _c if True]
for s,c in enumerate(list(reversed(_c[:2]))): sources.append(('’',s,_pq,c))

# ---- trace everything into font units with provisional vertical placement (row baseline)
G={}
for ch,s,i,comp in sources:
    g=meta[i]; k=g['sheet']; m,x0,y0,fs=mask_of(i,comp)
    plist,pad=trace(m)
    kpx=U/SW[k]*fs
    ys,xs=np.nonzero(m)
    def tx(p,x0=x0,y0=y0,kpx=kpx,base=g['base']):
        return ((p.x-pad+x0)*kpx, (base-(p.y-pad+y0))*kpx)
    contours=[]
    for c in plist:
        st=tx(c.start_point); segs=[]
        for sg in c.segments:
            if sg.is_corner: segs.append(('L',tx(sg.c))); segs.append(('L',tx(sg.end_point)))
            else: segs.append(('C',tx(sg.c1),tx(sg.c2),tx(sg.end_point)))
        contours.append((st,segs))
    xmin=(xs.min()+x0)*kpx; xmax=(xs.max()+x0)*kpx
    ymax=(g['base']-(ys.min()+y0))*kpx; ymin=(g['base']-(ys.max()+y0))*kpx
    # scanline profile (in units) for spacing
    rows_u=(g['base']-(np.arange(m.shape[0])+y0))*kpx
    left=np.array([ (np.nonzero(r)[0].min()+x0)*kpx if r.any() else np.nan for r in m])
    right=np.array([ (np.nonzero(r)[0].max()+x0)*kpx if r.any() else np.nan for r in m])
    G[(ch,s)]=dict(contours=contours,xmin=xmin,xmax=xmax,ymin=ymin,ymax=ymax,rows=rows_u,left=left,right=right,dy=0.0,src=i)

# ---- vertical placement
def classof(ch): return [G[(c,s)] for (c,s) in G if c==ch]
def place_bottom(ch,target): 
    for g in classof(ch): g['dy']=target-g['ymin']
def place_top(ch,target):
    for g in classof(ch): g['dy']=target-g['ymax']
def place_center(ch,target):
    for g in classof(ch): g['dy']=target-(g['ymin']+g['ymax'])/2
for ch in picks:
    if ch.isalnum() and ch not in DESC_C and ch!='q':
        gs=classof(ch); m=np.median([g['ymin'] for g in gs]); t=-OVERSHOOT if ch in ROUND_BOT else 0
        for g in gs: g['dy']=t-m-float(np.clip(0.5*(g['ymin']-m),-25,25))+(g['ymin']-m)*0-(g['ymin']-m)+(g['ymin']-m) if False else t-g['ymin']+float(np.clip(0.5*(g['ymin']-m),-25,25))
    elif ch in DESC_C:
        # align by top so x-height/cap line is consistent; keep half the bounce
        ref=CAP if ch.isupper() else (XH if ch!='j' else None)
        gs=classof(ch)
        if ref is None:
            itop=np.median([q['ymax'] for q in classof('i')]); m=np.median([q['ymax'] for q in gs])
            for g in gs: g['dy']=itop-m-0.5*(g['ymax']-m)
            continue
        tops=[g['ymax'] for g in gs] if ch not in 'gpqy' else None
        if ch in 'gpqy':
            # bowl top ~ x-height: use top of glyph
            m=np.median([g['ymax'] for g in gs])
            for g in gs: g['dy']=XH+OVERSHOOT-m-0.5*(g['ymax']-m)
        else:
            m=np.median([g['ymin'] for g in gs])
            for g in gs: g['dy']=(-OVERSHOOT if ch in ROUND_BOT else 0)-m-0.5*(g['ymin']-m) if ch=='J' else CAP-np.median([q['ymax'] for q in gs])+0*g['ymax']
DOT=np.median([g['ymax']-g['ymin'] for g in classof('.')])
DESC=-np.median([g['ymin']+g['dy'] for c in 'gpqy' for g in classof(c)])
for ch in '.…!?%#&:': place_bottom(ch,0)
place_top(',',DOT*1.1); place_top(';',XH*0.97)
for ch in ["'",'"','“','”','‘','’','*']: place_top(ch,CAP+10)
AX=XH*0.52
for ch in '-–—~+=×÷<>«»': place_center(ch,AX)
place_top('_',-70)
BC=(CAP-DESC)/2
for ch in '()[]{}|': place_center(ch,BC)
for ch in '/\\': place_bottom(ch,-0.04*CAP)
place_bottom('@',-0.14*CAP)
for g in G.values(): g['ymin']+=g['dy']; g['ymax']+=g['dy']; g['rows']=g['rows']+g['dy']

# ---- spacing: white-area method (HT Letterspacer style)
D=1.25*U
def zone(ch,g):
    if ch.islower() or ch in 'ı': return (0,XH)
    if ch.isupper() or ch.isdigit(): return (0,CAP)
    return (g['ymin'],g['ymax'])
def side(g,ch,which):
    z0,z1=zone(ch,g); sel=(g['rows']>=z0)&(g['rows']<=z1)
    if which=='L': prof=g['left'][sel]-g['xmin']
    else: prof=g['xmax']-g['right'][sel]
    prof=np.where(np.isnan(prof),D,np.minimum(prof,D))
    return float(prof.mean()) if prof.size else D
def target(ch):
    if ch.isupper(): return 0.95*U
    if ch.islower(): return 0.80*U
    if ch.isdigit(): return 0.80*U
    return 0.55*U
for (ch,s),g in G.items():
    T=target(ch)
    g['lsb']=max(T-side(g,ch,'L'),0.12*U); g['rsb']=max(T-side(g,ch,'R'),0.12*U)
    if ch in '.,:;…!': g['lsb']=g['rsb']=max(g['lsb'],0.35*U)
    g['adv']=round(g['lsb']+(g['xmax']-g['xmin'])+g['rsb'])
json.dump({f'{c}|{s}':dict(lsb=round(g['lsb']),rsb=round(g['rsb']),adv=g['adv'],src=g['src']) for (c,s),g in G.items()},open('spacing.json','w'),ensure_ascii=False)

# ---- glyph names, derived glyphs
def gname(ch,s): 
    b='uni%04X'%ord(ch)
    return b if s==0 else f'{b}.alt{s}'
glyphs={}   # name -> (adv, drawfn)
def drawer(g):
    ox=g['lsb']-g['xmin']; dy=g['dy']
    def f(pen):
        P=lambda p:(round(p[0]+ox),round(p[1]+dy))
        for st,segs in g['contours']:
            pen.moveTo(P(st))
            for sg in segs:
                if sg[0]=='L': pen.lineTo(P(sg[1]))
                else: pen.curveTo(P(sg[1]),P(sg[2]),P(sg[3]))
            pen.closePath()
    return f
nvar={}
for (ch,s),g in G.items():
    glyphs[gname(ch,s)]=(g['adv'],drawer(g)); nvar[ch]=max(nvar.get(ch,0),s+1)
# middle dot / bullet from period
def derived(src,scale,cy):
    g=G[(src,0)]; cx=(g['xmin']+g['xmax'])/2; mid=(g['ymin']+g['ymax'])/2
    w=(g['xmax']-g['xmin'])*scale; lsb=0.5*U; dyb=g['dy']
    def f(pen):
        P=lambda p:(round((p[0]-cx)*scale+lsb+w/2),round((p[1]+dyb-mid)*scale+cy))
        for st,segs in g['contours']:
            pen.moveTo(P(st))
            for sg in segs:
                if sg[0]=='L': pen.lineTo(P(sg[1]))
                else: pen.curveTo(P(sg[1]),P(sg[2]),P(sg[3]))
            pen.closePath()
    return (round(w+2*lsb),f)
glyphs['uni00B7']=derived('.',1.0,AX); glyphs['uni2022']=derived('.',1.45,AX); nvar['·']=1; nvar['•']=1
SPACE=round(0.26*UPM)
for s in range(3): glyphs['space' if s==0 else f'space.alt{s}']=(SPACE,lambda pen:None)
glyphs['.notdef']=(500,lambda pen:(pen.moveTo((50,0)),pen.lineTo((450,0)),pen.lineTo((450,700)),pen.lineTo((50,700)),pen.closePath()))
order=['.notdef','space','space.alt1','space.alt2']+sorted(n for n in glyphs if n not in ('.notdef','space','space.alt1','space.alt2'))
cmap={32:'space',0xA0:'space'}
for ch in nvar: cmap[ord(ch)]=gname(ch,0)

# ---- features
nv=dict(nvar); nv[' ']=3
def nm(ch,s): return 'space' if ch==' ' and s==0 else ('space.alt%d'%s if ch==' ' else gname(ch,s))
chars=[c for c in nv if nv[c]>=2]
slots={s:[nm(c,s) for c in nv if nv[c]>s] for s in range(4)}
slots[0]+=[]
def grp(c): return zlib.crc32(c.encode())%2   # 0 = forward cycle, 1 = reverse cycle
A=[c for c in chars if grp(c)==0]; B=[c for c in chars if grp(c)==1]
def cls(name,lst): return f"@{name} = [{' '.join(lst)}];" if lst else f"@{name} = [];"
fea=[cls(f'S{s}',slots[s]) for s in range(4)]
def lk(name,pairs): return f"lookup {name} {{\n"+"\n".join(f"  sub {a} by {b};" for a,b in pairs)+f"\n}} {name};"
fea.append(lk('to1',[(nm(c,0),nm(c,1)) for c in chars]))
fea.append(lk('to2',[(nm(c,0),nm(c,2)) for c in chars if nv[c]>=3]))
fea.append(lk('to3',[(nm(c,0),nm(c,3)) for c in chars if nv[c]>=4]))
def L(cs,n=None,only=None): 
    l=[nm(c,0) for c in cs if (n is None or nv[c]>=n) and (only is None or nv[c]==only)]
    return '['+' '.join(l)+']' if l else None
rules=[]
def r(prev,targ,lookup):
    if targ: rules.append(f"  sub @{prev} {targ}' lookup {lookup};")
# forward: 0->1->2->(3)->0
r('S0',L(A),'to1'); r('S1',L(A,3),'to2'); r('S2',L(A,4),'to3')
# reverse: 0->2->1->(3)->0 ; two-variant chars just alternate
r('S0',L(B,3),'to2'); r('S0',L(B,only=2),'to1'); r('S2',L(B,3),'to1'); r('S1',L(B,4),'to3')
fea.append("lookup cycle {\n"+"\n".join(rules)+"\n} cycle;")
fea.append("feature calt {\n  lookup cycle;\n} calt;")
# rand removed: HarfBuzz applies it by default and it overrides the cycle
for s in (1,2,3):
    pairs=[(nm(c,0),nm(c,s)) for c in nv if nv[c]>s and c!=' ']
    fea.append(f"feature ss0{s} {{\n"+"\n".join(f"  sub {a} by {b};" for a,b in pairs)+f"\n}} ss0{s};")
import os
KERN=open("kern.fea").read() if os.path.exists("kern.fea") else ""
FEA="languagesystem DFLT dflt;\nlanguagesystem latn dflt;\n"+"\n".join(fea)+"\n"+KERN
open('features.fea','w').write(FEA)

# ---- build CFF font
fb=FontBuilder(UPM,isTTF=False)
fb.setupGlyphOrder(order); fb.setupCharacterMap(cmap)
cs={}; adv={}
for n in order:
    a,f=glyphs[n]; pen=T2CharStringPen(a,None); f(pen); cs[n]=pen.getCharString(); adv[n]=a
fam='Julia Marker'
fb.setupCFF('JuliaMarker-Regular',{'FullName':fam},cs,{})
# metrics
from fontTools.pens.boundsPen import BoundsPen
lsbs={}; ymax=0; ymin=0
for n in order:
    bp=BoundsPen(None); glyphs[n][1](bp); b=bp.bounds
    lsbs[n]=b[0] if b else 0
    if b: ymax=max(ymax,b[3]); ymin=min(ymin,b[1])
fb.setupHorizontalMetrics({n:(adv[n],round(lsbs[n])) for n in order})
asc,desc=round(ymax)+10,round(ymin)-10
fb.setupHorizontalHeader(ascent=900,descent=-300,lineGap=0)
fb.setupNameTable({'familyName':fam,'styleName':'Regular','uniqueFontIdentifier':'JuliaMarker-Regular-1.0','psName':'JuliaMarker-Regular','version':'Version 1.000'})
fb.setupOS2(sTypoAscender=900,sTypoDescender=-300,sTypoLineGap=0,usWinAscent=asc,usWinDescent=-desc,
            sxHeight=round(XH),sCapHeight=CAP,fsSelection=0x40|0x80,achVendID='TNGB')
fb.setupPost()
addOpenTypeFeaturesFromString(fb.font,FEA)
ext=[]
for n in order:
    bp=BoundsPen(None); glyphs[n][1](bp)
    if bp.bounds: ext.append((bp.bounds[3],bp.bounds[1],n))
print('tallest',sorted(ext)[-4:]); print('deepest',sorted(ext,key=lambda e:e[1])[:4])
fb.save('JuliaMarker-Regular.otf')
from fontTools.ttLib import TTFont
f=TTFont('JuliaMarker-Regular.otf'); f.flavor='woff2'; f.save('JuliaMarker-Regular.woff2')
import os
print('glyphs',len(order),'otf',os.path.getsize('JuliaMarker-Regular.otf'),'woff2',os.path.getsize('JuliaMarker-Regular.woff2'))
print('asc',asc,'desc',desc,'DOT',round(DOT),'DESC',round(DESC))
