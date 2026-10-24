"""Stage 9, features: generated, never hand-written.

`calt` cycles variants with the previous glyph's slot as state. Characters are split
across two directions (forward 0→1→2→3, reverse 0→2→1→3) by crc32 parity, so
neighbouring letters don't step in lockstep; spaces carry the state; a glyph never
follows itself. `ss01`–`ss03` force a variant.

No `rand`: HarfBuzz applies it by default and it overrides the cycle.
"""
from __future__ import annotations

import zlib


def gname(ch: str, slot: int) -> str:
    """Production names only: uniXXXX, uniXXXX.altN."""
    b = 'uni%04X' % ord(ch)
    return b if slot == 0 else f'{b}.alt{slot}'


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
    rules = []
    def r(prev, targ, lookup):
        if targ: rules.append(f"  sub @{prev} {targ}' lookup {lookup};")
    # forward: 0->1->2->(3)->0
    r('S0', L(A), 'to1'); r('S1', L(A, 3), 'to2'); r('S2', L(A, 4), 'to3')
    # reverse: 0->2->1->(3)->0 ; two-variant chars just alternate
    r('S0', L(B, 3), 'to2'); r('S0', L(B, only=2), 'to1'); r('S2', L(B, 3), 'to1'); r('S1', L(B, 4), 'to3')
    fea.append("lookup cycle {\n" + "\n".join(rules) + "\n} cycle;")
    fea.append("feature calt {\n  lookup cycle;\n} calt;")
    for s in (1, 2, 3):
        pairs = [(nm(c, 0), nm(c, s)) for c in nv if nv[c] > s and c != ' ']
        fea.append(f"feature ss0{s} {{\n" + "\n".join(f"  sub {a} by {b};" for a, b in pairs) + f"\n}} ss0{s};")
    return "languagesystem DFLT dflt;\nlanguagesystem latn dflt;\n" + "\n".join(fea)
