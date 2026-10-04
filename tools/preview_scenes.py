"""The scenes tools/preview.py captures: Luce statements run on the fourth
frame of a luced-2d window with docs/sample.png open, each keyed by its
--scene name."""


def color_scene(mode):
    return '''            editor.workspace.colors.set_color(0.8069, 0.3515, 0.0497)
            editor.panels.catalog.open("color")
            let color = editor.panels.catalog.color else trap("the Color panel")
            # A capture keeps nothing in the user's settings.
            color.saved = none
            color.set_mode(%d)
            color.sliders.choose(1)
            color.show()
            editor.panels.refresh()''' % mode


def half_strokes(linear):
    """Black strokes at half opacity on white, crossing: 128 grey where the document
    blends in sRGB (Photoshop's default), 188 with gamma 1.0; 64 or 137 where they cross."""
    return ('''            editor.workspace.image.set_linear_blend(%s)
            # One plain layer alone: the base scene's picture, text and Screen mode hidden.
            let canvas = editor.workspace.canvas
            canvas.set_layer(canvas.layer_id(0), false, 1.0)
            canvas.set_layer(canvas.layer_id(2), false, 1.0)
            canvas.set_layer(canvas.layer_id(1), true, 1.0, 0)
            editor.workspace.layers.select(1)
            editor.workspace.canvas.select_all()
            editor.workspace.colors.set_color(1.0, 1.0, 1.0)
            editor.workspace.tools.brush.opacity = 1.0
            editor.workspace.painting.fill_selection(false)
            editor.workspace.selection.deselect()
            editor.workspace.choose_tool("brush")
            editor.workspace.colors.set_color(0.0, 0.0, 0.0)
            editor.workspace.tools.brush.hardness = 1.0
            editor.workspace.tools.brush.diameter = 90.0
            editor.workspace.tools.brush.opacity = 0.5
            for row in [220.0, 440.0, 660.0]:
                editor.workspace.painting.begin_stroke(160.0, row)
                editor.workspace.painting.extend_stroke(1240.0, row)
                editor.workspace.painting.end_stroke()
            editor.workspace.painting.begin_stroke(700.0, 120.0)
            editor.workspace.painting.extend_stroke(700.0, 760.0)
            editor.workspace.painting.end_stroke()
            editor.workspace.touch()
            editor.panels.refresh()''') % ('true' if linear else 'false')


