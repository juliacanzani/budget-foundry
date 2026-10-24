import { useMemo, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, Notice } from '@tangible/ui';
import { api, type Check } from './api';
import { CullView } from './CullView';
import type { Frame } from './GlyphArt';
import { LookAlikes } from './LookAlikes';
import { Preview } from './Preview';
import { StageRail } from './StageRail';

export function App() {
  const qc = useQueryClient();
  const project = useQuery({ queryKey: ['project'], queryFn: api.project });
  const glyphs = useQuery({ queryKey: ['glyphs'], queryFn: api.glyphs });
  const [message, setMessage] = useState('');
  const [building, setBuilding] = useState(false);
  const [checks, setChecks] = useState<Check[] | null>(null);
  const [buildError, setBuildError] = useState<string | null>(null);
  const events = useRef<EventSource | null>(null);

  // One frame for every tile, so sizes compare honestly across characters.
  const frame: Frame | null = useMemo(() => {
    if (!project.data || !glyphs.data) return null;
    const m = project.data.metrics;
    let top = m.cap * 1.25, bottom = -m.descender * 1.25;
    for (const g of glyphs.data) for (const c of g.candidates) { top = Math.max(top, c.ymax + 20); bottom = Math.min(bottom, c.ymin - 20); }
    return { top, bottom, cap: m.cap, xheight: m.xheight, descender: m.descender };
  }, [project.data, glyphs.data]);

  const build = async () => {
    setBuilding(true); setChecks(null); setBuildError(null); setMessage('Building the font…');
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
        setChecks(job.result.checks);
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
        <p className="app__name"><span className="app__product">Budget Foundry</span> {project.data.name}</p>
        <Button size="sm" theme="primary" label="Build font" loading={building} loadingLabel="Building" onClick={build} />
      </header>
      <StageRail stages={project.data.stages} toChoose={project.data.characters - project.data.decided} />
      <main className="app__main" id="main">
        {(checks || buildError) && (
          <Notice theme={buildError ? 'danger' : checks!.some((c) => c.status === 'fail') ? 'warning' : 'success'} dismissible onDismiss={() => { setChecks(null); setBuildError(null); }}>
            <Notice.Head title={buildError ? 'Build failed' : 'Font built'} />
            <Notice.Body>
              {buildError ? <p>{buildError}</p> : (
                <ul className="checks">
                  {checks!.map((c) => (
                    <li key={c.check} data-status={c.status}><strong>{c.check}</strong> <span>{c.status}</span>: {c.detail}</li>
                  ))}
                </ul>
              )}
            </Notice.Body>
          </Notice>
        )}
        <LookAlikes glyphs={glyphs.data} frame={frame} />
        <CullView glyphs={glyphs.data} frame={frame} announce={setMessage} />
      </main>
      <footer className="app__preview">
        <Preview frame={frame} />
      </footer>
      <p className="tui-visually-hidden" role="status" aria-live="polite">{message}</p>
    </div>
  );
}
