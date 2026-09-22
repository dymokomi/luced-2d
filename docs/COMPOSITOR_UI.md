<!-- Catalogued from archive/Compositor (MIT) on 2026-09-22; the reference for luced-2d's window. -->
# Compositor UI catalogue (macOS/SwiftUI+AppKit)

All paths under `/Users/sedov/Dev/luce_dev/archive/Compositor/Compositor/`.

## 1. Window layout — `ContentView.swift`, `CompositorApp.swift`, `UI/ProjectTabs.swift`

Single `Window("Compositor", id: "editor")`, default 1180×780, first launch fills the display; min 800×520; forced `.preferredColorScheme(.dark)`, editor background `Color(white: 0.14)`; toolbar style `.unifiedCompact(showsTitle: false)`.

Vertical stack (`editorStack`):
1. **Contextual tool header** — always present (height 42 pt, `UI/ToolHeaderStyle.swift`: title font 13 semibold, control font 12, horizontal padding 18), followed by a Divider. With no tool it reads "Select a tool" so the canvas never jumps.
2. **Middle row**: tool rail (fixed 56 pt wide, vertical ScrollView) | Divider | canvas area (optional 18 pt rulers on top/left, `UI/CanvasRulers.swift`) | drag-resize divider | **Layers panel**.
3. Divider + **status bar**, fixed 30 pt high, font 11 monospaced-digit, secondary color, 18 pt padding.

Layers panel width persists via `@AppStorage("layersPanelWidth")`, default **252**, range **202…352** (`LayersPanel.widths`); resized by dragging its left Divider (`PanelResizeEdge`, 8 pt hit strip, column-resize pointer, "Drag to resize the panel"). Nothing is collapsible or detachable except the dialogs, which are real floating `NSPanel`s (`UI/FloatingPanel.swift`: titled+closable, floating, hides on deactivate, opens centered on the canvas, remembers position per panel name for the session; close button = Cancel).

**Toolbar (navigation side)**: "+" New canvas button (⌘N, also a drop target for new tabs), fixed spacer, then the **project tab strip** — width `max(200, windowWidth − 352)`, height 34, horizontally scrolling, edges masked with 28 pt fades. Primary-action side: `Fit` (⌘0), `100%` (⌘1), `plus.magnifyingglass` (⌘+), `minus.magnifyingglass` (⌘−).

**Tabs** (`ProjectTabButton`): capsule, height 28, title 12 pt (semibold when active), width 35…155, 5 pt dot before the title when modified, `xmark` close button (16×28). Active fill `white 0.12` + border `white 0.22`; inactive `0.035`/`0.08`; drop-target state uses accent 0.3 fill + 2 pt accent border. While an image/layer drag is in flight an extra dashed capsule "＋ New" slot appears at the end ("Drop to open in a new canvas"). Dropping files/layers onto a tab adds them to that project; onto the canvas imports at the drop point (accent 3 pt rounded border overlay while targeted).

**Status bar** content: zoom % (62 pt wide), `W × H px`, `sRGB · Transparent`; or "Ready when you are" with no document; `ProgressView` + "Working…"/"Importing images…" when busy; otherwise a long per-tool hint string (e.g. Brush: "Drag to paint · [ ] size · Shift-[ ] hardness · 1–0 opacity · Escape cancel · Space to pan").

With no document, `NewCanvasSheet` is shown inline as the welcome view over the canvas.

## 2. Layers panel — `UI/LayersPanel.swift`, `UI/NativeLayerList.swift`, `UI/LayerAppearanceControls.swift`, `UI/BlendModePicker.swift`

Header: "Layers" (12 semibold) + layer count (tertiary), padding 18. Divider.
**Appearance block** (padding 12, disabled unless a layer is editable): row "Blend" + `NSPopUpButton` capsule listing all blend modes grouped with separators — Normal | Darken, Multiply, Color Burn, Linear Burn | Lighten, Screen, Color Dodge, Linear Dodge (Add) | Overlay, Soft Light, Hard Light, Vivid Light, Linear Light, Pin Light, Hard Mix | Difference, Exclusion, Subtract, Divide | Hue, Saturation, Color, Luminosity. Hovering a menu item live-previews it on canvas. Row "Opacity" + Slider 0…1 + text field (44 pt) + "%"; Up/Down arrows step 1%, Shift 10%.

