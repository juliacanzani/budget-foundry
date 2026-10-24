// One glyph drawn from its normalised outline, on the font's guides. Purely visual:
// the button around it carries the name and state.

export type Frame = { top: number; bottom: number; xheight: number; cap: number; descender: number };

type Props = { path: string | null; advance: number; frame: Frame; height: number; guides?: boolean };

export function GlyphArt({ path, advance, frame, height, guides = true }: Props) {
  const span = frame.top - frame.bottom;
  const width = Math.max(8, (advance * height) / span);
  return (
    <svg
      className="glyph-art"
      width={width}
      height={height}
      viewBox={`0 ${-frame.top} ${advance} ${span}`}
      aria-hidden="true"
      focusable="false"
    >
      <g transform="scale(1,-1)">
        {guides && (
          <g className="glyph-art__guides">
            <line x1={0} x2={advance} y1={frame.cap} y2={frame.cap} />
            <line x1={0} x2={advance} y1={frame.xheight} y2={frame.xheight} />
            <line className="is-baseline" x1={0} x2={advance} y1={0} y2={0} />
            <line x1={0} x2={advance} y1={-frame.descender} y2={-frame.descender} />
          </g>
        )}
        {path && <path className="glyph-art__ink" d={path} />}
      </g>
    </svg>
  );
}