def scenes(sample):
    """Every scene; `sample` is the path of the picture the capture opens.
    The table stays at the left margin: its strings are Luce, indented for
    where the harness puts them."""
    return {
    'style': '''            editor.panels.style.open()
            editor.workspace.choose_tool("brush")
            editor.panels.refresh()
            # A shadow, an inside orange stroke, and a blue inner shadow.
            editor.workspace.previews.set_style_value(0, 1.0)
            editor.workspace.previews.set_style_value(1, 14.0)
            editor.workspace.previews.set_style_value(2, 14.0)
            editor.workspace.previews.set_style_value(3, 10.0)
            editor.workspace.previews.set_style_value(8, 1.0)
            editor.workspace.previews.set_style_value(9, 8.0)
            editor.workspace.previews.set_style_value(10, 1.0)
            editor.workspace.previews.set_style_value(11, 0.3)
            editor.workspace.previews.set_style_value(20, 2.0)
            editor.workspace.previews.set_style_value(26, 1.0)
            editor.workspace.previews.set_style_value(32, 1.0)
            editor.panels.style.open()
            editor.panels.refresh()''',
    # A Black & White adjustment layer over the picture, a Levels layer clipped
    # and masked above it; the layers panel shows their icons.
    'adjustlayer': '''            editor.workspace.layers.select(1)
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
            var index = editor.workspace.canvas.layer_count() - 1
            while index >= 0:
                print(f"ADJUST {index} {editor.workspace.canvas.layer_name(index)} kind {editor.workspace.canvas.layer_adjustment(index)}")
                index -= 1
            editor.panels.refresh()''',
    # The Properties pane in front: a pixel layer's rows (name, blend, opacity, flags).
    'properties': '''            editor.workspace.layers.select(1)
            editor.panels.dock.select(editor.panels.properties.panel)
            editor.panels.refresh()''',
    # The Properties pane on a Hue/Saturation adjustment layer: its settings below.
    'propadjust': '''            editor.workspace.layers.select(1)
            editor.panels.actions.adjustment_layers[1].trigger()
            editor.panels.refresh()
            editor.panels.properties.adjustment.set_control(1, 0, 40.0)
            editor.panels.dock.select(editor.panels.properties.panel)
            editor.panels.refresh()''',
    # Hue/Saturation on the pixels, the Reds page showing its own sliders.
    'huesat': '''            editor.workspace.layers.select(0)
            editor.panels.adjust.open(1)
            editor.panels.adjust.show_page(1, 1)
            editor.panels.adjust.set_control(1, 0, 120.0)
            editor.panels.adjust.set_control(1, 1, 40.0)
            editor.panels.refresh()''',
    # The retouching tools on the picture: a clone of its top-left stamped on
    # the blue, Liquify pushing the circle's edge, a heal over the text's d.
    'retouch': '''            editor.workspace.layers.select(0)
            editor.panels.refresh()
            let area = editor.panels.view.layout().bounds()
            editor.workspace.viewport.fit(area.width, area.height)
            let zoom = editor.workspace.viewport.zoom
            let ox = area.x + editor.workspace.viewport.offset_x
            let oy = area.y + editor.workspace.viewport.offset_y
            editor.workspace.tools.brush.diameter = 120.0
            editor.workspace.tools.brush.hardness = 0.3
            editor.workspace.tools.brush.opacity = 1.0
            editor.workspace.choose_tool("clone")
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = ox + 150.0 * zoom, y = oy + 150.0 * zoom, button = 0, alt = true))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = ox + 150.0 * zoom, y = oy + 150.0 * zoom, button = 0, alt = true))
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = ox + 1100.0 * zoom, y = oy + 300.0 * zoom, button = 0))
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = ox + 1250.0 * zoom, y = oy + 300.0 * zoom))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = ox + 1250.0 * zoom, y = oy + 300.0 * zoom, button = 0))
            editor.workspace.choose_tool("smear")
            editor.workspace.tools.smear_mode = 2
            editor.workspace.tools.brush.diameter = 160.0
            editor.workspace.tools.brush.opacity = 0.8
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = ox + 850.0 * zoom, y = oy + 600.0 * zoom, button = 0))
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = ox + 780.0 * zoom, y = oy + 600.0 * zoom))
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = ox + 700.0 * zoom, y = oy + 600.0 * zoom))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = ox + 700.0 * zoom, y = oy + 600.0 * zoom, button = 0))
            editor.workspace.choose_tool("heal")
            editor.workspace.tools.brush.diameter = 90.0
            editor.workspace.tools.brush.opacity = 1.0
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = ox + 1120.0 * zoom, y = oy + 860.0 * zoom, button = 0))
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = ox + 1130.0 * zoom, y = oy + 900.0 * zoom))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = ox + 1130.0 * zoom, y = oy + 900.0 * zoom, button = 0))
            print(f"RETOUCH undo {editor.workspace.canvas.can_undo()}")
            editor.panels.refresh()''',
    # The Layers panel's row menu, right-clicked on the top layer.
    'layermenu': '''            editor.workspace.layers.select(1)
            editor.panels.refresh()
            let rows = editor.panels.layers.layout().bounds()
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = rows.x + 120.0, y = rows.y + 20.0, button = 1))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = rows.x + 120.0, y = rows.y + 20.0, button = 1))
            editor.panels.refresh()''',
    # A layer's name edited in its row.
    'rename': '''            editor.workspace.layers.select(1)
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
            let zoom = editor.workspace.viewport.zoom
            let ox = area.x + editor.workspace.viewport.offset_x
            let oy = area.y + editor.workspace.viewport.offset_y
            for corner in [[200.0, 200.0], [800.0, 150.0], [900.0, 600.0]]:
                editor.app.dispatch(Event(kind = EventKind.pointer_down, x = ox + corner[0] * zoom, y = oy + corner[1] * zoom, button = 0))
                editor.app.dispatch(Event(kind = EventKind.pointer_up, x = ox + corner[0] * zoom, y = oy + corner[1] * zoom, button = 0))
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = ox + 400.0 * zoom, y = oy + 700.0 * zoom))
            editor.panels.refresh()''',
    # The Channels panel: a saved ellipse shown red over the picture, and the green channel alone.
    'channels': '''            editor.workspace.canvas.select_ellipse(200, 100, 500, 400)
            _ = editor.workspace.canvas.save_selection_channel("Alpha 1")
            editor.workspace.canvas.deselect()
            editor.panels.catalog.open("channels")
            editor.workspace.canvas.set_channel_shown(0, true)
            editor.workspace.touch()
            editor.panels.refresh()''',
    'channelgray': '''            editor.workspace.canvas.select_ellipse(200, 100, 500, 400)
            _ = editor.workspace.canvas.save_selection_channel("Alpha 1")
            editor.panels.catalog.open("channels")
            editor.workspace.canvas.set_composite_view(false, true, false)
            editor.workspace.touch()
            editor.panels.refresh()''',
    # A vector layer of three elements, the ellipse active: its row and its outline.
    'vector': '''            editor.workspace.edits.add_layer()
            let id = editor.workspace.layers.selected_id()
            editor.workspace.canvas.set_shape(id, 0, 120.0, 80.0, 300.0, 200.0, 5, 12.0, true, 0.8, 0.2, 0.05, true, 0.0, 0.0, 0.0, 4.0)
            editor.workspace.canvas.add_shape(id, 1, 300.0, 180.0, 260.0, 220.0, 5, 0.0, true, 0.05, 0.2, 0.8, false, 0.0, 0.0, 0.0, 1.0)
            editor.workspace.canvas.add_shape(id, 3, 480.0, 60.0, 200.0, 200.0, 6, 0.0, false, 0.0, 0.0, 0.0, true, 0.1, 0.6, 0.1, 6.0)
            editor.workspace.canvas.set_active_element(id, 1)
            editor.panels.catalog.open("vector")
            editor.workspace.touch()
            editor.panels.refresh()''',
    # Layer › New Vector Layer and Window › Node Editor: the default graph, a
    # star cloned round a circle, the Clone's settings showing.
    'nodes': '''            editor.panels.actions.add_vector_layer.trigger()
            editor.panels.catalog.open("nodes")
            let nodes = editor.panels.catalog.nodes else trap("the Node Editor")
            nodes.show()
            nodes.view.layout_state.selected = [3]
            editor.panels.refresh()''',
    # Generative art: the default graph's ring made 36 stars, scaled at random,
    # colored along a gradient and jittered, over a scatter of small ones.
    'nodeart': '''            editor.panels.actions.add_vector_layer.trigger()
            let layer = editor.workspace.layers.selected_id()
            let canvas = editor.workspace.canvas
            canvas.set_graph_value(layer, 2, 0, 36.0)
            canvas.set_graph_value(layer, 3, 2, 25.0)
            let random = canvas.add_graph_node(layer, 15, 40.0, 620.0)
            canvas.link_graph(layer, random, 3, 2)
            let gradient = canvas.add_graph_node(layer, 16, 40.0, 760.0)
            canvas.link_graph(layer, gradient, 3, 4)
            let scatter = canvas.add_graph_node(layer, 9, 340.0, 520.0)
            canvas.set_graph_value(layer, scatter, 0, 400.0)
            canvas.set_graph_value(layer, scatter, 4, 1400.0)
            canvas.set_graph_value(layer, scatter, 5, 880.0)
            let dot = canvas.add_graph_node(layer, 2, 340.0, 380.0)
            canvas.set_graph_value(layer, dot, 2, 10.0)
            canvas.set_graph_value(layer, dot, 3, 10.0)
            canvas.set_graph_value(layer, dot, 6, 0.9)
            canvas.set_graph_value(layer, dot, 7, 0.85)
            canvas.set_graph_value(layer, dot, 8, 0.8)
            let dots = canvas.add_graph_node(layer, 11, 620.0, 420.0)
            canvas.link_graph(layer, dot, dots, 0)
            canvas.link_graph(layer, scatter, dots, 1)
            let both = canvas.add_graph_node(layer, 13, 900.0, 260.0)
            canvas.link_graph(layer, dots, both, 0)
            canvas.link_graph(layer, 3, both, 1)
            canvas.move_graph_node(layer, 4, 1160.0, 260.0)
            canvas.link_graph(layer, both, 4, 0)
            editor.workspace.touch()
            print(f"NODEART shapes {canvas.generated_count(editor.workspace.layers.selected)}")
            editor.panels.catalog.open("nodes")
            let nodes = editor.panels.catalog.nodes else trap("the Node Editor")
            nodes.show()
            nodes.view.layout_state.selected = [3]
            editor.panels.refresh()''',
    # Save, undo, redo, save again: the list must show all three.
    'channelundo': '''            editor.panels.catalog.open("channels")
            editor.panels.refresh()
            editor.workspace.canvas.select_ellipse(200, 100, 500, 400)
            _ = editor.workspace.canvas.save_selection_channel("Alpha 1")
            editor.workspace.touch()
            editor.panels.refresh()
            _ = editor.workspace.canvas.save_selection_channel("Alpha 2")
            editor.workspace.touch()
            editor.panels.refresh()
            editor.workspace.undo()
            editor.panels.refresh()
            editor.workspace.redo()
            editor.panels.refresh()
            _ = editor.workspace.canvas.save_selection_channel("Alpha 3")
            editor.workspace.touch()
            editor.panels.refresh()''',
    'quickmask': '''            editor.workspace.canvas.select_all()
            editor.workspace.colors.set_color(0.2, 0.2, 0.2)
            editor.workspace.painting.fill_selection(false)
            editor.workspace.canvas.select_ellipse(200, 100, 500, 400)
            editor.workspace.canvas.enter_quick_mask()
            editor.workspace.touch()
            editor.panels.refresh()''',
    'halfstrokes': half_strokes(False),
    'halfstrokeslinear': half_strokes(True),
    'guides': '''            _ = editor.workspace.canvas.add_guide(true, 700.0)
            _ = editor.workspace.canvas.add_guide(false, 300.0)
            editor.panels.refresh()''',
    # A text layer in a box, centred, being edited, in Georgia Italic.
    'text': '''            editor.workspace.choose_tool("text")
            editor.workspace.colors.set_color(1.0, 1.0, 1.0)
            editor.workspace.tools.typing.family = "Georgia"
            editor.workspace.tools.typing.style = "Italic"
            editor.workspace.tools.typing.size = 72.0
            editor.workspace.tools.typing.alignment = 1
            editor.workspace.tools.typing.tracking = 40.0
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
    'closeprompt': '''            editor.workspace.edits.add_layer()
            editor.panels.files.close_document()
            editor.panels.refresh()''',
    'jpeg': '''            editor.panels.files.export_jpeg()
            editor.panels.refresh()''',
    'noise': '''            editor.workspace.layers.select(0)
            editor.panels.adjust.add_noise()
            editor.panels.adjust.set_control(13, 0, 30.0)
            editor.panels.refresh()''',
    'settings': '''            editor.workspace.choose_tool("brush")
            editor.panels.settings_dialog.open()
            editor.panels.settings_dialog.show_page(1)
            editor.panels.refresh()''',
    'brush': '''            editor.workspace.layers.select(1)
            editor.workspace.colors.set_color(0.02, 0.18, 0.65)
            editor.workspace.tools.apply_preset("Spatter")
            editor.workspace.tools.brush.diameter = 40.0
            editor.workspace.painting.begin_stroke(200.0, 200.0)
            editor.workspace.painting.extend_stroke(600.0, 260.0)
            editor.workspace.painting.extend_stroke(1000.0, 180.0)
            editor.workspace.painting.end_stroke()
            editor.workspace.colors.set_color(0.9, 0.9, 0.9)
            editor.workspace.tools.apply_preset("Chalk")
            editor.workspace.tools.brush.diameter = 60.0
            editor.workspace.painting.begin_stroke(200.0, 420.0)
            editor.workspace.painting.extend_stroke(700.0, 480.0)
            editor.workspace.painting.extend_stroke(1100.0, 400.0)
            editor.workspace.painting.end_stroke()
            editor.workspace.colors.set_color(0.8, 0.1, 0.05)
            editor.workspace.tools.apply_preset("Canvas Wash")
            editor.workspace.tools.brush.diameter = 90.0
            editor.workspace.painting.begin_stroke(200.0, 640.0)
            editor.workspace.painting.extend_stroke(1100.0, 700.0)
            editor.workspace.painting.end_stroke()
            editor.workspace.colors.set_color(0.05, 0.05, 0.05)
            editor.workspace.tools.apply_preset("Ink Pen")
            editor.workspace.tools.brush.diameter = 14.0
            editor.workspace.painting.begin_stroke(1150.0, 200.0)
            editor.workspace.painting.extend_stroke(1300.0, 700.0)
            editor.workspace.painting.extend_stroke(1350.0, 300.0)
            editor.workspace.painting.end_stroke()
            editor.workspace.tools.apply_preset("Hard Round")
            editor.workspace.choose_tool("brush")
            editor.panels.open_brush()
            editor.panels.refresh()''',
    'documents': '''            editor.workspace.choose_tool("brush")
            editor.workspace.documents.create(900, 600)
            editor.workspace.documents.open("''' + sample + '''")
            editor.workspace.documents.switch_to(0)
            editor.panels.refresh()''',
    'zoom': '''            editor.workspace.choose_tool("brush")
            editor.panels.refresh()
            let bounds = editor.panels.view.layout().bounds()
            let cx = bounds.x + bounds.width * 0.5
            let cy = bounds.y + bounds.height * 0.5
            # The crop and resize above queued a refit; do it now, as a frame would.
            editor.workspace.viewport.fit(bounds.width, bounds.height)
            print(f"ZOOM start {editor.workspace.viewport.zoom} view {bounds.x},{bounds.y} {bounds.width}x{bounds.height}")
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = cx, y = cy))
            editor.app.dispatch(Event(kind = EventKind.scroll, x = cx, y = cy, scroll_y = 40.0, scroll_unit = ScrollUnit.points, meta = true))
            print(f"ZOOM after cmd-scroll {editor.workspace.viewport.zoom}")
            editor.app.dispatch(Event(kind = EventKind.scroll, x = cx, y = cy, scroll_y = 3.0, scroll_unit = ScrollUnit.lines))
            print(f"ZOOM after wheel {editor.workspace.viewport.zoom}")
            editor.app.dispatch(Event(kind = EventKind.key_down, key = Key.equal, meta = true))
            print(f"ZOOM after cmd-= {editor.workspace.viewport.zoom}")
            editor.workspace.choose_tool("zoom")
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = cx, y = cy, button = 0))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = cx, y = cy, button = 0))
            print(f"ZOOM after zoom tool click {editor.workspace.viewport.zoom}")
            editor.panels.refresh()''',
    'pan': '''            editor.workspace.choose_tool("brush")
            editor.panels.refresh()
            let bounds = editor.panels.view.layout().bounds()
            editor.workspace.viewport.fit(bounds.width, bounds.height)
            let cx = bounds.x + bounds.width * 0.5
            let cy = bounds.y + bounds.height * 0.5
            print(f"PAN start {editor.workspace.viewport.offset_x},{editor.workspace.viewport.offset_y}")
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
            print(f"PAN moved {editor.workspace.viewport.offset_x},{editor.workspace.viewport.offset_y}")
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = cx + 120.0, y = cy + 60.0, button = 0))
            editor.app.dispatch(Event(kind = EventKind.key_up, key = Key.space))
            print(f"PAN done {editor.workspace.viewport.offset_x},{editor.workspace.viewport.offset_y} painting {editor.workspace.canvas.painting()}")
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = cx, y = cy, button = 2))
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = cx - 50.0, y = cy))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = cx - 50.0, y = cy, button = 2))
            print(f"PAN middle {editor.workspace.viewport.offset_x},{editor.workspace.viewport.offset_y}")
            # Leave the last checker block 0.5 points wide at the view's right edge.
            editor.workspace.viewport.zoom = 1.0
            editor.workspace.viewport.offset_x = bounds.width - 768.0 - 0.5
            editor.workspace.viewport.offset_y = 10.0
            print(f"PAN far {editor.workspace.viewport.offset_x},{editor.workspace.viewport.offset_y} zoom {editor.workspace.viewport.zoom}")
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
            print(f"DROP start layers {editor.workspace.canvas.layer_count()} documents {editor.workspace.documents.count()}")
            editor.app.set_drop_paths(["''' + sample + '''", "/tmp/readme.txt"])
            editor.app.dispatch(Event(kind = EventKind.drag_entered, x = layer_area.x + 40.0, y = layer_area.y + 200.0))
            print(f"DROP over layers hovered {editor.panels.layers.layout().is_drop_hovered()} accepted {editor.panels.layers.layout().is_drop_accepted()}")
            editor.app.dispatch(Event(kind = EventKind.drop, x = layer_area.x + 40.0, y = layer_area.y + 200.0))
            print(f"DROP placed layers {editor.workspace.canvas.layer_count()} selected {editor.workspace.canvas.layer_name(editor.workspace.layers.selected)}")
            editor.app.dispatch(Event(kind = EventKind.drag_entered, x = canvas.x + 200.0, y = canvas.y + 200.0))
            editor.app.dispatch(Event(kind = EventKind.drop, x = canvas.x + 200.0, y = canvas.y + 200.0))
            print(f"DROP opened documents {editor.workspace.documents.count()} current {editor.workspace.documents.title(editor.workspace.documents.current)}")
            editor.app.set_drop_paths(["/tmp/readme.txt"])
            editor.app.dispatch(Event(kind = EventKind.drag_entered, x = canvas.x + 200.0, y = canvas.y + 200.0))
            print(f"DROP text refused {not editor.panels.view.layout().is_drop_accepted()}")
            editor.app.dispatch(Event(kind = EventKind.drag_left))
            editor.app.set_drop_paths(["''' + sample + '''"])
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
            editor.workspace.viewport.show_rulers = true
            editor.workspace.viewport.show_grid = true
            editor.workspace.viewport.units = "mm"
            editor.workspace.canvas.set_resolution(150.0)
            editor.panels.refresh()''',
    'document': '''            editor.workspace.choose_tool("brush")
            editor.workspace.viewport.units = "mm"
            editor.workspace.canvas.set_resolution(300.0)
            editor.panels.document_settings.open()
            editor.panels.refresh()''',
    'white': '''            editor.workspace.choose_tool("brush")
            editor.workspace.layers.select(0)
            editor.workspace.canvas.set_layer(editor.workspace.layers.selected_id(), false, 1.0)
            editor.workspace.layers.select(1)
            editor.workspace.canvas.set_layer(editor.workspace.layers.selected_id(), true, 1.0, 0)
            editor.workspace.colors.set_color(1.0, 1.0, 1.0)
            editor.workspace.tools.apply_preset("Hard Round")
            editor.workspace.tools.brush.diameter = 40.0
            editor.workspace.painting.begin_stroke(200.0, 200.0)
            editor.workspace.painting.extend_stroke(1000.0, 260.0)
            editor.workspace.painting.end_stroke()
            editor.workspace.tools.apply_preset("Soft Round")
            editor.workspace.tools.brush.diameter = 80.0
            editor.workspace.painting.begin_stroke(200.0, 450.0)
            editor.workspace.painting.extend_stroke(1000.0, 520.0)
            editor.workspace.painting.end_stroke()
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
            let before = editor.workspace.viewport.zoom
            editor.app.dispatch(Event(kind = EventKind.key_down, key = Key.z))
            editor.app.dispatch(Event(kind = EventKind.key_down, key = Key.z, repeated = true))
            print(f"ZOOMHOLD tool while held {editor.workspace.tools.tool}")
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = cx, y = cy, button = 0))
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = cx + 60.0, y = cy))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = cx + 60.0, y = cy, button = 0))
            editor.app.dispatch(Event(kind = EventKind.key_up, key = Key.z))
            print(f"ZOOMHOLD zoom {before} -> {editor.workspace.viewport.zoom} tool after {editor.workspace.tools.tool}")
            editor.panels.refresh()''',
    'pickerwhite': '''            editor.workspace.choose_tool("brush")
            editor.workspace.colors.set_color(1.0, 1.0, 1.0)
            editor.panels.panel_prompts.pick_color(false)
            editor.panels.refresh()''',
    'strokes': '''            editor.workspace.choose_tool("brush")
            editor.workspace.colors.set_color(0.9, 0.05, 0.05)
            editor.workspace.tools.brush.diameter = 18.0
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
            print(f"STROKES color after alt-click {editor.workspace.colors.color_hex()}")
            editor.panels.refresh()''',
    'selmove': '''            editor.workspace.layers.select(0)
            editor.workspace.choose_tool("move")
            editor.panels.refresh()
            let area = editor.panels.view.layout().bounds()
            let zoom = editor.workspace.viewport.zoom
            let ox = area.x + editor.workspace.viewport.offset_x
            let oy = area.y + editor.workspace.viewport.offset_y
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
            editor.workspace.previews.adjust(2, [])
            print(f"SELMOVE selection at {editor.workspace.canvas.selection_left()},{editor.workspace.canvas.selection_top()} undo {editor.workspace.canvas.can_undo()}")
            editor.panels.refresh()''',
    'movetool': '''            editor.workspace.edits.add_layer()
            editor.workspace.choose_tool("move")
            editor.panels.refresh()
            let area = editor.panels.view.layout().bounds()
            let zoom = editor.workspace.viewport.zoom
            let ox = area.x + editor.workspace.viewport.offset_x
            let oy = area.y + editor.workspace.viewport.offset_y
            # An orange block on a new layer.
            editor.workspace.colors.set_color(0.9, 0.35, 0.05)
            editor.workspace.canvas.select_rectangle(100, 100, 200, 150, 0)
            editor.workspace.canvas.fill(editor.workspace.layers.selected_id(), false)
            editor.workspace.canvas.deselect()
            let top = editor.workspace.layers.selected
            # Alt-Shift-drag: a copy of the layer, kept to the horizontal axis.
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = ox + 150.0 * zoom, y = oy + 150.0 * zoom, button = 0, alt = true))
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = ox + 400.0 * zoom, y = oy + 190.0 * zoom, alt = true, shift = true))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = ox + 450.0 * zoom, y = oy + 210.0 * zoom, button = 0, alt = true, shift = true))
            print(f"MOVETOOL layers {editor.workspace.canvas.layer_count()} copy at {editor.workspace.canvas.layer_at(420, 120)} original at {editor.workspace.canvas.layer_at(120, 120)} below {editor.workspace.canvas.layer_at(420, 300)}")
            # Cmd-click on the original picks its layer.
            editor.workspace.layers.select(0)
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = ox + 150.0 * zoom, y = oy + 150.0 * zoom, button = 0, meta = true))
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = ox + 150.0 * zoom, y = oy + 150.0 * zoom, button = 0, meta = true))
            print(f"MOVETOOL picked {editor.workspace.layers.selected} expected {top}")
            editor.panels.refresh()''',
    'ellipsedrag': '''            editor.workspace.choose_tool("ellipse")
            editor.panels.refresh()
            let area = editor.panels.view.layout().bounds()
            let zoom = editor.workspace.viewport.zoom
            let ox = area.x + editor.workspace.viewport.offset_x
            let oy = area.y + editor.workspace.viewport.offset_y
            # Mid-drag: the outline is the ellipse, not its bounding box.
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = ox + 200.0 * zoom, y = oy + 150.0 * zoom, button = 0))
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = ox + 700.0 * zoom, y = oy + 500.0 * zoom))
            editor.panels.refresh()''',
    'selmovedrag': '''            editor.workspace.layers.select(0)
            editor.workspace.choose_tool("move")
            editor.panels.refresh()
            let area = editor.panels.view.layout().bounds()
            let zoom = editor.workspace.viewport.zoom
            let ox = area.x + editor.workspace.viewport.offset_x
            let oy = area.y + editor.workspace.viewport.offset_y
            # Mid-drag of selected pixels: the ants go with them.
            editor.workspace.canvas.select_rectangle(100, 100, 300, 250, 0)
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = ox + 200.0 * zoom, y = oy + 200.0 * zoom, button = 0))
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = ox + 500.0 * zoom, y = oy + 350.0 * zoom))
            editor.panels.refresh()''',
    'transform': '''            editor.workspace.layers.select(1)
            editor.panels.refresh()
            let area = editor.panels.view.layout().bounds()
            editor.workspace.viewport.fit(area.width, area.height)
            let zoom = editor.workspace.viewport.zoom
            let ox = area.x + editor.workspace.viewport.offset_x
            let oy = area.y + editor.workspace.viewport.offset_y
            editor.panels.transform_flow.free_transform()
            let session = editor.workspace.transforms.transform else trap("a transform")
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
    'distort': '''            editor.workspace.layers.select(1)
            editor.panels.refresh()
            let area = editor.panels.view.layout().bounds()
            editor.workspace.viewport.fit(area.width, area.height)
            let zoom = editor.workspace.viewport.zoom
            let ox = area.x + editor.workspace.viewport.offset_x
            let oy = area.y + editor.workspace.viewport.offset_y
            editor.panels.transform_flow.free_transform()
            let session = editor.workspace.transforms.transform else trap("a transform")
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
            editor.workspace.viewport.fit(area.width, area.height)
            let zoom = editor.workspace.viewport.zoom
            let ox = area.x + editor.workspace.viewport.offset_x
            let oy = area.y + editor.workspace.viewport.offset_y
            # Pull the top-left corner in; the rest shades.
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = ox, y = oy, button = 0))
            print("CROP pressed")
            editor.app.dispatch(Event(kind = EventKind.pointer_moved, x = ox + 300.0 * zoom, y = oy + 200.0 * zoom))
            print("CROP dragged")
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = ox + 300.0 * zoom, y = oy + 200.0 * zoom, button = 0))
            let crop = editor.workspace.image.crop_box else trap("a crop box")
            print(f"CROP box {crop.left},{crop.top} {crop.width()}x{crop.height()}")
            editor.panels.refresh()''',
    'flip': '''            editor.workspace.layers.select(1)
            editor.workspace.transforms.flip_layer(true)
            editor.workspace.image.flip_canvas(false)
            print(f"FLIP undo {editor.workspace.canvas.can_undo()}")
            editor.panels.refresh()''',
    # Choosing the Crop tool rebuilds the header; a press after it once set off
    # a collection inside the relayout that trapped (luce-ui 0.6.5 fixed it).
    'croppress': '''            editor.workspace.choose_tool("crop")
            editor.panels.refresh()
            let area = editor.panels.view.layout().bounds()
            let ox = area.x + editor.workspace.viewport.offset_x
            let oy = area.y + editor.workspace.viewport.offset_y
            print(f"PRESS at {ox},{oy}")
            editor.app.dispatch(Event(kind = EventKind.pointer_down, x = ox, y = oy, button = 0))
            print("PRESS done")
            editor.app.dispatch(Event(kind = EventKind.pointer_up, x = ox, y = oy, button = 0))
            print("PRESS up")
            editor.panels.refresh()''',
    'groups': '''            editor.workspace.layers.select(1)
            editor.workspace.layers.toggle_picked(0)
            group_selected(editor.workspace)
            editor.workspace.edits.add_layer()
            editor.workspace.edits.toggle_mask(true)
            var index = editor.workspace.canvas.layer_count() - 1
            while index >= 0:
                let canvas = editor.workspace.canvas
                print(f"GROUPS {index} {canvas.layer_name(index)} depth {canvas.layer_depth(index)} group {canvas.layer_is_group(index)} masked {canvas.layer_masked(index)}")
                index -= 1
            editor.panels.refresh()''',
    'clipboard': '''            let saved = clipboard.read_text()
            editor.workspace.layers.select(0)
            editor.workspace.choose_tool("marquee")
            editor.panels.refresh()
            editor.workspace.canvas.select_rectangle(900, 150, 400, 300, 0)
            # Keys go where focus is: on the canvas, as after a click there.
            editor.panels.view.layout().request_focus()
            editor.app.layout(1400.0, 900.0)
            editor.app.dispatch(Event(kind = EventKind.key_down, key = Key.c, meta = true))
            editor.app.dispatch(Event(kind = EventKind.key_down, key = Key.v, meta = true))
            print(f"CLIPBOARD after paste layers {editor.workspace.canvas.layer_count()} selected {editor.workspace.canvas.layer_name(editor.workspace.layers.selected)}")
            editor.workspace.edits.move_layer(-500, 200)
            editor.workspace.layers.select(0)
            editor.workspace.canvas.select_rectangle(100, 500, 300, 200, 0)
            editor.app.dispatch(Event(kind = EventKind.key_down, key = Key.j, meta = true))
            editor.workspace.edits.move_layer(900, -350)
            print(f"CLIPBOARD after layer via copy layers {editor.workspace.canvas.layer_count()} selected {editor.workspace.canvas.layer_name(editor.workspace.layers.selected)}")
            clipboard.write_text(saved)
            editor.panels.refresh()''',
    # The Color panel's picker in each mode, on an orange foreground.
    'colortriangle': color_scene(0),
    'colorsquare': color_scene(1),
    'colorwheel': color_scene(2),
    'colorsliders': color_scene(3),
    'picker': '''            editor.workspace.choose_tool("brush")
            editor.workspace.colors.set_color(0.8069, 0.3515, 0.0497)
            editor.panels.panel_prompts.pick_color(false)
            editor.panels.refresh()''',
    # Brush Settings docked short, over strokes of a painted tip with a
    # texture; the Brushes panel's thumbnails beside it.
    'brushtip': """            editor.workspace.layers.select(1)
            editor.workspace.choose_tool("brush")
            let tip = BrushMask.create(64, 64)
            tip.line(8.0, 32.0, 56.0, 32.0, 6.0, 0.6, 1.0)
            tip.line(32.0, 8.0, 32.0, 56.0, 3.0, 0.9, 1.0)
            editor.workspace.tools.brush = preset("Hard Round", 60.0, 1.0)
            editor.workspace.tools.brush.tip = tip
            editor.workspace.tools.brush.texture = 2
            editor.workspace.tools.brush.texture_depth = 0.8
            editor.workspace.colors.set_color(0.05, 0.2, 0.7)
            editor.workspace.painting.begin_stroke(150.0, 200.0)
            editor.workspace.painting.extend_stroke(600.0, 300.0)
            editor.workspace.painting.extend_stroke(1100.0, 200.0)
            editor.workspace.painting.end_stroke()
            editor.panels.catalog.open("brushes")
            editor.panels.open_brush()
            editor.panels.refresh()
            editor.panels.dock.move(editor.panels.brush.panel, editor.panels.properties.panel, DockPosition.tab)
            editor.panels.refresh()""",
    # A plain round brush: the tip pad shows the round tip it paints with.
    'brushround': """            editor.workspace.choose_tool("brush")
            editor.workspace.tools.brush = preset("Soft Round", 60.0, 1.0)
            editor.workspace.tools.brush.roundness = 0.5
            editor.workspace.tools.brush.angle = 30.0
            editor.panels.open_brush()
            editor.panels.refresh()
            editor.panels.dock.move(editor.panels.brush.panel, editor.panels.properties.panel, DockPosition.tab)
            editor.panels.brush.open_section(0, false)
            editor.panels.refresh()""",
    'brushlist': """            editor.workspace.choose_tool("brush")
            editor.panels.open_brush()
            editor.panels.refresh()
            editor.panels.dock.move(editor.panels.brush.panel, editor.panels.properties.panel, DockPosition.tab)
            editor.panels.catalog.open("brushes")
            editor.panels.refresh()""",
    # Shape Dynamics open: Size on Pen Pressure, Angle on Azimuth.
    'brushdynamics': """            editor.workspace.choose_tool("brush")
            editor.workspace.tools.brush.dynamics[0] = mapped(1, 0.25, 0.3)
            editor.workspace.tools.brush.dynamics[3] = mapped(3)
            editor.panels.open_brush()
            editor.panels.refresh()
            editor.panels.dock.move(editor.panels.brush.panel, editor.panels.properties.panel, DockPosition.tab)
            editor.panels.brush.open_section(1, false)
            editor.panels.refresh()""",
    # Transfer open: Flow on Pen Tilt, Opacity fading over 40 dabs.
    'brushtransfer': """            editor.workspace.choose_tool("brush")
            editor.workspace.tools.brush.dynamics[1] = mapped(2, 0.1)
            editor.workspace.tools.brush.dynamics[2] = mapped(8, 0.0, 0.0, 40)
            editor.panels.open_brush()
            editor.panels.refresh()
            editor.panels.dock.move(editor.panels.brush.panel, editor.panels.properties.panel, DockPosition.tab)
            editor.panels.brush.open_section(5, false)
            editor.panels.refresh()""",
}
