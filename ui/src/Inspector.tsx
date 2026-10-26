import { forwardRef, useEffect, useRef, useState } from 'react';
import { Button, Slider } from '@tangible/ui';
import { StarFill, StarOutline } from '@tangible/ui/icons/system/index.js';
import { api, NO_CORRECTIONS, type Corrections, type Glyph } from './api';
import { startingKeep, useDecisions } from './decisions';
import { GlyphArt, type Frame, type Live } from './GlyphArt';

const sign = (v: number) => (v > 0 ? '+' : v < 0 ? '−' : '');

// The four corrections: range, step, how the value reads, and what each end does
const CONTROLS: { key: keyof Corrections; label: string; min: number; max: number; step: number;
  text: (v: number) => string; ends: [string, string] }[] = [
  { key: 'rotate', label: 'Rotate', min: -15, max: 15, step: 0.5, text: (v) => `${sign(v)}${Math.abs(v)}°`, ends: ['Lean right', 'Lean left'] },
  { key: 'baseline', label: 'Float', min: -80, max: 80, step: 2, text: (v) => `${sign(v)}${Math.abs(v)} units`, ends: ['Lower', 'Higher'] },
  { key: 'scale', label: 'Size', min: 0.7, max: 1.3, step: 0.01, text: (v) => `${Math.round(v * 100)}%`, ends: ['Smaller', 'Larger'] },
  { key: 'width', label: 'Width', min: 0.7, max: 1.3, step: 0.01, text: (v) => `${Math.round(v * 100)}%`, ends: ['Squish', 'Stretch'] },
  { key: 'weight', label: 'Weight', min: -0.4, max: 0.4, step: 0.02, text: (v) => `${sign(v)}${Math.abs(v).toFixed(2)} strokes`, ends: ['Thinner', 'Bolder'] },
];

/** A Slider that saves on release. TUI's Slider reports every step; its native input's
    `change` event fires on pointer release (and per key press, so those are debounced
    into one save). Every step goes to onPreview, which draws it at once. */
function CorrectionSlider({ id, control, value, onPreview, onCommit }: {
  id: string; control: (typeof CONTROLS)[number]; value: number; onPreview: (v: number) => void; onCommit: (v: number) => void;
}) {
  const [v, setV] = useState(value);
  const input = useRef<HTMLInputElement>(null);
  const commit = useRef(onCommit); commit.current = onCommit;
  const saved = useRef(value);
  useEffect(() => { setV(value); saved.current = value; }, [value]);
  useEffect(() => {
    const el = input.current; if (!el) return;
    let t: ReturnType<typeof setTimeout>, pointer = false;
    const save = () => { const n = el.valueAsNumber; if (n !== saved.current) { saved.current = n; commit.current(n); } };
    // A release saves at once; key presses wait for a pause
    const on = () => { clearTimeout(t); if (pointer) save(); else t = setTimeout(save, 350); pointer = false; };
    const down = () => { pointer = true; };
    const key = () => { pointer = false; };
    el.addEventListener('change', on); el.addEventListener('pointerdown', down); el.addEventListener('keydown', key);
    return () => { el.removeEventListener('change', on); el.removeEventListener('pointerdown', down); el.removeEventListener('keydown', key); clearTimeout(t); };
  }, []);
  const neutral = NO_CORRECTIONS[control.key];
  return (
    <div className="correction">
      <div className="correction__head">
        <span id={`${id}-label`} className="correction__label">{control.label}</span>
        <output htmlFor={id} className="correction__value">{control.text(v)}</output>
        {/* Only when there's something to reset: a disabled Reset reads as a live one */}
        {v !== neutral && <Button size="xs" variant="ghost" label="Reset" aria-label={`Reset ${control.label.toLowerCase()}`}
          onClick={() => { setV(neutral); onPreview(neutral); saved.current = neutral; onCommit(neutral); }} />}
      </div>
      <Slider ref={input} id={id} aria-labelledby={`${id}-label`} value={v} onValueChange={(n) => { setV(n); onPreview(n); }}
        min={Math.min(control.min, value)} max={Math.max(control.max, value)} step={control.step}
        startLabel={control.ends[0]} endLabel={control.ends[1]} getValueText={control.text} />
    </div>
  );
}

type Props = { glyphs: Glyph[]; active: string | null; frame: Frame; stroke: number; maxKeep: number; announce: (msg: string) => void };

