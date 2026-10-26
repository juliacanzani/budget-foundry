import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button, Chip, IconButton, SegmentedControl, Switch, Tooltip, TooltipProvider } from '@tangible/ui';
import { Check, StarFill, StarOutline } from '@tangible/ui/icons/system/index.js';
import { api, type Glyph } from './api';
import { startingKeep, useDecisions } from './decisions';
import { GlyphArt, type Frame } from './GlyphArt';

type Kind = 'all' | 'letters' | 'figures' | 'punctuation';
const kindOf = (ch: string): Exclude<Kind, 'all'> =>
  /\p{L}/u.test(ch) ? 'letters' : /\p{N}/u.test(ch) ? 'figures' : 'punctuation';

const TILE_HEIGHT = 104;
const hasCorrections = (c: { baseline: number; rotate: number; scale: number; weight: number }) =>
  c.baseline !== 0 || c.rotate !== 0 || c.scale !== 1 || c.weight !== 0;
const TILE_MIN_ART = 48;   // the 64px tile minus its xs (8px) side padding

type Props = {
  glyphs: Glyph[]; frame: Frame; maxKeep: number; announce: (msg: string) => void;
  active: string | null; onActive: (id: string | null) => void;
  /** Open the focused candidate in the inspector: Enter, or a click on a phone. */
  onInspect: (id: string, how: 'pointer' | 'keyboard') => void;
};

/**
 * One row per character, every candidate normalised and drawn on the guides.
 * Focus and keeping are separate: a tile takes focus (and fills the inspector) on a
 * click or the arrows; keeping is Space or the tile's check, the default is S or its star.
 * One tab stop for the whole list (roving focus); the shortcuts only act on a
 * focused tile, so they never fire while typing elsewhere.
 */
