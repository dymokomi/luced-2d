# Large canvases in luced-2d: research and proposed architecture

Status: research, September 2026. No code was changed to write this.
Target: a 50 × 80 in canvas at 300 dpi, which is **15000 × 24000 px (360 MP)**. Painting,
panning, zooming, adjusting, transforming, undo and saving should all stay fast.

The document has three parts:

1. What luced-2d / luce-image do today, and what breaks at 360 MP (§1).
2. How Photoshop, Krita, GIMP/GEGL, MyPaint, Procreate, Affinity, Figma, virtual texturing and
   others handle huge images (§2–§4), with sources.
3. A concrete architecture and a staged migration plan (§5–§7).

---

## 0. Summary

- **luce-image already has the right base.** It has 256 × 256 `rgba16_float` tiles that are
  sparse (empty = `none`), immutable and copy-on-write. Tiles are shared between the document and
  history. The compositor cache is keyed per tile and per pyramid level on content stamps. This is
  the same shape as Photoshop's, Krita's and GEGL's designs. Most of what is missing is **scale
  plumbing** around it, not a new model.
- **Hard blockers on the target document today:**
  1. **Whole-layer `flatten()`** is used by motion blur, lens correction, transform commit, layer
     styles, selection passes and retouch. It builds one texture the size of the layer, and
     luce-gpu caps textures at 16384 px per side. 24000 is more than that, so these operations
     fail outright. Where they do fit, each one needs a second full copy of the layer (2.9 GB).
  2. **Vulkan: one `vkAllocateMemory` per tile texture.** Windows drivers cap live allocations at
     4096 (`maxMemoryAllocationCount`). One fully painted 360 MP layer is 5546 tiles, so it cannot
     exist on Windows. Linux/Mesa allows far more; Metal has no such cap.
  3. **Everything lives on the GPU for ever.** There is no CPU or disk residency, and history
     tiles also stay on the GPU. One full 16-bit layer is 2.9 GB. One filter step keeps another
     2.9 GB for undo.
  4. **Zoomed-out rendering builds the pyramid from the level-0 composite.** A level-4 tile needs
     256 level-0 composites. The composite cache holds 512 tiles (256 MiB, not the 512 MiB its
     comment says). After an edit, coarse levels re-composite hundreds of level-0 tiles × every
     layer.
  5. **Save and open go through whole-document buffers.** `flattened_pixels` allocates 360 M × 16 B
     = 5.8 GB of f32. The luce-image codecs decode to f64 (11.5 GB for 360 MP RGBA). Their default
     `max_pixels` of 268 M rejects a 360 MP file.
  6. **Masks and the selection are stored as `rgba16_float` tiles**: 8 B/px where 1–2 B/px would
     do (2.9 GB instead of 0.36 GB per full mask).
- **What the industry converges on:**
  - fixed-size sparse tiles (64–256 px on the CPU, 256+ px on the GPU);
  - copy-on-write tiles as the undo mechanism;
  - a **per-layer mip pyramid** (Photoshop "cache levels", GEGL zoom handler, Krita LOD planes);
  - compositing **only visible tiles, at the level of detail matching the zoom**;
  - progressive refinement with background threads;
  - a tiered memory hierarchy: GPU, RAM, compressed RAM, disk swap;
  - previews at view resolution, with full-resolution work done in the background.
- **Biggest wins, in order:**
  1. Fix the blockers: GPU suballocation, windowed gathers instead of `flatten`, 1–2 B masks,
     streaming I/O.
  2. **Per-layer pyramids plus compositing at the view level**, with dirty-tile propagation and a
     coarse-level fallback. This makes zoomed-out work O(screen), not O(document).
  3. **Residency tiers**: a GPU LRU pool, an LZ4-compressed RAM tier and disk swap. History is
     demoted first.
  4. Background job scheduling with LOD previews for big brushes, filters and transforms.
  5. A tiled native file with incremental save and an embedded pyramid.

---

## 1. Where luced-2d / luce-image stand today

Read from `luce-image/src/luce_image/{tiles,composite,brush,filter,transform,document}.lucb`,
`canvas/{drawing,files,history}.lucb` and `luce-gpu/src/luce_gpu/gpu/{texture,vulkan/device}.lucb`.

| Aspect | Today | At 15000 × 24000 |
|---|---|---|
| Tile | 256² `rgba16_float`, straight alpha, linear light, **GPU only** (`Tiles`, `tiles.lucb`) | 59 × 94 = **5546 tiles/layer**, 512 KiB each, 2.68 GiB per full layer |
| Sparsity | `none` = transparent tile | Good, but no "solid color" tile, so a full white fill or white mask costs a full layer |
| COW | `Tile.references`, `clone()` shares, `set()` replaces, `redrawn()` only when sole owner | Right model; history snapshots are `Tiles` clones |
| Content identity | `Tile.stamp` (u64), the compositor digests stamps per cell | Right model |
| Compositor | `Composer.tile(doc, col, row, level)`; level 0 = flatten all layers per cell; level L = `halve()` of 4 level L−1 tiles | Level L needs all 4^L level-0 composites. Cache budget 512 entries × 512 KiB = 256 MiB, LRU with a linear scan |
| View | `draw_canvas` picks L with ≤ 1 texel per **point**, draws only visible tiles, nearest filter if zoom ≥ 1, else linear | Visible-only is right. Level per point (not per device pixel) is soft on Retina. Per-tile linear draws can show seams |
| Brush | Dabs → per-tile paint buffer (ping-pong) → rebuild only the touched tiles; stamps change, layer revision does not | Good at 100 %. A 5000 px brush touches ~400 tiles per dab |
| Filters / transforms / styles / selection passes / retouch | Several use `flatten(device, tiles)`, which makes one texture of the whole extent | **Fails**: luce-gpu `Texture.create` rejects > 16384 px per side |
| Gaussian blur | Separable, per tile with neighbour tiles (`pass`) | Right pattern; reach is limited to one neighbour tile (≤ 256 px halo) |
| Undo | Pixel snapshots = `Tiles` clones of the replaced tiles; state snapshots share tiles | Right model, but every history tile is pinned on the GPU |
| Save | `flattened_pixels` allocates W × H × 4 f32; layers go to PNG via f32 | 5.8 GB f32 plus the readback buffer; PNG encode of 360 MP in memory |
| Open | luce-image codecs decode to interleaved **f64** (DESIGN.md: "4096² RGBA = 512 MiB") | 11.5 GB; default `max_pixels` 268,435,456 < 360 M, so it is refused |
| GPU memory | Vulkan: `vulkan_memory()` calls `vkAllocateMemory` **per texture**. Metal: one `newTextureWithDescriptor` per tile (private storage) | Windows cap of 4096 allocations → fails after ~4000 tiles (≈ 1 full 256 MP layer) |
| Bounds | `content_bounds()` reads back **every** painted tile from the GPU | 2.9 GB of readback for a full layer |
| luce-gpu | No compute, no texture arrays, ≤ 4 sampled images per draw, 128 B uniforms, formats `rgba8`, `rgba8_linear`, `rgba16_float`, `r8` | Constrains the design: atlases need an indirection or per-tile draws |

**Consequence:** most of the model is right. What needs to change is how tiles are **stored**
(residency, formats, allocation), how **coarse levels** are produced (per layer, not per
composite), and every place that assumes **one texture per layer** or **one buffer per image**.

---

## 2. How the established systems do it

### 2.1 Adobe Photoshop

