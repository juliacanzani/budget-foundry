import { useEffect, useState } from 'react';
import { ContentIndicator, IconButton, Sidebar, StepIndicator } from '@tangible/ui';
import { Close, Redo, SidebarExpand } from '@tangible/ui/icons/system/index.js';
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

type Props = { stages: Stage[]; decided: number; characters: number };

function StageList({ stages, decided, characters }: Props) {
  const toChoose = characters - decided;
  return (
    <ol className="stages">
      {STAGES.map((s) => {
        const state = stateOf(s.key, stages);
        const current = s.key === 'cull';
        return (
          <li key={s.name} aria-current={current ? 'step' : undefined} className={current ? 'is-current' : undefined}>
            <span className="stages__state">
              {state && <StateIndicator state={state} />}
              {current && (
                <StepIndicator value={characters ? (100 * decided) / characters : 0} status={toChoose ? 'in-progress' : 'complete'}
                  size="xs" label={`${decided} of ${characters} chosen`} />
              )}
            </span>
            <span className="stages__name">
              {s.name}
              {current && toChoose > 0 && <span className="stages__note">{toChoose} to choose</span>}
              {!current && s.cli && <span className="stages__note">{state === 'stale' ? 'Out of date · ' : ''}CLI: {s.cli}</span>}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

// Collapsed or not, remembered per browser
const COLLAPSED_KEY = 'budget-foundry:rail-collapsed';
function readCollapsed() {
  try { return localStorage.getItem(COLLAPSED_KEY) === '1'; } catch { return false; }
}

/** The desktop sidebar. The list sits straight in the Sidebar, not in its Nav, so it survives
    the collapse as a column of rings; the names are hidden from view only, so screen readers
    keep them. Phones get StagesMenu instead (app.css swaps them). */
export function StageRail(props: Props) {
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const onCollapsedChange = (next: boolean) => {
    setCollapsed(next);
    try { if (next) localStorage.setItem(COLLAPSED_KEY, '1'); else localStorage.removeItem(COLLAPSED_KEY); } catch { /* not saved */ }
  };
  return (
    <Sidebar className="rail" aria-label="Stages" collapsible collapsed={collapsed} onCollapsedChange={onCollapsedChange}>
      <Sidebar.Toggle showTooltip tooltipSide="right" variant="ghost" size="sm" />
      <StageList {...props} />
    </Sidebar>
  );
}

// Where the rail gives way to the menu; matches the breakpoint in app.css
const NARROW = '(max-width: 52rem)';

/** Phones: the header button, and the stages in Sidebar's drawer. */
export function StagesMenu(props: Props) {
  const [open, setOpen] = useState(false);
  // Widening the window brings the rail back, so the drawer has nothing left to do
  useEffect(() => {
    const mq = window.matchMedia(NARROW);
    const on = () => { if (!mq.matches) setOpen(false); };
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, []);
  return (
    <>
      <IconButton className="stages-menu" icon={SidebarExpand} label="Stages" showTooltip tooltipSide="bottom"
        variant="ghost" size="sm" aria-haspopup="dialog" onClick={() => setOpen(true)} />
      <Sidebar drawer open={open} onClose={() => setOpen(false)} position="left" aria-label="Stages" className="stages-drawer">
        <Sidebar.Header>
          <h2>Stages</h2>
          <IconButton className="stages-drawer__close" icon={Close} label="Close" variant="ghost" size="sm" onClick={() => setOpen(false)} />
        </Sidebar.Header>
        {/* Not Sidebar.Nav: nothing here navigates, it's a status list */}
        <StageList {...props} />
      </Sidebar>
    </>
  );
}
