# eleusis UI catalogue

How eleusis-frameworks (`/Users/sedov/Dev/eleusis-frameworks`, Zig) and
eleusis-layout.2 (`/Users/sedov/Dev/eleusis-layout.2`) build their UI, as read
from the sources on 2026-09-22, so luce-ui and luced-2d can reproduce it. All
numbers are UI units (points); double at 2×. Colours are the authored sRGB
values (the app rotates them to Display-P3 and blends linear-premultiplied).

## Theme

Dark palette (`ui/theme.zig:154-214`), with eleusis-layout.2's overrides
(`app/theme.zig:50-85`) applied:

| Role | sRGB | Use |
|---|---|---|
| window = surface | 50,50,50 `#323232` | chrome and panes alike ("a layout tool's panes ARE the chrome") |
| tab_strip | 38,38,38 `#262626` | the recess a tab strip sits in; property-pane section headings |
| backdrop | 26,26,26 `#1A1A1A` | gaps between panes, divider gutters, every structural 1 px rule |
| surface_raised | 46,46,46 `#2E2E2E` | popover, menu, tooltip-like panels, raised button, table header |
| surface_sunken | 41,41,41 `#292929` | field well, slider groove, sunken (default) button, **pane bottom toolbar** |
| border | 58,58,58 `#3A3A3A` | ordinary border; property-row separator |
| border_focused | 150,150,150 `#969696` | focused border, drawn at 2× width |
| separator | white α0.10 | hairline between rows / menu sections |
| text | 217 `#D9D9D9` | primary text |
| text_muted | 140 `#8C8C8C` | secondary, placeholder, disabled labels, toolbar icons at rest |
| accent = selection | 231,160,63 `#E7A03F` | one orange for both |
| text_on_accent | black | 9.5:1 on the orange |
| selection_inactive | 120,84,40 `#785428` | selected row in an unfocused pane |
| hover / pressed | white α0.04 / α0.12 | washes composited over the resting fill; no fade |
| scrim / shadow | black α0.9 / α0.85 | modals |
| danger / warning | 232,84,74 / 232,172,74 | |
| scrollbar | 150 α0.55 | overlay thumb |
| row_stripe | white α0.006 | odd rows |

Metrics (`ui/theme.zig:267-312`): row_height 22, pad 8, gap 6,
corner_radius 6 (surfaces), corner_radius_small 5 (every control: buttons,
chips, fields, tabs, row highlights, menu rows, checkboxes), border_width 1
(2 when focused), text_size 13, input_height 26, icon_size 16, scroll_step 66.
Disabled = 0.2 opacity on the whole control (fill, border, label). Font: SF Pro
Text 13 pt, vertically centred by the font box. Icons: monochrome 16-unit
tiles fitted to the shorter side of their slot (so icon buttons are square).

## Window (eleusis-layout.2)

```
MENU BAR            h 28   fill window; titles hug text + 2×11 pad; 1 px backdrop rule below
DOCUMENT TAB STRIP  h 26
backdrop gap        h 6    (only above the workspace)
DOCK WORKSPACE             h = win - 54 - 6 - 24
1 px backdrop
STATUS BAR          h 24   fill window; pad 10/10; shows the hot control's hint, else document state
```
Default 1400 × 900. Default dock: `row(0.74 viewport | 0.26 col(0.24 boards,
0.40 assets, 0.36 properties))`. The menu bar is a mode: once open, moving
across titles switches menus. Dropdowns: width 220 (submenus 260), rows 22 with
pad 10/10, radius 5, hover fill; separators = 5 gap + 1 px `separator`;
shortcut hints right-aligned in text_muted; disabled rows at 0.2 opacity.

**There are no tooltips**: every control declares a one-line hint and the
status bar shows the hot one (a disabled control still reports its hint).

## Panes (`dock/root.zig`)

Tree of `area` (tab group: pane types + active) and n-ary `split` (axis,
fractions summing to 1). Metrics as the app sets them: header 26, divider 6
(grab band 6 + 2×9), min_area 120. Divider = a 6-unit `backdrop` gutter, no
centre line; resize cursors; dividers declared last so they win edges.
Drop zones: outer 28 % of a side = that edge (half-rect preview), inner =
centre (join as tab); preview fill selection α0.28 + 2-unit accent border, no
rounding; edge drop makes a 50/50 split; a pane type lives in at most one area
(dock = move). Layout persisted as one line in prefs.

### Header = the tab strip (the only header a pane has)
Height 26, fill `tab_strip`, no left pad, right pad 6, a 1 px `backdrop` rule
beneath (this line tops every pane). Tab: hug width 40..220, pad 10/10, spacing
4, corners **{5,5,0,0}**, fill = `surface` when active (tab and pane read as
one), pressed/hover wash otherwise, transparent at rest; icon 14×14 (text /
text_muted), title elided tail (min 34), × close 9×9 in a 14 slot for closable
tabs. `+` button 30 wide with a 16×16 icon, muted → text on hover. Clicks are
reported and applied after the layout pass, never during declaration.