**List** = `NSTableView` wrapped in `NativeLayerList`. Row height **52 pt** (+24 pt per layer effect listed), intercell spacing 2, multi-selection allowed, faint 1-device-pixel white line (alpha 0.06) at each row's bottom; hidden-by-ancestor rows are drawn at alpha 0.35. Empty state: `square.3.layers.3d` icon + "No layers yet" + hint.

Row contents left→right: **eye** (20×32, `eye`/`eye.slash`; press-and-drag up/down the list paints visibility onto every row passed — Photoshop's swipe); **disclosure chevron** (16×24, `chevron.right`/`chevron.down`, groups only); **layer thumbnail** in a 36 pt slot — pixel layers and masks render the whole canvas shape with the layer in place, adjustments/text/folders use a 36×36 symbol icon (folder, `textformat`, or the adjustment's SF Symbol, Curves rotated 90°); **link button** (9×20 rotated `link` chain, shown only when a mask exists on a normal layer; empty but clickable when unlinked); **mask thumbnail** (30 pt slot, hidden when no mask, red "╱" overlay when the mask is disabled); **name label** (13 pt, single line, truncating, prefixed "↳ " when clipped) over a **subtitle** (10 pt secondary): "1920 × 1080 px", "Text", "Adjustment · Double-click to edit", "Folder", or "Clipped to <name>". Indentation = `min(depth,8) × 24` pt plus another 24 pt if clipped. Active target is shown by a 2 pt accent border on either the layer or the mask thumbnail.

**Effect sub-rows** (`LayerEffectRow`, 24 pt each) under the row: own eye + effect name (11 pt, dimmed when off); click selects, double-click opens its panel, Option-drag copies the effect to another layer.

Interactions: single click selects (Cmd/Shift multi-select), click on the name re-targets the layer (not its mask); double-click on the name renames inline (bezeled field; Return keeps, Esc/click-away reverts); double-click a thumbnail opens text editing or the adjustment editor. Cmd-click a thumbnail loads its selection (Cmd-Shift adds, Cmd-Option subtracts). Shift-click a mask thumbnail enables/disables it. Drag to reorder (above/below, or onto a folder row to nest); Option-drag copies/duplicates (whole folder trees included); Option-drag from a mask thumbnail copies the mask onto another row. Option over the **bottom 10 pt** of a row shows a custom create/release-clipping cursor and clicking toggles the clipping mask; Option elsewhere shows the duplicate cursor. Keyboard inside the list: all tool letters, Tab (cycle tool mode), X/D (swap/reset colors), digits (opacity), arrows (nudge with Move tool), Delete, Return/Esc for transforms.

Context menu (every row): Rename…, Hide/Show Layer, Add White Mask, Add Black Mask, Enable/Disable Mask, Delete Mask, Release Clipping Mask, Move Out of Folder, Delete Layer / Folder.

**Footer buttons** (plain, secondary, 8/12 pt hit padding): `plus.square` New blank layer (⇧⌘N) · `folder.badge.plus` Group selected layers (⌘G) · `rectangle.inset.filled` Add layer mask (selection becomes black) · `sparkles` menu → Stroke…, Drop Shadow…, Color Overlay…, Inner Shadow…, Outer Glow… · `circle.lefthalf.filled` menu → new adjustment layer (Hue/Saturation, Levels, Curves, Exposure, Gradient Map, Grain, Invert, Black & White, Color Balance) · spacer · `trash` whose label switches between Delete selected effect / layer mask / layers / layer.

## 3. Tool rail — `ContentView.toolRail`, `Document/EditorSession.swift` (lines 89–99)

