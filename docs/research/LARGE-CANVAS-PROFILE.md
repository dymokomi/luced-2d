# luced-2d at 15000×24000 (360 MP): audit and profile

Measured 2026-09-25 on Apple Silicon (16 cores, 64 GB, Metal) with scratch
profilers (not in the repo). Companion to [LARGE-CANVAS-RESEARCH.md](LARGE-CANVAS-RESEARCH.md).

## What already scales

- Layers are 256² `rgba16_float` GPU tiles, shared copy-on-write between layers,
  undo and previews (`luce-image/src/luce_image/tiles.lucb`).
- The view draws only visible cells from a level-of-detail pyramid
  (`canvas/drawing.lucb`, `composite.lucb`), and cache keys follow content stamps.
- Brush strokes touch only dirty tiles, and pixel undo steps are pointer clones.
- Frames at 100 % and 50 % stay at 5–20 ms even at 360 MP.

## What fails outright at 360 MP

- Export (PNG/JPEG), saving `.l2d`, and reopening one. These fail above ~134 MP:
  the f64 `Image` raster runs into `max_bytes` 4 GiB and `max_pixels` 268 M.
- Free Transform of a full layer, Motion Blur, Lens Correction, Clone/Heal sources
  and layer styles all flatten a layer into one texture, which can't exceed 16384 px.
- Layer thumbnails and marching ants draw one quad per full-resolution tile and hit
  luce-gpu's 4,096 draws per frame.
- The Move-tool drag preview draws past luce-gpu's ±16384-point region limit.
- Windows (not measured): the Vulkan backend makes one `vkAllocateMemory` per tile,
  and drivers often allow only 4,096. One full layer is 5,546 tiles.

## Measurements

| step | 6 MP | 40 MP | 160 MP | 360 MP |
|---|---|---|---|---|
| fit frame, nothing changed | 0 ms | 122 ms | 480 ms | **1,074 ms** |
| 60-move stroke at fit | 125 ms | 7.4 s | 29 s | **64.8 s** |
| 60-move stroke at 100 % | 96 ms | 66 ms | 97 ms | 103 ms |
| fill full layer | 28 ms | 156 ms | 612 ms | 1.39 s |
| Levels | 13 ms | 88 ms | 351 ms | 780 ms |
| Gaussian blur r20 | 69 ms | 459 ms | 1.9 s | 4.5 s |
| free transform, full layer | 42 ms | 213 ms | 769 ms | **fails** |
| fill inside a selection | 168 ms | 1.15 s | 4.4 s | **10.5 s, 7.8 GB RSS** |
| histogram | 280 ms | 1.8 s | 7.6 s | **17.0 s** |
| save `.l2d` | 2.0 s | 13.2 s | **fails** | **fails** |
| export PNG | 1.0 s | 6.7 s | **fails** | **fails** |

Frames at fit zoom fall off a cliff between 24 MP (0 ms cached) and 35 MP (104 ms).

Opening a 24 MP picture:

| file | total | decode | `linear_rgba` | upload and first composite |
|---|---|---|---|---|
| JPEG | 7.6 s | 4.7 s, single-threaded | 1.8 s | 1.1 s |
| Sony ARW | 3.4 s | 1.2 s, threaded | 1.2 s | 1.0 s |

Windows (i9, 20 threads) takes about 1 s per MP to open, plus about 29 s to export a 24 MP PNG.

## Root causes

1. **The composite cache is too small.** It holds 512 tiles (`composite.lucb:84`),
   but a fit frame at 360 MP needs about 7,400 pyramid tiles, so every frame rebuilds
   from level 0. With a 12,000-tile budget the cached fit frame went from 1,074 ms to 0 ms.
2. **Each GPU tile pass is its own command buffer with a blocking wait.** On Metal that is
   `waitUntilCompleted`; on Vulkan, `vkQueueWaitIdle` plus a fresh staging buffer,
   framebuffer and descriptor pool. This is ~95 % of a cold frame, and it also dominates
   fills, adjustments, blur and uploads.
3. **Operations go back to one full-canvas buffer:**
   - `f32` RGBA: 5.76 GB at 360 MP
   - f64 `Image`: 11.5 GB
   - a full-canvas texture: not allowed above 16384 px
   - the CPU `u8` selection: 360 MB. Every structural undo step copies it, up to 64 × 360 MB.
4. **CPU pixel paths are scalar and single-threaded:**
   - `getpixel` does a per-pixel channel-name compare
   - a `pow` per sample, with no lookup table
   - per-sample `to_half`/`from_half`
   - byte-at-a-time PNG writes
   - JPEG and PNG decode into f64 on one thread

## Ranked work

| # | Problem | Fix | Needs a tiled, levelled canvas |
|---|---|---|---|
| B1 | The pyramid is rebuilt from level 0 each frame | Keep the levels, update the ancestors of dirty tiles, budget the cache in bytes | yes (core) |
| B2 | One submit and wait per tile pass | Batch tile passes into one command buffer; pool staging buffers and descriptors | luce-gpu |
| A1 | Save and export use whole images | Stream rows of tiles into the encoders; save layers as tiles | yes |
| A2 | Full-canvas textures | Tile-aware warp/resample shaders that read windows of tiles | yes |
| A3/A4 | 4,096 draws per frame; ±16384 regions | Thumbnails, ants and drag previews drawn from pyramid levels and culled | yes |
| A5 | Vulkan allocation count | Sub-allocate tiles from large blocks | luce-gpu |
| B3/B6 | The CPU selection copies | The selection as sparse GPU tiles, shared in undo | yes |
| B4 | Full-readback histogram | Compute it on the GPU or from a coarse level | yes |
| B5 | Full-resolution previews on every tick | Preview visible tiles at the view's level; apply full resolution once | yes |
| B7 | Shape and type layers rasterise the whole canvas | Rasterise only their tiles | yes |
| B8/B9 | Scalar single-threaded conversions and decode | Lookup tables, threads, decode straight into tiles | no |
| B11 | `relocate` is O(cells²) | Look tiles up by cell | yes |
