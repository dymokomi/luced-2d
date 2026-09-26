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

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base', type=Path, default=ROOT.parent / 'luce-base/build/luce-base')
parser.add_argument('--luce', type=Path, default=ROOT.parent / 'luce/build/luce')
parser.add_argument('--output', type=Path, default=ROOT / 'docs/preview.png')
parser.add_argument('--zoom', type=float, help='the view zoom to capture at, after the scene')
parser.add_argument('--scene', choices=['style', 'picker', 'settings', 'brush', 'documents', 'zoom', 'pan', 'crash', 'drop', 'swatch', 'rulers', 'document', 'white', 'brushdock', 'zoomhold', 'pickerwhite', 'strokes', 'selmove', 'clipboard', 'movetool', 'ellipsedrag', 'selmovedrag', 'transform', 'crop', 'flip', 'croppress', 'groups', 'adjustlayer', 'huesat', 'noise', 'retouch', 'closeprompt', 'jpeg', 'distort', 'layermenu', 'rename', 'canvassize', 'imagesize', 'polygon', 'guides', 'text', 'newcancel', 'channels', 'channelgray', 'quickmask', 'channelundo', 'vector', 'colortriangle', 'colorsquare', 'colorwheel', 'colorsliders'], default='style', help='which dialog to open in the capture')
arguments = parser.parse_args()
arguments.output.resolve().parent.mkdir(parents=True, exist_ok=True)

def color_scene(mode):
    return '''            editor.workspace.set_color(0.8069, 0.3515, 0.0497)
            editor.panels.catalog.open("color")
            let color = editor.panels.catalog.color else trap("the Color panel")
            # A capture keeps nothing in the user's settings.
            color.saved = none
            color.set_mode(%d)
            color.sliders.choose(1)
            color.show()
            editor.panels.refresh()''' % mode