### Bottom toolbar of a pane (`app/panes.zig:1314-1365`)
```
1 px rule, fill backdrop (#1A1A1A)          ← a DARK line, not the light separator
shelf: h 30 fixed, fill surface_sunken (#292929), pad left 6 / right 6, cross centre
       icon buttons 25×25, style plain (no resting fill), icon text_muted, zero pad
       spacer() pushes destructive actions (trash) to the far right
```
Runs edge to edge (the pane has no padding; the list above carries pad-top 8).
"A toolbar above a list reads as a header for it; below it reads as acting ON
it." Contents: Assets = add, swatch, folder, duplicate, …, trash; Boards =
new, duplicate, print, …, trash (disabled when one board). The Script pane's
bar differs: fill `window`, text buttons (Run raised+bordered, Open…/Save…
sunken) h 22.

### Properties pane (`app/panes.zig:1561-1681`)
Rows: h 22, pad left 8 / right 16 (scrollbar), label column fixed 50 in
text_muted, gap 6, value grows (read-only: trailing-aligned, head-elided, in
text). Between rows a 1-unit `border` rule. Wells inside rows: radius 0 and no
border (rows touch; a rounded corner between flush wells is a notch). Section
heading: 6 gap above, band h 22 pad 8/16 fill `tab_strip`, label text_muted.
Sections: name row, Transform (X, Y, Scale, Rotation, Opacity as drag
scrubbers), Crop, Color (26×14 swatch with 1 px border), Text (label column
72, rows 30), Info (read-only). Empty selection shows an empty pane. Content
height is counted (rows × 23), not measured.

## Controls (`ui/*.zig`)

- **Button**: hug width, grows to row height, pad 6/6 unless set, radius 5,
  border 1 only when `bordered` or focused (`border_focused`). Styles: sunken
  (default, surface_sunken), raised (surface_raised), plain (no resting fill),
  selected (accent fill + text_on_accent). Hover/pressed = white 4 % / 12 %
  washes over the resting fill; disabled = 0.2 opacity, no hover. Icon *or*
  text, never both. "Checked" = style selected (active tool, open menu title,
  Grid/Snap toggles). Sizes in the app: pane toolbar 25, tool rails 28,
  small property buttons 20, modal close 20×18.
- **Checkbox**: box 14×14 radius 5, on = accent fill + accent border, tick
  glyph in text_on_accent; label toggles it; row h 22, spacing 6.
- **Slider**: hit height 18, groove 4 (radius 2) surface_sunken, travelled
  part accent, knob 12 (radius 6) surface_raised with border; absolute
  positioning (press anywhere), arrows 1 %, shift ×10.
- **Number scrubber**: h 22, drag to change (threshold 2), click to type,
  ⌘-click resets; began/ended bracket one undo step.
- **Text field**: h 26 forced, fill surface_sunken always, border 1 → 2 on
  focus (border_focused), radius 5, text inset 6, caret 1 unit blinking 530 ms,
  commit-on-blur or cancel-on-blur policies.
- **Select**: button h 26 fill surface_raised, chevron 12 slot, radius 5;
  popup fill surface_raised, border 1, radius 6, pad 4, rows 26 with pad 8,
  current value in selection_inactive; flips above when out of room.
- **Table/list**: rows 22 virtualised; fill priority selected+focused
  selection → selected+unfocused selection_inactive → hover → odd row
  stripe; row radius 5 by default, **0 in the app's lists**; header row
  surface_raised; toggles (eye/lock/chevron) 20 wide, up to 4, drawn as real
  glyphs when off; indentation 20 per missing control column, 10 per tree
  depth; drop indicator 2-unit accent line; autoscroll while dragging.
- **Scrollbar**: overlay, 5 wide inset 2, thumb ≥ 24, radius 2.5, fill
  scrollbar → text_muted while dragged.
- **Separators**: structural rules are 1 px `backdrop`; hairlines between
  rows/menu sections are `separator`; property rows use `border`.
- **Modal**: surface_raised, border 1, radius 6, title bar h 26 fill window
  with a 1 px backdrop rule, body pad 16, scrim α0.9 fading in 120 ms.

## Viewport pane
Three reserved bands inset the canvas (never painted over it): left tool rail
40 wide (column, pad-top 8, spacing 3, fill window, 1 px backdrop rule on the
canvas edge, ten 28×28 buttons — active tool `selected` orange with black
icon, others sunken; every button's hint names the action and its shortcut),
right align rail 40 wide (mirror), bottom bar 34 high (fill surface, 1 px
backdrop rule on top, groups split by 2-wide `separator` rules with 6 gaps:
board size wells, printer, Grid/Snap toggles, then display selects, camera
readout, zoom %). The bar drops labels below 700 wide, the ODT select below
660, the display select below 540.

## Traps
1. surface == window == #323232; hierarchy comes from tab_strip 38,
   surface_sunken 41 and backdrop 26.
2. Every structural edge is a 1 px backdrop line, darker than its surroundings.
3. Rounding: 5 for controls, 6 for surfaces; dock tabs {5,5,0,0}; property
   wells and the app's list rows 0.
4. Disabled = 0.2 opacity on the whole control.
5. Hover/pressed are washes over the resting fill; nothing fades.
6. No tooltips; the status bar is the tooltip.
