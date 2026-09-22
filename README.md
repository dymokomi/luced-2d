# luced-2d

An image editor written in **Luce**, on its way to being a free Photoshop
replacement: layered documents held as GPU tiles by
[luce-image](https://github.com/dymokomi/luce-image), composed on the GPU and
drawn at any zoom, in a window built from **luce-ui** controls. The design and
the order of work are in [docs/DESIGN.md](docs/DESIGN.md).

![luced-2d showing a picture with a transparent corner](docs/preview.png)

## What it does today

- Opens PNG, JPEG, TIFF and EXR pictures as a document, or creates an empty one.
- Layers with names, visibility, opacity and all 26 Photoshop blend modes,
  composed on the GPU with a cache
  that re-renders only the tiles an edit touches.
- Brush and eraser (`B`, `E`, `[` `]` for size) painted on the GPU with soft
  edges and no dab artefacts; undo and redo of strokes.
- Pan with scroll or space-drag, zoom about the pointer with cmd/ctrl-scroll,
  `+`/`-`, Fit and 100%; pixels stay crisp when magnified.
- An Adjust menu with destructive adjustments: brightness/contrast, hue/
  saturation/lightness, invert, levels, desaturate, threshold, posterize —
  all undoable.
- Opens and saves through the desktop's file dialogs; saves the flattened
  document to PNG, JPEG or TIFF.

## Build and run

```sh
luc run
```

`luc build` produces `build/Luced 2D.app` on macOS; `luc run -- --smoke` runs
three native frames and exits; `luc run -- picture.png` opens a picture.
`luce-ui` and `luce-image` are expected as sibling checkouts.

## Tests and preview

```sh
python3 tests/run.py       # headless: workspace, view and panels
python3 tools/preview.py   # macOS: captures a real Metal frame into docs/preview.png
```

## Structure

- `src/workspace.luc`: the open document, its file, zoom, offset and selection.
- `src/view.luc`: the canvas widget: checkerboard, the document, pan and zoom.
- `src/panels.luc`: toolbar, layers panel, status line and the text prompt.
- `src/theme.luc`: the look, eleusis-layout's greys and orange.
- `src/app.luc`: application composition and commands.
- `src/main.luc`: entry point.
