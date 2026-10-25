import { useQueryClient } from '@tanstack/react-query';
import { api, NO_CORRECTIONS, type Candidate, type Corrections, type Glyph, type GlyphState } from './api';
import { record } from './history';

const message = (err: unknown) => (err instanceof Error ? err.message : String(err));

/** What decisions.json holds for a character. A rule's picks (curly singles) aren't in it. */
const stateOf = (g: Glyph): GlyphState =>
  g.source === 'auto' || !g.keep.length ? { keep: [], default: null } : { keep: g.keep, default: g.default };

// Undecided characters start from the suggestions the moment you touch them.
export const startingKeep = (g: Glyph) => (g.keep.length ? g.keep : g.candidates.filter((c) => c.suggested).map((c) => c.id));

/**
 * Every change to keepers, defaults and corrections goes through here, so each one is
 * saved, shown at once, announced and recorded for undo as one step.
 */
export function useDecisions(maxKeep: number, announce: (msg: string) => void) {
  const qc = useQueryClient();
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['glyphs'] });
    qc.invalidateQueries({ queryKey: ['preview'] });
    qc.invalidateQueries({ queryKey: ['project'] });
  };

  const write = async (char: string, to: GlyphState, expect?: GlyphState) => {
    await qc.cancelQueries({ queryKey: ['glyphs'] });
    const before = qc.getQueryData<Glyph[]>(['glyphs']);
    qc.setQueryData<Glyph[]>(['glyphs'], (gs) =>
      gs?.map((g) => (g.char === char ? { ...g, keep: to.keep, default: to.default, source: to.keep.length ? 'human' : null } : g)),
    );
    try {
      await api.choose(char, to.keep, to.default, expect);
    } catch (err) {
      if (before) qc.setQueryData(['glyphs'], before);
      throw err;
    } finally {
      refresh();
    }
  };

  const target = (keep: string[], def: string | null): GlyphState =>
    ({ keep, default: keep.length ? (def && keep.includes(def) ? def : keep[0]) : null });

  const describe = (g: Glyph, to: GlyphState) => {
    if (!to.keep.length) return `${g.char}: nothing kept`;
    const n = g.candidates.findIndex((c) => c.id === to.default) + 1;
    return `${g.char}: ${to.keep.length} kept, default is candidate ${n}`;
  };

  const choose = (g: Glyph, keep: string[], def: string | null, label: string) => {
    const from = stateOf(g), to = target(keep, def);
    announce(describe(g, to));
    write(g.char, to).then(
      () => record({ label, undo: () => write(g.char, from, to), redo: () => write(g.char, to, from) }),
      (err) => announce(`Not saved: ${message(err)}`),
    );
  };

  const full = (g: Glyph, keep: string[], id: string, verb: string) => {
    if (keep.includes(id) || keep.length < maxKeep) return false;
    announce(`${g.char} already has ${maxKeep} kept, the most the font can cycle. Unkeep one ${verb}.`);
    return true;
  };

  const toggleKeep = (g: Glyph, id: string) => {
    const keep = startingKeep(g);
    if (full(g, keep, id, 'first')) return;
    const next = keep.includes(id) ? keep.filter((k) => k !== id) : [...keep, id];
    const n = g.candidates.findIndex((c) => c.id === id) + 1;
    choose(g, next, g.keep.length ? g.default : next[0] ?? null, `${keep.includes(id) ? 'Unkeep' : 'Keep'} ${g.char} candidate ${n}`);
  };

  const makeDefault = (g: Glyph, id: string) => {
    const keep = startingKeep(g);
    if (full(g, keep, id, 'to make this the default')) return;
    const n = g.candidates.findIndex((c) => c.id === id) + 1;
    choose(g, keep.includes(id) ? keep : [...keep, id], id, `Default ${g.char}: candidate ${n}`);
  };

  const keepSuggested = (list: Glyph[]) => {
    const changes = list
      .map((g) => ({ g, from: stateOf(g), to: target(g.candidates.filter((c) => c.suggested).map((c) => c.id).slice(0, maxKeep), null) }))
      .filter((c) => c.to.keep.length);
    if (!changes.length) return;
    const label = changes.length === 1 ? `Keep suggestions for ${changes[0].g.char}` : `Keep suggestions for ${changes.length}`;
    announce(`Kept the suggestions for ${changes.length} character${changes.length === 1 ? '' : 's'}`);
    Promise.all(changes.map((c) => write(c.g.char, c.to))).then(
      () => record({
        label,
        undo: () => Promise.all(changes.map((c) => write(c.g.char, c.from, c.to))),
        redo: () => Promise.all(changes.map((c) => write(c.g.char, c.to, c.from))),
      }),
      (err) => announce(`Not saved: ${message(err)}`),
    );
  };

  const correct = (c: Candidate, next: Corrections, label: string) => {
    const from = c.corrections ?? NO_CORRECTIONS;
    const run = (to: Corrections, expect?: Corrections) => api.correct(c.id, to, expect).finally(refresh);
    return run(next).then(
      () => { record({ label, undo: () => run(from, next), redo: () => run(next, from) }); announce(label); },
      (err) => announce(`Not saved: ${message(err)}`),
    );
  };

  return { toggleKeep, makeDefault, keepSuggested, correct };
}
