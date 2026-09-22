# luced-2d — design

luced-2d is a free Photoshop replacement written in Luce: the feature set of
[Compositor](https://github.com/robbietilton/Compositor) (MIT, Mac-only, Swift),
the look and the engineering discipline of eleusis-layout, a GPU backend, and one
codebase for macOS, Windows and Linux.

This document records what was studied, what is missing, what gets built and in
which order. The three studies it distils are summarised in section 6.

## 1. What exists today

| Piece | State |
| --- | --- |
| `luce-base std.gpu` | A colored-triangle + coverage-mask rasterizer. No textures, no offscreen targets, no readback, no client shaders, fixed src-over blend. Metal on macOS; Vulkan on Windows only; **no Linux presentation or window**. |
| `luce-ui` | Good docking (`DStack`, `SplitView`), commands with shortcuts, high-DPI, 23 widgets, monospace text. `Painter` draws rectangles, triangles, lines and text only. `Raster.draw` turns pixels into triangles on the CPU every frame and is capped at 2048². |
| `luce-image` | Real codecs: PNG, JPEG, TIFF, EXR, multi-threaded. Not connected to luce-ui. |
| `luced-2d` | 559 lines: CPU raster, 16 layers, brush/eraser, snapshot undo, fit-to-window only. Everything in it is replaced. |

The blocker is one level below luce-ui: there is no way to put an image on the
GPU and draw it.

## 2. Architecture

Three packages, each with a real client:

```
luced-2d      (Luce)       the application: tools, panels, commands, theme
  ├─ luce-pixel (Luce Base) the image engine: document, tiles, render graph,
  │                         blend/adjust/filter shaders, brush, selections,
  │                         file format, PSD import; runs headless in tests
  ├─ luce-ui    (Luce Base) widgets, docking, theme roles, Painter.image
  ├─ luce-image (Luce Base) codecs
  └─ luce-base std.gpu      textures, targets, pipelines, readback
```

The canvas is not a widget; it is a second renderer (eleusis' load-bearing
finding). `luce-pixel` owns pixels and never imports `luce-ui`; the `Canvas`
widget in luced-2d only turns input into requests and draws the result plus
chrome (grid, guides, marquee, cursor) at screen resolution on top.

### 2.1 std.gpu, second version

Grow the boundary to what an image editor needs, nothing more, both backends at
parity, no vendor type crossing `std.gpu` (a test enforces it):

- **Textures**: `rgba8_unorm`, `rgba16_float`, `r8_unorm`; create, upload whole
  or by rows, mip levels, destroy with a stale-handle check ("wasDestroyed").
- **Targets**: render into a texture; readback to CPU bytes (export, eyedropper,
  alpha-aware hit tests).
- **Pipelines**: declared by the client — shader id, vertex layout, blend state
  (`over`, `replace`, `add`, `multiply`, custom factors), target format. Draws
  are a binding table (textures, uniforms) replayed by the backend. No lent
  encoders.
- **Shaders**: written once in GLSL (Vulkan dialect). A tool
  (`luce-base/tools/shaders.py`, needs `glslc` + `spirv-cross` only when a shader
  changes) emits a generated `.lucb` holding SPIR-V words and MSL source, checked
  in like the bootstrap snapshots. Metal compiles the MSL at runtime as it does
  today. Any package can ship shaders this way; `std.gpu` ships only the
  built-in ones (solid, image, coverage).
- **Offscreen queue**: compositing and export submit-and-wait on their own queue
  so a bake never blocks presentation.
- **Linux**: X11/Wayland window + Vulkan surface in `std.window` / `std.gpu`.

Blend is `over` with premultiplied alpha everywhere; `gpu.Color` gains alpha.

### 2.2 luce-ui additions

- `Painter.image(texture, source rect, destination rect, opacity)` and
  `Painter.rounded_rectangle`, gradients, dashed lines (marching ants).
  `luce_ui.Raster` is deleted; `luce_image.Image` uploads straight to a texture.
- Theme as **roles** (window, tab_strip, backdrop, surface, surface_raised,
  surface_sunken, border, border_focused, separator, text, text_muted, accent,
  text_on_accent, selection, selection_inactive, hover, pressed, danger,
  warning) with metrics (row_height, border_width, corner radius).
- Widgets: `slider`, `number_field` (drag-to-scrub), `checkbox`, `select`
  (dropdown), `tabs`, `tree_view` (layers: thumbnail, visibility, lock,
  drag-reorder into groups), `property_grid`, `ruler`, `status_bar`, `tooltip`,
  `floating_panel` (detachable modal editors), `curve_editor`, `gradient_editor`,
  `histogram`, `color_picker` (wheel/square + hex, not just three sliders),
  `image_view`, keyboard-navigable `menu_bar`.
- Input: OS file drop, image clipboard, raw two-finger pan/zoom, tablet pressure,
  custom cursor bitmaps, modifier state as live held keys.
- Shortcuts as a table with a duplicate-chord test; unbound is representable;
  user overrides merge per action.

### 2.3 luce-pixel

**Document** — a real tree, not a flat array with parent ids:

```
Document { width, height, dpi, color_space, root: Group, selection, guides }
Layer    { id, name, visible, locked, opacity, blend_mode, mask?, clip_to? , kind }
kind     = Raster(tiles) | Group(children, pass_through) | Adjustment(kind, params)
         | Text(...) | Shape(path, fill, stroke) | Fill(color|gradient|pattern)
```

Pixels are **tiles**: 256×256, `rgba16_float`, premultiplied, in the document's
colour space, resident on the GPU with a CPU shadow only for save. A layer's
`Tiles` is immutable and structurally shared: an edit produces a new `Tiles`
that reuses every untouched tile (Compositor's `RasterSnapshot`, tiled down to
the base). Layers keep native resolution and a non-destructive transform.

**Render graph** — the eleusis model in three passes: *validate* (bounds +
identity hash, also used for hit tests), *request* (region, scale, level, detail
exact|interactive), *evaluate* (tiles for exactly that region, cache first).
Node kinds: `tiles, place, mask, clip, adjust, filter, effect, over, group,
paper, display`. `over` is a node. Cache key = identity hash · region · level;
identity hash = kind + parameters + inputs' hashes, so changing a top layer's
opacity invalidates nothing below it. Regions come from a fixed lattice in
document space so keys survive panning.

**One renderer for screen and export**, differing only in the request: the canvas
asks for the viewport at the zoom's pyramid level with `interactive` detail;
export asks for the whole document at level 0, `exact`, no chrome, over paper,
from a document snapshot, and refuses rather than writes a wrong file. Above
100 % the screen shows document pixels scaled nearest-neighbour (Compositor's
crisp zoom, eleusis R8). No second engine, no silent fallback.

**Blend modes**: the 24 Photoshop modes in one shader set (Normal, Dissolve,
Darken, Multiply, Color Burn, Linear Burn, Darker Color, Lighten, Screen, Color
Dodge, Linear Dodge, Lighter Color, Overlay, Soft Light, Hard Light, Vivid
Light, Linear Light, Pin Light, Hard Mix, Difference, Exclusion, Subtract,
Divide, Hue, Saturation, Color, Luminosity). Folder opacity multiplies into
descendants; folders are pass-through unless given a blend mode.

**Masks**: per-layer 8-bit coverage with its own placement and link flag; a 1×1
uniform mask means "reveal all". Clipping is an explicit `clip_to` link to
another layer (validated: no cycles, no groups). Group masks multiply into all
descendants.

**Selection** lives in the document (so it is undoable): a path with
antialiasing and feather, rasterized on demand to a coverage tile set used as
the clip of every edit. Tools: rectangle, ellipse, lasso, polygon, magic wand,
quick mask painting, expand/contract/feather/invert, load from alpha or mask.

**Brush**: a density integral along the smoothed pointer path evaluated per
touched tile on the GPU — not stamped dabs — so output is independent of event
rate and self-crossings do not crease. Permanent coverage per tile plus a
provisional tail that is replaced, never double counted. Drives Brush, Eraser,
Clone Stamp, Healing, Blur, Smudge, Dodge/Burn with pressure and tilt.

**Undo**: self-inverting commands with continuous-gesture coalescing (a drag is
one step). Pixel edits capture the replaced tiles as their inverse, which is
cheap because tiles are shared. Drags preview off-model at 60 fps and commit
once on release. Open/save/close are not on the bus.

**Adjustments** (as layers and destructive): Levels (+auto), Curves,
Hue/Saturation, Color Balance, Exposure, Brightness/Contrast, Black & White,
Gradient Map, Invert, Threshold, Posterize, Vibrance.
**Filters**: Gaussian, Motion and Box blur, Sharpen/Unsharp Mask, Add Noise,
Grain, Median, High Pass, Lens Correction.
**Layer effects**: Stroke, Drop Shadow, Inner Shadow, Outer/Inner Glow, Color
Overlay, Gradient Overlay, Bevel.
**Transform**: move, scale, rotate, flip, skew, distort, perspective, warp —
non-destructive, sampling nearest/bilinear/bicubic.

**Files**: native document is a directory package `Name.l2d` holding
`document.prisma` (the tree, validated with explicit limits) and
`layers/<id>.png` / `<id>.mask.png` (16-bit where needed), written atomically.
Open/save PNG, JPEG, TIFF, EXR via luce-image. PSD import (8/16-bit RGB, groups,
masks, blend modes, editable fills; text rasterized) with a conversion report
before anything is applied; PSD export flattened + layers later.

**Colour**: 16-bit, sRGB or Display-P3 documents, compositing in the document's
space to match Photoshop; ICC embedded on export. Scene-linear/OCIO is out of
scope for now.

### 2.4 luced-2d, the application

Mirrors luced's structure: `main.luc` parses options; `editor/` composes
`Actions` (one `Command` per action, shared by menu bar, tool rail, palette and
keymap), `Views` (`DStack` with tool rail, tool-options bar, rulers + canvas,
Layers / Properties / History / Colour / Swatches / Navigator panels, status
bar), a `Workspace` controller with document tabs, and `tools/` — one module
per tool: move/transform, marquee, lasso, wand, crop, brush, eraser, clone,
heal, blur/smudge, gradient, fill, shape, type, eyedropper, hand, zoom.

**Look** — eleusis-layout, verbatim: brutalist, square, grey with one orange.
Pane surface `#323232`; tab strip 38; backdrop 26; borders 58; text 217, muted
140; accent and selection `#E7A03F` (231,160,63) with **black** text on it
(9.5:1; white would be 2.2:1); inactive selection (120,84,40); row height 22;
corner radius 0; 1 px borders; no shadows or gradients in chrome; the only
chromatic things are the accent, `danger` and `warning`.

## 3. Order of work

Each phase ends with something that runs on macOS and Windows and with tests
that run headless. Nothing is deleted until the replacement agrees pixel for
pixel where that applies.

1. **std.gpu v2** — textures, targets, readback, client pipelines, shader tool,
   alpha colour, boundary test; Metal first, Vulkan parity. `Painter.image`;
   `luce_ui.Raster` deleted; luced-2d and wolf3d moved to textures.
2. **luce-pixel core** — tiles, document tree, over/place/mask/clip nodes,
   identity-hash cache, canvas request with pyramid levels, zoom/pan camera,
   export; checkerboard fixtures with measured edges.
3. **luced-2d skeleton** — theme roles, eleusis look, docking layout, tabs,
   commands table, open/save PNG/JPEG/TIFF, layers panel with tree_view, undo.
4. **Brush engine** and painting tools with pressure; selections with quick mask.
5. **Blend modes, masks, clipping, adjustment layers, filters, layer effects,
   transform tool, text and shape layers.**
6. **Native format, PSD import, image clipboard, file drop.**
7. **Linux** — window + Vulkan surface, packaging; then Windows and Linux
   installs through `luc`.

## 4. What is deliberately not copied

From Compositor: no persistent composite (recomposites the visible stack on the
CPU each frame); blend modes split over three implementations; two composite
implementations that must agree; whole-document snapshot undo; flat layer array
with parent ids; 8-bit only; effects previews capped at 1536 px; a 917-line
session god object with modality as nil-guards.

From eleusis: OCIO/ACES and scene-linear working space (a layout tool for film
plates needs it; a Photoshop replacement needs to match Photoshop); the
immediate-mode UI (luce-ui is retained and stays so).

## 5. Rules carried over

- A cache key describes the pixels; a miss returns nothing and never blocks.
- Nothing on the frame path blocks; decodes and exports run on workers.
- Every cache downstream of a decode registers so invalidation is not kept by
  hand.
- Refuse and say so on the canvas rather than draw a quieter wrong picture.
- A module's header says what it hides; a module is created when it has a real
  client today and its shape is understood.
- Verify blur-class bugs with known-frequency fixtures and a standard-deviation
  budget, not only assertions.

## 6. Study notes

**Compositor** (`archive/Compositor`): `Document/EditorSession.swift`
(`ImageLayer` with optional facets), `Rendering/RasterSnapshot.swift` (sparse
immutable raster of shared tiles), `Rendering/DownsampleCache.swift` and
`TiledLayerRenderer.swift` (halving-aligned pieces with support margins so a
partial redraw equals a full one), `Document/BrushStroke.swift` +
`Rendering/MetalBrushCoverage.swift` (density integral), `docs/project-format.md`,
`docs/brush-performance.md`, `IO/PSD/`.

**eleusis-layout.2**: `PIPELINE.md`, `RENDER_GRAPH.md`, `ROADMAP.md`,
`src/app/render_graph.zig`, `node_eval.zig`, `texture_cache.zig`,
`asset_pixels.zig`, `sampler.zig`, `src/model/command.zig`,
`src/app/event_router.zig`, `keymap.zig`, `output.zig`, `theme.zig`.

**eleusis-frameworks**: `src/gpu/root.zig` + `boundary_test.zig`,
`docs/UI_FRAMEWORK.md`, `docs/ARCHITECTURE_AUDIT.md`, `src/dock/`,
`src/keybind/`, `src/image/`, `src/ui/theme.zig`. The design standard both
follow is `/Users/sedov/Dev/luce/SOFTWARE_DESIGN.md`.
