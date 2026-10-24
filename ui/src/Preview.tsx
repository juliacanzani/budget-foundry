import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Field, TextInput } from '@tangible/ui';
import { api, type Preview as PreviewData } from './api';
import type { Frame } from './GlyphArt';

const LINE_HEIGHT = 64;

function Line({ data, frame, label }: { data: PreviewData | undefined; frame: Frame; label: string }) {
  if (!data) return <div className="preview__line is-loading" aria-hidden="true" />;
  const span = frame.top - frame.bottom;
  const width = Math.max(1, data.width);
  return (
    <figure className="preview__line">
      <figcaption>{label}</figcaption>
      <svg height={LINE_HEIGHT} width={(width * LINE_HEIGHT) / span} viewBox={`0 ${-frame.top} ${width} ${span}`} aria-hidden="true" focusable="false">
        <g transform="scale(1,-1)">
          {data.glyphs.map((g, i) => g.path && <path key={i} d={g.path} transform={`translate(${g.x} 0)`} />)}
        </g>
      </svg>
    </figure>
  );
}

/** The current picks, set by HarfBuzz from an unkerned build, alternates off and on. */
export function Preview({ frame }: { frame: Frame }) {
  const [text, setText] = useState('Hamburgefonstiv: the quick brown fox, 2026!');
  const [debounced, setDebounced] = useState(text);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(text), 200);
    return () => clearTimeout(t);
  }, [text]);

  const off = useQuery({ queryKey: ['preview', debounced, false], queryFn: () => api.preview(debounced, false), placeholderData: (d) => d });
  const on = useQuery({ queryKey: ['preview', debounced, true], queryFn: () => api.preview(debounced, true), placeholderData: (d) => d });
  const missing = on.data?.missing ?? [];

  return (
    <section className="preview" aria-labelledby="preview-title">
      <div className="preview__controls">
        <h2 id="preview-title" className="tui-text-style-overline">Preview</h2>
        <Field>
          <Field.Label>Sample text</Field.Label>
          <Field.Control>
            <TextInput size="sm" value={text} maxLength={500} onChange={(e) => setText(e.target.value)} />
          </Field.Control>
          {missing.length > 0 && <Field.HelperText>Not in the font yet: {missing.join(' ')}</Field.HelperText>}
        </Field>
      </div>
      {/* Long samples scroll sideways; the region takes focus so the keyboard can scroll it too. */}
      <div className="preview__lines" role="region" aria-label="Preview lines" tabIndex={0}>
        <Line data={off.data} frame={frame} label="One glyph per letter" />
        <Line data={on.data} frame={frame} label="Alternates cycling" />
      </div>
      {on.isError && <p className="preview__error" role="status">Preview failed: {String(on.error)}</p>}
    </section>
  );
}
