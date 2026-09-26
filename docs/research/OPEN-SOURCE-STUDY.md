# What open-source editors teach luced-2d about huge documents: a source study

Status: research, 2026-09-25. No code was changed to write this.

This study follows [LARGE-CANVAS-RESEARCH.md](LARGE-CANVAS-RESEARCH.md) (the survey),
[LARGE-CANVAS-PROFILE.md](LARGE-CANVAS-PROFILE.md) (the measurements) and
[../design/CANVAS-ENGINE.md](../design/CANVAS-ENGINE.md) (the accepted engine design). It doesn't
repeat them. Their summaries of Krita, GEGL and MyPaint came mostly from documentation; this
study reads the code.

Sources are shallow clones in `.donors/study/` (outside every repo) of:
- Krita (`krita/`)
- GEGL (`gegl/`) and GIMP (`gimp/`)
- libvips (`libvips/`)
- darktable (`darktable/`)
- libmypaint (`libmypaint/`)
- OpenImageIO (`oiio/`)
- Pinta (`pinta/`)

Photopea has no source, so it is left out. Paths below are relative to each project's root.

The target is unchanged: 15000 × 24000 px (360 MP), `rgba16_float`, 256 px immutable GPU tiles.

---

## 0. Summary

1. **The slow Vulkan readback is our transfer plumbing, not GPU-canonical storage.** Nothing
   studied moves pixels between host and device the way we do:
   - **The pattern:** `luce-gpu/src/luce_gpu/gpu/vulkan/texture.lucb` `vulkan_texture_read`
     creates a `VkBuffer` and calls `vkAllocateMemory`, records one copy, submits, waits on the
     fence, maps, copies, unmaps and frees. It does all of that for every call.
   - **How often:** the Magic Wand and Load Selection call it once per 256 px cell
     (`luce-image/.../canvas/selecting.lucb` `read_tiles_cell`), which is 5546 times at 360 MP.
     Export calls it once per strip of 64 tiles (`canvas/bands.lucb`), with a fresh 30 MB
     allocation each time, and the GPU and CPU never overlap.
   - **What the others do:** every project here reuses its transfer memory:
     - Krita keeps a ring of 16 PBOs (pixel buffer objects) and grows it when its fences lag;
     - libvips holds 2 reserve buffers per thread and double-buffers its writes;
     - darktable reads each tile straight into the final host image through a row pitch;
     - OIIO writes through one 64 MB buffer.

   A 360 MP `rgba16_float` layer is 2.9 GB. At PCIe 4 speeds (≥ 12 GB/s) that is about 0.25 s of
   bus time, so 15–29 s is ~98 % overhead.
