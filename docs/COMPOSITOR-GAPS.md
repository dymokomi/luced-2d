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
2. [x] Unsaved-changes prompt on close and quit; Save keeps .l2d; File › Export
   PNG (Shift-Cmd-E) and Export JPEG with quality and matte (0.1.31).
3. [x] Layers that survive going off-canvas (0.1.32): moved, transformed, cropped
   or canvas-sized pixels stay past the canvas and come back; Image › Reveal All.
   Merge Down still flattens to the canvas.
4. [x] Transform (0.1.33): box on the Move tool (Show Transform Controls, Cmd-H);
   Cmd-T with a selection floats the pixels; numeric X/Y/W/H/Scale/angle, flips
   and sampling; several layers or a folder at once; free distort (Cmd-drag a
   corner); Alt-drag inside duplicates.
5. [x] Layers panel (0.1.34): double-click renames inline; the row menu with
   titles fitted to the selection; Alt-drag duplicates; Alt-click between rows
   clips; a drag down the eyes; Merge Layers / Merge Group; duplicate every
   selected layer and group; Move Out of Folder; new-group, effects and
   adjustment buttons in the footer; Cmd-Shift-click on the canvas adds a layer
   to the selection; opacity digits for every selected layer.
6. [x] Real dialogs (0.1.35): New Canvas (size from the clipboard image), Canvas
   Size (anchor grid, relative, units, extension color; Opt-Cmd-C), Image Size
   (aspect lock, resolution, resampling; Opt-Cmd-I), Trim.
7. [x] Selection (0.1.36): Polygonal Lasso (Shift-L); header with the four modes,
   Feather and Anti-alias; wand Sample Size and All Layers; Cmd-arrows move
   selected pixels; marquee autoscroll; selection changes undoable (0.1.30).
8. [x] Guides (0.1.37): dragged from the rulers, moved with the Move tool, dragged
   back to delete; snapping to guides, grid, layers and the canvas for moves,
   marquees, boxes and guides; Show Guides (Cmd-;), Snap (Shift-Cmd-;), Lock
   Guides (Opt-Cmd-;), Clear Guides.
9. [x] Live text layers (0.1.40): installed families and styles, size, color,
   alignment, tracking, leading, point text or a box that wraps; click (or drag
   a box) to type in a floating editor with the layer set live; click a text
   layer to edit it; Cmd-Return commits. Still to come: typing on the canvas
   itself with a caret, and several styles in one layer.
10. [x] Gradient (0.1.45): stays live after the drag with a handle at each
    end (Shift: 45°), follows the colors and options, Enter/Apply keeps it,
    Esc/Cancel drops it; on a mask when editing one. (Radial, reverse, to
    transparent and Shift 45° shipped in 0.1.29.)
11. [x] Crop (0.1.47): ratio menu (Free, Original, 1:1 … 9:16) held while
    dragging, Alt pulls both sides about the middle, the box starts at the
    selection, a W × H readout in the header; its edges snap.
12. [x] Masks (0.1.49): the chain between the thumbnails links or unlinks a
    mask (unlinked it stays when the layer moves or transforms; edited, it
    moves alone); masks on groups (the group flattened on its own, then laid
    down through its mask); adjustments, Gaussian Blur and Add Noise on the
    mask being edited; Copy Mask / Paste Mask; a new mask is the paint target.
13. [ ] Adjustments. Done: Curves adjustment layers (0.1.50); Levels eyedroppers
    and three Auto modes, Reset, Preview toggle (Alt-P), Gradient Map colors,
    the Hue/Saturation range eyedropper (0.1.51). Left: Hue/Saturation band
    sliders, drag on canvas and "outside this range" (they need more engine
    parameters). Originally: Curves adjustment layers; Levels eyedroppers, three Auto
    modes, Reset, Preview toggle (Opt-P); Hue/Sat band sliders, eyedroppers,
    drag on canvas, "outside this range"; Gradient Map colors.
14. [x] Styles (0.1.52): Drop Shadow by angle and distance (the light's
    angle, Photoshop's convention); Inner Glow (over the overlay, under the
    inner shadow and stroke).
15. [x] Effects listed under their layer in Layers (0.1.54): a line each, the
    eye hides one (listed, eye shut), the cross deletes it, Alt-drag onto
    another layer copies it, a double-click opens Layer Style.
16. [ ] Import. Done (0.1.55): File › Import Image… (one picture as a layer);
    PSD groups rebuilt and layer masks kept, merged-only PSDs as one layer,
    PSB. Left: several files at once, SVG (luce-svg needs colors), HEIC,
    Camera RAW.
17. [ ] Tool extras. Done (0.1.56): right-drag sets brush size (Shift:
    hardness); eyedropper sample ring; zoom % field; stepped zoom; pixel grid
    at 800%+; Add Noise Uniform/Gaussian. Left: Spot Healing modes, clone
    preview in the circle, Tab cycling tool modes, the idle tool (A).
    Originally: right-drag sets brush size (Shift: hardness); Spot Healing
    modes (Create Texture, Proximity Match); clone preview in the circle;
    eyedropper sample ring; Tab cycles tool modes; idle tool (A); zoom % field;
    stepped zoom; pixel grid at 800%+; Add Noise Uniform/Gaussian.
18. [x] Whole-layer clipboard (masks, styles, groups, adjustments), across
    documents; drag a layer onto a tab; paste in place.
19. [x] Filters: Motion Blur, Grain (and as a layer), Vignette, Bloom, Tonal
    Contrast, Lens Correction; blur and noise as adjustment layers.
20. [x] Heavy: Content-Aware Fill, Select Subject, Object Selection, Remove
    Background, Camera Raw Filter; update feed; remembered tool options;
    floating, movable adjustment panels. Subjects are found by color
    (GrabCut's idea, no trained model): a model would do better on busy
    pictures. Object Selection takes the marquee as its box, not a tool yet.

Then: the Script editor (from luced's code editor) and scripting — the Luce
interpreter bundled as luc does it, a Maya-like API over Commands, and a
headless mode.

luced-2d's extras over Compositor: Brightness/Contrast, Threshold, Posterize,
Desaturate; Layer via Cut, Crop to Selection; TIFF/EXR; color profiles and
units; Lab/OkLCh picker with history; brush dynamics, textures, presets;
intersect selection; spring-loaded tools; Darker/Lighter Color blends; crash
reports.
