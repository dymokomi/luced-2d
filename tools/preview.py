#!/usr/bin/env python3
"""Capture actual Metal output of luced-2d in an isolated build, without screen access."""
import argparse
import json
import re
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import zlib

from preview_scenes import scenes

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base', type=Path, default=ROOT.parent / 'luce-base/build/luce-base')
parser.add_argument('--luce', type=Path, default=ROOT.parent / 'luce/build/luce')
parser.add_argument('--output', type=Path, default=ROOT / 'docs/preview.png')
parser.add_argument('--zoom', type=float, help='the view zoom to capture at, after the scene')
parser.add_argument('--scene', choices=['style', 'picker', 'settings', 'brush', 'documents', 'zoom', 'pan', 'crash', 'drop', 'swatch', 'rulers', 'document', 'white', 'brushdock', 'zoomhold', 'pickerwhite', 'strokes', 'selmove', 'clipboard', 'movetool', 'ellipsedrag', 'selmovedrag', 'transform', 'crop', 'flip', 'croppress', 'groups', 'adjustlayer', 'huesat', 'noise', 'retouch', 'closeprompt', 'jpeg', 'distort', 'layermenu', 'rename', 'canvassize', 'imagesize', 'polygon', 'guides', 'text', 'newcancel', 'channels', 'channelgray', 'quickmask', 'channelundo', 'vector', 'nodes', 'nodeart', 'colortriangle', 'colorsquare', 'colorwheel', 'colorsliders', 'brushtip', 'brushdynamics', 'brushtransfer', 'brushlist', 'brushround', 'halfstrokes', 'halfstrokeslinear', 'properties', 'propadjust'], default='style', help='which dialog to open in the capture')
arguments = parser.parse_args()
arguments.output.resolve().parent.mkdir(parents=True, exist_ok=True)

SCENES = scenes(str(ROOT / 'docs/sample.png'))
SCENE = SCENES[arguments.scene]
if arguments.zoom:
    SCENE += '\n            editor.workspace.viewport.zoom = %r' % arguments.zoom