2. **Keep the GPU canonical, and give each immutable tile an optional RAM copy that is kept
   warm.** In practice that is the hybrid, and our immutability makes it coherent for free.
   - Krita and GIMP are CPU-canonical because their brushes, filters and compositing run on the
     CPU.
   - GEGL did try "canonical on the CPU with a device-side cache". It is now switched off
     (`gegl/opencl/gegl-buffer-cl-iterator.c:283` `#define OPENCL_USE_CACHE 0`; NEWS: "not
     crashing is more important than caching"), and GIMP ships with OpenCL off, calling it
     "often slower than multi-threaded".
   - That is the failure mode CPU-canonical storage would bring us: coherence round-trips on
     every GPU brush dab and filter.
   - The full argument is in §8.
3. **Don't read back 8 B/px when the CPU needs 1.** The wand and selection sources need a
   match or coverage byte, and exports need 3–4 bytes. Computing those on the GPU and reading
   back `r8` or `rgba8` moves 2–8× fewer bytes. Classifying whole cells as all or none from a
   pyramid level avoids reading most cells at all.
4. **Krita's Instant Preview is more than "paint twice".** It rests on five things:
   - the preview strokes run ahead of all queued full-resolution work;
   - full-resolution strokes run inside one SUSPEND…RESUME bracket whose updates are recorded,
     not shown, and are published in one swap;
   - the preview's undo goes to a surrogate store that is thrown away;
   - the whole thread pool runs at one level of detail at a time;
   - a small set of brush options block the preview.

   Also: **Krita allows smudge in LOD mode** (only its overlay mode blocks it), so our earlier
   "no LOD for smudge" rule was too strict.
5. **The cost of a huge smudge is bounded by sampling and by the GPU.**
   - Krita's color sampling uses Halton samples and stops once the mixed color converges
     (≥ 64 samples, then batches of 16, stop at Δ ≤ 2).
   - libmypaint samples every 7r-th pixel plus 1/(7r) at random, and re-samples at most every
     other dab.
   - Our smudge (`luce-image/.../warp.lucb`) reads cells back and carries a (2r+1)² f32 square
     on the CPU: 64 MB and 4 M pixel updates per dab at 2000 px. It belongs on the GPU.
6. **Liquify is a displacement grid, not a pixel operation.** Krita's
   `KisLiquifyTransformWorker` moves an 8 px control grid with 3σ Gaussian falloff. It previews
   at a lower level (in place) or on a ≤ 2000 px thumbnail, and commits by undoing the preview
   and warping once at full resolution.
7. **Memory governance details worth copying:**
   - Krita's nested thresholds, each 7/8 of the one above, swap history first.
   - GEGL counts a shared tile once, evicts shared dirty tiles with probability 1/n, backs off
     its trim adaptively, and refcounts swap blocks so COW reaches the disk.
   - GEGL's swap writer thread is fed immutable dups, and the producer compresses when the queue
     is full.
   - OIIO's clock sweep uses `try_lock` so that only one thread evicts.
8. **Details to avoid:**
   - Krita `qFatal`s when the swap file is full.
   - Krita's selection outline allocates 2 × W × H bytes on one thread (720 MB at 360 MP) and
     strokes an unsimplified path every 150 ms.
   - Krita buffers every PNG row (2.9 GB) before writing.
   - GIMP's undo size counts COW-shared buffers at full size.
   - GIMP's fuzzy select does a 1 × 1 `gegl_buffer_get` per pixel.
   - darktable exports with one blocking readback of the whole image.
9. **Our PNG encoder is already ahead.**
   - libvips, OIIO, darktable, GIMP and Krita all deflate on one thread.
   - `luce-png/.../encode.lucb` already filters and deflates bands on workers as independent
     segments.
   - What export lacks is the pipeline around the encoder: GPU conversion, batched readback,
     and double-buffered strips.

---

## 1. GPU→CPU readback, and where canonical pixels live

### 1.1 What we do today

The primitives:

| Where | What happens per call |
|---|---|
| `luce-gpu/.../vulkan/texture.lucb` `vulkan_texture_read` | `vulkan_staging` (a `vkCreateBuffer` and a `vkAllocateMemory`, host-cached since c9caefa), `vulkan_begin`, one `vkCmdCopyImageToBuffer`, `vulkan_end`, `vulkan_wait` (a fence wait, which retires everything submitted before it), `vkMapMemory`, `memory.copy`, `vkUnmapMemory`, `vkFreeMemory` |
| `luce-gpu/.../metal/texture.lucb` | `newBufferWithLength`, a blit, `waitUntilCompleted`. On unified memory the allocation is cheap and nothing crosses a bus |

The callers:

| Caller | Readbacks at 360 MP |
|---|---|
| `luce-canvas/.../tiles.lucb` `read_cell`, `read`, `bound_cell` | one per tile |
| `luce-image/.../canvas/selecting.lucb` `read_tiles_cell` / `read_picture_cell` (wand, Load Selection) | one per cell, 5546 in all, each with its own allocation and its own drain of the queue |
| `luce-image/.../canvas/bands.lucb` `Bands.fill` (export) | one per strip of up to 64 tiles (≈ 94 strips). Each needs a 30 MB staging allocation. The GPU waits while the CPU converts and encodes, and the CPU waits while the GPU composites |
| `luce-image/.../warp.lucb` (smudge, push) | one per cell the stroke first reaches |

Three costs stack up, and none of them depends on bandwidth:
- **Allocation.** Windows drivers and RADV make `vkAllocateMemory` of host memory expensive: it
  zeroes and maps pages, and allocations are counted.
- **A full stop per call.** One submission and one fence wait per call means one pipeline drain.
- **No overlap.** Nothing overlaps: the next read isn't recorded until the last one has been
  copied out.

Metal hides the first two costs, which is why the Mac numbers are 10× better on the same code.

The host-cached memory type landed in luce-gpu c9caefa, 19:03 on the same day as luced-2d 0.1.89.
**If the 15–29 s and 13 s figures predate it, measure them again first.** Uncached (write-combined)
reads are 10–20× slower on their own.

### 1.2 What each project does

**Krita** (CPU-canonical; the GPU is for display only)
- It only uploads. `libs/ui/opengl/kis_opengl_image_textures.cpp` `initBufferStorage` allocates
  **16 PBOs of one texture tile each** (`numTextureBuffers = 16`) in a
  `KisOpenGLBufferCircularStorage`.
- `BufferBinder` writes into the next buffer, and `glTexSubImage2D` sources from it. When the
  ring comes round to a buffer whose `KisOpenGLSync` fence hasn't signalled,
  `allocateMoreBuffers()` doubles the ring rather than waiting.
- Color conversion to the display space and packing run on the merge worker thread.
  `KisCanvas2::startUpdateCanvasProjection` is `Qt::DirectConnection`
  (`libs/ui/canvas/kis_canvas2.cpp:815`), so the GUI thread only issues the upload.
- Krita never reads pixels back from the GPU. Export, fill, selection and smudge all read the
  CPU tiles they already own.

**GEGL/GIMP** (CPU-canonical; OpenCL was an accelerator, now off)
- `gegl/opencl/gegl-buffer-cl-iterator.c` reads each ROI with `gegl_buffer_get` into a
  `CL_MEM_ALLOC_HOST_PTR` buffer, maps and unmaps it, runs the kernel, maps back and calls
  `gegl_buffer_set`. Chunks are 1 MP (`GEGL_CL_CHUNK_SIZE`).
- The device-side cache (`gegl-buffer-cl-cache.c`) hooked `gegl_tile_handler_cache_ext_flush`.
  Any CPU `GET` of a tile first "moves (not just copies) the content" back to the host, so there
  was one coherence round-trip for every CPU touch.
- It was disabled (`OPENCL_USE_CACHE 0`), and `use-opencl` defaults to FALSE in GEGL and in GIMP
  (`app/config/gimpgeglconfig.c:152`). GIMP's NEWS.pre-2-10 says: "OpenCL acceleration is often
  slower than multi-threaded implementation, and can also sometimes be 'glitchy'."

**darktable** (device-resident pipeline; the host holds the final image)
- `src/develop/pixelpipe_hb.c` `_dev_pixelpipe_process_rec` passes `cl_mem_output` from module to
  module and copies back only for GUI "important" inputs or host-tiled modules. The final
  readback is **one** blocking `_copy_image_to_host_err` of the whole output
  (`_dev_pixelpipe_process_rec_and_backcopy`).
- Tiling (`src/develop/tiling.c` `_default_process_tiling_cl_ptp`) keeps one in/out `cl_mem`
  pair per tile size. It reads **only the valid part of each tile straight into the final host
  image**:

  ```c
  err = dt_opencl_read_host_from_image_raw(devid, (char *)ovoid + ooffs, output, origin, region, opitch, TRUE);
  ```

  The offset plus row pitch mean there is no re-tiling on the CPU. Every read is still blocking.
- `process_tiling_cl_fast` copies full-width strips device to device when both images fit.
- **Pinned memory is gone.** No `CL_MEM_USE_HOST_PTR` or `ALLOC_HOST_PTR` is left in `src/`, and
  `pinned_memory` survives only as a config key the upgrade code retires
  (`src/common/darktable.c:2761–2816`). There are no vendor-specific transfer workarounds.
- The export pipe always runs synchronously (`opencl.h:189`, `dt_opencl_finish_sync_pipe`).
- The memory budget is the device memory minus a **600 MB headroom** (`DT_OPENCL_DEFAULT_HEADROOM`),
  and on unified-memory devices it is capped at a fraction of RAM (`unified_fraction`, default
  0.25).

**libvips** (CPU; no GPU)
- `libvips/iofuncs/buffer.c`: a per-thread buffer cache with `buffer_cache_max_reserve = 2`.
  `vips_buffer_new` moves a reserve buffer and reallocates only when it grows. The comment:
  "keep a few buffers in reserve per image, stops malloc/free".
- `iofuncs/sinkdisc.c`: two `WriteBuffer` strips (see §6).

**OpenImageIO**
- `libOpenImageIO/imagebuf.cpp` writes a cache-backed image through **one 64 MB budget buffer**:
  the whole image if it fits, otherwise rows of tiles, otherwise scanline chunks.
- `libtexture/imagecache.cpp` `check_max_mem` does a clock sweep of an atomic `m_used` bit per
  tile with `m_tile_sweep_mutex.try_lock()`. A thread that loses the try-lock carries on over
  budget instead of waiting.

### 1.3 What fits us

- Every design studied allocates transfer memory once and **pipelines** it (Krita's PBO ring,
  vips' double buffer).
- darktable's row-pitch reads map directly onto Vulkan `VkBufferImageCopy.bufferOffset` and
  `bufferRowLength`. Many tile copies can land in one scanline-contiguous staging buffer, which
  `bands.lucb` gets today only by compositing into a strip texture first.
- GEGL's history is the cautionary tale for any design in which the CPU owns pixels that GPU
  passes keep changing.

### 1.4 Recommendation (priority order)

1. **Measure before changing anything** (a day). On LINUX and WINDOWS, time each phase of
   `vulkan_texture_read`: create and allocate, submit, fence wait, map, copy, free. Do it for a
   256 × 256 read and for a 16384 × 256 strip, with c9caefa in place.
   - If allocation dominates, item 2 alone recovers most of it.
   - If the wait dominates, items 3–4 matter more.
2. **luce-gpu: a persistent readback ring.** `gpu/vulkan/texture.lucb`, `gpu/metal/texture.lucb`,
   `gpu/texture.lucb`.
   - 3 slots of 32–64 MiB each, `HOST_VISIBLE | HOST_CACHED` (falling back to `COHERENT`),
     allocated once per device and **mapped for good**.
   - Each slot has its own serial on the submission ring.
   - Metal gets the same shape: shared-storage `MTLBuffer`s kept in a ring.
   - This also applies to uploads: `vulkan_texture_upload` should suballocate from a staging ring
     too, like Krita's 16-PBO ring.
3. **luce-gpu: batched, asynchronous reads.**
   - Add `Batch.read(texture, region, into: slot, offset, row_length)`. It records a copy into a
     ring slot at a row pitch, so 59 tiles become one scanline-contiguous strip with no strip
     texture (darktable's `opitch`).
   - `batch.submit()` returns a ticket, and `ticket.wait()` gives `const u8[]` views into the
     mapped slot.
   - `Texture.read` stays as a thin synchronous wrapper.
   - This is the `Batch` of CANVAS-ENGINE.md §8.1 with readbacks in it.
4. **luce-canvas: a bulk read API** (`luce-canvas/src/luce_canvas/tiles.lucb`, then the `store`
   module).
   - `store.read_cells(cells[], format, visit(cell, bytes))` records every cell of a batch, waits
     once, and calls `visit` on workers while the next batch is on the GPU.
   - `read_cell`, `read` and `content_bounds` and the `selection_sources.Reader` callers move onto
     it.
   - Once the R tier exists, `read_cells` serves cells with an R copy from RAM without touching
     the GPU.
5. **Read back fewer bytes** (`luce-image/.../canvas/bands.lucb`, `selection_sources.lucb`,
   `canvas/selecting.lucb`).
   - **Export:** composite, then run a GPU pass that converts to 8-bit sRGB with the matte into an
     `rgba8` strip, then read that. This halves the bytes (1.44 GB instead of 2.9 GB) and removes
     the CPU lookup-table pass. Keep the CPU path for 16-bit exports.
   - **Wand, Color Range, Load Selection:** a GPU pass writes an `r8` match or coverage tile
     (8× fewer bytes).
   - **Whole cells first:** a `min`/`max` reduction over the pyramid classifies cells as wholly in
     or wholly out, and only mixed cells are read back. Most cells of a photo are mixed, but in
     flat art or masks most are not.
6. **luce-canvas: keep RAM copies warm** (§5.5 of the engine design, pulled forward).
   - When idle, and inside every batch that already reads, keep `R` copies of recently produced
     level-0 tiles.
   - The wand, export, heal and bounds then mostly read RAM.
   - On Apple unified memory, shared-storage tiles *are* the R copy.

---

## 2. Smudge and Liquify with 2000 px brushes

### 2.1 Krita

**Brush engine threading** (`plugins/paintops/defaultpaintops/brush/kis_brushop.cpp`,
`libs/image/brushengine/kis_paintop_utils.cpp`)
- `KisBrushOp::paintAt` only queues a dab (`m_dabExecutor->addDab`). Masks render as CONCURRENT
  jobs.
- `KisDabRenderingQueue` reuses the previous dab when parameters are within a precision level
  (`kis_dab_cache_base.cpp:32–38`). The level is exact below 30 px and level 3 above.
- `doAsynchronousUpdate` splits the union of the ready dabs into disjoint patches,
  `clamp(128, diameter·(2−spacing), 512)` px, shrinking them until there is at least one per
  thread. Each patch applies every dab that touches it, in order (`KisPainter::bltFixed(rect,
  QList<KisRenderedDab>)`, `kis_painter_blt_multi_fixed.cpp`).
- The update period adapts: `qBound(10, 1.5 × dab render time, 100)` ms, starting at 40 ms
  (`FreehandStrokeStrategy`).

**Color smudge** (`plugins/paintops/colorsmudge/`) doesn't use that machinery.
- `KisColorSmudgeOp::paintAt` works synchronously. It chooses a strategy (Lightness, Mask, Stamp,
  MaskLegacy) and blends a source rect (the previous dab rect moved to the new center) into the
  destination through the dab mask.
- **Source:** a `KisOverlayPaintDeviceWrapper(..., LazyPreciseMode)`.
  - It copies only the **64 px grid cells the stroke touches** (`KisRectsGrid(64)`) into a
    16-bit overlay.
  - Overlay mode samples `image->projection()` under `blockUpdates()` instead, and is a LOD
    **blocker** (`KisSmudgeOverlayModeOptionData::lodLimitations`).
  - Otherwise smudge is LOD-capable, and its size scales by `KisLodTransform::lodToScale`
    (`kis_colorsmudgeop.cpp:159`).
- **Dulling color sampling** (`KisColorSmudgeSampleUtils.h:135–225`):
  - Halton(2,3) points over the sample rect;
  - `minSamples = min(N, max(64, 0.02·N))`, then batches of 16;
  - it stops when the mixed color changes by ≤ 2.

  The cost barely depends on brush size.

**Liquify** (`libs/image/kis_liquify_transform_worker.cpp`,
`plugins/tools/tool_transform2/`)
- **The model:** `originalPoints` / `transformedPoints` on a grid with `pixelPrecision = 8` px
  (`tool_transform_args.cc:364`).
- **Brush ops** (`translatePoints`, `scalePoints`, `rotatePoints`, `undoPoints`) move points
  within 3σ, weighted by `exp(-0.5 (d/σ)²)`. Build-up and wash modes differ in how they
  accumulate.
- **Rasterizing:** only the dirtied subgrid is rasterized (`calculateCorrectSubGrid`), and the
  rest is copied fast (`cutOutSubgridFromBounds`).
- **Overlay preview:** a display-space `QImage` capped at 2000 px
  (`KisToolTransform::initThumbnailImage`), warped by `runOnQImage` on the GUI thread once per
  repaint.
- **In-place preview** (`InplaceTransformStrokeStrategy`):
  - It picks `lod = max(ceil(log2(maxDim / 2000)), desiredLOD)` and syncs its own LOD planes.
  - It keeps only the latest arguments, and applies them only if 30 ms have passed and
    `!hasUpdatesRunning()`.
  - **Finish:** undo the preview commands, then `reapplyTransform(args, 0)` at full resolution,
    then `repopulateUI`.

### 2.2 libmypaint

- `mypaint-tiled-surface.c` `draw_dab_internal` queues a copy of the dab into an
  `OperationQueue` per 64 px tile. `end_atomic` then runs `process_tile` over the dirty tiles
  with `#pragma omp parallel for`: one fetch and store per tile, all its dabs in order.
- **Smudge color** (`get_color`, `brushmodes.c` `get_color_pixels_accumulate`):

  ```c
  const int sample_interval = radius <= 2.0f ? 1 : (int)(radius * 7);
  const float random_sample_rate = 1.0f / (7 * radius);
  ```

- `mypaint-brush.c` `update_smudge_color` re-samples only when `recentness` falls below a
  threshold. The comment: "almost as expensive as rendering a dab … at most every second dab."
- The radius is clamped to `ACTUAL_RADIUS_MAX = 1000` as a "safety guard against rendering
  overload".

### 2.3 What fits us

- **Smudge is a feedback loop.** Each dab reads what the previous dab wrote, which is why no
  studied engine parallelizes across dabs. Within a dab, though, the work is per pixel and
  maps directly onto a fragment pass.
- **Tile-parallel, dab-serial.** Krita's per-patch "apply every intersecting dab in order" is
  exactly one GPU pass per touched tile per frame, looping over the frame's dabs in the shader.
  Our `brush.lucb` ping-pong already has that shape.
- **Liquify as a displacement field.** The field is small: an 8 px grid over 360 MP is 1875 ×
  3000 points, 45 MB of f32 pairs, and it can be kept sparse per 256 px cell. A GPU mesh warp of
  pyramid tiles makes the preview cost the screen, not the brush.

### 2.4 Recommendation (priority order)

1. **Move smudge to the GPU** (`luce-image/.../warp.lucb`, `brush.lucb` shaders, and a new
   `shaders/smudge.frag`).
   - The carried square becomes a small `rgba16_float` texture:
     - (2r+1)² at level 0, or at the preview level (next item);
     - capped, like libmypaint, at 1024² by carrying it one pyramid level coarser when r > 512.
   - Each dab is two passes:
     1. pick up: blend what is under the tip into the carried texture;
     2. lay down: draw the carried texture through the tip into each touched tile.
   - Both are recorded into the frame's batch, with **no readback at all**.
   - This removes the `SmudgeJob` threads, the per-cell readback and the per-dab uploads.
2. **Smudge gets a LOD preview** at the view level for brushes ≥ 256 px at < 50 % zoom (§3), with
   a level-0 replay after pen-up. This follows Krita, which allows it. Seeded dab positions make
   the replay deterministic. The carry state differs slightly between levels, which is the same
   "popping" Krita accepts.
3. **Sample the smudge "dulling" color on the GPU** from the source tile's pyramid level
   `ceil(log2(r / 32))`. A reduction pass over ≤ 64² texels is O(1) in brush size, and does the
   job of Krita's Halton early exit and libmypaint's stride for free.
4. **Liquify as a displacement grid** (a new `luce-image/.../liquify.lucb`; `warp.lucb` push mode
   goes away).
   - The grid is 8 px, stored per 256 px cell (33 × 33 points, 8.7 KB), and only the cells the
     brush reaches are allocated. Dabs update the grid on the CPU in µs (at most (3r/8)² points).
   - **Preview:** each visible tile at the view level is drawn as a warped mesh sampling the
     source layer's pyramid (at level L the grid step is 8/2^L px). It costs the screen whatever
     the brush size.
   - **Commit:** a tile job (engine §8.2). Each output cell's inverse map covers a window of
     source cells, and it is shaded at level 0. This is the same machinery as a transform commit.
   - **Undo:** the grid is small, so the stroke's undo step keeps the grid plus the old tiles
     that the commit replaced.
5. **Batch the dab tiles** (`brush.lucb`). Apply every dab of the frame that touches a tile in
   one pass (Krita's `bltFixed`), and adapt the flush period to measured GPU time: Krita's
   `[10, 100]` ms with 1.5× headroom.

---

## 3. Previews at a lower level of detail (Krita "Instant Preview", GEGL/GIMP)

### 3.1 Krita: the source-level mechanism

**The queue** (`libs/image/kis_strokes_queue.cpp` `startStroke`, lines 281–340)
- When a strategy's `createLodClone(lod)` returns a clone, the stroke becomes a **LOD0** stroke
  with a **LODN** buddy.
- If `lodNNeedsSynchronization` is set (any non-LOD stroke ran since the last sync), a
  `KisSyncLodCacheStrokeStrategy` stroke comes first.
- After two quick strokes the queue reads:
  `[SYNC] LODN_a LODN_b SUSPEND LOD0_a LOD0_b RESUME`.
- `findNewLodNPos` puts each new LODN stroke before the first LOD0, SUSPEND or RESUME, so
  **previews always overtake pending full-resolution work**. A LOD0 stroke that is running and
  supports suspension is paused (`KisStroke::suspendStroke` puts its suspend and resume jobs
  around the new LODN stroke).
- `KisStrokesQueue::addJob` clones every job's data with `createLodClone`. A stroke is LOD-capable
  only if the strategy and every job-data type can clone.

**One level at a time.** `KisLockFreeLodCounter` packs `(count << 8) | lod` into one atomic, and
the scheduler admits only jobs at the running level. **LOD0 and LODN work never overlap.**
`KisPaintDevice::currentData()` (`kis_paint_device.cc:522`) switches the device between
`m_data` and `m_lodData` by that counter.

**Reconciliation** (`kis_suspend_projection_updates_stroke_strategy.cpp`, doc comment at 478–513)
- SUSPEND installs a filter that **records** LOD0 projection updates instead of showing them.
- RESUME:
  1. replays them, merged into 64 px rects;
  2. blocks mipmap regeneration in the GUI (`BlockUILodSync`);
  3. waits for merges (a BARRIER);
  4. uploads the whole dirty area in 512 px patches as one batch (`emitNotifyBatchUpdateStarted` /
     `Ended`).

  The comment: "Ideally the user should not notice that the image has changed :)"
- If a new LODN stroke arrives during RESUME, the executed resume commands are undone and an epoch
  counter voids the uploads still in flight.

**Undo** (`kis_image.cc:1845`)
- While `currentLevelOfDetail() > 0`, `postExecutionUndoAdapter()` writes to a
  `KisSurrogateUndoStore lodNUndoStore`, which is cleared when the RESUME drains.
- `tryUndoLastStrokeAsync` cancels a pending LOD0 stroke and its buddy. If the buddy has already
  finished, it undoes the surrogate store.
- Esc on a finished LOD0 stroke closes the LOD range and forces a resync, because "the buddy …
  doesn't store any undo data".

**The level plane** (`kis_paint_device.cc:682–846`, `kis_sync_lod_cache_stroke_strategy.cpp`)
- There is **one** LODN plane per device, not a pyramid. It is built straight from LOD0 by an
  alpha-weighted box mix over 2^lod × 2^lod cells (`mixColorsOp`).
- The plane is built in 512² CONCURRENT patches into a side structure, then uploaded atomically
  (`uploadLodDataStruct`), so a cancelled sync leaves the old plane.
- The display uploads LODN patches straight into GL mip level N and samples only that level
  (`KisTextureTile::update`, `fixedLodLevel` in `highq_downscale.frag`).

**When a preview is used**
- `lod = scaleToLod(zoom, numMipmapLevels = 4)`.
- A zoom change is **deferred until the current LOD range drains** (`switchDesiredLevelOfDetail`).
- Brushes below `lodSizeThreshold` (100 px) paint LEGACY at full resolution
  (`KisLodAvailabilityModel`).
- Per-option **blockers**: Fade sensor, overlay smudge, masking brush. Texture is only a
  "limitation".
- The feature is **off by default** (`KisConfig::levelOfDetailEnabled` → false).
- Strategies that refuse:
  - `KisFilterStrokeStrategy`, unless `filter->supportsLevelOfDetail`;
  - `MoveStrokeStrategy`, if any node `!supportsLodMoves()`;
  - freehand, if the preset or the node disallows it.

**Transform and liquify** skip the buddy and handle their own level (§2.1).

### 3.2 GEGL and GIMP

- **GEGL**
  - `mipmap-rendering` defaults to **FALSE** (`gegl/gegl-config.c:414`), and GIMP never enables
    it.
  - `GeglCache` keeps `valid_region[8]` per level (`graph/gegl-cache.c`).
  - `gegl_buffer_get` with a scale below 0.5 halves until it can read zoom-handler tiles.
- **GIMP's projection**
  - Validated lazily: `app/gegl/gimptilehandlervalidate.c` renders a level-0 tile when a `GET`
    reaches a dirty one, straight into the tile's memory.
  - The zoom handler above it pulls level-0 tiles through the validator, so **GIMP's zoomed-out
    display still renders at full resolution**, just lazily and visible first.
- **Filter previews** (`app/core/gimpdrawablefilter.c`) are rendered the same way. The
  applicator's `gegl:cache` node keeps what was drawn.
- **On commit, GIMP reuses the preview.** `gimp_drawable_merge_filter` copies (COW) every rect
  already valid in the applicator cache (`gegl_buffer_list_valid_rectangles`, level 0 only) and
  computes only the remainder.

### 3.3 What fits us

- **Per-store pyramids.** Our design already has them, which is more general than Krita's single
  plane, and 0.1.89 previews filters at the view level.
- **What Krita adds:**
  - **queue discipline:** previews first, full resolution after, one swap, and one level at a
    time;
  - **undo discipline:** a throwaway preview undo, and cancel or undo of pending replays;
  - **the blocker list.**
- **What GIMP adds:** "commit reuses the preview". That only holds where the preview was computed
  at level 0, which for us means zoom ≥ 100 %.

### 3.4 Recommendation (priority order)

1. **A stroke replay protocol** (a `luce-canvas` jobs module; `luce-image/.../brush.lucb`,
   `canvas/drawing.lucb`, `canvas/history.lucb`).
   - A preview stroke paints into a **preview overlay store at level L**. The compositor shows
     it in place of the layer's level-L tiles.
   - The level-0 replay is a job whose output store is **published in one swap** when it
     completes (immutability makes that a pointer exchange), and the preview overlay is dropped
     then.
   - Replays queue behind new previews. A new preview stroke pauses a running replay between
     batches.
   - Only one level runs per batch.
2. **Undo during replay.**
   - The history entry holds the dab list plus the pre-stroke store. While the replay is pending,
     that entry *is* the undo.
   - Undo before the replay finishes cancels the job and drops the overlay: Krita's surrogate
     store without the machinery.
   - Esc on a stroke whose replay has finished is an ordinary undo.
3. **LOD eligibility per tool and brush.**
   - A threshold on *level-0 tiles touched per frame* (for example > 64), measured rather than
     Krita's 100 px, because GPU dabs are cheap.
   - **Blockers:** pencil and hard 1 px modes, texture scale below 1 px at level L, clone and
     heal (their sources would need level-L windows too; allowed later).
   - **Smudge is allowed** (§2.4).
4. **Zoom changes during a range.** Keep painting the running preview at its level. The new
   level applies to the next stroke (Krita's deferred switch), so one stroke never mixes levels.
5. **Filter commit reuses preview tiles** (`luce-image/.../filter_preview.lucb`,
   `canvas/filter_previews.lucb`). When the preview ran at level 0 (zoom ≥ 100 %) its output
   tiles are keyed by input stamps and parameters, and the apply job takes them as finished
   cells.

---

## 4. Memory governance: swap, undo, copy-on-write

### 4.1 Tile COW

**Krita** (`libs/image/tiles3`)
- **Two counters.** `KisTileData::m_usersCount` ("tiles/mementoes use this tiledata through
  COW") decides copying. `m_refCount` decides lifetime.
- **Uncommitted undo items don't force copies.** They take only `ref()`;
  `KisMementoItem::commit()` promotes them with `acquire(); deref()`, after which the next write
  copies.
- **The copy** (`kis_tile.cc`): `KisTile::lockForWrite` takes a double-checked `m_COWMutex` when
  `m_usersCount > 1`, clones, and calls `registerTileChange`.
- **The tile "write lock" doesn't exclude other writers.** It takes the swap lock in read mode.
  The scheduler keeps writers on disjoint rects.
- **Sharing instead of copying:**
  - `bitBlt` shares tiles that are wholly inside the rect and copies only the edges;
  - `clear(rect, color)` shares **one** `createDefaultTileData(color)` across every covered tile.
    That is our `Solid` cell.
- **Lookups:** the tile hash is Preshing's lock-free Leapfrog map with QSBR reclamation
  (`kis_tile_hash_table2.h`). A missing tile reads as a detached default tile without being
  inserted.
- **Extent:** per-row and per-column tile-count histograms (`KisTiledExtentManager`), so it is
  kept up to date with no scan.
- **Background save:** clones the image with `KisTiledDataManager`'s copy constructor, which is
  O(tiles) handle copies with no history (`KisDocument::lockAndCloneForSaving`), then exports on
  `QtConcurrent`.

**GEGL** (`gegl/buffer/gegl-tile.c`, `gegl-buffer-access.c`)
- **Sharing.** `gegl_tile_dup` shares the data and increments an inline `n_clones`. The first
  `gegl_tile_lock` unclones it, and skips the `memcpy` when the tile is fully damaged (about to
  be overwritten entirely).
- **Buffer copies.** `gegl_buffer_copy` shares whole tiles when the grids line up and copies the
  fringes pixel by pixel. **COW only works at whole-tile granularity**, which GIMP respects by
  aligning undo rects to tile supersets (`gimp_drawable_real_push_undo`).
- **One global zero tile** of 512 KiB backs every empty tile, and is never counted
  (`gegl-tile-handler-empty.c`).

### 4.2 Swap and caches

**Krita** (`swap/kis_tile_data_swapper_p.h:47–60`, `kis_tile_data_swapper.cpp`)

```
emergency = hard limit;  hardThreshold = emergency − emergency/8;  hardLimit = hardThreshold − hardThreshold/8
softThreshold = soft limit (≤ hardThreshold);  softLimit = softThreshold − softThreshold/8
```

- **The passes.** After every undo commit the swapper is kicked, sleeps 0.7 s, and then runs:
  - a **soft pass** over *historical* tiles only (`mementoed() && numUsers() <= 1`);
  - if memory is still too high, an **aggressive** second-chance clock over all tiles.
- **Eviction never blocks.** It uses `m_swapLock.tryLockForWrite()`.
- **Past the emergency threshold, the allocating thread pays.** The `KisTileData` constructors
  call `checkFreeMemory()`, which runs the swap pass synchronously.
- **The swap file.** `KisChunkAllocator` places chunks first-fit (next-fit first) in one temp
  file, grows it in 64 MiB slabs, and then calls
  **`qFatal("KisChunkAllocator: out of swap space")`** at `maxSwapSize` (4 GiB by default).
  `KisMemoryWindow` maps a 16 MiB write window and a 4 MiB read window.
- **Limits are read once.** Changing them in Preferences takes effect after a restart
  (`KisStoreLimits`).
- **The pre-clone pooler** (`KisTileDataPooler`) is **off by default** (`memoryPoolLimitPercent`
  0).

**GEGL** (`gegl-tile-handler-cache.c`, `gegl-tile-backend-swap.c`)
- **The cache**
  - One global cache holds every buffer's tiles, counted in bytes with **each clone set counted
    once** (`n_cached_clones` 0→1).
  - Trimming is an approximate global LRU: the buffer cache with the oldest stamp goes first,
    then its tail.
  - The trim target is `size × (1 − ratio)`. The ratio doubles from 1 % to 50 % when trims come
    within 100 ms of each other, and resets after 200 ms of quiet.
  - It skips tiles in use, and evicts a dirty *shared* tile only with probability 1/n (evicting
    one clone frees nothing, but still costs a write).
- **The swap writer**
  - One writer thread, fed `gegl_tile_dup` snapshots, so the thread that asked never blocks on a
    mutable tile.
  - The queue is capped at 10 % of the cache size. When it is full, the **producer compresses
    the tile itself** before waiting (`push_queue`).
  - Reads are served from the queue if the tile is still there.
- **Swap blocks are refcounted.** A `TILE_COPY` of a swapped tile just points at the same block,
  so COW reaches the disk.
- **Swap files are cleaned by dead pid** at startup (`gegl-buffer-swap.c`).
- **Wash never runs.** `gegl_tile_handler_cache_wash`, which should write back dirty tiles when
  idle, only fires on `GEGL_TILE_IDLE`, and nothing sends that command.

**OIIO** (`libtexture/imagecache.cpp`, `imagecache_pvt.h`)
- A clock sweep of an atomic `m_used` bit. The hand is a tile ID, not an iterator, so it survives
  concurrent inserts.
- Eviction takes a `try_lock`: one thread evicts and the others carry on.
- A 2-entry per-thread microcache sits in front of a sharded map.

### 4.3 Undo accounting

| Project | Bound | Counting |
|---|---|---|
| Krita | `undoStackLimit` = **200 commands** (`kis_config.cc:192`); no byte limit | Memory is held down indirectly: history tiles are swapped first once past the soft limit (2 % of the hard limit) |
| GIMP | `undo-size` = RAM/8, `undo-levels` ≥ 5, a hard cap of 1024 (`gimp_image_undo_free_space`) | `gimp_gegl_buffer_get_memsize` = bpp × w × h: **COW sharing and sparsity are ignored**, so a shared whole-layer snapshot counts its full size |
| Pinta | none (`DocumentHistory.PushNewItem`) | a full-surface clone per stroke, then `SurfaceDiff` (a bitmask plus changed pixels, or the whole surface if it saves < 10 %) |
| luced-2d 0.1.88 | `canvas/history.lucb`: 4 GiB default, set in Settings › Undo memory | unique live tiles past those the document shows. That is right, and better than GIMP |

### 4.4 What fits us

- Immutable tiles already give us Krita's COW without locks. What we lack is the *policy* layer:
  - Krita's historical-first eviction;
  - GEGL's "count shared once" and "evict shared tiles last";
  - OIIO's non-blocking clock.
- The engine design already calls for demoting history first (class 1). Krita shows that the
  split needs no guessing, because "held only by history" is an exact reference-count test.

### 4.5 Recommendation (priority order)

1. **luce-canvas residency: reference counts by holder kind** (document, history, job, preview),
   as engine §5.3 says. In Krita's terms, historical = `document == 0 && history > 0`. Use it for:
   - class 1 eviction;
   - the undo budget in `canvas/history.lucb`, which then counts **exclusive history bytes per
     step**, so trimming a step frees a known amount;
   - the status-bar "History x GB".
2. **Governor thresholds with hysteresis.** Per tier, use Krita's ladder: evict history above
   *soft*, evict everything above *hard*, make the allocating thread pay above *emergency*, each
   step 7/8 of the one above. Borrow GEGL's adaptive trim ratio (1 %→50 % under pressure) so a
   big job doesn't trim one tile at a time.
3. **Eviction is a clock with `try_lock`**, as in OIIO and Krita. Only one thread evicts, and the
   others overshoot briefly rather than wait. The age resets on every `store.texture(...)` pin.
4. **The swap writer takes immutable tiles.**
   - There is nothing to snapshot (unlike GEGL's dup), so demotion can be queued straight from the
     main thread.
   - The queue is capped (10 % of the RAM budget); when it is full, the producer compresses
     before blocking (GEGL).
   - Refcount slab blocks, so a tile shared by the document and history is written once.
5. **Never crash when swap is full.** Krita's `qFatal` is the counter-example. Keep engine §5.4's
   rule: fall back to the next budget, then report "Out of scratch space".
6. **Clean swap files by dead pid at startup** (`gegl_buffer_swap_clean_dir`), under
   `~/.luce/cache/luced-2d/swap/<pid>/`.
7. **Background save and export read a store snapshot.** Clone the document's stores (O(cells)
   handle copies, like Krita's `lockAndCloneForSaving`) and let the export job read it while
   editing goes on. Immutability makes the clone exact.

---

## 5. Selections

### 5.1 Krita

**`KisPixelSelection`** (`libs/image/kis_pixel_selection.cpp`)
- It is an alpha8 paint device whose default pixel means "not selected". `invert()` flips the
  pixels in the painted region *and* the default pixel, so an inverted empty selection stays
  sparse.
- **The outline cache** is a `QPainterPath` in image space, **patched analytically when that is
  cheap**:
  - `select(rect)` adds or subtracts the rect's path;
  - invert is bounds minus the outline;
  - boolean operations combine two valid caches;
  - `moveTo` translates.

  Otherwise it is invalidated, including by any pixel transaction
  (`KisTransactionData::possiblyResetOutlineCache`). Undo restores the saved outline.
- **Rebuilding** (`outline()` then `KisOutlineGenerator`) reads the whole `selectedExactRect` into
  a `w·h` buffer plus a `w·h` marks array: **720 MB at 360 MP**, on one thread, falling back to
  tiled storage on `bad_alloc`. The staircase contours are not simplified.
- **Marching ants** (`libs/ui/kis_selection_decoration.cc`)
  - The rebuild runs as `KisUpdateOutlineJob` on worker threads behind a 50 ms compressor, and a
    newer job overrides an older one.
  - Every 150 ms the whole path is stroked twice (white, then dashed black) and the full canvas
    is updated. There is no culling and no level of detail.
- Thumbnails are capped at 2000 px.

**Flood fill** (`libs/image/floodfill/kis_scanline_fill.cpp`)
- It is templated on difference, selection and pixel-access policies, so the per-pixel code
  inlines.
- **No visited bitmap.** The forward stack of `KisFillInterval`s is paired with a
  **`backwardMap`** of spans already filled in the opposite direction, and `processLine` crops
  against it.
- **Raw runs within a tile.** `m_srcIt->moveTo` + `numContiguousColumns(x)` gives a raw-pointer
  run inside one tile.
- **Memoized difference.** `OptimizedDifferencePolicy` (`KisColorSelectionPolicies.h:55`) keys a
  `QHash<quint64, quint8>` on the raw pixel bits. RGBA F16 is 8 bytes, so it fits.
- **Threading and bounds:**
  - The contiguous fill is single-threaded; only "select similar" (non-contiguous) splits into
    CONCURRENT patches (`createSimilarColorsSelectionJobs`).
  - The magic wand (`kis_tool_select_contiguous.cc`) runs as a BARRIER job on a worker, bounded
    by the image, on the native format.
  - Grow, shrink, feather and anti-alias then run only over the result's rect plus the radius.

### 5.2 GIMP

- `gimp_pickable_contiguous_region_by_seed` works on a float copy of the buffer (per the chosen
  criterion) and writes a full-extent `Y float` mask.
- `find_contiguous_region` is a serial scanline over `gegl_sampler_get`, with a **1 × 1
  `gegl_buffer_get` per pixel** for the visited test and a 1-row `gegl_buffer_set` per segment.
- Select-by-color (global) is parallel. Line-art fill allocates a `width × height` float distance
  map (1.44 GB at 360 MP).

### 5.3 What fits us

- Our sparse 256 px `u8` cells with a GPU mirror (`selection_cells.lucb`, `selection_mirror.lucb`)
  are already better than both. They are sparse with whole-cell fast paths, and the wand already
  takes a wholly matching cell whole (`selection_sources.lucb`).
- **What to borrow:**
  - Krita's analytic outline patching;
  - the rebuild as an overridable background job;
  - the backward-interval scanline for mixed cells;
  - a memo of difference results keyed on raw `u64` f16 pixels, useful for the CPU path over
    flat art.
- **What to avoid:** Krita's full-canvas outline trace and unculled ant stroking.

### 5.4 Recommendation (priority order)

1. **Wand, Color Range and Load Selection classify on the GPU** (`selection_sources.lucb`,
   `canvas/selecting.lucb`, `color_range.lucb`, new shaders).
   - A match pass writes `r8` per cell, and cells are read back through the batched ring (§1.4).
   - A reduction over the selection-to-be pyramid marks cells as all or none, which become `Full`
     or `Empty` cells with no readback.
   - The CPU flood (`flood`) then runs over `u8` cells only, 8× fewer bytes than today.
   - Expected wand time on Linux: well under Mac's 1.2 s, since it is bandwidth-bound on 360 MB.
2. **Flood at two levels.** Flood the cell graph first: a cell is full, empty or mixed, and full
   cells propagate through their edges at no pixel cost. Run Krita's span fill with a backward
   map only inside mixed cells reached from the seed. Parallelize across independent mixed cells
   per wavefront.
3. **Marching ants from the selection's pyramid** (`luce-image/.../selection_mirror.lucb`, view
   drawing).
   - A GPU edge pass (coverage crosses 0.5 between neighbors) over the visible cells at the view
     level, animated by a dash phase in the shader.
   - No vector outline: this costs the screen, never 2 × W × H. Krita's outline cost is exactly
     what makes huge selections slow there.
   - If vector outlines are needed (Path from Selection), trace per cell on workers, skipping
     full and empty cells. Cache per cell by stamp, and stitch.
4. **Analytic fast paths stay analytic.** Rect or ellipse select, invert and move update cells
   directly (Solid cells) without any trace. 0.1.86–0.1.87 already do most of this.
5. **Grow, shrink and feather only over dirty cells plus the radius** (as Krita does after a
   fill), as tile jobs with a radius window (engine §9.2).

---

## 6. Streaming export and threading

### 6.1 What each project does

**libvips**, the model to copy (`libvips/iofuncs/sinkdisc.c`, `threadpool.c`, `thread.c`)
- **Strip height.** `vips_get_tile_size` sizes a strip of `n_lines` rows (384 for 16 threads)
  and pieces of 16 rows by full width (FATSTRIP), or 128² tiles.
- **Two strips** (`WriteBuffer buf`, `buf_back`):
  - workers compute pieces of `buf` straight into its memory (`vips_region_prepare_to`);
  - a background write thread per buffer encodes the other one.
- **The swap** is in `wbuffer_allocate_fn`:
  1. `wbuffer_flush` waits until `buf_back` is written, which preserves order;
  2. then `VIPS_SWAP(WriteBuffer *, write->buf, write->buf_back)` (line 371).
- **Memory** is exactly two strips plus per-thread regions. Strip k+1 is computed while strip k
  is encoded.
- The worker pool grows and shrinks with the number of idle workers (`vips_threadpool_run`).
- **Encoders**
  - PNG (`foreign/vipspng.c` `write_png_block`) points `row_pointer[]` into the region's memory
    and calls `png_write_rows`, with no copy. The defaults are **compression 6, filter NONE**
    (`pngsave.c:294–295`).
  - JPEG (`vips2jpeg.c` `write_jpeg_block`) is the same with `jpeg_write_scanlines`.
  - Interlaced PNG forces the whole image into memory.
  - There is no parallel deflate.

**Krita**
- **PNG buffers the whole image first.** `libs/ui/kis_png_converter.cpp` `RowPointersStruct`
  allocates every row before one `png_write_image` (line 1661), which is 2.9 GB for our target.
  Compression level 3, libpng's adaptive filters, no progress ("XXX: Implement progress
  updating").
- JPEG and TIFF stream row by row through `KisHLineConstIterator`. JPEG first composites over the
  fill color into a full-size second device.
- Export runs on a COW snapshot in `QtConcurrent` (§4.1).

**GIMP**
- `plug-ins/common/file-png.c` loops over strips of `gimp_tile_height()` (128) rows with
  `gegl_buffer_get` → `png_write_rows`, at compression **9** by default, single-threaded.
- The plug-in fetches pixels one 128² tile at a time through a synchronous wire round-trip
  (`libgimp/gimptilebackendplugin.c`), about 22,000 of them at 360 MP.
- TIFF offers BigTIFF past 4 GB (`file-tiff-export.c`: opens `"wb8"`, and retries on the size
  error).

**darktable** (`src/imageio/imageio.c` `dt_imageio_export_with_flags`)
- Runs the whole pipe at export size.
- Reads the result back once, into host RAM.
- `png_write_image`s it at level 5.

**OIIO**
- PNG level 6, `PNG_NO_FILTERS`. Issue #2645 in `pngoutput.cpp` explains why: no filter choice
  beat NONE on both time and size, and NONE is the fastest but makes the largest files.
- Writes through a 64 MB chunk buffer.

### 6.2 What fits us

- `bands.lucb` already streams 256-row bands and converts on workers, and `luce-png` already
  deflates bands in parallel (`encode.lucb`: "filters and deflates on a worker as an independent
  segment"). None of the studied projects has parallel deflate.
- What is missing is **overlap** (vips' two strips) and **cheap transfer** (§1).

### 6.3 Recommendation (priority order)

1. **Three-stage export pipeline** (`luce-image/.../canvas/bands.lucb`, `canvas/files.lucb`,
   luced-2d `export_dialog.luc` for progress and cancel):
   1. the GPU composites band k+2 and converts it to `rgba8` (or `rgb8` for JPEG) into ring
      slot A;
   2. the readback of band k+1 lands in slot B;
   3. the encoder consumes band k from slot C, reading the mapped memory directly as row
      pointers (vips' `write_png_block` shape, no copy).

   Wait on a slot's fence only when reusing it (vips' `wbuffer_flush`). Memory is 3 slots of
   15000 × 256 × 4 B = 46 MB. **Expected time** is max(GPU composite, readback, encode) per band,
   not their sum.
2. **Export from a snapshot on a worker** (Krita). Clone the stores, then run the pipeline as a
   job with progress and cancel, so the canvas stays live. The GPU stages remain batches on the
   render thread (engine §8).
3. **PNG defaults** (`luce-png` options passed by `canvas/files.lucb`).
   - Benchmark level 6 with filter NONE against adaptive, on the 360 MP test document.
   - vips and OIIO chose NONE for speed. With parallel deflate we may afford adaptive, but
     measure it.
   - Offer "Fast" (level 1–3) in the export dialog.
4. **TIFF: switch to BigTIFF automatically** when the estimated size is over 4 GB (GIMP's
   fallback, done up front). 16-bit TIFF of 360 MP RGBA is 2.9 GB uncompressed, so this is close.
5. **Streaming import** into cells (engine §9.4) is unchanged. Nothing studied does better than
   strip decoding.

---

## 7. Scheduling: long operations without blocking the UI

### 7.1 Krita

**Threads and jobs** (`libs/image/kis_update_scheduler.cpp`, `kis_strokes_queue.cpp`,
`kis_updater_context.cpp`)
- **One pool** of `idealThreadCount()` slots (`KisUpdaterContext`). Each slot runs one merge,
  stroke or spontaneous job. When a job finishes, `processQueues()` is called on that same thread
  and the slot picks up the next job, so threads don't sleep between small jobs.
- **The job taxonomy:** CONCURRENT, SEQUENTIAL, BARRIER (also waits for pending merges),
  UNIQUELY_CONCURRENT, plus EXCLUSIVE (no merges run at all). A job may insert new jobs at the
  front of its own stroke's queue (`addMutatedJobs`), so it can fan out and then fence.
- **Balancing:** `balancingRatio × strokes.sizeMetric() > updates.sizeMetric()` decides who goes
  first.
  - The default ratio is 100, which favours strokes.
  - The async brush sets 0.01, because "FPS is controlled separately".

**Projection updates**
- Split at 512 px, and merged only if the union stays within a patch and is no bigger than the
  parts (`maxMergeAlpha` 1.0).
- A merge whose access rect overlaps a running job is refused, so parallel merges stay disjoint.

**Canvas pacing**
- `KisCanvasUpdatesCompressor` drops a queued update contained in a newer one and signals the GUI
  once per 0→1 transition.
- `frameRenderStartCompressor` fires at `1000 / fpsLimit` = 10 ms (`FIRST_ACTIVE`).
- The transform preview waits 30 ms *and* `!hasUpdatesRunning()`.

**Cancel.** `KisStroke::cancelStroke` uses a state table: jobs marked non-cancellable (the final
merge) survive, and cancelling an indirect-painting stroke just drops the temporary target.

### 7.2 GEGL/GIMP

**GEGL** (`gegl/process/gegl-processor.c`, `gegl/gegl-parallel.c`)
- **Chunked processing.** `GeglProcessor` renders `chunk_size` (1 MP) × 4^level × threads per
  call, splitting a larger dirty rect into bands. `gegl_processor_work` returns "more work" and a
  progress fraction.
- **Thread-count cost model.** `gegl_parallel_distribute` minimises `n/k + c·k`. The thread cost
  `c` is measured as the median of 10 empty distributions, and each operation's `pixel_time` is
  re-measured after every call (`gegl_operation_get_pixels_per_thread`, capped at 128²).
- **Not re-entrant.** A nested distribute runs serially.

**GIMP** (`app/core/gimpprojection.c`, `gimpchunkiterator.c`, `gimp-parallel.cc`)
- **Projection rendering.** Main-thread idle callbacks at `G_PRIORITY_HIGH_IDLE + 22`.
  `GimpChunkIterator` sizes the next chunk as last area × interval / last time, takes the median
  of 3, handles the viewport-intersecting region first, and stops each tick after 1/15 s.
- **Filter apply.** `gimp_gegl_apply_cached_operation` uses the same iterator:
  - 1/8 s per chunk when interactive and 1 s otherwise;
  - area filters always get the long interval, "since their processing speed tends to be
    sensitive to the chunk size";
  - it pumps the main loop between chunks to catch cancel.
- **Async work.** `gimp_parallel_run_async` has **one** worker with a priority queue. A task that
  returns unfinished is resumed or re-queued, which gives cooperative time-slicing.
  - The canonical pattern is `gimp_line_art_prepare_async`: take a COW snapshot, run it on the
    worker, and poll `gimp_async_is_canceled`.

### 7.3 What fits us

- **One GPU queue on the render thread.** Our GPU work stays on the main thread, so the useful
  parts are:
  - GIMP's adaptive chunk sizing, per job, with a per-frame budget;
  - Krita's rules for what may run together (one level at a time, barriers for commits);
  - Krita's "previews first".
- **CPU work leaves the main thread.** Codecs, flood fills, compression and conversions belong
  on workers fed by readback tickets (§1.4). GIMP's single async worker is too few: vips and
  Krita use every core.
- **Measured costs.** GEGL's measured-cost model applies to our `parallel.lucb` fan-outs: don't
  spawn 16 threads for 64 × 64 pixels.

### 7.4 Recommendation (priority order)

1. **A frame scheduler** in a `luce-canvas` jobs module, with luced-2d `view.luc` calling it once
   per frame.
   - Priority classes, highest first (engine and research §5.11):
     1. visible composite;
     2. active stroke;
     3. LOD previews;
     4. replays;
     5. user jobs (apply, commit, export);
     6. prefetch and warm-up.
   - Each job has a GIMP-style chunk iterator: the next batch size is last cells × budget / last
     time, the median of the last 3, with a budget of 6 ms per frame while interacting and 14 ms
     when idle.
   - Visible cells come first.
2. **Job kinds in Krita's terms.** Concurrent cells are one batch. A *fence* separates dependent
   batches. A *barrier* waits for pending view composites (a commit publishing a store). An
   *exclusive* job pauses the view's refinement (a structural change such as canvas size).
3. **Readback tickets connect GPU jobs to CPU workers.**
   - A GPU batch ends with reads.
   - Its ticket is handed to a CPU worker, which converts, floods or encodes.
   - The main thread only polls fences.

   This is where most of the 13 s wand time goes away: the GPU classifies batch k+1 while CPU
   workers flood batch k.
4. **Cancel and progress everywhere.** Jobs check cancel between batches. Output stores are
   published in one swap, so cancel leaves no partial state (engine §8.2). Progress is cells done
   over cells total.
5. **Adaptive thread count for CPU fan-outs** (`luce-image/.../parallel.lucb`, `warp.lucb`,
   `selection_sources.lucb`): measure the cost per item, and use k = argmin n/k + c·k (GEGL).

---

## 8. Overall recommendation: where canonical pixels should live

### 8.1 The three options, for our feature set

**CPU-canonical, with the GPU as a display cache (Krita, GIMP, Photoshop)**
- *For:*
  - export, wand, heal, smudge and bounds read RAM directly;
  - memory tiers are one ladder (RAM → compressed → disk);
  - no driver differences in readback.
- *Against:*
  - GPU brushes, GPU filters, pyramids and compositing each need an upload of their inputs and a
    readback of their outputs. That is exactly the coherence traffic that got GEGL's OpenCL cache
    switched off.
  - Keeping those features fast would mean moving them to the CPU: brush dabs, 20+ blend modes,
    blur, adjustments, styles, transform and the pyramid build, in 16-bit float, vectorized,
    over every core. That rewrites most of luce-image.
  - Krita's CPU pipeline is 15 years of that work, and its huge-brush answer is still a
    downscaled preview.

**GPU-canonical (ours today)**
- *For:*
  - every interactive path (brush, composite, pyramid, filter preview, transform preview) stays
    on the GPU with no transfers;
  - Metal is already fast end to end.
- *Against:*
  - every CPU consumer pays a readback;
  - VRAM is the scarce tier;
  - Vulkan drivers punish naive transfers;
  - the CPU-side algorithms (heal, smudge, flood) fight the storage.

**Hybrid: GPU-canonical tiles with warm RAM copies (engine tiers G + R)**
- A tile is immutable, so a RAM copy made at any time stays valid for ever. There is no
  coherence protocol, which is exactly what GEGL lacked.
- Tiles are born on the GPU and **get an R copy lazily**:
  - in the same batch as a readback that is happening anyway;
  - by idle trickle;
  - when the governor demotes them.
- **CPU consumers ask the store for bytes.** R copies are served from RAM, and the rest are read
  through the batched ring.
- **Pixels produced on the CPU are uploaded once:** heal output, decoded images.
- On Apple silicon, shared-storage tiles make G and R one allocation.

### 8.2 Recommendation

**Keep GPU-canonical storage and build the hybrid through the planned tiers. Don't migrate to
CPU-canonical.** The measured problem is transfer overhead (§1.1), not the storage model. The
bytes involved (≤ 2.9 GB per full-layer pass, 0.36 GB for a mask) cost well under a second on
any discrete GPU when transfers are batched and pipelined.

Order of work, each step shippable on its own:

| # | Change | Modules | Expected effect | Cost |
|---|---|---|---|---|
| 1 | Profile the phases of `vulkan_texture_read` on LINUX and WINDOWS | luce-gpu (scratch profiler) | tells us whether allocation or waiting dominates | 1 day |
| 2 | A persistent, mapped, host-cached readback ring and upload staging ring | luce-gpu `vulkan/texture.lucb`, `metal/texture.lucb` | removes per-read allocation; likely most of the Linux/Windows gap for strip reads | 2–3 days |
| 3 | Batched reads at a row pitch plus tickets; `store.read_cells` | luce-gpu `Batch`; luce-canvas `tiles.lucb` | one wait per batch, not per cell; wand, bounds, Load Selection | 1 week (overlaps engine step 2) |
| 4 | GPU-side conversion before readback: `rgba8` export strips, `r8` wand, Color Range and alpha masks; all-or-none cell classification | luce-image `canvas/bands.lucb`, `selection_sources.lucb`, `canvas/selecting.lucb`, shaders | 2–8× fewer bytes, less CPU conversion | 1 week |
| 5 | Three-stage export pipeline from a snapshot | `canvas/bands.lucb`, `canvas/files.lucb` | export time = the slowest stage; the UI stays live | 3–4 days |
| 6 | Smudge on the GPU; Liquify as a displacement grid with a mesh-warp preview | `warp.lucb`, new `liquify.lucb`, `brush.lucb` | removes the smudge readback; 2000 px brushes at 60 fps | 2 weeks |
| 7 | Warm RAM copies (trickle plus piggy-backed reads) as the first residency tier | luce-canvas residency | CPU consumers mostly read RAM; frees VRAM safely | part of engine step 5 |

Items 2–5 target the two measured numbers:
- **Export** should approach the Mac's 1.4–2.4 s on Linux and Windows. That bound is set by
  encode throughput.
- **The Magic Wand** should come in under the Mac's current 1.2 s everywhere.

### 8.3 Migration cost and risks

**Cost of this path.** About 4–5 weeks for items 1–6. It is mostly engine work that CANVAS-ENGINE.md
§10 steps 2 and 5 already plan, done in a different order: readback first, because it is what's
measured as broken. No feature has to change where it computes.

**Cost of the alternative (CPU-canonical).** In our judgement, several months:
- a vectorized f16/f32 CPU implementation of every brush, blend mode, adjustment, filter, style,
  transform and pyramid pass;
- an upload path for every display update (Krita's PBO ring);
- rewriting every test that assumes GPU tiles.

The Mac would get slower at interactive painting of huge brushes, the one area where it is
strongest today.

**Risks of staying GPU-canonical, and how to handle them:**
- **Driver variance in host-cached memory.** Some devices lack `HOST_CACHED` or make it slow.
  - Mitigation: keep the uncached fallback, but copy out with streaming (non-temporal) loads, or
    make one bulk `memcpy` into RAM before any per-pixel work.
  - Measure on RADV and on NVIDIA Windows.
- **Reading tiles the GPU just produced stalls on their batch.** Mitigations:
  - tickets let the CPU work on older batches;
  - trickle copies mean most reads find R copies.
- **VRAM pressure on 4–8 GB cards.** The governor's tiers (engine step 5) have to land before
  documents grow past VRAM. Until then, a hard failure is possible where Krita would just swap.
  This is the strongest argument for doing step 7 early on Windows and Linux.
- **CPU-heavy tools stay awkward** (heal's solver, flood fills). Mitigations:
  - move heal's solve to the GPU (multigrid) later;
  - until then heal reads windows of cells through `read_cells`, which is fine at brush size.
- **Two code paths for Metal and Vulkan transfers.** Keep one luce-gpu API (ring, batch read,
  ticket) with thin backends, and test both paths in the "evict everything" stress mode (engine
  §11).

**When to reconsider.** If after items 2–4 a batched 360 MP rgba8 readback on NVIDIA Windows still
takes > 3 s, with allocation and waits ruled out by the profile, the bus or driver is the limit.
The fallback then is not CPU-canonical storage but **eager R copies**: every tile a job finishes is
read back in the same batch, at a cost of RAM. That turns the hybrid into "both copies always",
which is Photoshop's shape with a GPU front.

---

## Source index (paths in `.donors/study/`)

**Krita**
- Tiles and COW: `libs/image/tiles3/kis_tile.cc`, `kis_tile_data_interface.h`,
  `kis_tile_data_store.cc`, `kis_tile_data_pooler.cc`, `kis_tile_hash_table2.h`,
  `kis_tiled_data_manager.cc`, `KisTiledExtentManager.cpp`.
- Undo: `kis_memento_manager.cc`.
- Swap: `swap/kis_tile_data_swapper.cpp`, `swap/kis_tile_data_swapper_p.h`,
  `swap/kis_swapped_data_store.cpp`, `swap/kis_chunk_allocator.cpp`,
  `swap/kis_memory_window.cpp`, `swap/kis_tile_compressor_2.cpp`.
- Scheduling and LOD: `libs/image/kis_strokes_queue.cpp`, `kis_update_scheduler.cpp`,
  `kis_simple_update_queue.cpp`, `kis_updater_context.cpp`, `kis_stroke.cpp`,
  `kis_lock_free_lod_counter.h`, `kis_suspend_projection_updates_stroke_strategy.cpp`,
  `kis_sync_lod_cache_stroke_strategy.cpp`, `kis_paint_device.cc`, `kis_image.cc`,
  `kis_image_config.cpp`.
- Selections and fill: `kis_pixel_selection.cpp`, `kis_outline_generator.cpp`,
  `floodfill/kis_scanline_fill.cpp`, `KisColorSelectionPolicies.h`, `kis_fill_painter.cc`.
- Liquify: `kis_liquify_transform_worker.cpp`.
- UI and canvas: `libs/ui/opengl/kis_opengl_image_textures.cpp`,
  `KisOpenGLBufferCircularStorage.cpp`, `kis_texture_tile.cpp`, `libs/ui/canvas/kis_canvas2.cpp`,
  `kis_canvas_updates_compressor.cpp`, `kis_selection_decoration.cc`, `kis_png_converter.cpp`,
  `KisDocument.cpp`, `kis_config.cc`, `tool/strokes/freehand_stroke.cpp`,
  `KisAsynchronousStrokeUpdateHelper.cpp`.
- Plugins: `plugins/paintops/defaultpaintops/brush/kis_brushop.cpp`,
  `plugins/paintops/colorsmudge/*`, `plugins/tools/tool_transform2/*`,
  `plugins/tools/selectiontools/kis_tool_select_contiguous.cc`.

**GEGL**
- `gegl/buffer/gegl-tile.c`, `gegl-buffer-access.c`, `gegl-tile-handler-cache.c`,
  `gegl-tile-backend-swap.c`, `gegl-tile-handler-empty.c`, `gegl-tile-handler-zoom.c`,
  `gegl-tile-alloc.c`, `gegl-buffer-iterator.c`, `gegl-buffer-config.c`, `gegl-buffer-swap.c`.
- `gegl/process/gegl-processor.c`, `gegl/gegl-parallel.c`, `gegl/graph/gegl-cache.c`,
  `gegl/operation/gegl-operation.c`, `gegl-operation-area-filter.c`.
- `gegl/opencl/gegl-buffer-cl-iterator.c`, `gegl-buffer-cl-cache.c`, `docs/NEWS.adoc`.

**GIMP**
- `app/core/gimpprojection.c`, `gimpchunkiterator.c`, `gimp-parallel.cc`, `gimpasync.c`,
  `gimplineart.c`, `gimpdrawablefilter.c`, `gimpdrawable-filters.c`,
  `gimppickable-contiguous-region.cc`, `gimpimage-undo.c`, `gimp-memsize.c`, `gimpdrawable.c`.
- `app/gegl/gimptilehandlervalidate.c`, `gimp-gegl-loops.cc`, `gimp-gegl-apply-operation.c`.
- `app/config/gimpgeglconfig.c`, `libgimp/gimptilebackendplugin.c`.
- `plug-ins/common/file-png.c`, `plug-ins/file-jpeg/jpeg-export.c`,
  `plug-ins/file-tiff/file-tiff-export.c`.

**libvips**
- `libvips/iofuncs/buffer.c`, `region.c`, `generate.c`, `thread.c`, `threadpool.c`, `sinkdisc.c`,
  `sinkscreen.c`, `cache.c`.
- `libvips/conversion/tilecache.c`.
- `libvips/foreign/pngsave.c`, `vipspng.c`, `spngsave.c`, `vips2jpeg.c`.

**darktable**
- `src/common/opencl.c`, `opencl.h`, `darktable.c`.
- `src/develop/pixelpipe_hb.c`, `tiling.c`.
- `src/imageio/imageio.c`, `src/imageio/format/png.c`.

**OpenImageIO**
- `src/libtexture/imagecache.cpp`, `imagecache_pvt.h`.
- `src/libOpenImageIO/imagebuf.cpp`, `src/png.imageio/pngoutput.cpp`.

**libmypaint**
- `mypaint-tiled-surface.c`, `operationqueue.c`, `brushmodes.c`, `mypaint-brush.c`.

**Pinta**
- `Pinta.Core/Classes/Layer.cs`, `SurfaceDiff.cs`, `DocumentHistory`.
