import { useEffect, useState } from 'react';
import { IconButton, Sidebar, StepList } from '@tangible/ui';
import { Close, SidebarExpand } from '@tangible/ui/icons/system/index.js';
import type { Stage } from './api';

// The spec's ten stages. Only culling has a screen so far; the rest run from the CLI.
const STAGES: { name: string; key: string | null; cli: string }[] = [
  { name: 'Template', key: 'template', cli: 'template' },
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
  if (key === 'template') return stages.find((s) => s.name === 'template')?.state ?? 'not run';
  const matching = stages.filter((s) => s.name === key || s.name.startsWith(`${key} `));
  if (!matching.length) return null;
  if (matching.some((s) => s.state === 'not run')) return 'not run';
  if (matching.some((s) => s.state === 'stale')) return 'stale';
  return 'done';
}

const LABELS = { notStarted: 'Not run', complete: 'Done', current: 'current stage' };

type Props = { stages: Stage[]; decided: number; characters: number };

/** A status list, not navigation: StepList without onSelect renders plain rows. A stale
    stage is done but out of date, so it keeps its tick and gets the attention dot; the
    line under the name says it in words. */
function StageList({ stages, decided, characters }: Props) {
  const toChoose = characters - decided;
  return (
    <StepList className="stages" aria-label="Stages" current="Cull and defaults" labels={LABELS}>
      {STAGES.map((s) => {
        const current = s.key === 'cull';
        const state = current ? null : stateOf(s.key, stages);
        return (
          <StepList.Item key={s.name} value={s.name}
            status={current ? (toChoose ? 'in-progress' : 'complete') : state === 'not run' ? 'not-started' : 'complete'}
            progress={current && characters ? (100 * decided) / characters : undefined}
            attention={state === 'stale'}>
            <span className="stages__name">
              {s.name}
              {current && toChoose > 0 && <span className="stages__note">{decided} of {characters} chosen</span>}
              {!current && s.cli && <span className="stages__note">{state === 'stale' ? 'Out of date · ' : ''}CLI: {s.cli}</span>}
            </span>
          </StepList.Item>
        );
      })}
    </StepList>
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
        <Sidebar.Header className="drawer-head">
          <h2>Stages</h2>
          <IconButton icon={Close} label="Close" variant="ghost" size="sm" onClick={() => setOpen(false)} />
        </Sidebar.Header>
        {/* Not Sidebar.Nav: nothing here navigates, it's a status list */}
        <StageList {...props} />
      </Sidebar>
    </>
  );
}
