# The canvas engine: design

Status: proposal for review, 2026-09-25. Builds on
[LARGE-CANVAS-RESEARCH.md](../research/LARGE-CANVAS-RESEARCH.md) (how other editors do
it) and [LARGE-CANVAS-PROFILE.md](../research/LARGE-CANVAS-PROFILE.md) (where
luced-2d stands).

## 1. What the engine is for

Every pixel luced-2d keeps is stored in the canvas engine, and every pixel it shows or
computes comes from it: layers, masks, the selection, undo history, previews, the pyramid
the view draws from, and what save and export write.

It has to hold whatever the user makes, from a 1000 px sketch to a 50 × 80 in print at
300 dpi (15000 × 24000, 360 MP, ~20 GB of 16-bit layers). It has to do that on a
16 GB laptop with integrated graphics as well as on a workstation with a 24 GB GPU, and
stay interactive throughout.

Other editors do this. Photoshop documents run to 300,000 px a side, and Krita and GIMP
edit gigapixel images. They share one idea: **the document is a set of small immutable
tiles that can live anywhere (GPU, RAM, compressed, disk), and all work is expressed per
tile, at the resolution it's needed.**

luce-image already stores layers as immutable 256 px GPU tiles, shared with undo. What's
missing is everything that lets those tiles be somewhere other than the GPU, be fetched at
a coarser level, and be processed in bulk without a wait per tile. This document makes
that one component with clear rules.

## 2. Rules the engine keeps

1. **Cost follows the screen or the edit, never the document.**
   - Drawing a frame costs what is on screen.
   - A stroke costs the tiles it touches.
   - Only explicit full-resolution jobs (apply a filter, commit a transform, save, export)
     visit every tile, and they run in the background with progress and cancel.
2. **Nothing fails because the document is big.**
   - When memory runs short, the engine moves tiles to a slower tier, streams work in
     smaller batches, or shows a coarser level for a moment.
   - An error reaches the user only when the disk is full.
3. **Tile content never changes once made.**
   - A change makes a new tile. Copies in any tier are therefore always valid, eviction
     never writes anything back, and undo is keeping old tiles.
4. **One path produces pixels.**
   - The view, thumbnails, previews, save and export all ask the engine for tiles at a
     level. There are no side paths that rebuild a whole image in one buffer.
5. **No single allocation grows with the document.**
   - Nothing allocates width × height of anything: no full-canvas textures, `f32` buffers
     or `Image` rasters. The one exception is the tile table itself, which is 8 bytes a
     cell (44 KB at 360 MP).

These rules are what make the component testable. Every one of them becomes a check in §11.

## 3. Where it lives

A new package, **luce-tiles**, between luce-gpu and luce-image:

```
luced-2d  ─────────────────────────────── the app: view, tools, dialogs
luce-image ────────────────────────────── document, compositor, brushes, filters, codecs glue
luce-tiles ────────────────────────────── the engine (this document)
   ├─ store        tiles, cells, formats, solid/empty, stamps
   ├─ residency    tiers G/R/C/D, pins, LRU, the memory governor
   ├─ pyramid      per-store levels, lazy, stamp-keyed
   ├─ jobs         tile jobs: windows of inputs, batches, progress, cancel
   └─ swap         compressed RAM and disk slabs
luce-gpu ──────────────────────────────── batches, fences, memory queries, pooled textures
luce-compress ─────────────────────────── + LZ4 block codec
```

Why a package of its own:
- It can be tested alone, with synthetic 100k × 100k stores and no editor.
- Its rules can't be bypassed by editor code.
- luce-image shrinks to image operations over an engine.

`Tiles` moves from `luce_image.tiles` to `luce_tiles.store` with the same name and
mostly the same methods, so the move itself is mechanical (§10, step 1).

## 4. The store

### 4.1 Cells and tiles

A **store** is a grid of 256 × 256 **cells** over an extent. This is today's `Tiles`, plus
the grid past the canvas that it already keeps. Each cell holds one of three things:

