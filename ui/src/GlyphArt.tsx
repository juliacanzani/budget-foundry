// One glyph drawn from its normalised outline, on the font's guides. Purely visual:
// the button around it carries the name and state.

import { useId, type CSSProperties } from 'react';

export type Frame = { top: number; bottom: number; xheight: number; cap: number; descender: number };

/** A correction not yet in the outline, drawn on top of it while the server catches up:
    rotate (degrees, anticlockwise), scale and width (across only) about the glyph's bottom middle, since
    placing re-seats it on its line; baseline in units; weight as a stroke (bolder) or
    an erode (thinner) of `pen` units, half a pen per side, as the build dilates. */
export type Live = { rotate: number; baseline: number; scale: number; width: number; pen: number };

type Props = { path: string | null; advance: number; frame: Frame; height: number; guides?: boolean; minWidth?: number; live?: Live };

export function GlyphArt({ path, advance, frame, height, guides = true, minWidth = 8, live }: Props) {
  const thin = useId();
  const span = frame.top - frame.bottom;
  const width = Math.max(minWidth, (advance * height) / span);
  // Narrow glyphs sit centred in a wider drawing, so the guides run the full width
  const units = (width * span) / height;
  const x0 = -(units - advance) / 2;
  return (
    <svg
      className="glyph-art"
      width={width}
      height={height}
      viewBox={`${x0} ${-frame.top} ${units} ${span}`}
      aria-hidden="true"
      focusable="false"
    >
      <g transform="scale(1,-1)">
        {guides && (
          <g className="glyph-art__guides">
            <line x1={x0} x2={x0 + units} y1={frame.cap} y2={frame.cap} />
            <line x1={x0} x2={x0 + units} y1={frame.xheight} y2={frame.xheight} />
            <line className="is-baseline" x1={x0} x2={x0 + units} y1={0} y2={0} />
            <line x1={x0} x2={x0 + units} y1={-frame.descender} y2={-frame.descender} />
          </g>
        )}
        {path && live && live.pen < 0 && (
          <filter id={thin} filterUnits="userSpaceOnUse" x={x0 - units} y={frame.bottom - span} width={units * 3} height={span * 3}>
            <feMorphology operator="erode" radius={-live.pen / 2} />
          </filter>
        )}
        {path && <path className="glyph-art__ink" d={path} style={live && liveStyle(live)}
          strokeWidth={live && live.pen > 0 ? live.pen : undefined} filter={live && live.pen < 0 ? `url(#${thin})` : undefined} />}
      </g>
    </svg>
  );
}

// The path's local y runs up (the group flips it), so its box's top is the glyph's bottom
const liveStyle = (l: Live): CSSProperties => ({
  transformBox: 'fill-box', transformOrigin: 'center top',
  transform: `translate(0px, ${l.baseline}px) rotate(${l.rotate}deg) scale(${l.scale * l.width}, ${l.scale})`,
  stroke: l.pen > 0 ? 'currentColor' : undefined, strokeLinejoin: 'round',
});
