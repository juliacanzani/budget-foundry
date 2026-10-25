// The local API (src/budget_foundry/server.py). Shapes mirror its JSON.

export type Stage = { name: string; state: 'not run' | 'stale' | 'done' };

export type Project = {
  name: string;
  mode: string;
  metrics: { upm: number; cap: number; xheight: number; descender: number; ascender: number; stroke: number };
  stages: Stage[];
  characters: number;
  decided: number;
  max_keep: number;      // the most versions of a character the font can cycle
  without_default: string[];
};

export type Candidate = {
  id: string;
  path: string;          // SVG path in font units, y up, origin at the left sidebearing
  advance: number;
  ymin: number;
  ymax: number;
  flags: string[];
  score: number;
  suggested: boolean;
  sheet: string;
};

export type Glyph = {
  char: string;
  codepoint: string;
  candidates: Candidate[];
  keep: string[];
  default: string | null;
  source: 'human' | 'ai' | 'auto' | null;
};

export type PreviewGlyph = { name: string; x: number; advance: number; path: string | null };
export type Preview = { width: number; glyphs: PreviewGlyph[]; missing: string[] };

export type Check = { check: string; status: 'pass' | 'warn' | 'fail'; detail: string };
export type BuildResult = {
  checks: Check[];
  files: { woff2: string; otf: string; specimen: string; css: string };
  export_to: string | null;
  blocked: boolean;
};
export type Job = { state: 'idle' | 'running' | 'done' | 'failed'; log?: string[]; error?: string; result?: BuildResult };

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ? String(body.detail) : `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  project: () => fetch('/api/project').then((r) => json<Project>(r)),
  glyphs: () => fetch('/api/glyphs').then((r) => json<Glyph[]>(r)),
  choose: (char: string, keep: string[], def: string | null) =>
    fetch(`/api/glyphs/${encodeURIComponent(char)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keep, default: def }),
    }).then((r) => json<Glyph>(r)),
  preview: (text: string, calt: boolean) =>
    fetch(`/api/preview?${new URLSearchParams({ text, calt: String(calt) })}`).then((r) => json<Preview>(r)),
  build: () => fetch('/api/build', { method: 'POST' }).then((r) => json<{ state: string }>(r)),
  exportFont: () => fetch('/api/export', { method: 'POST' }).then((r) => json<{ files: string[] }>(r)),
  job: (name: string) => fetch(`/api/jobs/${name}`).then((r) => json<Job>(r)),
  sourceTile: (id: string) => `/api/candidates/${encodeURIComponent(id)}/source.png`,
};
