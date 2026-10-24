import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Button, Chip, IconButton, SegmentedControl, Switch, Tooltip, TooltipProvider } from '@tangible/ui';
import { StarFill, StarOutline } from '@tangible/ui/icons/system/index.js';
import { api, type Glyph } from './api';
import { GlyphArt, type Frame } from './GlyphArt';

type Kind = 'all' | 'letters' | 'figures' | 'punctuation';
const kindOf = (ch: string): Exclude<Kind, 'all'> =>
  /\p{L}/u.test(ch) ? 'letters' : /\p{N}/u.test(ch) ? 'figures' : 'punctuation';

const TILE_HEIGHT = 104;
const TILE_MIN_ART = 48;   // the 64px tile minus its xs (8px) side padding

type Props = { glyphs: Glyph[]; frame: Frame; announce: (msg: string) => void };

/**
 * One row per character, every candidate normalised and drawn on the guides.
 * Keyboard: arrows move (up and down between characters), Space keeps, S stars the default.
 * One tab stop for the whole list (roving focus); the shortcuts only act on a
 * focused tile, so they never fire while typing elsewhere.
 */
export function CullView({ glyphs, frame, announce }: Props) {
  const qc = useQueryClient();
  const [kind, setKind] = useState<Kind>('all');
  const [onlyUndecided, setOnlyUndecided] = useState(false);
  const [showSource, setShowSource] = useState(false);
  const [active, setActive] = useState<string | null>(null);
  const tiles = useRef(new Map<string, HTMLButtonElement>());

  const visible = useMemo(
    () => glyphs.filter((g) => (kind === 'all' || kindOf(g.char) === kind) && (!onlyUndecided || g.keep.length === 0)),
    [glyphs, kind, onlyUndecided],
  );
  const undecided = glyphs.filter((g) => g.keep.length === 0 && g.candidates.length > 0);

  const choose = useMutation({
    mutationFn: ({ char, keep, def }: { char: string; keep: string[]; def: string | null }) => api.choose(char, keep, def),
    onMutate: async ({ char, keep, def }) => {
      await qc.cancelQueries({ queryKey: ['glyphs'] });
      const before = qc.getQueryData<Glyph[]>(['glyphs']);
      qc.setQueryData<Glyph[]>(['glyphs'], (gs) =>
        gs?.map((g) => (g.char === char ? { ...g, keep, default: keep.length ? def ?? keep[0] : null, source: 'human' } : g)),
      );
      return { before };
    },
    onError: (err, _vars, ctx) => {
      if (ctx?.before) qc.setQueryData(['glyphs'], ctx.before);
      announce(`Not saved: ${err instanceof Error ? err.message : String(err)}`);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['glyphs'] });
      qc.invalidateQueries({ queryKey: ['preview'] });
      qc.invalidateQueries({ queryKey: ['project'] });
    },
  });

  const describe = (g: Glyph, keep: string[], def: string | null) => {
    if (!keep.length) return `${g.char}: nothing kept`;
    const n = g.candidates.findIndex((c) => c.id === def) + 1;
    return `${g.char}: ${keep.length} kept, default is candidate ${n}`;
  };

  const save = (g: Glyph, keep: string[], def: string | null) => {
    const d = keep.length ? (def && keep.includes(def) ? def : keep[0]) : null;
    choose.mutate({ char: g.char, keep, def: d });
    announce(describe(g, keep, d));
  };

  // Undecided characters start from the suggestions the moment you touch them.
  const startingKeep = (g: Glyph) => (g.keep.length ? g.keep : g.candidates.filter((c) => c.suggested).map((c) => c.id));

  const toggle = (g: Glyph, id: string) => {
    const keep = startingKeep(g);
    const next = keep.includes(id) ? keep.filter((k) => k !== id) : [...keep, id];
    save(g, next, g.keep.length ? g.default : next[0] ?? null);
  };

  const star = (g: Glyph, id: string) => {
    const keep = startingKeep(g);
    save(g, keep.includes(id) ? keep : [...keep, id], id);
  };

  const keepSuggested = (list: Glyph[]) => {
    for (const g of list) {
      const keep = g.candidates.filter((c) => c.suggested).map((c) => c.id);
      if (keep.length) choose.mutate({ char: g.char, keep, def: keep[0] });
    }
    announce(`Kept the suggestions for ${list.length} character${list.length === 1 ? '' : 's'}`);
  };

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
  }, []);

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
      case 's': case 'S': star(visible[gi], row[ci]); e.preventDefault(); return;
      default: return;
    }
    e.preventDefault();
    focusTile(target);
  };

  useEffect(() => {
    // Keep a live tab stop when filters remove the focused tile.
    if (active && !positions.flat().includes(active)) setActive(null);
  }, [positions, active]);

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
          <kbd>←</kbd> <kbd>→</kbd> <kbd>↑</kbd> <kbd>↓</kbd> move · <kbd>Space</kbd> keep · <kbd>S</kbd> or the star: default
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
                  <span className="cull__count">{g.keep.length} of {g.candidates.length} kept</span>
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
                    <div className="tile" data-kept={kept || undefined} data-tentative={(!decided && kept) || undefined}>
                      <button
                        ref={(el) => { if (el) tiles.current.set(c.id, el); else tiles.current.delete(c.id); }}
                        type="button"
                        className="tile__toggle"
                        aria-pressed={decided ? kept : false}
                        tabIndex={c.id === tabStop ? 0 : -1}
                        onFocus={() => setActive(c.id)}
                        onClick={() => toggle(g, c.id)}
                        onKeyDown={(e) => onKeyDown(e, gi, ci)}
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
                          {isDefault ? ', default' : ''}
                          {!decided && kept ? ', suggested' : ''}
                          {c.flags.length ? `, ${c.flags.join(', ')}` : ''}
                        </span>
                      </button>
                      {/* The pointer's way to star a default; the keyboard's is S on the tile. Out of the
                          tab order so the list stays one stop; screen readers still reach it in browse mode. */}
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
