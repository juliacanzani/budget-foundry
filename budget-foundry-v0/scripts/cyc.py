import uharfbuzz as hb, collections
from fontTools.ttLib import TTFont
f=hb.Font(hb.Face(hb.Blob.from_file_path('JuliaMarker-Regular.otf')))
order=TTFont('JuliaMarker-Regular.otf').getGlyphOrder()
def slots(txt):
    b=hb.Buffer(); b.add_str(txt); b.guess_segment_properties(); hb.shape(f,b,{})
    return [int(order[g.codepoint].split('.alt')[1]) if '.alt' in order[g.codepoint] else 0 for g in b.glyph_infos]
s=slots('the quick brown fox jumped over the lazy dog')
print(' '.join(c+str(x) for c,x in zip('the quick brown fox jumped over the lazy dog',s)))
txt=('Some thoughts on making things by hand, and why they are worth it. The quick brown fox jumped over the lazy dog. Notes from the kitchen: what is on the menu this week. ')*3
s=slots(txt); print(collections.Counter(x for c,x in zip(txt,s) if c!=' '))
