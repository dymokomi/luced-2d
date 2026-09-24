# luced-2d against Compositor 1.2.11

The functions Compositor 1.2.11 has (archive/Compositor, audited 2026-09-24)
that luced-2d lacks or has in part, in the order to close them: what users hit
constantly first. Each item names where Compositor does it. Tick an item when
it ships.

Found beyond the old list, and first because they lose work:

- Undo covers only pixels and masks. Layer structure, properties, masks, styles,
  adjustment settings and selections are not undoable, and canvas size, crop,
  image size and merge down drop the whole history. Compositor undoes everything,
  with named steps (CompositorApp.swift:41, Document/DocumentHistory.swift).
- Pixels moved or transformed past the canvas are lost (transform.lucb); in
  Compositor layers may extend past the canvas (Document/LayerTransform.swift).
- Closing a document never asks about unsaved work, and Save As to PNG/JPEG
  re-targets the document to a flattened file (ProjectWorkspace.swift:106).

## Order of work

1. [x] Undo for everything (0.1.30): structural snapshots (records, tree, properties,
   styles, adjustment settings, extent, selection) beside tile snapshots; canvas
   size / crop / image size / merge undoable; step names ("Undo Brush Stroke").
2. [ ] Unsaved-changes prompt on close and quit; Save keeps .l2d; File › Export
   PNG (Shift-Cmd-E) and Export JPEG with quality and matte (JPEGExportSheet.swift).
3. [ ] Layers that survive going off-canvas: signed origin and grown extent.
4. [ ] Transform: box on the Move tool (Show Transform Controls, Cmd-H); Cmd-T
   with a selection floats the pixels; numeric W/H/Scale/angle and sampling;
   several layers or a folder at once; free distort (Cmd-drag a corner); Alt
   duplicates while transforming.
5. [ ] Layers panel: double-click renames inline; the full context menu
   (NativeLayerList.swift:119-215); Option-drag duplicates; Option-click between
   rows clips; swipe across eyes; merge selected / merge group; duplicate every
   selected layer and groups; Move Out of Folder; new-group, effects and
   adjustment buttons in the footer; Cmd-Shift-click on canvas adds a layer to
   the selection; opacity digits for every selected layer.
6. [ ] Real dialogs: New Canvas (size from the clipboard image), Canvas Size
   (anchor grid, relative, units, color; Opt-Cmd-C), Image Size (aspect lock,
   resampling; Opt-Cmd-I), Trim.
7. [ ] Polygonal lasso; selection header: mode control, Feather, anti-alias;
   wand Sample Size and all layers; Cmd-arrows move selected pixels; marquee
   autoscroll; selection changes undoable.
8. [ ] Guides (drag from rulers) and snapping to guides, grid, layers and
   bounds; Show Guides (Cmd-;), Snap (Shift-Cmd-;), Lock and Clear Guides.
9. [ ] Live, editable text layers: fonts and faces, color, alignment, tracking,
   leading, multi-line boxes, inline editing, double-click to edit, Cmd-Return.
10. [ ] Gradient: editable end points before Apply; on a mask. (Radial, reverse,
    to transparent and Shift 45° shipped in 0.1.29.)
11. [ ] Crop: ratios, symmetric (Option), start at the selection, size readout,
    snapping.
12. [ ] Masks: link/unlink and move on their own; masks on groups; invert, blur
    and noise on a mask; copy a mask to another layer; thumbnail background.
13. [ ] Adjustments: Curves adjustment layers; Levels eyedroppers, three Auto
    modes, Reset, Preview toggle (Opt-P); Hue/Sat band sliders, eyedroppers,
    drag on canvas, "outside this range"; Gradient Map colors.
14. [ ] Styles: Drop Shadow by angle and distance; Inner Glow.
15. [ ] Effects listed under their layer in Layers, each with an eye, delete,
    Option-drag to copy.
16. [ ] Import: File › Import Images…; PSD groups and masks, merged-only PSDs,
    PSB; HEIC, SVG, Camera RAW.
17. [ ] Tool extras: right-drag sets brush size (Shift: hardness); Spot Healing
    modes (Create Texture, Proximity Match); clone preview in the circle;
    eyedropper sample ring; Tab cycles tool modes; idle tool (A); zoom % field;
    stepped zoom; pixel grid at 800%+; Add Noise Uniform/Gaussian.
18. [ ] Whole-layer clipboard (masks, styles, groups, adjustments), across
    documents; drag a layer onto a tab; paste in place.
19. [ ] Filters: Motion Blur, Grain (and as a layer), Vignette, Bloom, Tonal
    Contrast, Lens Correction; blur and noise as adjustment layers.
20. [ ] Heavy: Content-Aware Fill, Select Subject, Object Selection, Remove
    Background, Camera Raw Filter; update feed; remembered tool options;
    floating, movable adjustment panels.

Then: the Script editor (from luced's code editor) and scripting — the Luce
interpreter bundled as luc does it, a Maya-like API over Commands, and a
headless mode.

luced-2d's extras over Compositor: Brightness/Contrast, Threshold, Posterize,
Desaturate; Layer via Cut, Crop to Selection; TIFF/EXR; color profiles and
units; Lab/OkLCh picker with history; brush dynamics, textures, presets;
intersect selection; spring-loaded tools; Darker/Lighter Color blends; crash
reports.