| Cell | Meaning | Cost |
|---|---|---|
| `Empty` | transparent (a mask's: white, revealing) | 0 |
| `Solid(color)` | every texel the same color | 16 B |
| `Pixels(tile)` | a shared, immutable, reference-counted tile | its tiers (§5) |

`Solid` is new. A white background layer, a "reveal all" mask, a filled selection or a
cleared area then costs nothing: a 360 MP white background is 16 B instead of 2.9 GB.
- Fills produce solids directly.
- A tile produced on the GPU is checked for uniformity when its readback happens anyway
  (the tile passes through RAM on its way to C/D). It is never read back just to check.
- The compositor samples a solid as a uniform color, so there's no texture.

Each tile carries metadata made when it is produced:
- `stamp`: unique per content, as today.
- `alpha_box`: the box within the tile holding any alpha, empty when none. `content_bounds`
  and trimming then read no pixels.
- `format` and `bytes`.

### 4.2 Formats

A store's format is fixed at creation:

| Store | 16-bit document (now) | 8-bit document (later) |
|---|---|---|
| Color layer, composite, pyramid | `rgba16_float`, 8 B/px, 512 KiB a tile | `rgba8` sRGB, 4 B/px |
| Layer mask, selection, channels | `r16_float`, 2 B/px, 128 KiB a tile (new in luce-gpu) | `r8`, 1 B/px |

Masks and the selection are 8 B/px today, and move to 2 B/px here. The selection also
moves from a CPU `u8` buffer into a store, shared with undo like any layer. That removes
the 360 MB copy each structural undo step makes now.

### 4.3 Tile size: 256, fixed

The owner asked whether tiles should be bigger, or depend on the platform. The answer
splits in two, because two different sizes are involved.

**The logical tile, which is what the store cuts the document into, stays 256 × 256 on
every platform.**
- It is the unit of change. A 30 px brush dab dirties 1–4 cells, and undo keeps just
  those. At 1024 px a dab would copy 16× more memory per touched cell and keep 16× more
  per undo step, and sparse layers would waste most of each tile.
- It is the unit of residency. The view at 100 % on a 5K screen needs ~270 cells. At
  1024 px, the ring of partly visible tiles would cost several times the screen.
- A fixed size keeps stamps, pyramids, files and tests independent of the machine.
- Photoshop's "cache tile size" setting (128K–1024K) exists because its tiles are also its
  I/O unit on disk. Here the I/O unit is decoupled (below).

**The physical allocation is platform- and GPU-dependent.** What makes small tiles
expensive today isn't their size. It is one GPU allocation per tile, and one command buffer
plus a wait per tile operation. Both change:
- GPU tiles are carved out of pooled **pages**:
  - Vulkan: 64–256 MiB `VkDeviceMemory` slabs. This also lifts Windows' 4096-allocation
    limit.
  - Metal: `MTLHeap`s.
  - Page size is chosen from the device's memory: 64 MiB below 4 GiB, 256 MiB above 8 GiB.
- Work is recorded in **batches**: hundreds of tile passes per command buffer (§8).
- Disk I/O moves whole 64 MiB slabs.

The per-tile overhead then disappears without paying for bigger tiles. `tile_size` stays a
single constant, so if measurement ever says otherwise it can change in one place.

## 5. Residency: where a tile's bytes are

### 5.1 Tiers

A tile's content can have copies in any subset of four tiers:

| Tier | Form | Typical cost of a color tile |
|---|---|---|
| **G** GPU | a slot in a pooled page | 512 KiB of GPU memory |
| **R** RAM | raw `f16` bytes | 512 KiB |
| **C** compressed RAM | LZ4 over byte-shuffled planes | 50–400 KiB for photos, 1–20 KiB for flat art |
| **D** disk | an offset in a swap slab file, LZ4 | 0 RAM |

The tiers are coherent by construction, because content never changes (rule 3).
- Dropping a copy is free whenever another tier holds one.
- Demoting the last copy costs one move: G→R is a readback, R→C a compression, C→D a write.
- Promoting reverses that: D→C→R→G.

**Apple unified memory:** G and R are the same memory (shared-storage heaps), so the
engine counts the two once. Macs therefore have three tiers.

### 5.2 Pins

Code that uses a tile's texture holds a **pin** for as long as the GPU might still read or
write it: until the batch it was recorded in has completed (§8). A pinned tile is never
evicted from G. Pins are released by fence, not by hand, so a forgotten unpin can't leak
residency.

The access rule replaces today's `tiles.texture(c, r)`:

```
let texture = try store.texture(column, row, batch)   # makes G-resident, pins until batch completes
```

Everything the compositor, brushes and filters do goes through this call.
- If the tile isn't on the GPU, the call promotes it.
- If the pool is full, the call first evicts unpinned tiles.
- If even that isn't enough (the batch pins more than the pool holds), the call ends the
  batch early, waits for it, unpins, and continues in a new batch. Jobs are written to
  survive exactly that (§8).

### 5.3 Priorities

Eviction takes the lowest class first, and the least recently used within a class:

| Class | Tiles |
|---|---|
| 0 | derived tiles that aren't on screen (pyramid, composite cache): dropped, never demoted |
| 1 | history-only tiles, held only by undo snapshots |
| 2 | live level-0 tiles off screen |
| 3 | the prefetch ring around the view |
| 4 | on screen at the view's level |
| 5 | pinned: in the current batch (never evicted) |

"History-only" is known exactly, because the store counts references by holder kind:
document, history, or job. It needs no guess.

### 5.4 The memory governor

One governor per process holds three budgets, and each tier stays within its own.

**GPU budget:**
- Metal: `recommendedMaxWorkingSetSize` minus what the window and UI use, times 0.75.
  Unified memory also counts against the RAM budget.
- Vulkan: `VK_EXT_memory_budget`'s heap budget for the device-local heap, times 0.8.
  Without that extension, 60 % of the device-local heap size. Also capped by
  `maxMemoryAllocationCount` through page count.
- Re-read on every memory warning, and every few seconds while a job runs, since other apps
  change it.

**RAM budget:**
- "Memory usage" in Settings, as in Photoshop: default 60 % of physical RAM, 25–90 %.
- Read from `sysctl hw.memsize` on macOS, `GlobalMemoryStatusEx` on Windows, `/proc/meminfo`
  on Linux.
- Shared by R and C; R is capped at half of it.

**Disk budget:**
- "Scratch disk" in Settings: a folder, default `~/.luce/cache/luced-2d/swap`, capped at
  the smaller of 64 GiB and free space minus 10 GiB.

**When an allocation fails** (a texture or page can't be created, or `malloc` fails):
1. The governor evicts class 0–4 tiles from that tier until the request fits, then retries.
2. If nothing is evictable, the batch is too big, so it is split (§5.2) and the request
   retried.
3. The view asks for its tiles through the same path. If it can't get them, it shows the
   nearest coarser level it has (§7.3): never a blank canvas, never an error.
4. Only a failed write to D (disk full) is reported, as "Out of scratch space: free disk
   space or choose another scratch folder".

**The governor also shrinks proactively** when the OS signals memory pressure: the
`DispatchSource` memory-pressure event on macOS, low-memory notifications on Windows,
`/proc/pressure` on Linux. It drops class 0, then demotes class 1 to C/D.

**Status bar:** "GPU 1.2/6 GB · RAM 3.4/19 GB · Scratch 0 GB · History 0.8 GB", the way
Photoshop's efficiency indicator shows it.

### 5.5 Background movement

Demotion and promotion to and from C and D run on worker threads. Compressing, writing,
reading and decompressing never touch the GPU. G↔R crosses the GPU, which stays on the
main thread, and is batched. The engine also:
- trickles R copies of recently made GPU tiles when idle, so a later G eviction is free;
- prefetches the ring around the view from C/D into R before it's needed.

## 6. Pyramids

Every store can answer for a cell at **level L**. Level 0 is document pixels; level L
covers 2^L × 2^L level-0 cells in one 256 px tile.
- A level-L tile is **derived**: its key is (store, L, c, r, the four child stamps). It
  lives in class 0, gets dropped when space is short, and is rebuilt on demand.
- The build downsamples 2 × 2 **in premultiplied space**. Today's `halve()` averages
  straight alpha, which darkens soft edges and has to be fixed.
- Solids propagate: four solids of one color make a solid, and empties make an empty.
- Invalidation is implicit. A stroke changes level-0 stamps, so the keys of its ancestors
  change and only that chain is rebuilt, when next requested: at most 7 downsamples for
  360 MP. Undo restores old stamps, so the old ancestors are cache hits.
- Vector shapes and text don't downsample. They render straight at the level asked, from
  their description (§9).
- The file stores the top levels (§9.4), so opening a 360 MP document shows at once.

Keeping levels **per store (per layer)**, rather than only the composite, is what makes the
view cost follow the screen. A zoomed-out frame composites N layers' level-L tiles per
visible cell, instead of N × 4^L level-0 tiles.

The trade-off: blend modes that aren't linear (Difference, Hard Mix, clipping) look very
slightly different zoomed out than the exact composite shrunk. Photoshop, Krita and GIMP all
accept this for display. 100 %, save and export are always exact.

## 7. The view

### 7.1 Level per device pixel

`L = clamp(floor(log2(1 / (zoom × backing_scale))), 0, Lmax)`. So a Retina display at 25 %
draws level 1, which is sharp.

### 7.2 Composite per visible cell

- For each visible cell, the compositor blends the layers' level-L tiles (masks, styles and
  adjustments applied) into a composite tile. Its key is the same kind of stamp digest
  `hash_layers` builds today, over one cell at level L.
- The cache of composite tiles is class 0 and budgeted in bytes. Lookup is a hash map, not
  today's linear scan of 512 slots.
- While painting, the compositor also keeps, per visible cell, the composite of everything
  below the active layer. A dab then recomposites `below ⊕ active ⊕ above`, which is 2 draws
  when painting on the top layer.

### 7.3 Never blank, never blocking

- If a cell's level-L composite isn't ready (inputs on disk, or this frame's time budget
  spent), the view draws its nearest ready ancestor, scaled up. It refines over the next
  frames within a per-frame GPU budget: ~6 ms while interacting, more when idle.
- The top three levels of the composite are always kept, so something is always ready.
- A ring of one cell around the viewport is prefetched, plus the parent level while zooming
  out and the child level while zooming in.

### 7.4 One view texture

Visible composite tiles are copied into one view-sized texture, which is drawn to the window
once. That means no seams between tiles, and one place for the display color transform,
the checkerboard and rotation. Panning shifts the view texture and fills only newly exposed
cells.

## 8. Jobs and batches

### 8.1 luce-gpu batches

luce-gpu gains a `Batch`: one command buffer that records many texture passes (renders,
copies, uploads through a staging ring, readbacks into a ring) and is submitted once. It
comes with a fence to ask whether it has completed or to wait for it. Textures made or
written in a batch are usable by later batches without waiting, since the GPU orders
batches on one queue.
- `texture.frame()` and the synchronous `upload`/`read` stay as one-pass conveniences.
- The engine uses batches everywhere.

This one change removes the wait that is ~95 % of today's cold frame, and most of the
per-tile cost of fills, adjustments, opening and saving.

### 8.2 Tile jobs

Every whole-layer operation is a **tile job**:

```
job(output store, inputs: [(store, radius in cells, level)], per_cell: pass)
```

- For each output cell, the job gathers the input cells within the radius into a small
  window. A blur of radius r reads a 3 × 3 window of cells, while a transform reads the
  cells its inverse map covers. It then records the pass into the current batch, and puts
  the result in the output store.
- The window replaces `flatten()`. No full-canvas texture is ever made, so the 16384 px
  limit stops mattering.
- A job runs in batches of k cells, sized from the governor's free G budget. It can pause
  between batches (for the view's frame), report progress, and be cancelled. Its output is
  a new store that replaces the old only when the job completes, so cancelling leaves the
  document untouched and completing is one undo step.
- **Visible cells first**, so the result appears where the user is looking.
- **Previews** run the same job at the view's level, over visible cells only, on every
  slider change. Apply runs it at level 0 over every cell, in the background.

The Levels histogram becomes a reduction job over a pyramid level (at most 1024 × 1024
samples), computed on the GPU.

## 9. How each feature uses the engine

### 9.1 Brushes

Dabs go into the active layer's level-0 cells through the batch, pinning only the cells
under the stroke. A very large brush at low zoom (3000 px at 12 %) paints the view's level
for display, Krita-style. The level-0 replay then runs as a job after pen-up. Until it
finishes, the stroke's own undo step holds the replay.

### 9.2 Selection and masks

- **Masks and the selection:** `r16_float` stores.
- **Marquee, lasso and wand:** they write the cells they cover. Solids fill the inside of
  a big rectangle.
- **Marching ants:** drawn from the selection's pyramid at the view's level.
- **Feather, expand and contract:** jobs with a radius.

### 9.3 Transform, shapes, text

- **Free transform:**
  - Preview: the source layer's view-level tiles, warped on screen.
  - Commit: a job whose inputs are the cells the inverse map covers.
- **Vector shapes and text:** rasterised per cell, at the level asked, from their
  description. There's no full-canvas buffer, so rule 5 holds.
- **The Move tool's drag:** the layer's view-level tiles, drawn offset and culled to the
  screen.

### 9.4 Files

**Native `.l2d`, version 2:** per layer, a table of cells.
- Each cell is empty, solid, or a compressed tile chunk (LZ4 by default, deflate as an
  option).
- The top pyramid levels are stored too, for instant display.
- **Incremental save:** cells whose stamp hasn't changed since the last save keep their
  chunks, so saving after a stroke writes a few tiles.
- **Opening:** reads the tables and the stored levels, and pages level-0 chunks in lazily
  as they're needed (straight into C/R).

**Export (PNG/TIFF/JPEG):**
- A job composes level-0 composite cells one row of cells at a time: 256 rows × the width.
  Each row is converted to 8/16-bit on worker threads and handed to a **streaming encoder**
  (row-oriented APIs in luce-png, luce-tiff and luce-jpeg). Peak memory is one row of
  cells, about 30 MB at 15000 px wide.

**Import:** a streaming decoder writes strips straight into cells, and the pyramid is built
in the same pass.

### 9.5 Undo

History snapshots hold stores. Tiles are shared, so a step costs only the tiles it replaced.
- History-only tiles are class 1, so they leave the GPU first and go to disk before any live
  tile.
- A history budget in bytes (default 25 % of the RAM budget, plus spill to disk) trims the
  oldest steps beyond 64 steps or that size.

## 10. Building it without breaking the editor

Each step ships on its own with the editor working, tested and published. Numbers are
checked by the acceptance tests of §11.

1. **luce-tiles package; `Tiles` moves in.**
   - The existing API is unchanged. `texture(c, r)` becomes `texture(c, r, batch)` with a
     default "immediate" batch, so callers compile.
   - The per-store cell array gains `Solid`.
   - Gate: the luce-image, canvas and luced-2d suites pass.
2. **luce-gpu `Batch`, fences, pooled pages (Metal heaps, Vulkan slabs) and
   `r16_float`/`r8`; memory queries.**
   - The compositor, brush, fill, adjust and filter passes record into batches.
   - Gate: at 360 MP, a cold fit frame drops from ~1 s towards ~50 ms. 20,000 tiles can be
     created on Windows.
3. **Per-store pyramids and view-level compositing, with a byte-budgeted hash-map cache;
   premultiplied halving; the view texture.**
   - Gate: at 360 MP, the fit frame is 0 ms cached, and a stroke at fit updates at 60 fps.
4. **Jobs with windows. `flatten()` and every whole-image path are removed:**
   - transform, motion blur, lens correction, styles, clone/heal sources, selection passes;
   - streaming export and save, streaming import.
   - Gate: at 360 MP, export, save, transform, blur and styles all complete, and no
     allocation grows with the document (checked by a test hook).
5. **Residency tiers and the governor.**
   - R/C/D with LZ4, swap slabs, pins, priorities, budgets from the platform, the Settings
     page and the status bar.
   - Gate: a 20 GB document works on a 16 GB machine, and on an 8 GB GPU the idle GPU use
     stays under 1 GiB at fit.
6. **Selection and masks as small-format stores; history budget; native file v2 with
   incremental save and stored levels.**
7. **Refinements:**
   - atlas pages, if per-tile passes still measure over 30 µs;
   - an 8-bit document mode;
   - threaded codecs and lookup-table conversions.

Steps 1–3 are what make big documents feel fast. Steps 4–5 make them always work.

## 11. Acceptance tests

These run as a benchmark suite (`luce-tiles/bench`), on this Mac and on the WINDOWS and
LINUX testers, against a synthetic 15000 × 24000 document with 12 layers:
- 4 photographic layers
- 4 sparse paint layers
- 2 masks
- 2 adjustment layers

| Action | Target |
|---|---|
| New 360 MP document, white background | < 100 ms, < 1 MB of pixels |
| Open `.l2d` v2 of that document | first frame < 300 ms |
| Fit view, cold (no stored levels) | coarse frame < 100 ms; refined < 5 s, never blocking |
| Pan and zoom | 60 fps; new cells filled within 3 frames |
| 300 px brush at 100 % | ≤ 8 ms a frame |
| 3000 px brush at 12 % | 60 fps; full-resolution replay done ≤ 1 s after pen-up |
| Gaussian blur r = 50 | preview < 150 ms; apply < 15 s in the background |
| Free transform | 60 fps drag; commit < 15 s in the background |
| Undo a stroke | < 50 ms |
| Save after one stroke | < 1 s |
| Export PNG | completes; peak RAM < 1 GB above the document |
| GPU memory at fit, idle | < 1 GiB whatever the document |
| 16 GB RAM machine | the 20 GB document opens, edits, saves |

Plus two checks:
- An allocation tracker fails the suite if any single allocation exceeds 64 MiB.
- An "evict everything" stress mode drops all G and R copies after every operation, and
  the ordinary test suites must still pass under it.

## 12. Decisions for the owner

1. **A new luce-tiles package** (recommended), or keep the engine inside luce-image.
2. **Per-layer pyramids**, with zoomed-out display composited from downsampled layers as
   Photoshop and Krita do (recommended). The alternative, a composite-only pyramid, is exact
   at every zoom but slow to update after adjustments at low zoom.
3. **Memory settings in Settings**, as in Photoshop: a "Memory usage" percentage and a
   scratch folder (recommended), rather than automatic only.
4. **Tile size 256 fixed, with GPU pages sized per platform** (recommended, §4.3), rather
   than a per-platform tile size.
