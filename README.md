# luced-2d

A small native paint program in the spirit of `luced`: the application is
written in the simple **Luce** dialect and composes **luce-ui** controls, while
luce-ui is written in low-level **Luce Base**.

![luced-2d with a painted document](docs/preview.png)

It has a canvas panel, a layers panel, a toolbar with brush and eraser, and a
properties panel for the document, the active tool and the active layer.

## Features

- **Canvas**: checkerboard transparency, centered document with automatic zoom
  to fit, brush cursor outline, pointer capture with segmented strokes.
- **Tools**: brush and eraser with independent diameter (1..512) and hardness
  (0..100); color swatches in the toolbar; keyboard shortcuts `B` and `E`.
- **Layers**: up to 16 layers, per-layer opacity (0..100) and visibility,
  add/delete/move/rename/clear, top-first listing.
- **Document**: resolution (1..2048 per side, at most 1048576 pixels), DPI
  (1..2400), pixel-preserving resize.
- **Undo/redo** of the active layer, `Cmd/Ctrl+Z` and `Cmd/Ctrl+Shift+Z`.
- Properties are edited through the shared `TextPrompt` with validation.

## Build and run

Keep `luced-2d`, `luce-ui`, `luce`, and `luce-base` as sibling checkouts. Build
the native compilers first, as described by `luced`:

```sh
(cd ../luce-base && ./build.sh)
(cd ../luce && LUCE_BASE_COMPILER=../luce-base/build/luce-base ./build.sh)
python3 tools/build.py
./build/luced-2d
```

`tools/build.py` accepts `--luce` and `--base` for explicit compiler paths.
`--smoke` runs three native frames and exits.

## Tests and preview

```sh
python3 tests/run.py
# macOS: read back the actual Metal frame in an isolated test build
python3 tools/preview.py
```

`tests/run.py` builds a temporary package without a native window and checks
painting, erasing, layers, resize, canvas strokes, panel property editing, layer
buttons and keyboard shortcuts. `tools/preview.py` captures real Metal output
into `docs/preview.png`.

## Structure

- `src/document.luc`: document, layers, raster pixels, undo/redo, flattening.
- `src/canvas.luc`: the interactive canvas widget and gesture handling.
- `src/panels.luc`: toolbar, properties and layers panels bound to the document.
- `src/app.luc`: application composition and keyboard actions.
- `src/main.luc`: entry point.
- `src/luce_ui/raster.lucb` (in `luce-ui`): the reusable RGBA raster surface
  behind layers: dabs, erasing, compositing, resizing and GPU drawing.

The canvas keeps one composited `Raster` cache per document revision; strokes
paint into the active layer, and undo history stores layer copies.

## Dependency changes in luce-ui

This repository relies on two additions to `luce-ui`:

- `Raster` (`src/luce_ui/raster.lucb`): a mutable, full-color, transparent
  raster with source-over painting, destination-out erasing, compositing,
  pixel-preserving resize and run-based GPU drawing.
- `ListView.select` now keeps the first row visible when selection is set
  before the first layout, and exposes `scroll_offset()` for tests.

## Limitations

- Session only: there is no file format, import or export yet.
- Undo history is per layer and bounded to 12 steps.
- No zoom or pan controls; the view fits the window.
- Layer thumbnails, blending modes, selections and text are future work.