56 pt wide, 36×36 buttons, 10 pt gaps, selected state = white 0.12 fill + 0.14 border, radius 7. Order and labels (tooltips as displayed):

| Tool | Icon | Key | Header (contextual bar) |
|---|---|---|---|
| Move / Transform | `arrow.up.left.and.arrow.down.right` | V | `TransformInspector`: "Transform"/"Transform Mask", Auto Select toggle, Show Controls toggle (⌘H), X, Y, W, H fields (85 pt), link/lock-ratio toggle, Scale % (110), rotation ° (75), Sampling picker, Flip H, Flip V, Cancel (Esc), Apply (Return) |
| Marquee | `rectangle.dashed` / `circle.dashed` | M (cycles Rectangle/Ellipse) | `LassoControls` |
| Lasso | `lasso` / custom polygonal icon | L (cycles Freehand/Polygonal) | `LassoControls` |
| Magic (Wand/Object) | `wand.and.stars` / custom object icon | W, Tab switches | `LassoControls` + wand or object options |
| Crop | `crop` | C | Ratio picker (Free, Original, 1:1, 4:3, 16:9), live "W × H px", Cancel, Apply Crop |
| Brush / Eraser | `paintbrush.pointed` | B / E | `BrushControls` |
| Spot Healing | `bandage` | J | `BrushControls` + type segmented picker |
| Clone Stamp | custom stamp icon | S | `BrushControls` + Aligned toggle, Sample This Layer/All Layers, "Option-click to set the source" |
| Smear (Blur/Smudge/Liquify) | `drop` | R | `BrushControls`, "Strength" instead of Opacity, mode picker |
| Gradient | custom dithered icon | G | Shape (Linear/Radial), gradient swatch, Colors style picker, Reverse, Opacity slider 0.01…1 + field, Cancel/Apply when drawing |
| Shape | `square.on.circle` | U, Shift-U/Tab cycles | Rectangle/Ellipse/Line picker; Line: Width slider 1…100 (field to 5000, default 4); Rectangle: Radius slider 0…200 (field to 5000, default 0); Fill swatch |
| Type | `textformat` | T | Font pop-up (210 pt), Size field px, color swatch, left/center/right align buttons, Tracking, Leading (empty = "Auto" = 120%), Edit Text / Cancel + Done |
| Eyedropper | `eyedropper` | I | "Eyedropper" + "Sample Ring" checkbox (default on) |
| Hand | `hand.draw` | H | "Pan" |
| Zoom | `magnifyingglass` | Z | "Zoom" + zoom % field (0.1–3200%) |

Below the tools: the **color palette** (`UI/ColorPaletteControls.swift`) — 24 pt foreground swatch over a background swatch offset 12 pt, a 45°-rotated swap arrow (X) and a reset arrow (D); on a mask, clicking a swatch offers "Black · Hide" / "White · Reveal".

`BrushControls` fields: Size 1–2000 px (default **40**), Hardness slider 0…1 + % field (default 1), Opacity/Strength slider 0.01…1 + % field (1–9 = 10–90%, 0 = 100%), Smoothing 0…100 (Brush only, default 0), plus a Color swatch or a Black/White mask-paint picker.

`LassoControls` fields: kind picker, **selection mode segmented control** (New/Add/Subtract/…, reflects held Shift/Option), Anti-alias toggle, Expand / Contract buttons with px fields (1–500, default 1), Feather button + field (1–250, default 2), Deselect; Wand adds Tolerance 0–255 (default 32), Sample Size, This Layer/All Layers, Contiguous (default on); Object Selection adds sample scope and Edge −10…10 px.

## 4. Menus & shortcuts — `CompositorApp.swift`, `UI/KeyboardShortcuts.swift`

