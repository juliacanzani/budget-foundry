import { useState } from 'react';
import { Button, Card, Field, Notice, Slider, Switch, Textarea } from '@tangible/ui';
import { ThemeButton } from '../ThemeButton';
import { useTheme } from '../theme';

// Written into the page by budget_foundry/specimen.py.
export type SpecimenData = {
  family: string;
  version: string;
  glyphs: number;
  hero: string;
  samples: string[];
  sizesText: string;
  cycling: string;
  kerning: string;
  grid: { char: string; codepoint: string; variants: number }[];
  fallback: string;
};

const SIZES = [96, 64, 40, 28, 20];

/** Feature settings for one variant shown on its own: cycling off, a stylistic set on. */
const variant = (n: number) => (n === 0 ? "'calt' 0" : `'calt' 0, 'ss0${n}' 1`);

export function Specimen({ data }: { data: SpecimenData }) {
  const { theme, mode, setMode } = useTheme();
  const [text, setText] = useState(data.hero);
  // Big on a desktop, still whole words on a phone
  const [size, setSize] = useState(() => Math.max(24, Math.min(112, Math.round(window.innerWidth / 28) * 4)));
  const [calt, setCalt] = useState(true);
  const [kern, setKern] = useState(true);
  const [sample, setSample] = useState(0);

  const live = {
    fontFamily: `'${data.family}', cursive`,
    fontFeatureSettings: calt ? 'normal' : "'calt' 0",
    fontKerning: kern ? 'normal' : 'none',
  } as const;
  const shuffle = () => {
    const next = (sample + 1) % data.samples.length;
    setSample(next); setText(data.samples[next]);
  };

  return (
    <div className="tui-interface tui-font-sans specimen" data-theme={theme}>
      <header className="specimen__bar">
        <div>
          <h1>{data.family}</h1>
          <p className="specimen__meta">{data.glyphs} glyphs · version {data.version} · made with Budget Foundry</p>
        </div>
        <ThemeButton mode={mode} resolved={theme} onChange={setMode} />
      </header>

      <main className="specimen__main">
        <section aria-labelledby="try">
          <h2 id="try" className="tui-visually-hidden">Try it</h2>
          <Field>
            <Field.Label>Sample text</Field.Label>
            <Field.Control>
              <Textarea className="specimen__hero" value={text} onChange={(e) => setText(e.target.value)} autoResize
                spellCheck={false} style={{ ...live, fontSize: `${size}px` }} />
            </Field.Control>
          </Field>
          <div className="specimen__controls">
            <div className="specimen__size">
              <span id="size-label">Size</span>
              <Slider aria-labelledby="size-label" min={24} max={200} step={4} value={size} onValueChange={setSize} getValueText={(v) => `${v} pixels`} />
              <output htmlFor="size-label" aria-hidden="true">{size}px</output>
            </div>
            <Switch size="sm" label="Alternates cycling" checked={calt} onCheckedChange={setCalt} />
            <Switch size="sm" label="Kerning" checked={kern} onCheckedChange={setKern} />
            {data.samples.length > 1 && <Button size="sm" variant="outline" label="Another sample" onClick={shuffle} />}
          </div>
        </section>

        <section aria-labelledby="sizes">
          <h2 id="sizes">Sizes</h2>
          <div className="specimen__sizes">
            {/* Sizes stay true to their label, so a phone leaves out the ones a word can't fit */}
            {SIZES.filter((s, i) => i === SIZES.length - 1 || s <= window.innerWidth / 5).map((s) => (
              <p key={s} style={{ ...live, fontSize: `${s}px` }}><span className="specimen__px">{s}px</span> {data.sizesText}</p>
            ))}
          </div>
        </section>

        <section aria-labelledby="cycling">
          <h2 id="cycling">Alternates cycling on and off</h2>
          <div className="specimen__compare">
            <Card variant="outline"><Card.Body>
              <p className="specimen__caption">Cycling (the default)</p>
              <p className="specimen__line" style={{ fontFamily: live.fontFamily }}>{data.cycling}</p>
            </Card.Body></Card>
            <Card variant="outline"><Card.Body>
              <p className="specimen__caption">One glyph per letter</p>
              <p className="specimen__line" style={{ fontFamily: live.fontFamily, fontFeatureSettings: "'calt' 0" }}>{data.cycling}</p>
            </Card.Body></Card>
          </div>
        </section>

        <section aria-labelledby="kerning">
          <h2 id="kerning">Kerning off and on</h2>
          <div className="specimen__compare">
            <Card variant="outline"><Card.Body>
              <p className="specimen__caption">Kerning off</p>
              <p className="specimen__line" style={{ fontFamily: live.fontFamily, fontKerning: 'none' }}>{data.kerning}</p>
            </Card.Body></Card>
            <Card variant="outline"><Card.Body>
              <p className="specimen__caption">Kerning on (the default)</p>
              <p className="specimen__line" style={{ fontFamily: live.fontFamily }}>{data.kerning}</p>
            </Card.Body></Card>
          </div>
        </section>

        <section aria-labelledby="charset">
          <h2 id="charset">Character set, every alternate</h2>
          <ul className="specimen__grid">
            {data.grid.map((g) => (
              <li key={g.char}>
                <Card variant="outline" as="div" className="specimen__cell">
                  <Card.Body>
                    <span className="specimen__variants" style={{ fontFamily: live.fontFamily }} aria-hidden="true">
                      {Array.from({ length: g.variants }, (_, n) => (
                        <span key={n} style={{ fontFeatureSettings: variant(n) }}>{g.char}</span>
                      ))}
                    </span>
                    <span className="tui-visually-hidden">{g.char}, </span>
                    <span className="specimen__cp">{g.codepoint}{g.variants > 1 ? ` · ${g.variants} forms` : ''}</span>
                  </Card.Body>
                </Card>
              </li>
            ))}
          </ul>
        </section>

        {data.fallback && (
          <Notice theme="info">
            <Notice.Head title="Not in the font yet" titleAs="h2" />
            <Notice.Body>{data.fallback}</Notice.Body>
          </Notice>
        )}
      </main>
    </div>
  );
}
