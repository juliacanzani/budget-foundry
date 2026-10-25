"""Stage 9, features: generated, never hand-written.

`calt` cycles variants with the previous glyph's slot as state. Characters are split
across two directions (forward 0→1→2, reverse 0→2→1) by crc32 parity, so neighbouring
letters don't step in lockstep; spaces carry the state; a glyph never follows itself.
`ss01`–`ss03` force a variant.

Nearly every glyph sits in slot 0, 1 or 2, so one glyph of lookback gives three states:
enough for three variants, never for four (the fourth-variant characters' defaults
never showed). Characters with four variants look back two glyphs instead (see
wide_slot); the result is never the previous slot, so doubles still never repeat.
On English prose each of the four slots lands at roughly 20-30%.

No `rand`: HarfBuzz applies it by default and it overrides the cycle.
"""
from __future__ import annotations

import zlib

MAX_VARIANTS = 4                                       # the cycle's slots; more are never shown


def gname(ch: str, slot: int) -> str:
    """Production names only: uniXXXX, uniXXXX.altN."""
    b = 'uni%04X' % ord(ch)
    return b if slot == 0 else f'{b}.alt{slot}'


def wide_slot(q: int, p: int) -> int:
    """Slot for a four-variant glyph after slots q, p. Running text almost only
    produces q != p within 0-2: stepping one way takes the fourth slot, otherwise the
    slot neither neighbour used. Anything else steps on from p."""
    if q != p and q < 3 and p < 3:
        return 3 if p == (q + 1) % 3 else 3 - p - q
    return (p + 1) % 4


def generate(nvar: dict[str, int], space_variants: int = 3) -> str:
    nv = dict(nvar); nv[' '] = space_variants
    def nm(ch, s): return 'space' if ch == ' ' and s == 0 else ('space.alt%d' % s if ch == ' ' else gname(ch, s))
    chars = [c for c in nv if nv[c] >= 2]
    slots = {s: [nm(c, s) for c in nv if nv[c] > s] for s in range(4)}
    def grp(c): return zlib.crc32(c.encode()) % 2   # 0 = forward cycle, 1 = reverse cycle
    A = [c for c in chars if grp(c) == 0]; B = [c for c in chars if grp(c) == 1]
    def cls(name, lst): return f"@{name} = [{' '.join(lst)}];" if lst else f"@{name} = [];"
    fea = [cls(f'S{s}', slots[s]) for s in range(4)]
    def lk(name, pairs): return f"lookup {name} {{\n" + "\n".join(f"  sub {a} by {b};" for a, b in pairs) + f"\n}} {name};"
    fea.append(lk('to1', [(nm(c, 0), nm(c, 1)) for c in chars]))
    fea.append(lk('to2', [(nm(c, 0), nm(c, 2)) for c in chars if nv[c] >= 3]))
    fea.append(lk('to3', [(nm(c, 0), nm(c, 3)) for c in chars if nv[c] >= 4]))
    def L(cs, n=None, only=None):
        l = [nm(c, 0) for c in cs if (n is None or nv[c] >= n) and (only is None or nv[c] == only)]
        return '[' + ' '.join(l) + ']' if l else None
    if any(nv[c] > MAX_VARIANTS for c in chars): raise ValueError(f'at most {MAX_VARIANTS} variants per character')
    rules = []
    def r(prev, cs, out):
        targ = L(cs)
        if targ and out: rules.append(f"  sub {prev} {targ}' lookup to{out};")
        elif targ: rules.append(f"  ignore sub {prev} {targ}';")
    by = lambda grp, n: [c for c in grp if nv[c] == n]
    # four variants: two glyphs of lookback; with only one glyph before, one
    wide = by(A, 4) + by(B, 4)
    for q in range(4):
        for p in range(4): r(f'@S{q} @S{p}', wide, wide_slot(q, p))
    for p in range(4): r(f'@S{p}', wide, (p + 1) % 4)
    # forward: 0->1->2->0
    r('@S0', by(A, 3) + by(A, 2), 1); r('@S1', by(A, 3), 2)
    # reverse: 0->2->1->0 ; two-variant chars just alternate
    r('@S0', by(B, 3), 2); r('@S0', by(B, 2), 1); r('@S2', by(B, 3), 1)
    fea.append("lookup cycle {\n" + "\n".join(rules) + "\n} cycle;")
    fea.append("feature calt {\n  lookup cycle;\n} calt;")
    for s in (1, 2, 3):
        pairs = [(nm(c, 0), nm(c, s)) for c in nv if nv[c] > s and c != ' ']
        fea.append(f"feature ss0{s} {{\n" + "\n".join(f"  sub {a} by {b};" for a, b in pairs) + f"\n}} ss0{s};")
    return "languagesystem DFLT dflt;\nlanguagesystem latn dflt;\n" + "\n".join(fea)
