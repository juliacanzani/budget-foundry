import { Chip } from '@tangible/ui';
import type { Stage } from './api';

// The spec's ten stages. Only culling has a screen so far; the rest run from the CLI.
const STAGES: { name: string; key: string | null; cli: string }[] = [
  { name: 'Template', key: null, cli: 'template' },
  { name: 'Import', key: 'import', cli: 'add, import' },
  { name: 'Segment and label', key: 'segment', cli: 'segment' },
  { name: 'Normalise', key: 'normalise', cli: 'build' },
  { name: 'Cull and defaults', key: 'cull', cli: '' },
  { name: 'Trace', key: 'normalise', cli: 'build' },
  { name: 'Space', key: 'normalise', cli: 'build' },
  { name: 'Kern', key: 'build', cli: 'build' },
  { name: 'Features', key: 'build', cli: 'build' },
  { name: 'Build and export', key: 'build', cli: 'build, export' },
];

const THEME = { done: 'success', stale: 'warning', 'not run': 'secondary' } as const;

function stateOf(key: string | null, stages: Stage[]): Stage['state'] | null {
  if (key === null || key === 'cull') return null;
  const matching = stages.filter((s) => s.name === key || s.name.startsWith(`${key} `));
  if (!matching.length) return null;
  if (matching.some((s) => s.state === 'not run')) return 'not run';
  if (matching.some((s) => s.state === 'stale')) return 'stale';
  return 'done';
}

export function StageRail({ stages, toChoose }: { stages: Stage[]; toChoose: number }) {
  return (
    <nav className="rail" aria-label="Stages">
      <ol>
        {STAGES.map((s, i) => {
          const state = stateOf(s.key, stages);
          const current = s.key === 'cull';
          return (
            <li key={s.name} aria-current={current ? 'step' : undefined} className={current ? 'is-current' : undefined}>
              <span className="rail__n" aria-hidden="true">{i + 1}</span>
              <span className="rail__name">
                {s.name}
                {!current && s.cli && <span className="rail__cli">CLI: {s.cli}</span>}
              </span>
              {state && (
                <Chip size="sm" variant="outline" theme={THEME[state]}>{state}</Chip>
              )}
              {current && (
                <Chip size="sm" variant="outline" theme={toChoose ? 'warning' : 'success'}>{toChoose ? `${toChoose} to choose` : 'done'}</Chip>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
