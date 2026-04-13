#!/usr/bin/env python3

# pyright: reportMissingImports=false

from pathlib import Path
from types import SimpleNamespace
import sys


sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from main import AnnotationGUI


class FakeVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeScale:
    def __init__(self):
        self.state = None

    def config(self, *, state):
        self.state = state


class FakeCanvas:
    def __init__(self):
        self.created = []
        self.deleted = []
        self.raised = []
        self.next_id = 1

    def create_line(self, *coords, **kwargs):
        item_id = self.next_id
        self.next_id += 1
        self.created.append((item_id, coords, kwargs))
        return item_id

    def delete(self, item_id):
        self.deleted.append(item_id)

    def tag_raise(self, item):
        self.raised.append(item)


def make_gui_stub():
    gui = AnnotationGUI.__new__(AnnotationGUI)
    gui.hover_enabled = FakeVar(False)
    gui.femoral_axis_enabled = FakeVar(False)
    gui.selected_landmark = FakeVar("")
    gui.femoral_axis_count = FakeVar(5)
    gui.femoral_axis_proj_length = FakeVar(60)
    gui.femoral_axis_whisker_tip_length = FakeVar(10)
    gui.femoral_axis_item_ids = []
    gui.radius_scale = FakeScale()
    gui.femoral_axis_count_scale = FakeScale()
    gui.femoral_axis_whisker_tip_length_scale = FakeScale()
    gui.canvas = FakeCanvas()
    gui.current_image = object()
    return gui


def test_toggle_hover_disables_femoral_axis_tool():
    gui = make_gui_stub()
    gui.hover_enabled.set(True)
    gui.femoral_axis_enabled.set(True)
    calls = []
    gui._hide_hover_circle = lambda: calls.append("hide_hover")
    gui._clear_femoral_axis_overlay = lambda: calls.append("clear_femoral_axis")

    gui._toggle_hover()

    assert gui.radius_scale.state == "normal"
    assert gui.femoral_axis_enabled.get() is False
    assert gui.femoral_axis_count_scale.state == "disabled"
    assert gui.femoral_axis_whisker_tip_length_scale.state == "disabled"
    assert calls == ["clear_femoral_axis"]


def test_mousewheel_adjusts_femoral_axis_length_for_selected_fa_landmark():
    gui = make_gui_stub()
    gui.right_mouse_held = False
    gui.femoral_axis_enabled.set(True)
    gui.selected_landmark.set("L-FA")
    gui.hover_enabled.set(True)
    deltas = []
    gui._change_femoral_axis_length = lambda delta: deltas.append(delta)

    gui._on_mousewheel(SimpleNamespace(delta=120))

    assert deltas == [2]


def test_update_femoral_axis_overlay_draws_whiskers_and_tip_caps():
    gui = make_gui_stub()
    gui.femoral_axis_enabled.set(True)
    gui.selected_landmark.set("L-FA")
    gui.femoral_axis_count.set(2)
    gui.femoral_axis_proj_length.set(12)
    gui.femoral_axis_whisker_tip_length.set(4)
    gui._get_active_femoral_axis_line_screen = lambda: (0.0, 0.0, 100.0, 0.0)

    gui._update_femoral_axis_overlay()

    assert len(gui.canvas.created) == 6
    assert len(gui.femoral_axis_item_ids) == 6
    assert gui.canvas.raised[-1] == "marker"
