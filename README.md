# luced-2d

An image editor written in **Luce**, on its way to being a free Photoshop
replacement: layered documents held as GPU tiles by
[luce-image](https://github.com/dymokomi/luce-image), composed on the GPU and
drawn at any zoom, in a window built from **luce-ui** controls. The design and
the order of work are in [docs/DESIGN.md](docs/DESIGN.md).

![luced-2d showing a picture with a transparent corner](docs/preview.png)

## What it does today

- Opens PNG, JPEG, TIFF and EXR pictures as a document, Photoshop `.psd` files
  as layers (names, visibility, opacity, blend modes, clipping), or creates an
  empty one.
- Layer › Layer Style: drop shadow, stroke and outer glow drawn under the
  layer, non-destructively, edited live and saved in `.l2d`.
- Layers with names, visibility, opacity and all 26 Photoshop blend modes,
  composed on the GPU with a cache
  that re-renders only the tiles an edit touches.
- Move tool (`V`): drag with a live preview, or nudge, the layer's pixels;
  Edit › Free Transform (cmd-T) scales, rotates and moves a layer with a live
  preview; Filter › Gaussian Blur.
- Image › Crop to Selection, Canvas Size, Image Size; Layer › Duplicate, Move
  Up/Down, Merge Down (cmd-J, cmd-], cmd-[, cmd-E).
- Per-pixel selections: rectangular marquee (`M`), elliptical marquee,
  lasso (`L`) and magic wand (`W`, with tolerance and contiguous options),
  shift adds and alt subtracts, Select › All, Deselect, Inverse,
  Expand, Contract and Feather (cmd-A, cmd-D, cmd-shift-I); marching ants;
  painting and fills stay inside; Fill (alt-Delete) and Clear (Delete).
- Text tool (`T`): click, type, and the text is set into the layer's pixels
  in the foreground colour at the chosen size.
- Brush and eraser (`B`, `E`, `[` `]` for size) painted on the GPU with soft
  edges and no dab artefacts; undo and redo of strokes.
- Pan with two-finger scroll, hand tool (`H`) or space-drag; zoom about the
  pointer with a touchpad pinch, the mouse wheel, cmd/ctrl-scroll, the zoom
  tool (`Z`), `+`/`-`, Fit and 100%; pixels stay crisp when magnified.
- An Adjust menu with destructive adjustments: brightness/contrast, hue/
  saturation/lightness, invert, levels (cmd-L), curves (cmd-M: a Photoshop-
  style curve editor per channel), desaturate, threshold, posterize, and
  Filter › Gaussian Blur. Each opens a bar of sliders under
  the header that previews live on the layer; Apply keeps the result as one
  undo step, Cancel puts the pixels back.
- Opens and saves through the desktop's file dialogs. Saving as `.l2d` keeps
  every layer, mask and blend setting (a directory with a `document.prisma`
  manifest and one PNG per layer); PNG, JPEG or TIFF save the flattened picture.

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
- `src/actions.luc`: one `Command` per action, as in luced; menus, the tool
  rail and shortcuts present the same instances, enabled by document state.
- `src/panels.luc`: the window after Compositor's: menu bar, contextual tool
  header, adjust bar, tool rail, layers panel, status line and the text prompt.
- `src/layers.luc`: the layer list with thumbnails, masks and clipping.
- `src/theme.luc`: the look, eleusis-layout's greys and orange.
- `src/app.luc`: application composition.
- `src/main.luc`: entry point.