- **File**: New Canvas… ⌘N, Open Project… ⌘O, Import Images…, Save ⌘S, Save As… ⇧⌘S, Export PNG… ⇧⌘E, Export JPEG… ⌥⇧⌘S, Close Project ⌘W.
- **Edit**: Undo/Redo ⌘Z/⇧⌘Z (named, e.g. "Undo Move Layer"), Cut ⌘X, Copy ⌘C, Copy Merged ⇧⌘C, Paste ⌘V, Keyboard Shortcuts…, Fill with Foreground Color ⌥⌫, Fill with Background Color ⌘⌫, Clear Selection Pixels, Content-Aware Fill… ⇧⌫.
- **Select**: All ⌘A, Deselect ⌘D, Inverse ⇧⌘I, Layer's Pixels, Subject ⌥⌘A, Mask's Black Areas, Expand…, Contract…, Feather….
- **Image**: Curves… ⌘M, Levels… ⌘L, Hue/Saturation… ⌘U, Black & White…, Color Balance…, Exposure…, Gradient Map…, Grain…, Invert (/Invert Mask) ⌘I, Canvas Size… ⌥⌘C, Image Size… ⌥⌘I, Flip Canvas Horizontal/Vertical.
- **Filter**: Gaussian Blur…, Motion Blur…, Add Noise…, Lens Correction…, Remove Background….
- **Layer**: New Adjustment Layer ▸ (9 kinds), Edit Adjustment…, Transform Layer/Selection ⌘T, Duplicate Layer / Layer via Copy ⌘J, Create/Release Clipping Mask ⌥⌘G, Group Selected Layers ⌘G, Move Out of Folder, New Blank Layer ⇧⌘N, Rename Layer…, Hide/Show Layer, Move Layer Up ⌘], Move Layer Down ⌘[, Merge ⌘E, Flip Layer H/V, Delete Layer/Layers/Layer Mask/effect.
- **View** (after .toolbar): Fit Canvas ⌘0, Actual Pixels ⌘1, Zoom In ⌘=, Zoom Out ⌘−, Pixel Grid (800% and above), Snap, Show Transform Controls ⌘H, Show ▸ Grid ⌘' / Guides ⌘;, Rulers ⌘R, Snap ⇧⌘;, Snap To ▸ Guides/Grid/Layers/Document Bounds, Lock Guides ⌥⌘;, Clear Guides.

Every shortcut is remappable: **Keyboard Shortcuts…** opens a 660 pt floating panel with a search field, three groups (Menus, Canvas & Layers, Text Editing), click-to-record buttons, conflict warning line, Restore Defaults / Cancel / Save. Canvas keys include tool letters, Tab (cycle mode), Space (temporary Hand), `[`/`]` brush size, Shift-`[`/`]` hardness, Shift-−/= blend mode, digits 0–9 opacity (two digits = exact %), arrows nudge 1 px (Shift 10 px, ⌘ moves pixels), ⌥P toggles Levels preview.

## 5. Dialogs & floating panels

Floating, non-modal, live-previewing panels (all `FloatingPanelController`; title-bar close = Cancel; Esc = Cancel, Return = OK):
- **Levels** (`UI/LevelsSheet.swift`, 440 pt): Channel picker (RGB/Red/Green/Blue), 150 pt histogram + triangle handles for input black/gamma/white, fields Input black, Gamma (2 dp), Input white, black→white output ramp with two handles, Output black/white fields (0–255), Sample eyedroppers, Auto buttons, Preview toggle (⌥P), Reset, Cancel/OK.
- **Hue/Saturation** (460 pt): Range menu, eyedroppers (set/add/remove) and targeted-adjustment hand, Hue (−180…180, or 0…360 colorizing), Saturation (−100…100 / 0…100), Lightness (−100…100), dual spectrum bars with 4 draggable band handles, "Apply outside this range instead", Colorize, Preview, Reset, Cancel/OK.
- **Filter panel** (`UI/FilterSheet.swift`, 380 pt) — per kind: Gaussian Blur radius 0.1–250 px (log slider); Motion Blur angle −90…90°, distance 1–2000 px; Add Noise amount 0.1–400%, Uniform/Gaussian, Monochromatic; Lens Correction distortion −100…100; Remove Background quality Basic/Advanced + Refine 0–40 px, Contrast 0–100%, Shift Edge −10…10; Content-Aware Fill (text only); Curves (260 pt graph, click to add up to 32 points, "Input x · Output y", Remove point, Reset curve); Exposure/Gradient Map/Grain/Black & White (6 color sliders + Tint)/Color Balance (Shadows/Midtones/Highlights triples + Preserve Luminosity). All have a Preview toggle, "Limited to the selection" note, Cancel/OK with progress text ("Applying…"/"Working…").
- **Effects** (`UI/EffectsSheet.swift`, 340 pt): Stroke (Outside/Inside, Color, Size 0–20 slider, Opacity), Drop Shadow (Opacity, Angle −180…180, Distance 0–100, Blur 0–100), Color Overlay, Inner Shadow, Outer Glow — all live-preview; Cancel/OK.
- **Expand/Contract/Feather Selection** (380 pt): Amount slider + field (1–500, feather 1–250), Cancel/OK.
- **Color picker** (`UI/ColorPickerSheet.swift`): 256 pt saturation/brightness square, 20 pt hue strip with arrows, 64 pt preview, R/G/B fields and hex, "Click the canvas to sample", OK/Cancel.

Window-modal sheets: **New canvas** (inline welcome too, 500 pt: Width/Height defaults 1920×1080 or clipboard size, "Transparent canvas · sRGB", validation 1–30,000 px, buttons Open project / Import image / Create canvas); **Canvas Size** (450 pt: units, W/H, Relative, Lock ratio, 3×3 anchor grid with names, extension Transparent/Foreground/Background/Black/White/Custom, byte estimate); **Image Size** (430 pt: units Pixels/Percent/Inches/Centimeters, W/H, Lock aspect ratio, Resolution px/in 1–9600, Resample + Sampling, live "Result: W × H pixels", Cancel/Resize); **Export JPEG** (560×330 live encoded preview, Quality 0–1 slider with %, transparency matte color, file-size readout, Cancel/Export…); **RAW Develop** (Exposure ±3 EV, Temperature 2000–12000 K, Tint ±150, Boost 0–1, live preview, Reset/Cancel/Import); **PSD conversion** list sheet. PNG/JPEG/Save use `NSSavePanel` sheets.

## 6. Canvas overlays — `Rendering/EditorCanvas.swift`, `TransformOverlay.swift`, `BrushCursorOverlay.swift`, `UI/CanvasRulers.swift`

Rulers 18 pt (⌘R), dark `white 0.2`, 1-2-5 major steps ≈70 pt apart with 8 pt monospaced labels, minor ticks every 1/10 (3/5/8 pt lengths); dragging from a ruler creates a guide, dragging back onto a ruler deletes it. Guides: cyan `rgba(0,1,1,0.9)` hairlines spanning the whole view; Lock Guides ⌥⌘;. Layout grid (⌘'): majors every **64 px** solid `white 0.7 α0.45`, dotted subdivisions every **8 px** (drawn when ≥4 pt apart). Pixel grid from **800%**; crisp pixel rendering from **200%**. Snap guides while dragging are accent-colored lines. Marching ants: white line under a black `[4,4]` dash animated on an 8-phase timer. Transform box: accent 1 pt outline, eight white 7×7 accent-stroked handles plus an 8 pt round rotation handle 28 pt out from the top edge; distorted transforms hide rotation. Brush cursor: white 2.5 pt + black 1 pt circle at brush size, dashed inner ring while hardness is being dragged, crosshair for the clone source, and a clipped preview of what one click would stamp. Eyedropper sample ring: 24 pt gray ring split into new (top)/previous (bottom) colors. Zoom range 0.001–32 (0.1%–3200%); zoom via ⌘±, toolbar buttons, Zoom tool click / Option-click / horizontal drag, pinch, scroll; pan via Hand tool, held Space, or middle-drag; Fit leaves 96 pt of margin.
