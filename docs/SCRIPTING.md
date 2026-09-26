# Scripting luced-2d

A script is a Luce program that imports `luced`. Every call into `luced` is one
editor action, done in the open document while the script runs, and the whole run
is one undo step.

```luce
import luced

pub func main(arguments: list[str]) -> int!:
    luced.add_layer("Glow")
    luced.set_color(1.0, 0.8, 0.2)
    luced.select_ellipse(100, 100, 300, 300)
    luced.fill()
    luced.deselect()
    luced.filter("Gaussian Blur", [40.0])
    luced.add_adjustment_layer("Vignette", [-60.0])
    print(f"{luced.document_width()} by {luced.document_height()}")
    return 0
```

## Running scripts

- **In the editor:** File › Script Editor… (Alt-Cmd-E, or Alt-Ctrl-E off macOS) opens
  the editor.
  - Write or open a script, then press Run (or Enter).
  - What it prints, and any error, shows in the console below the script.
  - Stop ends a run where it is.
  - Scripts are saved wherever you choose; `~/.luced-2d/scripts` is the usual place.
- **Headless:** `luced-2d --script batch.luc photo.jpg` runs a script with no window.
  - Each file named opens first, and the script starts on the last one.
  - The script's output goes to stdout.
  - The exit status is 0 when every action succeeded.
  - Batch work is a loop over files in a shell, or `open`/`export` calls inside one
    script.

The interpreter is Luce's own. The editor runs `luce run --sandbox` from the Luce
installation, `~/.local/luce/bin/luce`, or else `luce` on the PATH. The sandbox keeps a
script's own file access inside `~/.luced-2d/run`; the editor itself does the opening,
saving and exporting a script asks for.

## The API

The full, commented list is `scripting/luced.luc`.

- **Queries:**
  - `document_width()`, `document_height()`, `layer_names()`, `selected_layer()` and
    `document_path()`.
  - They describe the document as it was when the script started. The script's own
    changes are not seen by them.
- **Documents:** `new_document`, `open`, `save`, `export` (PNG or JPEG by extension),
  `place`, `undo`, `redo`.
- **Menu commands:** `run(id)` runs any menu command by its id, as the Settings
  dialog's shortcut list shows them.
- **Layers:** `add_layer`, `select_layer`, `select_layer_named`, `rename_layer`,
  `delete_layer`, `duplicate_layer`, `merge_down`, `move_layer_up`, `set_opacity`,
  `set_blend` (by Photoshop's name), `set_visible`, `move_by`, `add_mask`.
- **Painting:** `set_color` and `set_background` (sRGB, 0..1), `set_brush`, `stroke`
  (x, y pairs), `line`, `fill`, `clear`, `gradient`, `text`.
- **Selections:** `select_rectangle`, `select_ellipse` (mode 0 new, 1 add, 2 subtract,
  3 intersect), `select_all`, `deselect`, `invert_selection`, `select_color_range`;
  alpha channels by name: `save_selection`, `load_selection` (the same modes),
  `delete_channel`.
- **Pixels:**
  - `adjust(name, settings)` and `add_adjustment_layer(name, settings)`: settings are in
    the units and order the adjustment's dialog shows, and the ones left out keep
    their defaults.
  - `filter(name, settings)`: "Gaussian Blur", "Add Noise", "Motion Blur",
    "Lens Correction", "Bloom", "Tonal Contrast".
- **Transforms:** `distort`, `skew`, `perspective`, `warp`, `warp_points`, `puppet_warp`.
- **Vectors:** the Vector panel's elements of the selected layer, by their place in it
  (0 the bottom):
  - `add_vector(kind, x, y, width, height)` ("rectangle", "ellipse", "line",
    "polygon") and `add_path(points, closed)` add an element, on a new vector layer
    unless the selected layer is one or holds nothing.
  - `new_path(name)` makes an empty path for the Pen.
  - `select_vector` (-1 for none), `rename_vector`, `set_vector_visible`,
    `move_vector`, `duplicate_vector`, `delete_vector`, `vector_selection` (the
    selection modes above) and `transform_vector`.
- **Canvas:** `resize_image`, `resize_canvas`, `crop`, `flip_canvas`.

The first action that fails stops the run. What ran before it stays, as one undo step,
and the console says what failed.

## How it works

Each call prints one line: `@l2d`, the action's name and its fields, tab-separated,
with tabs, newlines and backslashes escaped. The editor reads the script's output as it
arrives and does each action, as its menus would (`src/script_commands.luc`). Any other
line goes to the console. `document.luc`, written beside the script for each run, holds
the queries' answers.