- **Virtual memory of tiles.** Photoshop runs its own VM. At start-up it sizes a RAM pool (70 %
  of RAM by default) split into pages. "A tile is a square area of pixels of a single layer
  including geometry bounds. A tile consumes one or more pages." Scratch files on disk back the
  pages. "The VM is responsible for ensuring that source and destination tiles for the current
  iteration are in memory, loading them from scratch files as required," and flushes pages to
  make room. The same VM holds image data, **all undo history**, and the working storage of the
  current command.
  ([Chrome Developers: How Photoshop solved working with files larger than can fit into memory](https://developer.chrome.com/blog/how-photoshop-solved-working-with-files-larger-than-can-fit-into-memory),
  [photoshopguides: Performance](https://photoshopguides.github.io/Performance))
- **Image pyramid = "Cache Levels".** "Image data is stored using a mipmap representation, a
  pyramidal set of tiles providing image data at a range of low to high resolutions," so
  Photoshop works on data at the right resolution when zoomed out or previewing.
  - Cache Levels range 1–8, default 4.
  - Level 1 disables the pyramid ("only the current screen image cached").
  - Adobe recommends **> 4 for documents of 50 MP or more**. The "Huge Pixel Dimensions" (formerly
    "Big and Flat") preset sets **6 levels and 1024 K tiles**. "Web/UI" sets 2 levels and 128 K.
  ([Chrome blog](https://developer.chrome.com/blog/how-photoshop-solved-working-with-files-larger-than-can-fit-into-memory),
  [Adobe community: cache levels & tile size](https://community.adobe.com/t5/photoshop/selecting-cache-levels-tile-size-in-preferences-gt-performance/m-p/9939657),
  [Adobe community: huge pixel dimensions and many layers](https://community.adobe.com/questions-712/optimizing-cache-levels-and-tile-size-for-huge-pixel-dimensions-and-many-layers-1176182))
- **Cache Tile Size** is given in bytes per tile: 128 K / 132 K / 1024 K / 1028 K.
  - The odd sizes worked around Pentium 4 cache aliasing. Chris Cox (Adobe): "1024 should be fine
    for 99.9 % of folks."
  - Bigger tiles speed up whole-image operations (filters). Smaller tiles make brush strokes more
    responsive, because fewer bytes are dirtied per dab.
  - The pixel geometry per tile is not documented. 1 MiB is about 512² RGBA8 interleaved or
    1024² for one 8-bit plane.
  ([Adobe community: Cache Tile Size, logic of use](https://community.adobe.com/questions-712/2018-cache-tile-size-logic-of-use-help-pls-1067233))
- **History.** Undo states live in the same tile VM. Only changed tiles are new, but a
  whole-image filter makes a whole-image state. The default is 50 states. For multi-GB files,
  experts advise about 20. "Purge Histories" frees them.
  ([Adobe community thread](https://community.adobe.com/questions-712/optimizing-cache-levels-and-tile-size-for-huge-pixel-dimensions-and-many-layers-1176182),
  [photoshopguides](https://photoshopguides.github.io/Performance))
- **Limits.** PSD is limited to 30000 px per side and 2 GB. **PSB goes to 300000 px per side.**
  Above 30000 px some plug-in filters are unavailable (they assume one in-memory buffer).
  ([bwillcreative: PSD vs PSB](https://www.bwillcreative.com/psd-vs-psb-photoshop-files/))
- **Bit depth.** "16-bit" is really 0..32768 (15 bits + 1), chosen so that blends use shifts and
  have an exact midpoint. It is 8 B/px for RGBA, the same as our `rgba16_float`.
  ([Adobe community: 16-bit or 15-bit+1?](https://community.adobe.com/questions-712/16-bit-or-15-bit-1-1132730))
- **GPU.** The GPU is used for canvas display (zoom, pan, rotate) and some features. The pixel
  data model is CPU and VM. Brush lag on 300 dpi documents is classically a sign of running out
  of RAM and paging to scratch.
  ([cgdirector: Photoshop brush lag](https://www.cgdirector.com/how-to-fix-photoshop-brush-lag/))

### 2.2 Krita

Read from the source (invent.kde.org/graphics/krita, `libs/image/tiles3`, `libs/ui/opengl`,
`kis_image_config.cpp`).

- **Data tiles: 64 × 64 px** (`__TILE_DATA_WIDTH 64`), any pixel size. A `KisTiledDataManager`
  keeps a hash table of tiles. Missing tiles read as the device's **default pixel**, so they cost
  nothing.
  ([KDE wiki: Tile Data Format](https://community.kde.org/Krita/Tile_Data_Format))
- **COW and undo.** `KisMementoManager`: when a tile gets new tile-data through COW, the old data
  is wrapped in a `KisMementoItem`. At `commit()` the memento becomes a co-owner. "Every write
  request to the original tile will lead to duplicating tileData and registering it here again."
  Undo is a list of per-tile old data, the same as our snapshot model.
- **Memory limits** (defaults from `KisImageConfig`):
  - hard limit = 50 % of RAM;
  - soft limit = 2 %;
  - pool limit = 0 %;
  - max swap 4096 MiB;
  - swap slab 64 MiB;
  - swap window 16 MiB.

  The swapper (`kis_tile_data_swapper_p.h`) has graded thresholds:
  - above the **soft limit**, it swaps out *memento (undo) tiles*;
  - above the **hard limit**, it swaps out working tiles until the level drops back under it;
  - above the **emergency threshold**, new tiles are not created until memory is freed.

  Each threshold is 1/8 above the level it drains to.
  ([kis_image_config.cpp](https://invent.kde.org/graphics/krita/-/blob/master/libs/image/kis_image_config.cpp))
- **Compression.** Swap and `.kra` use the same compressor, `KisTileCompressor2`. It is **LZF**
  after `linearizeColors`, which splits pixels into per-channel planes so bytes of the same
  channel sit together and compress better. Tiles are compressed individually, and each tile
  header records the codec. Saving used to be slow because of whole-file zip, and per-tile
  compression fixed it.
  ([KDE wiki: Tile Data Format](https://community.kde.org/Krita/Tile_Data_Format))
- **Projection updates.** Dirty rects are walked up the layer tree and merged in patches of
  **512 × 512** (`updatePatchWidth/Height`), on all cores. `KisUpdateScheduler` balances two
  queues (canvas updates and stroke jobs). Jobs are concurrent, sequential or barrier.
  ([Krita strokes documentation](https://docs.krita.org/en/untranslatable_pages/strokes_documentation.html))
- **OpenGL canvas.**
  - Texture tiles are **256 px** by default (`openGLTextureSize`).
  - Each has an **overlap border of 2^numMipmapLevels = 16 px** (`numMipmapLevels` = 4), so every
    texture tile's own mipmaps sample correctly across tile seams.
  - 8-bit images upload as RGBA8, 16-bit as RGBA16, float as RGBA16F/RGBA32F.
  - Updates go through `glTexSubImage2D` on only the changed part.
  - A 2017 attempt to use 2048 px textures was **reverted after 9 days**: a small brush on a
    large canvas forced regeneration of whole large mip chains. The measured fps gain (46 → 94 fps
    at 1024 px) was not worth it.
  ([Phabricator D8280](https://phabricator.kde.org/D8280),
  [kis_opengl_image_textures.cpp](https://github.com/KDE/krita/blob/master/libs/ui/opengl/kis_opengl_image_textures.cpp))
- **Level of detail ("Instant Preview", Kickstarter 2015).**
  - The canvas picks `lod = scaleToLod(zoom, numMipmapLevels)`, at most 4 (1/16).
  - A "sync LOD cache" stroke builds, **per paint device**, a LOD clone by box-averaging
    2^lod × 2^lod cells (`updateLodDataManager` uses `mixColorsOp` over each cell).
  - A stroke is then executed **twice**: first on the LOD planes for instant feedback, then on
    the full-resolution data in the background.
  - It works for freehand and geometric tools, move, filters and animation.
  - Brush features whose output is not scale-invariant (auto-spacing, fuzzy size, tip density,
    texture) cause visible "popping" when the full-resolution result replaces the preview. The
    default activation threshold is a **100 px brush**.
  ([Krita manual: Instant Preview](https://docs.krita.org/en/reference_manual/instant_preview.html),
  source `kis_paint_device.cc`, `kis_canvas2.cpp`)

### 2.3 GIMP / GEGL

Read from the source (gitlab.gnome.org/GNOME/gegl, gimp `app/core`).

- **GeglBuffer.**
  - Default tile **128 × 128** (`tile-width/height` in `gegl-buffer-config.c`; older docs say
    128 × 64).
  - Tile cache 512 MiB by default. GIMP's preference suggests half of RAM or more.
  - Tiles pass through a **tile-handler chain**: empty handler → zoom handler → cache → backend.
  - The **empty handler** returns one shared zero tile for missing tiles (sparse).
  - The **zoom handler** (`gegl-tile-handler-zoom.c`) synthesises a level-z tile on demand by
    downscaling 4 level-(z−1) tiles. Each tile carries a 64-bit **damage mask** (8 × 8 sub-regions)
    so mipmap invalidation is finer than a tile.
  - Backends: RAM, file, swap.
  ([GEGL environment](https://www.gegl.org/environment.html),
  [gegl-tile-backend.h](https://gitlab.gnome.org/GNOME/gegl/-/blob/master/gegl/buffer/gegl-tile-backend.h))
- **Swap compression** (GIMP 2.10.14+). The aliases are:
  - "fast" (default) = **rle8**, falling back to zlib1;
  - "balanced" = rle4 or zlib;
  - "best" = zlib9.

  Compression "can both reduce the swap size and increase its speed by minimizing input/output."
  ([GIMP 3.0 manual: System Resources](https://docs.gimp.org/3.0/en/gimp-prefs-system-resources.html),
  `gegl-compression.c`)
- **Level-aware processing.** `GeglProcessor` takes a `level`. It renders `rect >> level` and
  asks each node's cache whether that rectangle is already valid at that level
  (`valid_region[level]`). With `GEGL_MIPMAP_RENDERING`, ops run on the smaller versions
  ("generates a smaller version of the original image and processes it for preview" while "the
  real thing" is computed in the background).
  ([Libre Arts: GEGL gets mipmaps](https://librearts.org/2015/06/gegl-gets-mipmaps/),
  `gegl-processor.c`)
- **GimpProjection** (the composite).
  - It is a **tile pyramid**: memory estimate × 4/3, "a geometric sum with a ratio of 1/4".
  - It renders **asynchronously in chunks** with a **priority rect** (the visible area).
    `GimpChunkIterator` targets **1/15 s per chunk** and adapts the chunk area from the median of
    the last 3 timings (min 4096 px², max 4096 × 4096).
  - Invalidation is aligned to 32 × 32 update chunks.
  - Layer groups render in big chunks rather than tile by tile (2.10.10).
  ([gimpprojection.c](https://gitlab.gnome.org/GNOME/gimp/-/blob/master/app/core/gimpprojection.c),
  [gimpchunkiterator.c](https://gitlab.gnome.org/GNOME/gimp/-/blob/master/app/core/gimpchunkiterator.c),
  [GIMP 2.10.8 news](https://www.gimp.org/news/2018/11/08/gimp-2-10-8-released/))

### 2.4 MyPaint / libmypaint

- **64 × 64 tiles** of RGBA **fix15** (uint16 where 1<<15 = 1.0), premultiplied. Tiles exist
  only where painted. Only the tiles a stroke touches are recomposited, and the screen update is
  clipped to the bounding box of the new dabs.
- Dab mask generation dominates the brush cost. The engine batches dabs and processes tiles in
  parallel.
  ([MyPaint Development Documentation](https://github.com/mypaint/mypaint/wiki/Development-Documentation),
  [libmypaint PERFORMANCE](https://github.com/mypaint/libmypaint/blob/master/PERFORMANCE),
  [mypaint-tiled-surface.c](https://github.com/mypaint/libmypaint/blob/master/mypaint-tiled-surface.c))

### 2.5 Procreate

- Limits are set **by RAM, not by design**: layers × pixels must fit.
  - M1 iPad Pro 8 GB: 8192² × 11 layers.
  - M1 iPad Pro 16 GB: 8192² × 24 layers, and 16384 × 8192 × 10 layers.
  - 24 layers at 8192² RGBA8 is 6 GiB, which suggests roughly uncompressed 8-bit residency in
    unified memory, capped by what iPadOS lets an app use.
- The largest canvas matches the 16384 Metal texture limit on one side.
  ([Procreate: layer limits](https://procreate.com/insight/2021/layer-limits),
  [Procreate on X](https://x.com/Procreate/status/1637679823429545985))
- Lesson: a fully resident, GPU-first design is simple and fast, but it hard-caps document size.
  Photoshop and Krita avoid that cap with a VM and tiles.

### 2.6 Affinity Photo, Pixelmator Pro, Photopea

- **Affinity:**
  - It exposes a **RAM Usage Limit** (the slider tops out at 64 GiB) and a scratch folder.
  - Affinity Designer's canvas limit depends on dpi (640 × 640 in at 400 dpi = 256000 px per
    side; 853 × 853 in at 300 dpi), so the internal limit is in pixels, not inches.
  - Internals are not public.
  ([Affinity forum: RAM usage limit](https://forum.affinity.serif.com/index.php?%2Ftopic%2F152526-affinity-photodesignerpublisher-performance-settings-ram-usage-limit-bug%2F=),
  [Affinity Preferences](https://s3-eu-west-1.amazonaws.com/affinity-docs/help/photo/en-US.lproj/pages/Workspace/preferences.html))
- **Pixelmator Pro** is built on Metal and Core Image. Core Image renders in tiles internally,
  and Pixelmator's "zoom engine" shows large images at any zoom without lag. Details are not
  published.
  ([AppleInsider](https://appleinsider.com/articles/17/09/05/pixelmator-pro-image-tool-with-coreml-metal-2-enhancements-coming-in-the-fall-to-ios-macos),
  [Wikipedia: Pixelmator Pro](https://en.wikipedia.org/wiki/Pixelmator_Pro))
- **Photopea** uses WebGL where the canvas fits `MAX_TEXTURE_SIZE`. It only auto-disables WebGL
  when the canvas exceeds the limit, and oversize layers in free transform are a known failure.
  This is the same class of bug as our `flatten()`.
  ([photopea issue #4303](https://github.com/photopea/photopea/issues/4303)).
  The generic WebGL advice for 32000² output is to render in 1024² parts and assemble them.
  ([WebGL2 Fundamentals](https://webgl2fundamentals.org/webgl/lessons/webgl-qna-how-to-render-large-scale-images-like-32000x32000.html))

### 2.7 Figma

- The renderer is "a highly-optimized **tile-based** engine" on the GPU, written from scratch
  (WebGL, now WebGPU). Only what is visible is rendered; zoom and pan trigger just-in-time tile
  rendering.
- The WebGPU port batches uniforms and draws into few render passes and caches bind groups. That
  is the same concern as our "one render pass per tile" cost (§5.9).
  ([Figma: Building a professional design tool on the web](https://www.figma.com/blog/building-a-professional-design-tool-on-the-web/),
  [Figma: Rendering powered by WebGPU](https://www.figma.com/blog/figma-rendering-powered-by-webgpu/))

### 2.8 Virtual texturing, megatextures, map tiles

- **Sparse virtual textures** (Barrett, GDC 2008; id Tech 5 / RAGE):
  - A huge virtual texture is cut into pages, typically **128 × 128 including a 1 px border**
    (126 usable). The border lets bilinear filtering stay inside a page.
  - A **page table / indirection texture** (itself mipmapped) maps virtual pages to slots in a
    **physical page cache** (one big atlas). A low-resolution **feedback pass** (for example ¼ × ¼
    of the screen) reports which pages and mips are needed. Pages stream in and are evicted LRU.
  - The **coarsest level stays resident**, so there is always something to show.
  - RAGE used 120k × 120k virtual textures (about 53 GB as DXT).
  ([GDC 2008 Barrett](https://archive.org/details/GDC2008Barrett),
  [Sparse Virtual Textures, T. Sagristà](https://tonisagrista.com/blog/2023/sparse-virtual-textures/),
  [Holger Dammertz notes](https://holger.dammertz.org/stuff/notes_VirtualTexturing.html),
  [id Tech 5 Challenges](https://mrl.cs.vsb.cz/people/gaura/agu/05-JP_id_Tech_5_Challenges.pdf))
- **Hardware sparse textures.**
  - Metal sparse textures map tiles of **64 KB on macOS and 16 KB on iOS** from an
    `MTLHeapType.sparse` heap. Apple's sample "Streaming large images with Metal sparse textures"
    uses access counters to decide residency.
  - Vulkan has sparse residency (`sparseResidencyImage2D`), with uneven support.
  - These are an option later, not a need: an explicit tile table does the same job portably.
  ([Apple: sparse tile size](https://developer.apple.com/documentation/metal/mtldevice/sparsetilesize(with:pixelformat:samplecount:)),
  [Apple: streaming large images](https://developer.apple.com/documentation/metal/metal_sample_code_library/streaming_large_images_with_metal_sparse_textures))
- **Map tiles** (Google Maps, OSM, Deep Zoom, FlashPix) are the same idea as an image pyramid:
  256 px tiles per zoom level, with the client drawing the parent tile scaled while children load.
  FlashPix (Kodak, 1996) was literally "a tiled, multi-resolution image" format for editing big
  images on small machines.
  ([Wikipedia: FlashPix](https://en.wikipedia.org/wiki/FlashPix))

### 2.9 Blender texture paint

- A 16K texture at 1 byte/px is already 256 MB, and several may be painted at once (channels,
  UDIMs).
- Blender's PBVH image-paint design paints per UDIM tile and updates GPU textures partially.
  **Mipmap regeneration during painting is a known cost** (older versions turned mipmaps off in
  paint mode). This is the same lesson as Krita's D8280.
  ([Blender #96223 PBVH image texture painting](https://projects.blender.org/blender/blender/issues/96223),
  [Blender PR #160670](https://projects.blender.org/blender/blender/pulls/160670))

---

## 3. Common techniques, distilled

| Technique | Who | What it buys | Notes for us |
|---|---|---|---|
| Fixed tiles, sparse (missing = default pixel) | all | Memory ∝ painted area; O(1) random access | Have it. Add a **solid** tile (one color) |
| COW tiles as undo | Krita mementos, PS VM, us | An undo step costs only the changed tiles | Have it. Needs demotion off the GPU |
| Per-layer mip pyramid (box 2 × 2) | PS cache levels, GEGL zoom handler, Krita LOD | Zoomed-out display and preview cost ∝ screen | **Missing** (we only pyramid the composite) |
| Composite only visible tiles at view LOD | PS, Krita, GIMP, Figma | Frame cost independent of document size | Have visible-only; the LOD is built wrongly (bottom-up from level 0) |
| Dirty-tile tracking, propagated up the pyramid | GEGL damage masks, Krita dirty rects | A stroke costs O(touched tiles × levels) | Stamps give it for free if the pyramid is per layer |
| Progressive refinement (coarse first) | GIMP chunk iterator, VT, maps | No blank canvas; latency hidden | Missing |
| Background threads / time-sliced jobs | all | UI stays at 60 fps during long work | Missing (GPU work is synchronous on the main thread) |
| Run the op on the preview level, then full resolution | Krita LOD strokes, GEGL mipmap rendering | Instant feedback for big brushes and filters | Missing |
| GPU tile cache or atlas with residency and LRU | Krita textures, VT | GPU memory bounded | Missing (all tiles resident, one allocation each) |
| Compress cold tiles | Krita LZF, GEGL rle/zlib | 2–10× on flat art, ~1.2–1.6× on photos | Missing; needs LZ4 |
| Disk swap in slabs | PS scratch, Krita 64 MiB slabs, GEGL swap | Documents larger than RAM | Missing |
| Soft limit for undo, hard limit for working data | Krita | History goes cold first | Missing |
| 16-bit int vs f16 vs f32 | PS 15+1 int, Krita int16/F16/F32, GIMP linear float | Precision vs 2× memory | We use f16. Offer 8-bit storage for 8-bit documents |
| Adjustments evaluated lazily per tile | PS adjustment layers, GEGL graph | No pixels stored | Have it (compositor) |
| Per-tile compression in the file, embedded pyramid | Krita `.kra` v2, PSB composite + thumbnails | Fast save, fast open preview | Missing (PNG per layer) |

---

## 4. Memory math for 15000 × 24000 (360 MP)

### 4.1 Per full layer (level 0)

| Storage | B/px | One full layer | + full pyramid (×4/3) |
|---|---|---|---|
| RGBA8 | 4 | 1.44 GB (1.34 GiB) | 1.92 GB |
| RGBA16 int / **RGBA16F (ours)** | 8 | **2.88 GB (2.68 GiB)** | 3.84 GB |
| RGBA32F | 16 | 5.76 GB (5.36 GiB) | 7.68 GB |
| Mask R8 | 1 | 0.36 GB | 0.48 GB |
| Mask R16F | 2 | 0.72 GB | 0.96 GB |
| Mask stored as RGBA16F (today) | 8 | 2.88 GB | 3.84 GB |

### 4.2 Tile counts at 256 px

Padding waste is 1 % (15104 × 24064).

| Level | Scale | Grid | Tiles | Fits on a 2880 px tall screen? |
|---|---|---|---|---|
| 0 | 1 | 59 × 94 | 5546 | 100 % zoom |
| 1 | 1/2 | 30 × 47 | 1410 | |
| 2 | 1/4 | 15 × 24 | 360 | |
| 3 | 1/8 | 8 × 12 | 96 | whole document at ~12 % (Retina fit) |
| 4 | 1/16 | 4 × 6 | 24 | fit on a 1440 pt display |
| 5 | 1/32 | 2 × 3 | 6 | |
| 6 | 1/64 | 1 × 2 | 2 | |
| 7 | 1/128 | 1 × 1 | 1 | thumbnail / navigator |

Levels 1–7 together hold 1899 tiles, 34 % of level 0.

A 5120 × 2880 (5K) viewport needs at most (20 + 1) × (12 + 1) = **273 tiles** at the view's
level, whatever the document size. At RGBA16F that is 137 MiB for the composite of one screen.
**The view working set is bounded by the screen, not the document.** This is the invariant the
architecture must protect.

### 4.3 A realistic document

Take a realistic 360 MP, 16-bit document with 12 layers:

- 6 full-canvas photographic layers: 6 × 2.88 = 17.3 GB;
- 4 paint layers at ~20 % coverage: 2.3 GB;
- 2 adjustment layers with masks: R8 0.72 GB (today 5.8 GB).

Level 0 totals about **20 GB**. With 50 history steps that include one full-layer filter, add
+2.9 GB per such step.

- **Photoshop** would hold the same ~20 GB (its 16-bit is also 8 B/px) in 70 % of RAM plus scratch
  disk, and would page.
- **Krita** in 16-bit integer would use the same 8 B/px, up to 50 % of RAM, then swap to LZF (max
  4 GiB of swap by default, which is too small for this, so the user must raise it).
- **Procreate** could not open it at all (16384 max per side).

Practical budgets for luced-2d:

| Machine | GPU tile pool | RAM tile tier (uncompressed + compressed) | Disk swap |
|---|---|---|---|
| Mac 16 GB unified (Metal working set ≈ 65–75 % of RAM ≈ 11–12 GB; [Apple forum](https://developer.apple.com/forums/thread/732035)) | 3 GiB (~6000 tiles) | 5 GiB | 32 GiB |
| Mac 32 GB unified | 6 GiB | 12 GiB | 64 GiB |
| PC 32 GB RAM, 8 GB discrete GPU | 3.5 GiB | 14 GiB | 64 GiB |
| PC 32 GB RAM, 16 GB discrete GPU | 8 GiB | 14 GiB | 64 GiB |

Default GPU pool = min(45 % of VRAM, 8 GiB) on discrete GPUs, and min(25 % of RAM,
0.5 × `recommendedMaxWorkingSetSize`) on unified memory. Unified memory also holds the RAM tier,
so the two must share one budget. On Apple silicon, a GPU tile in shared storage *is* the RAM
copy, so the tiers can merge (§5.4).

With these budgets the realistic document fits: its working set is about 1 GB, and cold layers
and history sit compressed or on disk. A **full-resolution operation over a whole layer**
(filter, transform commit, save) streams through the pools tile by tile and never needs the
layer resident at once.

---

## 5. Proposed architecture for luce-image / luced-2d

Design rule: **every operation's cost scales with (tiles it touches at the level it runs at) or
(tiles on screen), never with document size.** The only exceptions are explicit
full-resolution jobs (apply filter, commit transform, export). Those run in the background in
tile order.

### 5.1 Tiles: size, formats, variants

- **Keep 256 × 256.** It matches Krita's GPU texture tile, map tiles and the VT page class.
  - It is 512 KiB at RGBA16F.
  - The per-draw overhead is amortised over 65536 px.
  - A 50 px brush dirties 1–4 tiles.

  The 64 px CPU tiles of Krita and MyPaint suit CPU brush engines. Our brushes run on the GPU,
  where per-draw and per-pass overhead dominates below ~256. Krita's attempt at 2048 px textures
  shows that too big hurts small brushes (§2.2).
- **Formats per tile store** (`Tiles` gets a `format` fixed at creation):

  | Store | 16-bit document | 8-bit document | Notes |
  |---|---|---|---|
  | Color layer | `rgba16_float`, 8 B | `rgba8` (sRGB-encoded, GPU decodes on sample, encodes on write), 4 B | 8-bit mode halves memory and matches Photoshop 8-bit semantics |
  | Layer mask, selection, quick mask, channel | `r16_float`, 2 B (add to luce-gpu) | `r8`, 1 B | 4–8× smaller than today |
  | Composite cache, pyramid of color | same as the color store | same | |
  | Future 32-bit float document | `rgba32_float`, 16 B | — | Only if HDR/EXR work demands it; f16 already covers ±65504 with an 11-bit significand |

  f16 has 1024 steps per power of two, so in linear light it is finer than 16-bit int in the
  shadows and coarser near 1.0 (1/2048). That is fine for editing and display. Exact 16-bit TIFF
  round-trips need int16, and are a non-goal for now.
- **Tile variants** (the cell in `Tiles.cells`):
  - `Empty`: transparent, or white for a mask. Costs 0.
  - `Solid(color: 4 × f32)`: a uniform tile. Costs 16 B.
    - Produced by fills, "reveal all" and "hide all" masks, adjustment-applied solids, and
      background layers.
    - Detected cheaply when a tile is written back to the CPU (all texels equal).
    - Solids are sampled as a 1 × 1 texture or a uniform. A "New document, white background" at
      360 MP then costs **16 B instead of 2.9 GB**.
  - `Pixels(TileData*)`: shared, immutable, reference-counted (today's `Tile`), with the residency
    fields of §5.4.
- **Per-tile metadata**, computed when the tile is produced:
  - `stamp` (have);
  - `alpha_bounds` (u8 × 4 box within the tile, or empty), so `content_bounds()` never reads the
    GPU back;
  - optionally a 64-bit coverage mask of 8 × 8 sub-blocks, which is GEGL's damage idea and lets
    a pyramid update skip untouched quarters.

### 5.2 GPU memory: slabs or atlases instead of one allocation per tile

- **Stage 0 (minimal).** In luce-gpu's Vulkan backend, suballocate same-size textures from
  **64 MiB `VkDeviceMemory` slabs** (128 RGBA16F tiles or 256 RGBA8 tiles per slab). All tile
  images have identical size, format and requirements, so this is a trivial fixed-slot allocator,
  not a general VMA. It lifts the 4096-allocation cap
  ([VMA FAQ](https://gpuopen-librariesandsdks.github.io/VulkanMemoryAllocator/html/faq.html):
  "as low as 4096, so allocating a separate one for each resource is not an option"). On Metal,
  optionally place tiles in an `MTLHeap` for faster create and destroy.
- **Stage 2 or later (throughput).** Use **atlas pages**: 4096² textures holding 16 × 16 = 256
  tiles (128 MiB at RGBA16F). A tile then lives at (page, slot).
  - One render pass per atlas page can update many tiles (scissored draws). Today every tile
    render opens its own `texture.frame()` pass, which is expensive on tile-based (Apple) GPUs and
    costly in Vulkan barriers.
  - One draw can sample many tiles from the same page, which gets round the 4-image limit.
  - Downside: sampling near a slot edge bleeds into neighbours. Shaders must clamp to the slot
    rect, or slots get a 1–2 px gutter (the VT border trick). Only the pyramid and display paths
    need filtered sampling. Brush, blend and adjust passes are 1:1 texel maps.

  Decide by measuring: if per-tile passes cost > 30 µs each, atlas pages pay for themselves.

### 5.3 Pyramids: per layer, lazy, stamp-keyed

- **What gets a pyramid:** every raster layer's color tiles and every mask. Adjustment layers
  have no pixels. **Vector shapes, text and fills** render at the requested level directly from
  their description and never downsample (§5.7). **Groups** get a cached composite per level,
  like any composite.
- **Level L tile (c, r)** = 2 × 2 box downsample of level L−1 tiles (2c..2c+1, 2r..2r+1).
  - It is done **in premultiplied space**:
    `rgb = Σ(rgb·a) / Σa`, `a = Σa / 4`.
    Tiles are straight alpha, and a plain bilinear `copy_image` at half size averages straight
    colors, which darkens soft edges (see the straight-alpha contract). Today's `halve()` should be
    checked for exactly this.
  - Level L exists only up to Lmax = ⌈log2(max(W, H) / 256)⌉ (7 for 24000).
- **Keying.** A level-L tile is derived data. Its key is
  `(layer store id, L, c, r, digest of the 4 child stamps)`, and the tile gets its own stamp. It
  lives in a **derived-tile cache** (LRU, evictable at any time, never written to history or
  file, except for the embedded preview of §5.10).
- **Invalidation is implicit.** When a stroke replaces level-0 tile (c, r), its stamp changes, so
  the parent's key changes. Only the chain (c >> k, r >> k), k = 1..L, is rebuilt, and only
  **when requested**: one downsample per level, at most 7 for 360 MP. Siblings stay cached.
- **Undo is free:** restoring old level-0 tiles restores old stamps, so the old pyramid tiles are
  cache hits if still resident.
- **Build on demand, top-down request, bottom-up compute.** When the view asks for level L and
  a child is missing, the request recurses. Recursion stops at resident tiles or at `Empty` and
  `Solid` children (a solid parent of 4 solids is a solid). To avoid the **cold build cost**
  (opening a 360 MP file and fitting it means reading all 5546 level-0 tiles once), the pyramid
  is also **stored in the native file** (§5.10) and built during import in the same pass that
  writes the level-0 tiles.
- **Memory.** Worst case +34 %, but only levels that were viewed are materialised, and they are
  the first thing evicted. A fit-to-screen view of a 12-layer document needs 12 × 24 level-4
  tiles, which is **144 MiB** in total.

### 5.4 Residency tiers

Each `TileData` (immutable content) can have any subset of these copies:

| Tier | Form | Cost | Budget (defaults, §4) | Eviction |
|---|---|---|---|---|
| **G** GPU | texture slot (slab or atlas) | 512 KiB | GPU pool | LRU with priorities; clean copies are just dropped |
| **R** RAM | raw bytes (straight-alpha f16) | 512 KiB | part of the RAM tier | LRU, compressed into C |
| **C** RAM compressed | LZ4 of byte-shuffled planes | ~50–400 KiB photos; 1–20 KiB flat art | part of the RAM tier | LRU, written to D |
| **D** disk | offset in a swap slab file, LZ4 | 0 RAM | swap cap (default 64 GiB, like PS scratch) | deleted with the last reference |

Rules:

- **Because tiles are immutable, copies never go stale.** There is no write-back coherency
  problem. A tile produced on the GPU gets its R/C copy lazily: when the GPU pool evicts it, when
  saving, or in background "trickle" readback when idle. A readback is ~512 KiB per tile, about
  40–100 µs over PCIe.
- **Apple unified memory:** allocate tiles with shared storage in a heap so the G copy is
  CPU-readable. G and R then coincide, and C and D remain.
- **History-only tiles go cold first**, as in Krita's soft limit. A tile referenced only by
  snapshots (reference count held only by history) has **low priority** in G and is demoted to C
  and then D before any live tile.
- **Pinned:** tiles being read or written by the current GPU command batch. The GPU scheduler
  pins inputs and outputs for the duration of a job (the PS VM "ensures source and destination
  tiles for the current iteration are in memory").
- **Priorities for G** (evict lowest first):
  1. history-only;
  2. derived tiles of off-screen levels;
  3. off-screen live level-0 tiles;
  4. prefetch ring;
  5. visible at the view level;
  6. active stroke and job tiles.
- **Compression choice: LZ4.**
  - 780 MB/s compress and **4970 MB/s decompress per core**; ratio 2.1 on the Silesia corpus.
    Zstd -1 is 515 / 1380 MB/s with ratio 2.9. zlib-1 is 100 / 415 MB/s.
    ([lz4 benchmarks](https://github.com/lz4/lz4))
  - A 512 KiB tile decompresses in ~0.1 ms.
  - **Shuffle first**: split each f16 into a high-byte plane and a low-byte plane, per channel
    (Krita's `linearizeColors`, Blosc shuffle). Sign and exponent bytes compress very well.
  - Port the LZ4 block format into luce-compress (~500 lines). Use zstd or deflate for the file
    only if ratio matters there.
- **Disk swap:** append-only **64 MiB slab files** under `~/.luce/cache/luced-2d/swap/<pid>/`
  (Krita slab size), with a free list per slab and compaction when a slab is < 25 % live. Files
  are deleted at exit or on crash recovery.
- **Accounting UI:** show "Memory: GPU x / y GiB, RAM x / y GiB, swap x GiB, history x GiB" in the
  status bar. This mirrors Photoshop's Efficiency and Scratch Sizes indicator and lets users see
  why something is slow.

### 5.5 View compositing at the screen's level of detail

1. **Choose the level per device pixel**, not per point:
   `L = clamp(floor(log2(1 / (zoom × backing_scale))), 0, Lmax)`. Retina at 25 % then uses L1, not
   L2, so it is sharp.
2. **Composite per visible tile at level L:**
   - For each layer, take its level-L tile (§5.3), its level-L mask tile, and adjustments
     evaluated on the fly. Blend bottom to top into a **level-L composite tile**.
   - Cost per visible tile = N layer draws **regardless of zoom**. Today it is N × 4^L at
     level L, because level L is built from level-0 composites.
   - Key = digest of (per-layer level-L stamps, params), exactly the current `hash_layers` but
     over one cell at level L.
   - Nonlinear modes (Difference, Hard Mix, Dissolve, Threshold, clipping) composited from
     downsampled inputs differ slightly from downsampling the full-resolution composite.
     Photoshop, Krita and GIMP accept this for display. Export always uses L0. The status bar can
     say "preview at 25 %" the way Photoshop's older versions asked users to view sharpening at
     100 %.
3. **Below-active cache:**
   - While a layer is being painted, cache per visible tile the composite of **everything below
     the active layer** (keyed by those layers' stamps). A dab then recomposites
     `below ⊕ active ⊕ layers above`: 1 + 1 + A draws instead of N.
   - With the active layer on top (common when painting), that is 2 draws per tile per frame.
     Layers below that are not visible elsewhere can be evicted from G while painting.
4. **Present without seams:**
   - Copy the visible level-L composite tiles into one **view texture** in texel space. This
     needs at most (screen / zoom-at-level) × 1 px of border, which stays ≤ 2 × screen, under
     16384.
   - Then draw that texture to the swapchain once, with the right filter: nearest above 100 %,
     bilinear or bicubic between levels, optionally trilinear blending L and L+1 for smooth
     animated zoom.
   - This removes per-tile edge clamping, and gives one place for the display color transform,
     the checkerboard and rotation.
   - Pan by moving the view texture's origin, and only fill the newly exposed tiles (the fixed
     lattice makes panning incremental).
5. **Progressive refinement:**
   - The top levels of the composite (Lmax−2..Lmax, ≤ 9 tiles for 360 MP) are always kept, like
     the VT root pages.
   - If a needed level-L tile is not ready (inputs in D, or the per-frame budget is used up),
     draw its nearest resident ancestor scaled up.
   - Refine within a **per-frame GPU budget**: 6 ms at 60 Hz while interacting, more when idle.
     Adapt the chunk count from the median of the last 3 frame timings (GIMP's chunk iterator
     targets 1/15 s per chunk).
   - The canvas is never blank and never blocks.
6. **Prefetch** a one-tile ring around the viewport at L, and the parent level. During zoom
   animation, request L+1 first.
7. **Replace the linear-scan cache lookup** with a hash map, and budget in **bytes**. The current
   comment says "1 MiB each"; tiles are 512 KiB.

### 5.6 Brushes and strokes

- **At zoom ≥ 50 % (normal case):** keep today's engine. Queue dabs, rebuild the touched level-0
  tiles once per frame, and give stamps to the changed tiles. After the frame's level-0 updates:
  - for each dirty tile, request its pyramid chain only up to the **view level** (other levels
    rebuild lazily);
  - invalidate the composite at the view level through stamps (automatic).

  Cost per frame ≈ touched tiles × (paint + 1–2 downsamples) + affected visible tiles × (2 + A).
- **Big-brush / zoomed-out mode** (Krita Instant Preview):
  - Trigger: estimated level-0 tiles touched per frame > 64 (for example a 3000 px brush at 12 %
    zoom).
  - The stroke paints its dabs **at the view level L** (diameter / 2^L, spacing in level-L
    pixels) into a level-L *preview paint buffer*. The compositor treats that buffer as "active
    layer's level-L tile ⊕ paint".
  - The same dab list is **replayed on level 0** by the background scheduler within its per-frame
    budget.
  - When replay finishes, the level-0 result replaces the preview, and the pyramid and composite
    update through stamps.
  - The dab list must be deterministic. It already is (seeded jitter in `Stroke.random`).
    Scale-variant features (texture scale, spacing floors at 1 px, pencil hard edges) will "pop"
    slightly, as Krita documents; a per-brush "no LOD preview" flag avoids it.
  - Undo of a stroke that is still replaying waits for or cancels the replay, and the history
    entry is committed when replay ends.
- **Eraser, clone, heal, smudge, dodge/burn** use the same tile paths. Clone and heal read source
  tiles through the same windowed gather (§5.8); smudge must replay at level 0 exactly, so no LOD
  preview for smudge.
- **Fills and gradients** over the whole canvas or selection:
  - Produce `Solid` tiles where the fill is uniform and fully covered.
  - Gradient tiles are rendered directly per tile at L0.
  - Stop bumping `layer.revision` for fills: it invalidates every composite tile of the layer,
    while stamps already cover it.

### 5.7 Adjustments, filters, styles, vector shapes, text

- **Adjustment layers:** already lazy per tile in the compositor. Evaluate them at the view
  level; per-pixel ops commute well enough with downsampling. Curves and Levels histograms
  should be computed from the **level-2 or level-3 pyramid** (5.6 M or 1.4 M samples) rather
  than full resolution. Photoshop's histogram "cache" warning exists for exactly this reason.
- **Destructive adjustments (Image › Adjustments):**
  - Preview = the same shader as an adjustment layer over the visible level-L composite (instant).
  - Apply = a background job over all non-empty level-0 tiles (Solid tiles map to Solid tiles).
    That is ~5546 single-pass draws, a few seconds at most.
- **Spatial filters** (blur, sharpen, noise, median, high pass, motion, lens) become **windowed
  tile ops**:
  - For output tile T, the input is the window T ± halo, where halo = ⌈3σ⌉ for Gaussian, the
    distance for motion blur, and the maximum displacement for lens correction.
  - Gather that window from source tiles into a scratch texture of at most 2048² (see §5.8), and
    shade T.
  - Huge radii (halo > 512 px) run at a coarser pyramid level ℓ = ⌈log2(halo / 256)⌉ with the
    radius / 2^ℓ, then upsample. Error is negligible for Gaussian-like kernels; this is the
    classic trick for huge blurs.
  - **Dialog preview** runs the filter on the **visible tiles at the view level** with its
    parameters scaled by 1/2^L (Krita LOD filters, GEGL mipmap rendering), plus an optional 100 %
    loupe region. Apply runs the full-resolution job in the background with progress and cancel,
    then commits a new `Tiles` atomically (COW makes cancel free).
- **Blur adjustment layers** (the compositor reaches into the 8 neighbour cells today): at level
  L use radius / 2^L. The neighbour reach then stays one cell at any level for radii up to 256 × 2^L.
- **Layer styles** (shadow, glow, stroke, bevel): today they use `flatten` and whole-layer
  `stamps()`.
  - Render per output tile with a halo equal to the effect extent, at the view level with scaled
    size and distance.
  - Cache per (layer stamps in the halo window, style digest, level, tile).
  - The layer-wide `tiles.stamps()` fold per request becomes a maintained per-layer content
    counter.
- **Vector shape layers and text:** resolution-independent.
  - Rasterise the path or glyphs **directly into the requested level-L tile** (scale the geometry
    by 1/2^L, analytic coverage AA). No pyramid, no level-0 pixels unless exported or
    rasterised.
  - Cache per (shape revision, L, tile).
  - A 20000 px-wide shape costs nothing while zoomed out.
  - Stroke and fill effects follow the style path above.

### 5.8 Free transform and other resampling

- **Replace `flatten`** with a **windowed gather**: `gather(tiles, level, rect_in_level_px,
  margin) → scratch texture`. It composes the needed source tiles (Empty or Solid expand
  cheaply) into a texture of at most 4096², from a pooled set of scratch textures.
  - Every current `flatten` caller (resampled filters, `apply_selected`, styles, selection
    passes, retouch) takes a window per output tile, or per batch of output tiles, instead of the
    whole layer.
  - This fixes the 16384 limit and the 2.9 GB duplicate.
- **Transform preview (drag):** draw the layer's **level-L** tiles as transformed quads (affine or
  perspective via a homography per quad; warp via a mesh) straight into the view composite. It
  costs visible tiles only and runs at 60 fps on 360 MP.
- **Transform commit:**
  - For each destination level-0 tile inside the transformed bounds, map its corners back to
    source, take the bounding rect plus 2 px (bicubic), and choose the **source level**
    ℓ = max(0, floor(log2(1 / min_scale))) so strong downscales sample the pyramid (mip-mapped
    resampling, no aliasing).
  - Gather the window and shade.
  - Run as a background job with progress; a 360 MP layer is ~5546 tile shades.
  - Destination tiles outside the transformed bounds stay `Empty` or keep their shared tiles.
- **Image Size** (resample the whole document) uses the same per-destination-tile path. Canvas
  Size, crop and rotate by 90° are tile re-indexing plus edge-tile shifts, and cheap.

### 5.9 Undo and history

- **Keep the snapshot model** (COW `Tiles` clones; state snapshots sharing tiles).
- **Account in bytes:** each snapshot records the bytes of tiles it alone holds, which is exact
  with reference counts.
- History budget = min(step count, default 50; **bytes**, default 25 % of the RAM tier). The
  oldest steps are dropped past either limit.
- **History tiles are demoted first** (§5.4). Undoing a whole-layer filter from 30 steps back
  decompresses 5546 tiles: about 0.5–1 s from C, a few s from D. That is acceptable and matches
  Photoshop on scratch.
- Stroke replay (§5.6) and background filter jobs commit their history entry **when they finish**
  (Krita commits undo "after execution completes").
- Pyramids and composites are never in history. They come back through stamp keys.

### 5.10 Files: tiled native format, streaming codecs

- **Native `.l2d`** keeps `document.prisma` for the tree. Each layer's pixels become
  `layers/<id>.tiles`:
  - Header: format, size, tile size.
  - **Tile index**: for each cell, kind (Empty / Solid + color / Pixels), offset, length, codec,
    content hash.
  - **Blobs**: LZ4 or zstd of shuffled planes, each tile independent (Krita `.kra` v2).
  - **Embedded pyramid**: levels ≥ 3 of the flattened composite and of each layer. This is small:
    1899 tiles are all of levels 1–7, and levels ≥ 3 are only 130 tiles per layer.

  The file then opens to a correct screen in ~100 ms, before any level-0 tile is read.
- **Incremental save:** a tile whose content hash is already in the file is not rewritten. New
  blobs are appended, and the index is rewritten atomically. Compaction runs when dead space is
  > 30 %. Saving after a stroke on a 20 GB document writes only a few MB.
- **Lazy open:** read the index and the pyramid. Level-0 tiles are paged in on demand (the file
  itself acts as tier D; memory-mapping is fine).
- **Codecs:** decode PNG, TIFF and JPEG **by strips of 256 rows directly into tiles**
  (15000 × 256 × 8 B = 30 MB per strip for RGBA16F). Encode exports by strips pulled from the L0
  composite tile row by tile row. Remove the f64 whole-image path and the `max_pixels` default of
  268 M from the editor path. Keep it for the scripting `Image` API with explicit limits.
- **PSD/PSB:** PSB is required above 30000 px per side and 2 GB. Write it by streaming layers
  tile row by tile row.

### 5.11 Scheduling and threads

- **One GPU job scheduler** on the render thread. Each frame it runs, in priority order:
  1. visible composite at the view level (plus fallback ancestors);
  2. the active stroke's level-0 updates;
  3. stroke replays and LOD work;
  4. prefetch;
  5. user jobs (filter apply, transform commit, export), in chunks;
  6. idle work: pyramid warm-up, trickle readback of dirty GPU-only tiles.

  It is time-budgeted per frame (6 ms interactive, 14 ms when idle) and adapts the chunk size
  from recent timings.
- **CPU worker pool** (cores − 2): LZ4 compress and decompress, disk I/O, codec strips,
  readback conversions, histogram reductions. Handoff to the GPU thread is by queue.
  Immutability makes tile data safe to share across threads without locks; only reference
  counts need atomics.
- **Cancellation:** every job checks a flag between tiles. Results are committed as one `Tiles`
  swap, so cancel leaves no partial state.

### 5.12 Target numbers (acceptance tests)

On an M-series Mac with 16 GB and on a PC with an 8 GB GPU, using the 15000 × 24000 16-bit
document of §4.3:

| Action | Target |
|---|---|
| New 360 MP document | < 100 ms; 0 B of pixels (Empty or Solid) |
| Open native `.l2d` (20 GB of layers) | first correct frame < 300 ms; interactive immediately |
| Fit view, first full-quality frame from cold (no embedded pyramid) | coarse frame < 100 ms; refined < 5 s, never blocking |
| Pan and zoom | 60 fps; newly exposed tiles fill within 2–3 frames |
| 300 px brush at 100 % | ≤ 8 ms per frame on GPU for level-0 + pyramid + composite |
| 3000 px brush at 12 % | 60 fps preview; level-0 replay done within ~1 s after pen-up |
| Gaussian blur r = 50 | preview < 150 ms; apply < 15 s in background |
| Free transform drag | 60 fps; commit < 15 s in background |
| Undo of a stroke | < 50 ms |
| Save after one stroke (incremental) | < 1 s |
| GPU memory, idle, fit view | < 1 GiB whatever the document size |

---

## 6. Staged migration plan

Ordered by payoff per effort, with blockers first. Each stage leaves the editor working.

### Stage 0 — remove hard failures (≈ 1–2 weeks)

1. **luce-gpu Vulkan slab suballocation** for same-size textures (64 MiB slabs). Test: create
   20000 tiles on Windows. *Fixes the 4096-allocation failure.*
2. **`gather()` windowed source** replacing `flatten()` in `filter.lucb` (resampled),
   `transform.lucb`, `style.lucb`, `selection_passes.lucb` and `canvas/retouch.lucb`. Test: every
   filter and transform on a 20000 × 24000 document. *Fixes the > 16384 px failure and removes
   the 2.9 GB duplicates.*
3. **Masks and selection to `r8`** (and add `r16_float` to luce-gpu for 16-bit documents).
   *8× less mask memory.*
4. **Composer:** a byte-based budget (default 512 MiB = 1024 tiles), a hash-map lookup, a
   corrected comment, and removal of the `layer.revision` bump on fills and gradients (stamps
   suffice).
5. **Streaming save and export** (tile rows), and **streaming import** into tiles. Drop the
   `flattened_pixels` whole-image f32 and the f64 decode on the editor path. Store per-tile
   `alpha_bounds` so `content_bounds()` needs no readback.

### Stage 1 — per-layer pyramids and composite at the view level (≈ 2–3 weeks; the biggest felt win)

1. A premultiplied 2 × 2 downsample shader, and a `Pyramid` for each `Tiles` (derived-tile cache
   keyed by child stamps).
2. `Composer.tile(level L)` composites the layers' level-L tiles directly (no recursion through
   level 0).
3. Level choice per device pixel; seamless view texture; ancestor fallback; per-frame budget with
   progressive refinement; prefetch ring.
4. Below-active composite cache while painting.
5. Vector shape and text layers rasterise directly at level L.

After Stage 1, zoomed-out painting, panning and adjustment-layer tweaks cost O(screen).

### Stage 2 — residency tiers (≈ 3–4 weeks)

1. `TileData` residency (G, R, C, D) with priorities and LRU. The GPU pool budget is set from the
   device (Metal `recommendedMaxWorkingSetSize`, Vulkan heap sizes).
2. LZ4 plus byte shuffle in luce-compress; swap slab files; demotion of history-only tiles first.
3. Background readback of GPU-produced tiles; unified-memory fast path on Apple.
4. History byte budget; memory indicator in the status bar.

After Stage 2, documents larger than VRAM (and larger than RAM) work.

### Stage 3 — background jobs and LOD previews (≈ 3 weeks)

1. The GPU job scheduler (§5.11) and the CPU worker pool; cancellable, atomically committed jobs
   with progress.
2. Filters: preview at the view level with scaled parameters; apply in the background; huge
   radii at a coarser level.
3. Free transform: pyramid-level quad preview; mip-aware tiled commit in the background.
4. Big-brush LOD preview with level-0 replay (Krita Instant Preview), and a per-brush opt-out.

### Stage 4 — native tiled file (≈ 2 weeks)

1. `layers/<id>.tiles` with an index, per-tile LZ4 or zstd blobs and Empty/Solid entries, plus
   an embedded pyramid (levels ≥ 3).
2. Incremental append-save plus compaction; lazy open with the file as tier D.
3. PSB export for > 30000 px.

### Stage 5 — refinements (as needed)

- `Solid` tiles everywhere (fills, masks, adjust-apply); `rgba8` storage for 8-bit documents.
- Atlas pages with batched render passes, if profiling shows per-tile pass overhead.
- Histograms from the pyramid; the navigator panel from level Lmax.
- Optional Metal/Vulkan sparse textures: not needed while the explicit tile table works.

---

## 7. Open questions and risks

- **Blend fidelity at coarse levels.** Composite-of-downsampled differs from
  downsample-of-composite for nonlinear modes and hard clipping. Decide whether Difference, Hard
  Mix and Dissolve layers force a finer level (L−1) on screen, or accept the difference like
  Photoshop and Krita do.
- **f16 precision** near 1.0 in linear light (1/2048 steps) vs Photoshop 16-bit (1/32768).
  Visible banding is unlikely after display encoding, but exact 16-bit TIFF round-trips are lost.
- **Atlas vs per-tile textures:** measure the per-pass cost on Apple M-series and on
  Windows/NVIDIA before committing to atlases.
- **GPU-side authority vs CPU-side authority.** This proposal keeps the GPU as the place where
  pixels are produced and the RAM/disk tiers as caches of immutable data. Photoshop and Krita are
  CPU-authoritative. Immutability is what makes the GPU-first variant safe; it must stay an
  invariant (`redrawn()` only while the reference count is 1 and the tile has no R/C/D copy yet,
  or those copies are dropped).
- **Crash safety of swap:** swap is scratch; recovery comes from autosaved `.l2d` files
  (incremental save makes frequent autosave cheap).

---

## Sources

- Chrome Developers, "How Photoshop solved working with files larger than can fit into memory": https://developer.chrome.com/blog/how-photoshop-solved-working-with-files-larger-than-can-fit-into-memory
- Adobe community, cache levels and tile size: https://community.adobe.com/t5/photoshop/selecting-cache-levels-tile-size-in-preferences-gt-performance/m-p/9939657
- Adobe community, huge pixel dimensions and many layers: https://community.adobe.com/questions-712/optimizing-cache-levels-and-tile-size-for-huge-pixel-dimensions-and-many-layers-1176182
- Adobe community, Cache Tile Size (Chris Cox): https://community.adobe.com/questions-712/2018-cache-tile-size-logic-of-use-help-pls-1067233
- Adobe community, 16-bit or 15-bit+1: https://community.adobe.com/questions-712/16-bit-or-15-bit-1-1132730
- Adobe performance preferences: https://helpx.adobe.com/photoshop/using/performance-preferences.html
- Photoshop performance settings guide: https://photoshopguides.github.io/Performance
- PSD vs PSB limits: https://www.bwillcreative.com/psd-vs-psb-photoshop-files/
- Photoshop brush lag: https://www.cgdirector.com/how-to-fix-photoshop-brush-lag/
- Krita manual, Instant Preview: https://docs.krita.org/en/reference_manual/instant_preview.html
- Krita strokes documentation: https://docs.krita.org/en/untranslatable_pages/strokes_documentation.html
- KDE wiki, Krita tile data format: https://community.kde.org/Krita/Tile_Data_Format
- Krita source: https://invent.kde.org/graphics/krita (libs/image/tiles3, libs/image/kis_image_config.cpp, libs/ui/kis_config.cc, libs/ui/opengl/kis_opengl_image_textures.cpp, libs/image/kis_paint_device.cc, libs/ui/canvas/kis_canvas2.cpp)
- Krita D8280 (texture size revert): https://phabricator.kde.org/D8280
- Krita KisTextureTileInfoPool commit: https://invent.kde.org/graphics/krita/-/commit/54282a72cee6256f29be9970793b32f6ffae6aa1
- GEGL environment variables: https://www.gegl.org/environment.html
- GEGL source: https://gitlab.gnome.org/GNOME/gegl (gegl/buffer/gegl-buffer-config.c, gegl-compression.c, gegl-tile-handler-zoom.c, gegl/process/gegl-processor.c)
- Libre Arts, GEGL gets mipmaps: https://librearts.org/2015/06/gegl-gets-mipmaps/
- GIMP 3.0 manual, System Resources: https://docs.gimp.org/3.0/en/gimp-prefs-system-resources.html
- GIMP 2.10.8 news (adaptive chunks): https://www.gimp.org/news/2018/11/08/gimp-2-10-8-released/
- GIMP 2.10.10 news (group rendering): https://www.gimp.org/news/2019/04/07/gimp-2-10-10-released/
- GIMP source: https://gitlab.gnome.org/GNOME/gimp/-/blob/master/app/core/gimpprojection.c and gimpchunkiterator.c
- MyPaint development documentation: https://github.com/mypaint/mypaint/wiki/Development-Documentation
- libmypaint PERFORMANCE: https://github.com/mypaint/libmypaint/blob/master/PERFORMANCE
- Procreate layer limits: https://procreate.com/insight/2021/layer-limits
- Affinity RAM usage limit: https://forum.affinity.serif.com/index.php?%2Ftopic%2F152526-affinity-photodesignerpublisher-performance-settings-ram-usage-limit-bug%2F=
- Pixelmator Pro (AppleInsider): https://appleinsider.com/articles/17/09/05/pixelmator-pro-image-tool-with-coreml-metal-2-enhancements-coming-in-the-fall-to-ios-macos
- Photopea issue #4303: https://github.com/photopea/photopea/issues/4303
- WebGL2 Fundamentals, rendering 32000²: https://webgl2fundamentals.org/webgl/lessons/webgl-qna-how-to-render-large-scale-images-like-32000x32000.html
- Figma, building a professional design tool: https://www.figma.com/blog/building-a-professional-design-tool-on-the-web/
- Figma, rendering powered by WebGPU: https://www.figma.com/blog/figma-rendering-powered-by-webgpu/
- Sean Barrett, Sparse Virtual Texture Memory (GDC 2008): https://archive.org/details/GDC2008Barrett
- Sparse virtual textures (Sagristà): https://tonisagrista.com/blog/2023/sparse-virtual-textures/
- Sparse virtual texturing notes (Dammertz): https://holger.dammertz.org/stuff/notes_VirtualTexturing.html
- id Tech 5 challenges (van Waveren): https://mrl.cs.vsb.cz/people/gaura/agu/05-JP_id_Tech_5_Challenges.pdf
- Apple, Metal sparse tile size: https://developer.apple.com/documentation/metal/mtldevice/sparsetilesize(with:pixelformat:samplecount:)
- Apple, streaming large images with sparse textures: https://developer.apple.com/documentation/metal/metal_sample_code_library/streaming_large_images_with_metal_sparse_textures
- Apple forum, recommendedMaxWorkingSetSize: https://developer.apple.com/forums/thread/732035
- VMA FAQ (allocation count limit): https://gpuopen-librariesandsdks.github.io/VulkanMemoryAllocator/html/faq.html
- Vulkan memory allocation (io7m): https://blog.io7m.com/2023/11/11/vulkan-memory-allocation.xhtml
- LZ4 benchmarks: https://github.com/lz4/lz4
- Blender PBVH image painting design: https://projects.blender.org/blender/blender/issues/96223
- Blender texture paint optimisations PR: https://projects.blender.org/blender/blender/pulls/160670
- FlashPix: https://en.wikipedia.org/wiki/FlashPix