/** The difference between what the sliders say and what the outline was built with */
function liveOf(saved: Corrections, draft: Partial<Corrections>, stroke: number): Live | undefined {
  const d = { ...saved, ...draft };
  const live = { rotate: d.rotate - saved.rotate, baseline: d.baseline - saved.baseline,
    scale: d.scale / saved.scale, width: d.width / saved.width, pen: (d.weight - saved.weight) * stroke };
  return live.rotate || live.baseline || live.scale !== 1 || live.width !== 1 || live.pen ? live : undefined;
}

/** The focused candidate, large, with its source, keep and default, its flags' fixes and
    its corrections. The heading takes focus when Enter on a tile sends you here. */
export const Inspector = forwardRef<HTMLHeadingElement, Props>(function Inspector({ glyphs, active, frame, stroke, maxKeep, announce }, heading) {
  const { toggleKeep, makeDefault, correct } = useDecisions(maxKeep, announce);
  // Slider values as you drag, drawn at once; the real outline replaces them when it's in.
  // A new outline (saved, undone, another candidate) starts from what it was built with.
  const [draft, setDraft] = useState<Partial<Corrections>>({});
  const g = active ? glyphs.find((x) => x.candidates.some((c) => c.id === active)) : undefined;
  const ci = g ? g.candidates.findIndex((c) => c.id === active) : -1;
  const c = g?.candidates[ci];
  const built = c ? `${c.id} ${JSON.stringify(c.corrections)} ${c.path?.length}` : '';
  // Reset in render, not an effect, so the new outline never shows with the old draft on it
  const [draftFor, setDraftFor] = useState(built);
  if (draftFor !== built) { setDraftFor(built); setDraft({}); }
  if (!g || !c) {
    return <p className="inspector__empty">Focus a candidate to see it here: click it, or arrow to it in the list.</p>;
  }
  const decided = g.keep.length > 0;
  const kept = startingKeep(g).includes(c.id) && decided;
  const isDefault = decided && g.default === c.id;
  const cor = c.corrections;
  const name = `${g.char === ' ' ? 'space' : g.char} candidate ${ci + 1}`;
  const set = (patch: Partial<Corrections>, label: string) => {
    if (!cor) return;
    setDraft((d) => ({ ...d, ...patch }));
    correct(c, { ...cor, ...draft, ...patch }, label);
  };
  const live = cor ? liveOf(cor, draft, stroke) : undefined;
  return (
    <div className="inspector__body">
      <h3 id="inspector-title" className="inspector__title" tabIndex={-1} ref={heading}>
        <span aria-hidden="true">{g.char}</span>
        <span className="inspector__of">
          <span className="tui-visually-hidden">{g.char === ' ' ? 'space' : g.char} ({g.codepoint}), </span>
          candidate {ci + 1} of {g.candidates.length}
        </span>
      </h3>
      <div className="inspector__art">
        <GlyphArt path={c.path} advance={c.advance} frame={frame} height={168} minWidth={96} live={live} />
        <figure className="inspector__source">
          <img src={api.sourceTile(c.id)} alt="" height={84} />
          <figcaption>As written</figcaption>
        </figure>
      </div>
      <div className="inspector__actions">
        <Button size="sm" variant={kept ? 'solid' : 'outline'} aria-pressed={kept} label={kept ? 'Kept' : 'Keep'}
          onClick={() => toggleKeep(g, c.id)} />
        <Button size="sm" variant="outline" aria-pressed={isDefault} leftIconName={isDefault ? StarFill : StarOutline}
          className="inspector__default" label={isDefault ? 'Default' : 'Make default'} onClick={() => makeDefault(g, c.id)} />
      </div>

      {c.flags.length > 0 && (
        <section className="inspector__section" aria-labelledby="inspector-flags">
          <h4 id="inspector-flags">Flags</h4>
          <ul className="inspector__flags">
            {c.flags.map((f) => {
              const fix = c.fixes.find((x) => x.flag === f);
              return (
                <li key={f}>
                  <span>{f}</span>
                  {fix && (fix.evened ? <span className="inspector__note">Evened out in the font</span>
                    : fix.applied ? <span className="inspector__fixed">Fixed</span>
                    : <Button size="xs" variant="outline" label={fix.label} onClick={() => set(fix.set, `${fix.label}: ${name}`)} />)}
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {cor && (
        <section className="inspector__section" aria-labelledby="inspector-corrections">
          <h4 id="inspector-corrections">Corrections</h4>
          {CONTROLS.map((k) => (
            <CorrectionSlider key={`${c.id}-${k.key}`} id={`correct-${k.key}`} control={k} value={cor[k.key]}
              onPreview={(v) => setDraft((d) => ({ ...d, [k.key]: v }))}
              onCommit={(v) => set({ [k.key]: v }, `${k.label} ${name}`)} />
          ))}
        </section>
      )}
    </div>
  );
});
