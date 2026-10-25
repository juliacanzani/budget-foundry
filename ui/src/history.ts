import { useSyncExternalStore } from 'react';

/**
 * Global undo and redo, after the LMS course builder's undo manager: finished changes
 * only (a slider records on release, not per step), a new change drops the redo side.
 * Each record undoes by writing its old value back through the API with the new one as
 * the expected current value, so a change made elsewhere since is refused, not lost.
 * Session only; candidate IDs are content hashes, so nothing in here goes stale.
 */
export type Change = { label: string; undo: () => Promise<unknown>; redo: () => Promise<unknown> };

// Two stacks; the top of each (its last item) is the next to undo or redo
let past: Change[] = [];
let future: Change[] = [];
let busy = false;
let snapshot = { canUndo: false, canRedo: false, busy: false, undoLabel: '', redoLabel: '' };
const listeners = new Set<() => void>();

function emit() {
  snapshot = {
    canUndo: past.length > 0 && !busy, canRedo: future.length > 0 && !busy, busy,
    undoLabel: past.at(-1)?.label ?? '', redoLabel: future.at(-1)?.label ?? '',
  };
  listeners.forEach((l) => l());
}

export function record(change: Change) {
  past.push(change);
  future = [];
  emit();
}

async function step(from: Change[], to: Change[], run: (c: Change) => Promise<unknown>, done: string): Promise<string | null> {
  const c = from.pop();
  if (!c) return null;
  busy = true; emit();
  try {
    await run(c);
    to.push(c);
    return `${c.label} — ${done}`;
  } catch (err) {
    // Changed elsewhere since, or the server refused: this record can't apply any more
    return `Couldn't ${done === 'undone' ? 'undo' : 'redo'} “${c.label}”: ${err instanceof Error ? err.message : String(err)}`;
  } finally {
    busy = false; emit();
  }
}

export const undo = () => step(past, future, (c) => c.undo(), 'undone');
export const redo = () => step(future, past, (c) => c.redo(), 'redone');

export function useHistory() {
  return useSyncExternalStore((l) => { listeners.add(l); return () => listeners.delete(l); }, () => snapshot);
}
