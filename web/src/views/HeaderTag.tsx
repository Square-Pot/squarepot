// SPDX-License-Identifier: AGPL-3.0-or-later
// The header's brand mark, per the approved mockup v3 (#189, variant A): a real
// label of a random collection plant — a scannable Data Matrix carrying its
// number (never printed as text) and its botanical name set large on the
// vertical middle — whose two 45° bevels form a tip pointing at the heading.
import { encode } from "../domain/datamatrix";
import { plainText, type Run } from "../domain/names";
import { useI18n } from "../i18n";

// The label's geometry as drawn in the mockup: 292x56 units, 20-unit bevels
// meeting at the tip, a 34-unit Data Matrix at the left, the name from x=56.
const W = 292;
const H = 56;
const BEVEL = 20;
const DM = 34;
const DM_X = 10;
const DM_Y = 11;
const NAME_X = 56;
/** Where the name may reach to: short of the bevel, with a little air. */
const NAME_MAX = 208;

/** The label shape: a rectangle whose right end narrows into a tip. */
const SHAPE = `M1.5 1.5 L${String(W - BEVEL)} 1.5 L${String(W - 1.5)} ${String(H / 2)} L${String(W - BEVEL)} ${String(H - 1.5)} L1.5 ${String(H - 1.5)} Z`;

export function HeaderTag({ tag, name }: { tag: string; name: Run[] }) {
  const { t } = useI18n();
  const text = plainText(name);
  const modules = encode(tag);
  const module = DM / modules.length;
  const dark: { x: number; y: number }[] = [];
  modules.forEach((row, y) => {
    row.forEach((on, x) => {
      if (on) dark.push({ x: DM_X + x * module, y: DM_Y + y * module });
    });
  });
  const small = text.length > 18;
  return (
    <svg
      className="tag"
      width={(W * 0.8).toFixed(1)}
      height={(H * 0.8).toFixed(1)}
      viewBox={`0 0 ${String(W)} ${String(H)}`}
      role="img"
      aria-label={t(`Бирка: ${text}`, `Label: ${text}`)}
    >
      <path
        d={SHAPE}
        fill="#fff"
        stroke="#111"
        strokeWidth={1.5}
        style={{ filter: "drop-shadow(1px 1px 0 rgba(17,17,17,.16))" }}
      />
      <g fill="#111" shapeRendering="crispEdges">
        {dark.map((at, i) => (
          <rect
            key={i}
            x={at.x.toFixed(2)}
            y={at.y.toFixed(2)}
            width={module.toFixed(2)}
            height={module.toFixed(2)}
          />
        ))}
      </g>
      <text
        x={NAME_X}
        y={H / 2 + 6}
        className="tagname"
        fontSize={small ? 16.5 : 18.5}
        textLength={small && text.length > 26 ? NAME_MAX : undefined}
        lengthAdjust="spacingAndGlyphs"
      >
        {text}
      </text>
    </svg>
  );
}