SCENES = {
    'style': '''            editor.panels.style.open()
            editor.workspace.choose_tool("brush")
            editor.panels.refresh()
            # A shadow, an inside orange stroke, and a blue inner shadow.
            editor.workspace.set_style_value(0, 1.0)
            editor.workspace.set_style_value(1, 14.0)
            editor.workspace.set_style_value(2, 14.0)
            editor.workspace.set_style_value(3, 10.0)
            editor.workspace.set_style_value(8, 1.0)
            editor.workspace.set_style_value(9, 8.0)
            editor.workspace.set_style_value(10, 1.0)
            editor.workspace.set_style_value(11, 0.3)
            editor.workspace.set_style_value(20, 2.0)
            editor.workspace.set_style_value(26, 1.0)
            editor.workspace.set_style_value(32, 1.0)
            editor.panels.style.open()
            editor.panels.refresh()''',
    # A Black & White adjustment layer over the picture, a Levels layer clipped
    # and masked above it; the layers panel shows their icons.
    'adjustlayer': '''            editor.workspace.select(1)
            editor.panels.actions.adjustment_layers[8].trigger()
            editor.panels.refresh()
            editor.panels.properties.adjustment.set_control(9, 0, 120.0)
            editor.panels.actions.adjustment_layers[3].trigger()
            editor.panels.refresh()
            editor.panels.properties.adjustment.set_control(3, 1, 180.0)
            editor.workspace.canvas.measure_histogram_below(editor.workspace.canvas.layer_id(3))
            var total = 0
            var nonzero = 0
            var slot = 0
            while slot < 256:
                let n = editor.workspace.canvas.histogram(0, slot)
                total += n
                if n > 0:
                    nonzero += 1
                slot += 1
            print(f"ADJUST histogram total {total} bins {nonzero} at128 {editor.workspace.canvas.histogram(0, 128)} at255 {editor.workspace.canvas.histogram(0, 255)}")
            var index = editor.workspace.layer_count() - 1
            while index >= 0:
                print(f"ADJUST {index} {editor.workspace.canvas.layer_name(index)} kind {editor.workspace.canvas.layer_adjustment(index)}")
                index -= 1
            editor.panels.refresh()''',
    # Hue/Saturation on the pixels, the Reds page showing its own sliders.
    'huesat': '''            editor.workspace.select(0)
            editor.panels.adjust.open(1)
            editor.panels.adjust.show_page(1, 1)
            editor.panels.adjust.set_control(1, 0, 120.0)
            editor.panels.adjust.set_control(1, 1, 40.0)
            editor.panels.refresh()''',
    # The retouching tools on the picture: a clone of its top-left stamped on
    # the blue, Liquify pushing the circle's edge, a heal over the text's d.
    'retouch': '''            editor.workspace.select(0)
            editor.panels.refresh()
            let area = editor.panels.view.layout().bounds()
            editor.workspace.fit(area.width, area.height)
            let zoom = editor.workspace.zoom
            let ox = area.x + editor.workspace.offset_x
            let oy = area.y + editor.workspace.offset_y
            editor.workspace.brush.diameter = 120.0
            editor.workspace.brush.hardness = 0.3
            editor.workspace.brush.opacity = 1.0
            editor.workspace.choose_tool("clone")
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = ox + 150.0 * zoom, y = oy + 150.0 * zoom, button = 0, alt = true))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = ox + 150.0 * zoom, y = oy + 150.0 * zoom, button = 0, alt = true))
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = ox + 1100.0 * zoom, y = oy + 300.0 * zoom, button = 0))
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = ox + 1250.0 * zoom, y = oy + 300.0 * zoom))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = ox + 1250.0 * zoom, y = oy + 300.0 * zoom, button = 0))
            editor.workspace.choose_tool("smear")
            editor.workspace.smear_mode = 2
            editor.workspace.brush.diameter = 160.0
            editor.workspace.brush.opacity = 0.8
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = ox + 850.0 * zoom, y = oy + 600.0 * zoom, button = 0))
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = ox + 780.0 * zoom, y = oy + 600.0 * zoom))
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = ox + 700.0 * zoom, y = oy + 600.0 * zoom))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = ox + 700.0 * zoom, y = oy + 600.0 * zoom, button = 0))
            editor.workspace.choose_tool("heal")
            editor.workspace.brush.diameter = 90.0
            editor.workspace.brush.opacity = 1.0
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = ox + 1120.0 * zoom, y = oy + 860.0 * zoom, button = 0))
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = ox + 1130.0 * zoom, y = oy + 900.0 * zoom))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = ox + 1130.0 * zoom, y = oy + 900.0 * zoom, button = 0))
            print(f"RETOUCH undo {editor.workspace.canvas.can_undo()}")
            editor.panels.refresh()''',
    # The Layers panel's row menu, right-clicked on the top layer.
    'layermenu': '''            editor.workspace.select(1)
            editor.panels.refresh()
            let rows = editor.panels.layers.layout().bounds()
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = rows.x + 120.0, y = rows.y + 20.0, button = 1))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = rows.x + 120.0, y = rows.y + 20.0, button = 1))
            editor.panels.refresh()''',
    # A layer's name edited in its row.
    'rename': '''            editor.workspace.select(1)
            editor.panels.refresh()
            editor.panels.actions.rename_layer.trigger()
            editor.panels.refresh()''',
    'canvassize': '''            editor.panels.actions.canvas_size.trigger()
            editor.panels.refresh()''',
    'imagesize': '''            editor.panels.actions.image_size.trigger()
            editor.panels.refresh()''',
    # The Polygonal Lasso with three corners set and the line following the pointer.
    'polygon': '''            editor.workspace.choose_tool("polygon")
            editor.panels.refresh()
            let area = editor.panels.view.layout().bounds()
            let zoom = editor.workspace.zoom
            let ox = area.x + editor.workspace.offset_x
            let oy = area.y + editor.workspace.offset_y
            for corner in [[200.0, 200.0], [800.0, 150.0], [900.0, 600.0]]:
                editor.app.dispatch(Event(kind = EventKind.pointer_down, x = ox + corner[0] * zoom, y = oy + corner[1] * zoom, button = 0))
                editor.app.dispatch(Event(kind = EventKind.pointer_up, x = ox + corner[0] * zoom, y = oy + corner[1] * zoom, button = 0))
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = ox + 400.0 * zoom, y = oy + 700.0 * zoom))
            editor.panels.refresh()''',
    # The Channels panel: a saved ellipse shown red over the picture, and the green channel alone.
    'channels': '''            editor.workspace.canvas.select_ellipse(200, 100, 500, 400)
            discard(editor.workspace.canvas.save_selection_channel("Alpha 1"))
            editor.workspace.canvas.deselect()
            editor.panels.catalog.open("channels")
            editor.workspace.canvas.set_channel_shown(0, true)
            editor.workspace.touch()
            editor.panels.refresh()''',
    'channelgray': '''            editor.workspace.canvas.select_ellipse(200, 100, 500, 400)
            discard(editor.workspace.canvas.save_selection_channel("Alpha 1"))
            editor.panels.catalog.open("channels")
            editor.workspace.canvas.set_composite_view(false, true, false)
            editor.workspace.touch()
            editor.panels.refresh()''',
    # A vector layer of three elements, the ellipse active: its row and its outline.
    'vector': '''            editor.workspace.add_layer()
            let id = editor.workspace.selected_id()
            editor.workspace.canvas.set_shape(id, 0, 120.0, 80.0, 300.0, 200.0, 5, 12.0, true, 0.8, 0.2, 0.05, true, 0.0, 0.0, 0.0, 4.0)
            editor.workspace.canvas.add_shape(id, 1, 300.0, 180.0, 260.0, 220.0, 5, 0.0, true, 0.05, 0.2, 0.8, false, 0.0, 0.0, 0.0, 1.0)
            editor.workspace.canvas.add_shape(id, 3, 480.0, 60.0, 200.0, 200.0, 6, 0.0, false, 0.0, 0.0, 0.0, true, 0.1, 0.6, 0.1, 6.0)
            editor.workspace.canvas.set_active_element(id, 1)
            editor.panels.catalog.open("vector")
            editor.workspace.touch()
            editor.panels.refresh()''',
    # Save, undo, redo, save again: the list must show all three.
    'channelundo': '''            editor.panels.catalog.open("channels")
            editor.panels.refresh()
            editor.workspace.canvas.select_ellipse(200, 100, 500, 400)
            discard(editor.workspace.canvas.save_selection_channel("Alpha 1"))
            editor.workspace.touch()
            editor.panels.refresh()
            discard(editor.workspace.canvas.save_selection_channel("Alpha 2"))
            editor.workspace.touch()
            editor.panels.refresh()
            editor.workspace.undo()
            editor.panels.refresh()
            editor.workspace.redo()
            editor.panels.refresh()
            discard(editor.workspace.canvas.save_selection_channel("Alpha 3"))
            editor.workspace.touch()
            editor.panels.refresh()''',
    'quickmask': '''            editor.workspace.canvas.select_all()
            editor.workspace.set_color(0.2, 0.2, 0.2)
            editor.workspace.fill_selection(false)
            editor.workspace.canvas.select_ellipse(200, 100, 500, 400)
            editor.workspace.canvas.enter_quick_mask()
            editor.workspace.touch()
            editor.panels.refresh()''',
    'guides': '''            discard(editor.workspace.canvas.add_guide(true, 700.0))
            discard(editor.workspace.canvas.add_guide(false, 300.0))
            editor.panels.refresh()''',
    # A text layer in a box, centred, being edited, in Georgia Italic.
    'text': '''            editor.workspace.choose_tool("text")
            editor.workspace.set_color(1.0, 1.0, 1.0)
            editor.workspace.typing.family = "Georgia"
            editor.workspace.typing.style = "Italic"
            editor.workspace.typing.size = 72.0
            editor.workspace.typing.alignment = 1
            editor.workspace.typing.tracking = 40.0
            editor.panels.text_editing.begin_new(150.0, 120.0, 700.0)
            editor.panels.text_editing.replace_text("Live type in a box, centred and wrapping as it goes")
            editor.panels.refresh()''',
    'newcancel': '''            editor.panels.actions.new_document.trigger()
            editor.panels.refresh()
            let dialogs = editor.panels.size_dialogs
            print(f"NEWCANCEL open {dialogs.new_canvas.dialog.is_open()}")
            editor.app.layout(1400.0, 900.0)
            let button = dialogs.new_canvas.cancel_button.layout().bounds()
            print(f"NEWCANCEL button {button.x},{button.y} {button.width}x{button.height}")
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = button.x + button.width * 0.5, y = button.y + button.height * 0.5))
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = button.x + button.width * 0.5, y = button.y + button.height * 0.5, button = 0))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = button.x + button.width * 0.5, y = button.y + button.height * 0.5, button = 0))
            print(f"NEWCANCEL after {dialogs.new_canvas.dialog.is_open()}")
            editor.panels.refresh()''',
    'closeprompt': '''            editor.workspace.add_layer()
            editor.panels.files.close_document()
            editor.panels.refresh()''',
    'jpeg': '''            editor.panels.files.export_jpeg()
            editor.panels.refresh()''',
    'noise': '''            editor.workspace.select(0)
            editor.panels.adjust.add_noise()
            editor.panels.adjust.set_control(13, 0, 30.0)
            editor.panels.refresh()''',
    'settings': '''            editor.workspace.choose_tool("brush")
            editor.panels.settings_dialog.open()
            editor.panels.settings_dialog.show_page(1)
            editor.panels.refresh()''',
    'brush': '''            editor.workspace.select(1)
            editor.workspace.set_color(0.02, 0.18, 0.65)
            editor.workspace.apply_preset("Spatter")
            editor.workspace.brush.diameter = 40.0
            editor.workspace.begin_stroke(200.0, 200.0)
            editor.workspace.extend_stroke(600.0, 260.0)
            editor.workspace.extend_stroke(1000.0, 180.0)
            editor.workspace.end_stroke()
            editor.workspace.set_color(0.9, 0.9, 0.9)
            editor.workspace.apply_preset("Chalk")
            editor.workspace.brush.diameter = 60.0
            editor.workspace.begin_stroke(200.0, 420.0)
            editor.workspace.extend_stroke(700.0, 480.0)
            editor.workspace.extend_stroke(1100.0, 400.0)
            editor.workspace.end_stroke()
            editor.workspace.set_color(0.8, 0.1, 0.05)
            editor.workspace.apply_preset("Canvas Wash")
            editor.workspace.brush.diameter = 90.0
            editor.workspace.begin_stroke(200.0, 640.0)
            editor.workspace.extend_stroke(1100.0, 700.0)
            editor.workspace.end_stroke()
            editor.workspace.set_color(0.05, 0.05, 0.05)
            editor.workspace.apply_preset("Ink Pen")
            editor.workspace.brush.diameter = 14.0
            editor.workspace.begin_stroke(1150.0, 200.0)
            editor.workspace.extend_stroke(1300.0, 700.0)
            editor.workspace.extend_stroke(1350.0, 300.0)
            editor.workspace.end_stroke()
            editor.workspace.apply_preset("Hard Round")
            editor.workspace.choose_tool("brush")
            editor.panels.open_brush()
            editor.panels.refresh()''',
    'documents': '''            editor.workspace.choose_tool("brush")
            editor.workspace.create(900, 600)
            editor.workspace.open("''' + str(ROOT / 'docs/sample.png') + '''")
            editor.workspace.switch_document(0)
            editor.panels.refresh()''',
    'zoom': '''            editor.workspace.choose_tool("brush")
            editor.panels.refresh()
            let bounds = editor.panels.view.layout().bounds()
            let cx = bounds.x + bounds.width * 0.5
            let cy = bounds.y + bounds.height * 0.5
            # The crop and resize above queued a refit; do it now, as a frame would.
            editor.workspace.fit(bounds.width, bounds.height)
            print(f"ZOOM start {editor.workspace.zoom} view {bounds.x},{bounds.y} {bounds.width}x{bounds.height}")
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = cx, y = cy))
            editor.app.dispatch(Event(kind = EventKind.scroll, x = cx, y = cy, scroll_y = 40.0, scroll_unit = ScrollUnit.points, meta = true))
            print(f"ZOOM after cmd-scroll {editor.workspace.zoom}")
            editor.app.dispatch(Event(kind = EventKind.scroll, x = cx, y = cy, scroll_y = 3.0, scroll_unit = ScrollUnit.lines))
            print(f"ZOOM after wheel {editor.workspace.zoom}")
            editor.app.dispatch(Event(kind = EventKind.key_down, key = Key.equal, meta = true))
            print(f"ZOOM after cmd-= {editor.workspace.zoom}")
            editor.workspace.choose_tool("zoom")
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = cx, y = cy, button = 0))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = cx, y = cy, button = 0))
            print(f"ZOOM after zoom tool click {editor.workspace.zoom}")
            editor.panels.refresh()''',
    'pan': '''            editor.workspace.choose_tool("brush")
            editor.panels.refresh()
            let bounds = editor.panels.view.layout().bounds()
            editor.workspace.fit(bounds.width, bounds.height)
            let cx = bounds.x + bounds.width * 0.5
            let cy = bounds.y + bounds.height * 0.5
            print(f"PAN start {editor.workspace.offset_x},{editor.workspace.offset_y}")
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = cx, y = cy))
            # A click on the canvas first, as a person would: it paints a dot and takes focus.
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = cx, y = cy, button = 0))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = cx, y = cy, button = 0))
            print("PAN clicked")
            editor.app.dispatch(Event(kind = EventKind.key_down, key = Key.space))
            print("PAN space down")
            editor.app.dispatch(Event(kind = EventKind.key_down, key = Key.space, repeated = true))
            print("PAN space repeat")
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = cx, y = cy, button = 0))
            print("PAN pointer down")
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = cx + 120.0, y = cy + 60.0))
            print(f"PAN moved {editor.workspace.offset_x},{editor.workspace.offset_y}")
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = cx + 120.0, y = cy + 60.0, button = 0))
            editor.app.dispatch(Event(kind = EventKind.key_up, key = Key.space))
            print(f"PAN done {editor.workspace.offset_x},{editor.workspace.offset_y} painting {editor.workspace.canvas.painting()}")
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = cx, y = cy, button = 2))
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = cx - 50.0, y = cy))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = cx - 50.0, y = cy, button = 2))
            print(f"PAN middle {editor.workspace.offset_x},{editor.workspace.offset_y}")
            # Leave the last checker block 0.5 points wide at the view's right edge.
            editor.workspace.zoom = 1.0
            editor.workspace.offset_x = bounds.width - 768.0 - 0.5
            editor.workspace.offset_y = 10.0
            print(f"PAN far {editor.workspace.offset_x},{editor.workspace.offset_y} zoom {editor.workspace.zoom}")
            editor.panels.refresh()''',
    'crash': '''            editor.panels.show_crash("trap: src/view.luc:1:1: a sample report\\nat frame 0")
            editor.panels.refresh()
            let copy = editor.panels.crash.copy.layout().bounds()
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = copy.x + 4.0, y = copy.y + 4.0, button = 0))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = copy.x + 4.0, y = copy.y + 4.0, button = 0))
            editor.panels.refresh()''',
    'drop': '''            editor.workspace.choose_tool("brush")
            editor.panels.refresh()
            let layer_area = editor.panels.layers.layout().bounds()
            let canvas = editor.panels.view.layout().bounds()
            print(f"DROP start layers {editor.workspace.layer_count()} documents {editor.workspace.document_count()}")
            editor.app.set_drop_paths(["''' + str(ROOT / 'docs/sample.png') + '''", "/tmp/readme.txt"])
            editor.app.dispatch(Event(kind = EventKind.drag_entered, x = layer_area.x + 40.0, y = layer_area.y + 200.0))
            print(f"DROP over layers hovered {editor.panels.layers.layout().is_drop_hovered()} accepted {editor.panels.layers.layout().is_drop_accepted()}")
            editor.app.dispatch(Event(kind = EventKind.drop, x = layer_area.x + 40.0, y = layer_area.y + 200.0))
            print(f"DROP placed layers {editor.workspace.layer_count()} selected {editor.workspace.canvas.layer_name(editor.workspace.selected)}")
            editor.app.dispatch(Event(kind = EventKind.drag_entered, x = canvas.x + 200.0, y = canvas.y + 200.0))
            editor.app.dispatch(Event(kind = EventKind.drop, x = canvas.x + 200.0, y = canvas.y + 200.0))
            print(f"DROP opened documents {editor.workspace.document_count()} current {editor.workspace.document_title(editor.workspace.current)}")
            editor.app.set_drop_paths(["/tmp/readme.txt"])
            editor.app.dispatch(Event(kind = EventKind.drag_entered, x = canvas.x + 200.0, y = canvas.y + 200.0))
            print(f"DROP text refused {not editor.panels.view.layout().is_drop_accepted()}")
            editor.app.dispatch(Event(kind = EventKind.drag_left))
            editor.app.set_drop_paths(["''' + str(ROOT / 'docs/sample.png') + '''"])
            editor.app.dispatch(Event(kind = EventKind.drag_entered, x = canvas.x + 300.0, y = canvas.y + 300.0))
            editor.panels.refresh()''',
    'swatch': '''            editor.workspace.choose_tool("brush")
            editor.panels.refresh()
            let swatch = editor.panels.palette.layout().bounds()
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = swatch.x + 5.0, y = swatch.y + 5.0, button = 0))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = swatch.x + 5.0, y = swatch.y + 5.0, button = 0))
            print(f"SWATCH picker open {editor.panels.picker.is_open()}")
            editor.panels.refresh()''',
    'rulers': '''            editor.workspace.choose_tool("brush")
            editor.workspace.show_rulers = true
            editor.workspace.show_grid = true
            editor.workspace.units = "mm"
            editor.workspace.canvas.set_resolution(150.0)
            editor.panels.refresh()''',
    'document': '''            editor.workspace.choose_tool("brush")
            editor.workspace.units = "mm"
            editor.workspace.canvas.set_resolution(300.0)
            editor.panels.document_settings.open()
            editor.panels.refresh()''',
    'white': '''            editor.workspace.choose_tool("brush")
            editor.workspace.select(0)
            editor.workspace.canvas.set_layer(editor.workspace.selected_id(), false, 1.0)
            editor.workspace.select(1)
            editor.workspace.canvas.set_layer(editor.workspace.selected_id(), true, 1.0, 0)
            editor.workspace.set_color(1.0, 1.0, 1.0)
            editor.workspace.apply_preset("Hard Round")
            editor.workspace.brush.diameter = 40.0
            editor.workspace.begin_stroke(200.0, 200.0)
            editor.workspace.extend_stroke(1000.0, 260.0)
            editor.workspace.end_stroke()
            editor.workspace.apply_preset("Soft Round")
            editor.workspace.brush.diameter = 80.0
            editor.workspace.begin_stroke(200.0, 450.0)
            editor.workspace.extend_stroke(1000.0, 520.0)
            editor.workspace.end_stroke()
            editor.panels.refresh()''',
    'brushdock': '''            editor.workspace.choose_tool("brush")
            editor.panels.open_brush()
            editor.panels.refresh()
            editor.panels.dock.move(editor.panels.brush.panel, editor.panels.properties.panel, DockPosition.tab)
            editor.panels.refresh()
            print(f"BRUSHDOCK floating {editor.panels.dock.is_floating(editor.panels.brush.panel)}")
            editor.panels.refresh()''',
    'zoomhold': '''            editor.workspace.choose_tool("marquee")
            editor.panels.refresh()
            let area = editor.panels.view.layout().bounds()
            let cx = area.x + area.width * 0.5
            let cy = area.y + area.height * 0.5
            # A click on the canvas focuses it, as a person's would.
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = cx, y = cy, button = 0))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = cx, y = cy, button = 0))
            let before = editor.workspace.zoom
            editor.app.dispatch(Event(kind = EventKind.key_down, key = Key.z))
            editor.app.dispatch(Event(kind = EventKind.key_down, key = Key.z, repeated = true))
            print(f"ZOOMHOLD tool while held {editor.workspace.tool}")
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = cx, y = cy, button = 0))
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = cx + 60.0, y = cy))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = cx + 60.0, y = cy, button = 0))
            editor.app.dispatch(Event(kind = EventKind.key_up, key = Key.z))
            print(f"ZOOMHOLD zoom {before} -> {editor.workspace.zoom} tool after {editor.workspace.tool}")
            editor.panels.refresh()''',
    'pickerwhite': '''            editor.workspace.choose_tool("brush")
            editor.workspace.set_color(1.0, 1.0, 1.0)
            editor.panels.pick_color(false)
            editor.panels.refresh()''',
    'strokes': '''            editor.workspace.choose_tool("brush")
            editor.workspace.set_color(0.9, 0.05, 0.05)
            editor.workspace.brush.diameter = 18.0
            editor.panels.refresh()
            let area = editor.panels.view.layout().bounds()
            let x0 = area.x + 150.0
            let y0 = area.y + 150.0
            # A short stroke, then a Shift-click: a straight line from its end.
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = x0, y = y0, button = 0))
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = x0 + 40.0, y = y0 + 10.0))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = x0 + 40.0, y = y0 + 10.0, button = 0))
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = x0 + 400.0, y = y0 + 200.0, button = 0, shift = true))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = x0 + 400.0, y = y0 + 200.0, button = 0, shift = true))
            # A Shift-drag that wobbles keeps to the horizontal it started along.
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = x0, y = y0 + 320.0, button = 0))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = x0, y = y0 + 320.0, button = 0))
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = x0 + 20.0, y = y0 + 360.0, button = 0, shift = true))
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = x0 + 120.0, y = y0 + 370.0, shift = true))
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = x0 + 260.0, y = y0 + 330.0, shift = true))
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = x0 + 420.0, y = y0 + 400.0, shift = true))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = x0 + 420.0, y = y0 + 400.0, button = 0, shift = true))
            # Alt-click with the brush samples the color under it.
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = area.x + area.width - 200.0, y = area.y + 200.0, button = 0, alt = true))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = area.x + area.width - 200.0, y = area.y + 200.0, button = 0, alt = true))
            print(f"STROKES color after alt-click {editor.workspace.color_hex()}")
            editor.panels.refresh()''',
    'selmove': '''            editor.workspace.select(0)
            editor.workspace.choose_tool("move")
            editor.panels.refresh()
            let area = editor.panels.view.layout().bounds()
            let zoom = editor.workspace.zoom
            let ox = area.x + editor.workspace.offset_x
            let oy = area.y + editor.workspace.offset_y
            # Select the top-left of the picture and drag its pixels right and down.
            editor.workspace.canvas.select_rectangle(0, 0, 300, 250, 0)
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = ox + 100.0 * zoom, y = oy + 100.0 * zoom, button = 0))
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = ox + 300.0 * zoom, y = oy + 200.0 * zoom))
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = ox + 500.0 * zoom, y = oy + 300.0 * zoom))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = ox + 500.0 * zoom, y = oy + 300.0 * zoom, button = 0))
            print(f"SELMOVE selection at {editor.workspace.canvas.selection_left()},{editor.workspace.canvas.selection_top()}")
            # Cmd-Alt-drag with the brush: a copy of the moved pixels further right.
            editor.workspace.choose_tool("brush")
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = ox + 500.0 * zoom, y = oy + 300.0 * zoom, button = 0, meta = true, alt = true))
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = ox + 850.0 * zoom, y = oy + 300.0 * zoom, meta = true, alt = true))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = ox + 850.0 * zoom, y = oy + 300.0 * zoom, button = 0, meta = true, alt = true))
            # Invert only inside the selection.
            editor.workspace.adjust(2, [])
            print(f"SELMOVE selection at {editor.workspace.canvas.selection_left()},{editor.workspace.canvas.selection_top()} undo {editor.workspace.canvas.can_undo()}")
            editor.panels.refresh()''',
    'movetool': '''            editor.workspace.add_layer()
            editor.workspace.choose_tool("move")
            editor.panels.refresh()
            let area = editor.panels.view.layout().bounds()
            let zoom = editor.workspace.zoom
            let ox = area.x + editor.workspace.offset_x
            let oy = area.y + editor.workspace.offset_y
            # An orange block on a new layer.
            editor.workspace.set_color(0.9, 0.35, 0.05)
            editor.workspace.canvas.select_rectangle(100, 100, 200, 150, 0)
            editor.workspace.canvas.fill(editor.workspace.selected_id(), false)
            editor.workspace.canvas.deselect()
            let top = editor.workspace.selected
            # Alt-Shift-drag: a copy of the layer, kept to the horizontal axis.
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = ox + 150.0 * zoom, y = oy + 150.0 * zoom, button = 0, alt = true))
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = ox + 400.0 * zoom, y = oy + 190.0 * zoom, alt = true, shift = true))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = ox + 450.0 * zoom, y = oy + 210.0 * zoom, button = 0, alt = true, shift = true))
            print(f"MOVETOOL layers {editor.workspace.layer_count()} copy at {editor.workspace.canvas.layer_at(420, 120)} original at {editor.workspace.canvas.layer_at(120, 120)} below {editor.workspace.canvas.layer_at(420, 300)}")
            # Cmd-click on the original picks its layer.
            editor.workspace.select(0)
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = ox + 150.0 * zoom, y = oy + 150.0 * zoom, button = 0, meta = true))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = ox + 150.0 * zoom, y = oy + 150.0 * zoom, button = 0, meta = true))
            print(f"MOVETOOL picked {editor.workspace.selected} expected {top}")
            editor.panels.refresh()''',
    'ellipsedrag': '''            editor.workspace.choose_tool("ellipse")
            editor.panels.refresh()
            let area = editor.panels.view.layout().bounds()
            let zoom = editor.workspace.zoom
            let ox = area.x + editor.workspace.offset_x
            let oy = area.y + editor.workspace.offset_y
            # Mid-drag: the outline is the ellipse, not its bounding box.
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = ox + 200.0 * zoom, y = oy + 150.0 * zoom, button = 0))
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = ox + 700.0 * zoom, y = oy + 500.0 * zoom))
            editor.panels.refresh()''',
    'selmovedrag': '''            editor.workspace.select(0)
            editor.workspace.choose_tool("move")
            editor.panels.refresh()
            let area = editor.panels.view.layout().bounds()
            let zoom = editor.workspace.zoom
            let ox = area.x + editor.workspace.offset_x
            let oy = area.y + editor.workspace.offset_y
            # Mid-drag of selected pixels: the ants go with them.
            editor.workspace.canvas.select_rectangle(100, 100, 300, 250, 0)
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = ox + 200.0 * zoom, y = oy + 200.0 * zoom, button = 0))
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = ox + 500.0 * zoom, y = oy + 350.0 * zoom))
            editor.panels.refresh()''',
    'transform': '''            editor.workspace.select(1)
            editor.panels.refresh()
            let area = editor.panels.view.layout().bounds()
            editor.workspace.fit(area.width, area.height)
            let zoom = editor.workspace.zoom
            let ox = area.x + editor.workspace.offset_x
            let oy = area.y + editor.workspace.offset_y
            editor.panels.free_transform()
            let session = editor.workspace.transform else trap("a transform")
            let box = session.box
            print(f"TRANSFORM box {box.left},{box.top} {box.width}x{box.height}")
            # Shrink from the bottom-right corner, then turn it a little from outside.
            let corner_x = box.left + box.width
            let corner_y = box.top + box.height
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = ox + corner_x * zoom, y = oy + corner_y * zoom, button = 0))
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = ox + (corner_x - 200.0) * zoom, y = oy + (corner_y - 200.0) * zoom))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = ox + (corner_x - 200.0) * zoom, y = oy + (corner_y - 200.0) * zoom, button = 0))
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = ox + 1350.0 * zoom, y = oy + 440.0 * zoom, button = 0))
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = ox + 1300.0 * zoom, y = oy + 800.0 * zoom))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = ox + 1300.0 * zoom, y = oy + 800.0 * zoom, button = 0))
            print(f"TRANSFORM scale {box.scale_x} {box.scale_y} angle {box.angle} move {box.dx} {box.dy}")
            editor.panels.refresh()''',
    # Cmd-dragging the top-right corner out: a perspective distortion.
    'distort': '''            editor.workspace.select(1)
            editor.panels.refresh()
            let area = editor.panels.view.layout().bounds()
            editor.workspace.fit(area.width, area.height)
            let zoom = editor.workspace.zoom
            let ox = area.x + editor.workspace.offset_x
            let oy = area.y + editor.workspace.offset_y
            editor.panels.free_transform()
            let session = editor.workspace.transform else trap("a transform")
            let box = session.box
            let corner_x = box.left + box.width
            let corner_y = box.top
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = ox + corner_x * zoom, y = oy + corner_y * zoom, button = 0, meta = true))
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = ox + (corner_x + 150.0) * zoom, y = oy + (corner_y - 120.0) * zoom, meta = true))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = ox + (corner_x + 150.0) * zoom, y = oy + (corner_y - 120.0) * zoom, button = 0, meta = true))
            print(f"DISTORT distorted {box.distorted} corners {box.corners}")
            editor.panels.refresh()''',
    'crop': '''            print("CROP choose")
            editor.workspace.choose_tool("crop")
            print("CROP chosen")
            editor.panels.refresh()
            print("CROP refreshed")
            let area = editor.panels.view.layout().bounds()
            editor.workspace.fit(area.width, area.height)
            let zoom = editor.workspace.zoom
            let ox = area.x + editor.workspace.offset_x
            let oy = area.y + editor.workspace.offset_y
            # Pull the top-left corner in; the rest shades.
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = ox, y = oy, button = 0))
            print("CROP pressed")
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = ox + 300.0 * zoom, y = oy + 200.0 * zoom))
            print("CROP dragged")
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = ox + 300.0 * zoom, y = oy + 200.0 * zoom, button = 0))
            let crop = editor.workspace.crop_box else trap("a crop box")
            print(f"CROP box {crop.left},{crop.top} {crop.width()}x{crop.height()}")
            editor.panels.refresh()''',
    'flip': '''            editor.workspace.select(1)
            editor.workspace.flip_layer(true)
            editor.workspace.flip_canvas(false)
            print(f"FLIP undo {editor.workspace.canvas.can_undo()}")
            editor.panels.refresh()''',
    # Choosing the Crop tool rebuilds the header; a press after it once set off
    # a collection inside the relayout that trapped (luce-ui 0.6.5 fixed it).
    'croppress': '''            editor.workspace.choose_tool("crop")
            editor.panels.refresh()
            let area = editor.panels.view.layout().bounds()
            let ox = area.x + editor.workspace.offset_x
            let oy = area.y + editor.workspace.offset_y
            print(f"PRESS at {ox},{oy}")
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = ox, y = oy, button = 0))
            print("PRESS done")
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = ox, y = oy, button = 0))
            print("PRESS up")
            editor.panels.refresh()''',
    'groups': '''            editor.workspace.select(1)
            editor.workspace.toggle_picked(0)
            group_selected(editor.workspace)
            editor.workspace.add_layer()
            editor.workspace.toggle_mask(true)
            var index = editor.workspace.layer_count() - 1
            while index >= 0:
                let canvas = editor.workspace.canvas
                print(f"GROUPS {index} {canvas.layer_name(index)} depth {canvas.layer_depth(index)} group {canvas.layer_is_group(index)} masked {canvas.layer_masked(index)}")
                index -= 1
            editor.panels.refresh()''',
    'clipboard': '''            let saved = clipboard.read_text()
            editor.workspace.select(0)
            editor.workspace.choose_tool("marquee")
            editor.panels.refresh()
            editor.workspace.canvas.select_rectangle(900, 150, 400, 300, 0)
            # Keys go where focus is: on the canvas, as after a click there.
            editor.panels.view.layout().request_focus()
            editor.app.layout(1400.0, 900.0)
            editor.app.dispatch(Event(kind = EventKind.key_down, key = Key.c, meta = true))
            editor.app.dispatch(Event(kind = EventKind.key_down, key = Key.v, meta = true))
            print(f"CLIPBOARD after paste layers {editor.workspace.layer_count()} selected {editor.workspace.canvas.layer_name(editor.workspace.selected)}")
            editor.workspace.move_layer(-500, 200)
            editor.workspace.select(0)
            editor.workspace.canvas.select_rectangle(100, 500, 300, 200, 0)
            editor.app.dispatch(Event(kind = EventKind.key_down, key = Key.j, meta = true))
            editor.workspace.move_layer(900, -350)
            print(f"CLIPBOARD after layer via copy layers {editor.workspace.layer_count()} selected {editor.workspace.canvas.layer_name(editor.workspace.selected)}")
            clipboard.write_text(saved)
            editor.panels.refresh()''',
    # The Color panel's picker in each mode, on an orange foreground.
    'colortriangle': color_scene(0),
    'colorsquare': color_scene(1),
    'colorwheel': color_scene(2),
    'colorsliders': color_scene(3),
    'picker': '''            editor.workspace.choose_tool("brush")
            editor.workspace.set_color(0.8069, 0.3515, 0.0497)
            editor.panels.pick_color(false)
            editor.panels.refresh()''',
}
SCENE = SCENES[arguments.scene]
if arguments.zoom:
    SCENE += '\n            editor.workspace.zoom = %r' % arguments.zoom
