import uharfbuzz as hb, sys
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
from PIL import Image, ImageDraw, ImageChops
FONT=sys.argv[1] if len(sys.argv)>1 else 'JuliaMarker-Regular.otf'
blob=hb.Blob.from_file_path(FONT); face=hb.Face(blob); font=hb.Font(face)
tt=TTFont(FONT); gs=tt.getGlyphSet(); order=tt.getGlyphOrder()
class Poly(BasePen):
    def __init__(s,gs): super().__init__(gs); s.polys=[]; s.cur=[]
    def _moveTo(s,p): s.cur=[p]
    def _lineTo(s,p): s.cur.append(p)
    def _curveToOne(s,a,b,c):
        p0=s.cur[-1]
        for t in [i/12 for i in range(1,13)]:
            mt=1-t; s.cur.append((mt**3*p0[0]+3*mt*mt*t*a[0]+3*mt*t*t*b[0]+t**3*c[0], mt**3*p0[1]+3*mt*mt*t*a[1]+3*mt*t*t*b[1]+t**3*c[1]))
    def _closePath(s): s.polys.append(s.cur); s.cur=[]
def line(text,size=90,feats=None,guides=True):
    buf=hb.Buffer(); buf.add_str(text); buf.guess_segment_properties()
    hb.shape(font,buf,feats or {})
    sc=size/1000; W=int(sum(p.x_advance for p in buf.glyph_positions)*sc)+40; H=int(size*1.6)
    base=int(size*1.1)
    img=Image.new('L',(W,H),0); x=20
    for info,pos in zip(buf.glyph_infos,buf.glyph_positions):
        pen=Poly(gs); gs[order[info.codepoint]].draw(pen)
        m=Image.new('L',(W,H),0)
        for poly in pen.polys:
            if len(poly)<3: continue
            t=Image.new('L',(W,H),0)
            ImageDraw.Draw(t).polygon([(x+px*sc,base-py*sc) for px,py in poly],fill=255)
            m=ImageChops.logical_xor(m.convert('1'),t.convert('1')).convert('L')
        img=ImageChops.lighter(img,m); x+=pos.x_advance*sc
    out=Image.new('RGB',(W,H),'white'); d=ImageDraw.Draw(out)
    if guides:
        for y,c in [(0,(120,160,220)),(465,(230,200,120)),(700,(230,200,120))]:
            d.line([(0,base-y*sc),(W,base-y*sc)],fill=c)
    out.paste((0,0,0),mask=img)
    return out
def sheet(lines,fname,size=90):
    ims=[line(t,size) for t in lines]
    W=max(i.width for i in ims); H=sum(i.height for i in ims)
    o=Image.new('RGB',(W,H),'white'); y=0
    for i in ims: o.paste(i,(0,y)); y+=i.height
    o.thumbnail((1900,4000)); o.save(fname)
if __name__=='__main__':
    sheet(['minimum hamburgefonstiv','The quick brown fox jumped','over the lazy dog','eeee oooo llll tttt iiii','HELLO Mississippi 2026','Julia’s digital garden!','“Notes, (drafts) & ideas…” — #42 @ 100%'],'spec1.png')
