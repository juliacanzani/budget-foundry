import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, IconButton, Notice, Sidebar } from '@tangible/ui';
import { Close, Redo, Undo } from '@tangible/ui/icons/system/index.js';
import { systemTheme, type Mode } from './theme';
import { ThemeButton, themeLabel } from './ThemeButton';
import { api, type BuildResult as Result } from './api';
import { BuildResult } from './BuildResult';
import { CullView } from './CullView';
import type { Frame } from './GlyphArt';
import { redo, undo, useHistory } from './history';
import { Inspector } from './Inspector';
import { LookAlikes } from './LookAlikes';
import { Preview } from './Preview';
import { StageRail, StagesMenu } from './StageRail';

// Where the side columns give way to drawers; matches the breakpoint in app.css
const NARROW = '(max-width: 52rem)';
function useNarrow() {
  const [narrow, setNarrow] = useState(() => window.matchMedia(NARROW).matches);
  useEffect(() => {
    const mq = window.matchMedia(NARROW);
    const on = () => setNarrow(mq.matches);
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, []);
  return narrow;
}

// ⌘Z and ⇧⌘Z belong to a text field while you type in one; sliders and buttons pass them on
const typing = (t: EventTarget | null) =>
  t instanceof HTMLElement && (t.isContentEditable || t instanceof HTMLTextAreaElement
    || (t instanceof HTMLInputElement && !['range', 'checkbox', 'radio', 'button'].includes(t.type)));

export function App({ mode, resolved, onModeChange }: { mode: Mode; resolved: 'light' | 'dark'; onModeChange: (m: Mode) => void }) {
  const qc = useQueryClient();
  const project = useQuery({ queryKey: ['project'], queryFn: api.project });
  const glyphs = useQuery({ queryKey: ['glyphs'], queryFn: api.glyphs });
  const [message, setMessage] = useState('');
  const [building, setBuilding] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [buildError, setBuildError] = useState<string | null>(null);
  const events = useRef<EventSource | null>(null);
  const [active, setActive] = useState<string | null>(null);
  const [drawer, setDrawer] = useState(false);
  const narrow = useNarrow();
  const inspectorHeading = useRef<HTMLHeadingElement>(null);
  const history = useHistory();

  useEffect(() => { if (!narrow) setDrawer(false); }, [narrow]);

  const step = async (which: 'undo' | 'redo') => {
    if (building) return;
    const m = await (which === 'undo' ? undo() : redo());
    if (m) setMessage(m);
  };
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.altKey || typing(e.target)) return;
      const k = e.key.toLowerCase();
      if (k === 'z') { e.preventDefault(); step(e.shiftKey ? 'redo' : 'undo'); }
      else if (k === 'y' && e.ctrlKey && !e.metaKey) { e.preventDefault(); step('redo'); }
    };
    window.addEventListener('keydown', on);
    return () => window.removeEventListener('keydown', on);
  });

  const inspect = (_id: string, how: 'pointer' | 'keyboard') => {
    if (narrow) setDrawer(true);
    else if (how === 'keyboard') inspectorHeading.current?.focus();
  };

  // One frame for every tile, so sizes compare honestly across characters.
  const frame: Frame | null = useMemo(() => {
    if (!project.data || !glyphs.data) return null;
    const m = project.data.metrics;
    let top = m.cap * 1.25, bottom = -m.descender * 1.25;
    for (const g of glyphs.data) for (const c of g.candidates) { top = Math.max(top, c.ymax + 20); bottom = Math.min(bottom, c.ymin - 20); }
    return { top, bottom, cap: m.cap, xheight: m.xheight, descender: m.descender };
  }, [project.data, glyphs.data]);

  const build = async () => {
    setBuilding(true); setResult(null); setBuildError(null); setMessage('Building the font…');
    events.current?.close();
    const es = new EventSource('/api/events');
    events.current = es;
    es.onmessage = async (ev) => {
      const e = JSON.parse(ev.data);
      if (e.job !== 'build' || !e.state) return;
      es.close();
      const job = await api.job('build');
      setBuilding(false);
      qc.invalidateQueries({ queryKey: ['project'] });
      if (job.state === 'done' && job.result) {
        setResult(job.result);
        const failed = job.result.checks.filter((c) => c.status === 'fail').length;
        setMessage(failed ? `Built, ${failed} check${failed === 1 ? '' : 's'} failed` : 'Built, every check passed');
      } else {
        setBuildError(job.error ?? 'Build failed'); setMessage('Build failed');
      }
    };
    try { await api.build(); } catch (err) { es.close(); setBuilding(false); setBuildError(String(err)); setMessage('Build failed'); }
  };

  if (project.isError || glyphs.isError) {
    return (
      <main className="app-error">
        <Notice theme="danger"><Notice.Head title="Can't reach the project" /><Notice.Body>{String(project.error ?? glyphs.error)}</Notice.Body></Notice>
      </main>
    );
  }
  if (!project.data || !glyphs.data || !frame) return <p className="app-loading" role="status">Loading the project…</p>;

  return (
    <div className="app">
      <header className="app__bar">
        <StagesMenu stages={project.data.stages} decided={project.data.decided} characters={project.data.characters} />
        <p className="app__name"><span className="app__product">Budget Foundry</span> {project.data.name}</p>
        <span className="app__history">
          <IconButton icon={Undo} label={history.canUndo ? `Undo: ${history.undoLabel}` : 'Undo'} showTooltip tooltipSide="bottom"
            variant="ghost" size="sm" disabled={!history.canUndo || building} aria-keyshortcuts="Meta+Z Control+Z" onClick={() => step('undo')} />
          <IconButton icon={Redo} label={history.canRedo ? `Redo: ${history.redoLabel}` : 'Redo'} showTooltip tooltipSide="bottom"
            variant="ghost" size="sm" disabled={!history.canRedo || building} aria-keyshortcuts="Meta+Shift+Z Control+Shift+Z" onClick={() => step('redo')} />
        </span>
        <ThemeButton mode={mode} resolved={resolved} onChange={(m) => {
          onModeChange(m);
          const r = m === 'system' ? systemTheme() : m;
          setMessage(themeLabel(m, r).replace('. Click to change', ''));
        }} />
        <Button size="sm" theme="primary" label="Build font" loading={building} loadingLabel="Building" onClick={build} />
      </header>
      <StageRail stages={project.data.stages} decided={project.data.decided} characters={project.data.characters} />
      <main className="app__main" id="main">
        <BuildResult result={result} error={buildError} onDismiss={() => { setResult(null); setBuildError(null); }} />
        <LookAlikes glyphs={glyphs.data} frame={frame} />
        <CullView glyphs={glyphs.data} frame={frame} maxKeep={project.data.max_keep} announce={setMessage}
          active={active} onActive={setActive} onInspect={inspect} />
      </main>
      <aside className="inspector" id="inspector" aria-label="Inspector">
        <Inspector ref={inspectorHeading} glyphs={glyphs.data} active={active} frame={frame} maxKeep={project.data.max_keep} announce={setMessage} />
      </aside>
      {/* Phones: the inspector as a drawer from the right, opened from a tile */}
      <Sidebar drawer open={drawer} onClose={() => setDrawer(false)} position="right" aria-label="Inspector" className="inspector-drawer">
        <div className="drawer-head">
          <h2>Inspector</h2>
          <IconButton icon={Close} label="Close" variant="ghost" size="sm" onClick={() => setDrawer(false)} />
        </div>
        <div className="inspector-drawer__body">
          <Inspector glyphs={glyphs.data} active={active} frame={frame} maxKeep={project.data.max_keep} announce={setMessage} />
        </div>
      </Sidebar>
      <footer className="app__preview">
        <Preview frame={frame} />
      </footer>
      <p className="tui-visually-hidden" role="status" aria-live="polite">{message}</p>
    </div>
  );
}