# Only what the scene uses: Luce rejects an unused import.
_input = [name for name in ('EventKind', 'ScrollUnit', 'Key') if name in SCENE]
SCENE_IMPORTS = ('from layer_groups import group_selected\n' if 'group_selected' in SCENE else '') + ('import clipboard\n' if 'clipboard.' in SCENE else '') + ('from ui import Event\n' if 'Event(' in SCENE else '') + ('from ui import DockPosition\n' if 'DockPosition' in SCENE else '') + ('from input import ' + ', '.join(_input) + '\n' if _input else '')
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
import files
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
    editor.workspace.open("''' + str(ROOT / 'docs/sample.png') + '''")
    editor.workspace.add_layer()
    editor.panels.refresh()
    var frames = 0
    var captured = false
    let observed = editor.app.on_frame(func (elapsed: float) -> unit!:
        discard(elapsed)
        frames += 1
        if frames == 4:
            editor.workspace.set_color(0.8069, 0.3515, 0.0497)
            editor.workspace.brush.diameter = 48.0
            editor.workspace.begin_stroke(180.0, 480.0)
            editor.workspace.extend_stroke(420.0, 140.0)
            editor.workspace.extend_stroke(700.0, 520.0)
            editor.workspace.end_stroke()
            editor.workspace.erasing = true
            editor.workspace.brush.diameter = 90.0
            editor.workspace.begin_stroke(760.0, 320.0)
            editor.workspace.extend_stroke(900.0, 360.0)
            editor.workspace.end_stroke()
            editor.workspace.erasing = false
            editor.workspace.cycle_blend(6)
            editor.workspace.select(0)
            editor.workspace.adjust(1, [0.5, 0.3, 0.0])
            editor.workspace.select(1)
            editor.workspace.canvas.select_rectangle(120, 80, 360, 240, 0)
            editor.workspace.set_color(0.75, 0.03, 0.02)
            editor.workspace.brush.opacity = 0.6
            editor.workspace.fill_selection(false)
            editor.workspace.deselect()
            editor.workspace.blur(6.0)
            editor.workspace.move_layer(60, -40)
            editor.workspace.canvas.select_rectangle(200, 60, 700, 440, 0)
            editor.workspace.crop()
            editor.workspace.resize_image(1400, 880)
            editor.workspace.canvas.select_ellipse(300, 150, 600, 500, 0)
            editor.workspace.canvas.select_rectangle(700, 300, 500, 400, 1)
            editor.workspace.adjust_selection(0, 12)
            editor.workspace.choose_tool("wand")
            editor.workspace.select_wand(1100.0, 700.0, 0)
            editor.workspace.set_color(1.0, 1.0, 1.0)
            let words = editor.workspace.canvas.add_layer("luced 2d")
            editor.workspace.canvas.set_type(words, "luced 2d", "Menlo", "Regular", 96.0, 1.0, 1.0, 1.0, 640.0, 560.0)
            editor.workspace.set_color(0.75, 0.03, 0.02)
            editor.workspace.select(0)
            editor.workspace.canvas.select_rectangle(0, 700, 1400, 180, 0)
            editor.workspace.set_color(0.02, 0.02, 0.03)
            editor.workspace.brush.opacity = 0.9
            editor.workspace.fill_gradient(700.0, 880.0, 700.0, 700.0)
            editor.workspace.deselect()
            editor.workspace.select(1)
            editor.workspace.set_color(0.75, 0.03, 0.02)
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