# Only what the scene uses: Luce rejects an unused import.
_input = [name for name in ('EventKind', 'ScrollUnit', 'Key') if name in SCENE]
SCENE_IMPORTS = ('from brush_mask import BrushMask\n' if 'BrushMask' in SCENE else '') + ('from brush import preset\n' if 'preset(' in SCENE else '') + ('from brush_dynamics import mapped\n' if 'mapped(' in SCENE else '') + ('from layer_groups import group_selected\n' if 'group_selected' in SCENE else '') + ('import clipboard\n' if 'clipboard.' in SCENE else '') + ('from ui import Event\n' if 'Event(' in SCENE else '') + ('from ui import DockPosition\n' if 'DockPosition' in SCENE else '') + ('from input import ' + ', '.join(_input) + '\n' if _input else '')
with tempfile.TemporaryDirectory(prefix='luced-2d-preview-') as temporary:
    work = Path(temporary)
    shutil.copytree(ROOT / 'src', work / 'src')
    # the application's own dependencies, each from the checkout beside this one
    manifest = (ROOT / 'package.prisma').read_text()
    dependencies = ''.join('    def dependency "%s" {\n        str owner = "dymokomi"\n        str version = "%s"\n        str path = %s\n    }\n' % (name, version, json.dumps(str(ROOT.parent / name)))
                           for name, version in re.findall(r'def dependency "([^"]+)" \{\s*str owner = "[^"]*"\s*str version = "([^"]+)"', manifest))
    (work / 'package.prisma').write_text('#prisma 4.0\ndef package "luced-2d-preview" {\n    str owner = "dymokomi"\n    str version = "0.0.0"\n    str kind = "tool"\n    str language = "luce"\n    str entry = "src/main.luc"\n' + dependencies + '}\n')
    native = (ROOT.parent / 'luce-gpu/tests/programs/gpu/native.lucb').read_text()
    native += '''
from luce_std import files
import memory
import ownership
import strings

## Run the cycle collector now, so a scene can find where references go wrong.
pub func collect():
    ownership.collect()

pub func save(path: str) -> !:
    let texture = captured_texture else trap("no captured frame")
    let width = uint(texture, sel("width"))
    let height = uint(texture, sel("height"))
    let device = msg(texture, sel("device"))
    let queue = msg(device, sel("newCommandQueue"))
    defer invoke(queue, sel("release"))
    let row_bytes = (width * 4 + 255) & ~(u64)255
    let storage = buffer(device, sel("newBufferWithLength:options:"), row_bytes * height, 0)
    defer invoke(storage, sel("release"))
    let command = msg(queue, sel("commandBuffer"))
    let encoder = msg(command, sel("blitCommandEncoder"))
    blit(encoder, sel("copyFromTexture:sourceSlice:sourceLevel:sourceOrigin:sourceSize:toBuffer:destinationOffset:destinationBytesPerRow:destinationBytesPerImage:"), texture, 0, 0, GpuProbeOrigin(), GpuProbeExtent(width = width, height = height, depth = 1), storage, 0, row_bytes, row_bytes * height)
    invoke(encoder, sel("endEncoding"))
    invoke(command, sel("commit"))
    invoke(command, sel("waitUntilCompleted"))
    assert(uint(command, sel("status")) == 4)
    let bytes = (const u8*)msg(storage, sel("contents"))
    var header: u8[100]
    let prefix = try format(header, f"P6\\n{width} {height}\\n255\\n")
    let output = try alloc u8[prefix.length + (usize)(width * height * 3)]
    defer free(output)
    memory.copy(output, prefix.bytes, prefix.length)
    for y in 0..<height:
        for x in 0..<width:
            let source = y * row_bytes + x * 4
            let destination = prefix.length + (usize)((y * width + x) * 3)
            output[destination] = bytes[source + 2]
            output[destination + 1] = bytes[source + 1]
            output[destination + 2] = bytes[source]
    let name = try strings.copy(path)
    defer strings.release(name)
    try files.write((c.str)name, output)
'''
    (work / 'src/probe.lucb').write_text(native)
    ppm = work / 'preview.ppm'
    (work / 'src/main.luc').write_text('''import probe
from app import Luce2D
''' + SCENE_IMPORTS + '''pub func main(arguments: list[str]) -> int!:
    discard(arguments)
    let editor = Luce2D()
    editor.workspace.documents.open("''' + str(ROOT / 'docs/sample.png') + '''")
    editor.workspace.edits.add_layer()
    editor.panels.refresh()
    var frames = 0
    var captured = false
    let observed = editor.app.on_frame(func (elapsed: float) -> unit!:
        discard(elapsed)
        frames += 1
        if frames == 4:
            editor.workspace.colors.set_color(0.8069, 0.3515, 0.0497)
            editor.workspace.tools.brush.diameter = 48.0
            editor.workspace.painting.begin_stroke(180.0, 480.0)
            editor.workspace.painting.extend_stroke(420.0, 140.0)
            editor.workspace.painting.extend_stroke(700.0, 520.0)
            editor.workspace.painting.end_stroke()
            editor.workspace.tools.erasing = true
            editor.workspace.tools.brush.diameter = 90.0
            editor.workspace.painting.begin_stroke(760.0, 320.0)
            editor.workspace.painting.extend_stroke(900.0, 360.0)
            editor.workspace.painting.end_stroke()
            editor.workspace.tools.erasing = false
            editor.workspace.edits.cycle_blend(6)
            editor.workspace.layers.select(0)
            editor.workspace.previews.adjust(1, [0.5, 0.3, 0.0])
            editor.workspace.layers.select(1)
            editor.workspace.canvas.select_rectangle(120, 80, 360, 240, 0)
            editor.workspace.colors.set_color(0.75, 0.03, 0.02)
            editor.workspace.tools.brush.opacity = 0.6
            editor.workspace.painting.fill_selection(false)
            editor.workspace.selection.deselect()
            editor.workspace.previews.blur(6.0)
            editor.workspace.edits.move_layer(60, -40)
            editor.workspace.canvas.select_rectangle(200, 60, 700, 440, 0)
            editor.workspace.image.crop()
            editor.workspace.image.resize_image(1400, 880)
            editor.workspace.canvas.select_ellipse(300, 150, 600, 500, 0)
            editor.workspace.canvas.select_rectangle(700, 300, 500, 400, 1)
            editor.workspace.selection.adjust_selection(0, 12)
            editor.workspace.choose_tool("wand")
            editor.workspace.selection.select_wand(1100.0, 700.0, 0)
            editor.workspace.colors.set_color(1.0, 1.0, 1.0)
            let words = editor.workspace.canvas.add_layer("luced 2d")
            editor.workspace.canvas.set_type(words, "luced 2d", "Menlo", "Regular", 96.0, 1.0, 1.0, 1.0, 640.0, 560.0)
            editor.workspace.colors.set_color(0.75, 0.03, 0.02)
            editor.workspace.layers.select(0)
            editor.workspace.canvas.select_rectangle(0, 700, 1400, 180, 0)
            editor.workspace.colors.set_color(0.02, 0.02, 0.03)
            editor.workspace.tools.brush.opacity = 0.9
            editor.workspace.painting.fill_gradient(700.0, 880.0, 700.0, 700.0)
            editor.workspace.selection.deselect()
            editor.workspace.layers.select(1)
            editor.workspace.colors.set_color(0.75, 0.03, 0.02)
''' + SCENE + '''
        if captured:
            editor.app.stop()
        elif frames >= 12:
            probe.begin("luced-2d")
            editor.panels.refresh()
            captured = true)
    editor.app.run()
    observed.disconnect()
    probe.save(''' + json.dumps(str(ppm)) + ''')
    probe.end()
    editor.close()
    return 0
''')
    binary = work / 'preview'
    subprocess.run([str(arguments.luce.resolve()), 'build', str(work / 'src/main.luc'), '--native', '-o', str(binary)], check=True, env=dict(os.environ, LUCE_BASE=str(arguments.base.resolve())), timeout=180)
    subprocess.run([str(binary)], check=True, timeout=60)
    raw = ppm.read_bytes()
    parts = raw.split(b'\n', 3)
    assert parts[0] == b'P6'
    width, height = map(int, parts[1].split())
    pixels = parts[3]
    rows = b''.join(b'\x00' + pixels[y * width * 3:(y + 1) * width * 3] for y in range(height))
    def chunk(tag: bytes, payload: bytes) -> bytes:
        return struct.pack('>I', len(payload)) + tag + payload + struct.pack('>I', zlib.crc32(tag + payload) & 0xffffffff)
    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(rows, 9))
    png += chunk(b'IEND', b'')
    arguments.output.resolve().write_bytes(png)
print(arguments.output.resolve())
