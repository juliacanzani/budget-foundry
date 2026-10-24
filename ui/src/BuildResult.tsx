import { useState } from 'react';
import { Button, Icon, Notice } from '@tangible/ui';
import { AlertTriangle, CheckCircleFill, CloseCircleFill, Download, ExternalLink } from '@tangible/ui/icons/system/index.js';
import { api, type BuildResult as Result, type Check } from './api';

const ICON = { pass: CheckCircleFill, warn: AlertTriangle, fail: CloseCircleFill } as const;
const WORD = { pass: 'Passed', warn: 'Warning', fail: 'Failed' } as const;
const ORDER = { fail: 0, warn: 1, pass: 2 } as const;

function CheckItem({ c, detail }: { c: Check; detail: boolean }) {
  return (
    <li className="check" data-status={c.status}>
      <Icon name={ICON[c.status]} label={WORD[c.status]} />
      <span className="check__text">
        <span className="check__name">{c.check}</span>
        {detail && <span className="check__detail">{c.detail}</span>}
      </span>
    </li>
  );
}

/** What the build produced, what to do next, and the checks, problems first. */
export function BuildResult({ result, error, onDismiss }: { result: Result | null; error: string | null; onDismiss: () => void }) {
  const [exported, setExported] = useState<string[] | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  if (error) {
    return (
      <Notice theme="danger" dismissible onDismiss={onDismiss}>
        <Notice.Head title="The build stopped" />
        <Notice.Body><p>{error}</p><p>The font in the build folder is the last one that finished.</p></Notice.Body>
      </Notice>
    );
  }
  if (!result) return null;

  const checks = [...result.checks].sort((a, b) => ORDER[a.status] - ORDER[b.status]);
  const failed = checks.filter((c) => c.status === 'fail');
  const warned = checks.filter((c) => c.status === 'warn');
  const passed = checks.filter((c) => c.status === 'pass');
  const file = (name: string) => `/api/build/files/${encodeURIComponent(name)}`;

  const title = failed.length
    ? `Font built · ${failed.length} check${failed.length === 1 ? '' : 's'} failed`
    : warned.length ? `Font built · ${warned.length} warning${warned.length === 1 ? '' : 's'}` : 'Font built · every check passed';

  const doExport = async () => {
    setExporting(true); setExportError(null);
    try { setExported((await api.exportFont()).files); } catch (e) { setExportError(e instanceof Error ? e.message : String(e)); }
    setExporting(false);
  };

  return (
    <Notice theme={failed.length ? 'warning' : 'success'} dismissible onDismiss={onDismiss} className="build-result">
      <Notice.Head title={title} />
      <Notice.Body>
        <p className="build-result__next">
          {failed.length
            ? 'Export is blocked until the failed checks pass. The preview and the files below still work.'
            : result.export_to
              ? `Next: look it over in the specimen, then export to ${result.export_to}.`
              : 'Next: look it over in the specimen, then download the font, or set export_to in project.toml to send it straight to your site.'}
        </p>
        <div className="build-result__actions">
          <Button size="sm" theme="primary" label="Open specimen" rightIconName={ExternalLink}
            href={file(result.files.specimen)} target="_blank" />
          <Button size="sm" variant="outline" label="Download WOFF2" leftIconName={Download} href={file(result.files.woff2)} />
          {result.export_to && (
            <Button size="sm" variant="outline" label="Export" disabled={failed.length > 0} loading={exporting} loadingLabel="Exporting" onClick={doExport} />
          )}
        </div>
        {exported && <p className="build-result__done" role="status">Exported {exported.length} files to {result.export_to}.</p>}
        {exportError && <p className="build-result__error" role="alert">{exportError}</p>}
        {(failed.length > 0 || warned.length > 0) && (
          <ul className="checks" aria-label="Checks to look at">
            {[...failed, ...warned].map((c) => <CheckItem key={c.check} c={c} detail />)}
          </ul>
        )}
        <ul className="checks is-compact" aria-label="Passed checks">
          {passed.map((c) => <CheckItem key={c.check} c={c} detail={false} />)}
        </ul>
      </Notice.Body>
    </Notice>
  );
}
