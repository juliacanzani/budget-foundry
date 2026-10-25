import { useState } from 'react';
import { ContentIndicator, IconButton, StepIndicator } from '@tangible/ui';
import { Redo, SidebarCollapse, SidebarExpand } from '@tangible/ui/icons/system/index.js';
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

function stateOf(key: string | null, stages: Stage[]): Stage['state'] | null {
  if (key === null || key === 'cull') return null;
  const matching = stages.filter((s) => s.name === key || s.name.startsWith(`${key} `));
  if (!matching.length) return null;
  if (matching.some((s) => s.state === 'not run')) return 'not run';
  if (matching.some((s) => s.state === 'stale')) return 'stale';
  return 'done';
}

const WORDS = { notStarted: 'Not run', complete: 'Done', status: (s: string) => s };

/** The stage's state as a ring. StepIndicator has no "out of date", so stale gets a warning
    ring, decorative: the line under the name says it in words. */
function StateIndicator({ state }: { state: Stage['state'] }) {
  if (state === 'stale') return <ContentIndicator icon={Redo} theme="warning" size="xs" />;
  return <StepIndicator status={state === 'done' ? 'complete' : 'not-started'} size="xs" labels={WORDS} />;
}

// Collapsed or not, remembered per browser
const COLLAPSED_KEY = 'budget-foundry:rail-collapsed';
function readCollapsed() {
  try { return localStorage.getItem(COLLAPSED_KEY) === '1'; } catch { return false; }
}

export function StageRail({ stages, decided, characters }: { stages: Stage[]; decided: number; characters: number }) {
  const toChoose = characters - decided;
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const toggle = () => {
    setCollapsed(!collapsed);
    try { if (collapsed) localStorage.removeItem(COLLAPSED_KEY); else localStorage.setItem(COLLAPSED_KEY, '1'); } catch { /* not saved */ }
  };
  // Collapsed keeps the rings; the names stay in the accessibility tree, only hidden from view
  return (
    <nav className={`rail${collapsed ? ' is-collapsed' : ''}`} aria-label="Stages">
      <div className="rail__inner">
        <IconButton className="rail__toggle" icon={collapsed ? SidebarExpand : SidebarCollapse}
          label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} showTooltip tooltipSide="right"
          variant="ghost" size="sm" onClick={toggle} />
        <ol>
          {STAGES.map((s) => {
            const state = stateOf(s.key, stages);
            const current = s.key === 'cull';
            return (
              <li key={s.name} aria-current={current ? 'step' : undefined} className={current ? 'is-current' : undefined}>
                <span className="rail__state">
                  {state && <StateIndicator state={state} />}
                  {current && (
                    <StepIndicator value={characters ? (100 * decided) / characters : 0} status={toChoose ? 'in-progress' : 'complete'}
                      size="xs" label={`${decided} of ${characters} chosen`} />
                  )}
                </span>
                <span className="rail__name">
                  {s.name}
                  {current && toChoose > 0 && <span className="rail__cli">{toChoose} to choose</span>}
                  {!current && s.cli && <span className="rail__cli">{state === 'stale' ? 'Out of date · ' : ''}CLI: {s.cli}</span>}
                </span>
              </li>
            );
          })}
        </ol>
      </div>
    </nav>
  );
}