export function CullView({ glyphs, frame, maxKeep, announce, active, onActive: setActive, onInspect }: Props) {
  const [kind, setKind] = useState<Kind>('all');
  const [onlyUndecided, setOnlyUndecided] = useState(false);
  const [showSource, setShowSource] = useState(false);
  const tiles = useRef(new Map<string, HTMLButtonElement>());
  const { toggleKeep: toggle, makeDefault: star, keepSuggested } = useDecisions(maxKeep, announce);

  const visible = useMemo(
    () => glyphs.filter((g) => (kind === 'all' || kindOf(g.char) === kind) && (!onlyUndecided || g.keep.length === 0)),
    [glyphs, kind, onlyUndecided],
  );
  const undecided = glyphs.filter((g) => g.keep.length === 0 && g.candidates.length > 0);

  // ---- roving focus
  const positions = useMemo(() => visible.map((g) => g.candidates.map((c) => c.id)), [visible]);
  const tabStop = useMemo(() => {
    const all = positions.flat();
    return active && all.includes(active) ? active : all[0] ?? null;
  }, [positions, active]);

  const focusTile = useCallback((id: string | undefined) => {
    if (!id) return;
    setActive(id);
    tiles.current.get(id)?.focus();
  }, [setActive]);

  const onKeyDown = (e: React.KeyboardEvent, gi: number, ci: number) => {
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    const row = positions[gi];
    const go = (dg: number) => {
      const r = positions[gi + dg];
      return r ? r[Math.min(ci, r.length - 1)] : undefined;
    };
    let target: string | undefined;
    switch (e.key) {
      case 'ArrowRight': target = row[ci + 1] ?? positions[gi + 1]?.[0]; break;
      case 'ArrowLeft': target = row[ci - 1] ?? positions[gi - 1]?.at(-1); break;
      case 'ArrowDown': target = go(1); break;
      case 'ArrowUp': target = go(-1); break;
      case 'Home': target = row[0]; break;
      case 'End': target = row.at(-1); break;
      case ' ': toggle(visible[gi], row[ci]); e.preventDefault(); return;    // not the button's click: that inspects
      case 'Enter': onInspect(row[ci], 'keyboard'); e.preventDefault(); return;
      case 's': case 'S': star(visible[gi], row[ci]); e.preventDefault(); return;
      default: return;
    }
    e.preventDefault();
    focusTile(target);
  };

  useEffect(() => {
    // Keep a live tab stop when filters remove the focused tile.
    if (active && !positions.flat().includes(active)) setActive(null);
  }, [positions, active, setActive]);

  const keptCount = glyphs.filter((g) => g.keep.length).length;

  return (
    <section className="cull" aria-labelledby="cull-title">
      <header className="cull__head">
        <div className="cull__title">
          <h1 id="cull-title" className="tui-text-style-headline-04">Cull and choose defaults</h1>
          <p className="cull__tally">
            <strong>{keptCount}</strong> of {glyphs.length} characters have keepers
            {undecided.length > 0 && <> · <strong>{undecided.length}</strong> still to choose</>}
          </p>
        </div>
        <div className="cull__tools">
          <SegmentedControl aria-label="Show characters" value={kind} onValueChange={(v) => setKind(v as Kind)} size="sm">
            <SegmentedControl.Item value="all">All</SegmentedControl.Item>
            <SegmentedControl.Item value="letters">Letters</SegmentedControl.Item>
            <SegmentedControl.Item value="figures">Figures</SegmentedControl.Item>
            <SegmentedControl.Item value="punctuation">Punctuation</SegmentedControl.Item>
          </SegmentedControl>
          <Switch size="sm" label="Only to choose" checked={onlyUndecided} onCheckedChange={setOnlyUndecided} />
          <Switch size="sm" label="Source photos" checked={showSource} onCheckedChange={setShowSource} />
          {undecided.length > 0 && (
            <Button size="sm" variant="outline" label={`Keep suggestions for ${undecided.length}`} onClick={() => keepSuggested(undecided)} />
          )}
        </div>
        <p className="cull__keys" id="cull-keys">
          <kbd>←</kbd> <kbd>→</kbd> <kbd>↑</kbd> <kbd>↓</kbd> move · <kbd>Space</kbd> or the check: keep · <kbd>S</kbd> or the star: default · <kbd>Enter</kbd> inspector
        </p>
      </header>

      {visible.length === 0 && <p className="cull__empty">Nothing to show with these filters.</p>}

      <TooltipProvider>
      <div className="cull__list" role="group" aria-label="Candidates" aria-describedby="cull-keys">
        {visible.map((g, gi) => {
          const decided = g.keep.length > 0;
          const keep = startingKeep(g);
          const def = decided ? g.default : keep[0] ?? null;
          const headingId = `char-${g.codepoint}`;
          return (
            <div key={g.char} role="group" className="cull__char" aria-labelledby={headingId} data-decided={decided || undefined}>
              <div className="cull__label">
                <h2 id={headingId} className="cull__glyph">
                  <span aria-hidden="true">{g.char}</span>
                  <span className="tui-visually-hidden">{g.char === ' ' ? 'space' : g.char} ({g.codepoint})</span>
                </h2>
                <span className="cull__cp" aria-hidden="true">{g.codepoint}</span>
                {decided ? (
                  <span className="cull__count" data-over={g.keep.length > maxKeep || undefined}>
                    {g.keep.length} of {g.candidates.length} kept
                    {g.keep.length > maxKeep && ` · the font takes ${maxKeep}, unkeep ${g.keep.length - maxKeep}`}
                  </span>
                ) : (
                  <Chip size="sm" theme="warning" variant="outline">To choose</Chip>
                )}
                {g.source === 'auto' && decided && <Chip size="sm" variant="ghost">auto</Chip>}
                {!decided && keep.length > 0 && (
                  <Button size="sm" variant="ghost" label={`Keep ${keep.length} suggested`} onClick={() => keepSuggested([g])} />
                )}
              </div>
              <div className="cull__tiles">
                {g.candidates.map((c, ci) => {
                  const kept = keep.includes(c.id);
                  const isDefault = c.id === def && kept;
                  return (
                    <div key={c.id} className="tile-cell">
                    <div className="tile" data-kept={kept || undefined} data-tentative={(!decided && kept) || undefined}
                      data-active={c.id === active || undefined}>
                      <button
                        ref={(el) => { if (el) tiles.current.set(c.id, el); else tiles.current.delete(c.id); }}
                        type="button"
                        className="tile__toggle"
                        tabIndex={c.id === tabStop ? 0 : -1}
                        onFocus={() => setActive(c.id)}
                        onClick={() => { focusTile(c.id); onInspect(c.id, 'pointer'); }}
                        onKeyDown={(e) => onKeyDown(e, gi, ci)}
                        onKeyUp={(e) => { if (e.key === ' ') e.preventDefault(); }}
                      >
                        <span className="tile__art">
                          {showSource ? (
                            <img src={api.sourceTile(c.id)} alt="" height={TILE_HEIGHT} />
                          ) : (
                            <GlyphArt path={c.path} advance={c.advance} frame={frame} height={TILE_HEIGHT} minWidth={TILE_MIN_ART} />
                          )}
                        </span>
                        <span className="tui-visually-hidden">
                          Candidate {ci + 1} of {g.candidates.length}
                          {decided ? (kept ? ', kept' : ', not kept') : ''}
                          {isDefault ? ', default' : ''}
                          {!decided && kept ? ', suggested' : ''}
                          {c.corrections && hasCorrections(c.corrections) ? ', corrected' : ''}
                          {c.flags.length ? `, ${c.flags.join(', ')}` : ''}
                        </span>
                      </button>
                      {/* The pointer's ways to keep and to star a default; the keyboard's are Space and S
                          on the tile. Out of the tab order so the list stays one stop; screen readers still
                          reach them in browse mode. */}
                      <Tooltip>
                        <Tooltip.Trigger asChild>
                          <IconButton
                            className="tile__keep"
                            icon={Check}
                            label="Keep"
                            aria-pressed={decided ? kept : false}
                            variant="ghost"
                            size="xs"
                            tabIndex={-1}
                            onClick={() => toggle(g, c.id)}
                          />
                        </Tooltip.Trigger>
                        <Tooltip.Content side="top">
                          {decided && kept ? `Kept · Space to unkeep` : `Keep this ${g.char} · Space`}
                        </Tooltip.Content>
                      </Tooltip>
                      <Tooltip>
                        <Tooltip.Trigger asChild>
                          <IconButton
                            className="tile__star"
                            icon={isDefault ? StarFill : StarOutline}
                            label="Default"
                            aria-pressed={isDefault}
                            variant="ghost"
                            size="xs"
                            tabIndex={-1}
                            onClick={() => star(g, c.id)}
                          />
                        </Tooltip.Trigger>
                        <Tooltip.Content side="top">
                          {isDefault ? `The default ${g.char}` : `Make this ${g.char} the default`} · <kbd>S</kbd>
                        </Tooltip.Content>
                      </Tooltip>
                    </div>
                    {/* In the toggle's name already; shown under the box for the eye */}
                    {c.flags.length > 0 && <span className="tile__flags" aria-hidden="true">{c.flags.join(', ')}</span>}
                    {c.corrections && hasCorrections(c.corrections) && <span className="tile__corrected" aria-hidden="true">corrected</span>}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
      </TooltipProvider>
    </section>
  );
}
