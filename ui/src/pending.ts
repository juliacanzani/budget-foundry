import { useSyncExternalStore } from 'react';

/** How many saves are still on their way to a fresh preview. The preview shows a
    loader while any are, since the server takes a moment to rebuild. */
let count = 0;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

export async function track<T>(work: Promise<T>): Promise<T> {
  count++; emit();
  try { return await work; } finally { count--; emit(); }
}

export const usePending = () =>
  useSyncExternalStore((l) => { listeners.add(l); return () => listeners.delete(l); }, () => count > 0);
