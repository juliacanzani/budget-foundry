import type { Glyph } from './api';
import { GlyphArt, type Frame } from './GlyphArt';

// Pairs that a loose hand turns into each other.
const SETS = ['Y4', 'a2', 'S6', 'lI1', 'O0', 'Z2', 'B8'];

/** Each set's current defaults side by side, so a Y that reads as a 4 shows up. */
export function LookAlikes({ glyphs, frame }: { glyphs: Glyph[]; frame: Frame }) {
  const by = new Map(glyphs.map((g) => [g.char, g]));
  const sets = SETS.map((s) => [...s].map((ch) => by.get(ch)).filter((g): g is Glyph => !!g?.default)).filter((s) => s.length > 1);
  if (!sets.length) return null;
  return (
    <section className="lookalikes" aria-labelledby="lookalikes-title">
      <h2 id="lookalikes-title" className="tui-text-style-overline">Look-alikes, by default glyph</h2>
      <ul>
        {sets.map((s) => (
          <li key={s.map((g) => g.char).join('')}>
            <span className="tui-visually-hidden">{s.map((g) => g.char).join(' against ')}</span>
            {s.map((g) => {
              const c = g.candidates.find((c) => c.id === g.default)!;
              return (
                <span key={g.char} className="lookalikes__glyph">
                  <GlyphArt path={c.path} advance={c.advance} frame={frame} height={56} guides={false} />
                  <span aria-hidden="true">{g.char}</span>
                </span>
              );
            })}
          </li>
        ))}
      </ul>
    </section>
  );
}
