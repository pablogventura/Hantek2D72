#!/usr/bin/env python3
"""Simplified Python translation of the Hantek 2D72 tool.

This module reimplements the core logic of the original C version using
PyUSB and GTK (via PyGObject).  The program is intentionally compact and
focuses on demonstrating how the device is accessed from Python.  Not all
features of the C implementation are currently ported.
"""
from __future__ import annotations

import json
import os
import struct
from dataclasses import dataclass, field

import usb.core
import usb.util
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

# ---------------------------------------------------------------------------
# Constants from Hantek.h
# ---------------------------------------------------------------------------
VENDOR = 0x0483
PRODUCT = 0x2D42

FUNC_SCOPE_SETTING = 0x0000
FUNC_SCOPE_CAPTURE = 0x0100
FUNC_AWG_SETTING = 0x0002
FUNC_SCREEN_SETTING = 0x0003

# Scope settings
SCOPE_ENABLE_CH1 = 0x00
SCOPE_ENABLE_CH2 = 0x06
SCOPE_START_RECV = 0x16
SCOPE_SCALE_TIME = 0x0E
SCOPE_OFFSET_TIME = 0x0F
SCOPE_TRIGGER_SOURCE = 0x10
SCOPE_TRIGGER_LEVEL = 0x14

# AWG settings
AWG_FREQ = 0x01
AWG_AMP = 0x02
AWG_OFF = 0x03
AWG_START = 0x08

# Screen values
SCREEN_VAL_SCOPE = 0x00
SCREEN_VAL_DMM = 0x01
SCREEN_VAL_AWG = 0x02

# Configuration storage
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "Hantek2D72")
CONFIG_FILE = os.path.join(CONFIG_DIR, "Hantek.cfg")

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class HantekCommand:
    func: int
    cmd: int
    vals: list[int] = field(default_factory=lambda: [0, 0, 0, 0])

    def to_bytes(self) -> bytes:
        """Return command in the 10-byte format used on the USB wire."""
        return struct.pack(
            "<BBHBBBBBB",
            0x00,
            0x0A,
            self.func,
            self.cmd,
            *self.vals,
            0x00,
        )


def _default_list(v, n):
    return [v for _ in range(n)]


@dataclass
class Config:
    channel_enable: list[bool] = field(default_factory=lambda: _default_list(True, 2))
    time_scale: int = 0
    time_offset: float = 0.0
    trigger_source: int = 0
    trigger_level: float = 0.0
    awg_frequency: float = 1000.0
    awg_amplitude: float = 2.5
    awg_offset: float = 0.0
    num_samples: int = 1200


def load_config() -> Config:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf8") as fh:
            return Config(**json.load(fh))
    cfg = Config()
    save_config(cfg)
    return cfg


def save_config(cfg: Config) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf8") as fh:
        json.dump(cfg.__dict__, fh, indent=2)
# ---------------------------------------------------------------------------
# USB helpers
# ---------------------------------------------------------------------------

def find_device(vendor: int, product: int) -> usb.core.Device:
    dev = usb.core.find(idVendor=vendor, idProduct=product)
    if dev is None:
        raise IOError("USB device not found")
    return dev


def claim_interfaces(dev: usb.core.Device) -> None:
    for cfg in dev:
        for intf in cfg:
            if dev.is_kernel_driver_active(intf.bInterfaceNumber):
                dev.detach_kernel_driver(intf.bInterfaceNumber)
            usb.util.claim_interface(dev, intf.bInterfaceNumber)


def release_interfaces(dev: usb.core.Device) -> None:
    for cfg in dev:
        for intf in cfg:
            usb.util.release_interface(dev, intf.bInterfaceNumber)


def send_command(dev: usb.core.Device, cmd: HantekCommand) -> None:
    dev.write(0x02, cmd.to_bytes())
# ---------------------------------------------------------------------------
# GTK widget references and callbacks
# ---------------------------------------------------------------------------

handle: usb.core.Device | None = None
cur_config: Config

# Widgets (set during GUI setup)
scope_radio: Gtk.RadioButton
awg_radio: Gtk.RadioButton
dmm_radio: Gtk.RadioButton

channel_enable_switch_ch1: Gtk.Switch
channel_enable_switch_ch2: Gtk.Switch

time_scale_combobox: Gtk.ComboBox
time_offset_spinbutton: Gtk.SpinButton

trigger_source_combobox: Gtk.ComboBox
trigger_level_spinbutton: Gtk.SpinButton

awg_frequency_spinbutton: Gtk.SpinButton
awg_amplitude_spinbutton: Gtk.SpinButton
awg_offset_spinbutton: Gtk.SpinButton

capture_samples_spinbutton: Gtk.SpinButton
drawing_area: Gtk.Widget


def on_window_main_destroy(widget, data):
    Gtk.main_quit()


def on_channel_enable(switch: Gtk.Switch, state: bool, data=None):
    idx = 0 if switch is channel_enable_switch_ch1 else 1
    cmd = SCOPE_ENABLE_CH1 if idx == 0 else SCOPE_ENABLE_CH2
    cur_config.channel_enable[idx] = state
    send_command(handle, HantekCommand(FUNC_SCOPE_SETTING, cmd,
                                       [int(state), 0, 0, 0]))
    switch.set_state(state)
    save_config(cur_config)
    return True


def on_channel_offset(widget: Gtk.SpinButton, scroll, data=None):
    save_config(cur_config)


def on_channel_bwlimit(switch: Gtk.Switch, state: bool, data=None):
    switch.set_state(state)
    save_config(cur_config)
    return True


def on_channel_coupling(widget: Gtk.ComboBox, data=None):
    save_config(cur_config)


def on_channel_scale(widget: Gtk.ComboBox, data=None):
    save_config(cur_config)


def on_channel_probe(widget: Gtk.ComboBox, data=None):
    save_config(cur_config)


def on_time_scale(widget: Gtk.ComboBox, data=None):
    val = widget.get_active()
    cur_config.time_scale = val
    send_command(handle, HantekCommand(FUNC_SCOPE_SETTING, SCOPE_SCALE_TIME,
                                       [val, 0, 0, 0]))
    save_config(cur_config)


def on_time_offset(widget: Gtk.SpinButton, scroll, data=None):
    val = widget.get_value()
    cur_config.time_offset = val
    send_command(handle, HantekCommand(FUNC_SCOPE_SETTING, SCOPE_OFFSET_TIME,
                                       [int(val), 0, 0, 0]))
    save_config(cur_config)


def on_trigger_source(widget: Gtk.ComboBox, data=None):
    val = widget.get_active()
    cur_config.trigger_source = val
    send_command(handle, HantekCommand(FUNC_SCOPE_SETTING, SCOPE_TRIGGER_SOURCE,
                                       [val, 0, 0, 0]))
    save_config(cur_config)


def on_trigger_slope(widget: Gtk.ComboBox, data=None):
    return


def on_trigger_mode(widget: Gtk.ComboBox, data=None):
    return


def on_trigger_level(widget: Gtk.SpinButton, scroll, data=None):
    val = widget.get_value()
    cur_config.trigger_level = val
    send_command(handle, HantekCommand(FUNC_SCOPE_SETTING, SCOPE_TRIGGER_LEVEL,
                                       [int(val), 0, 0, 0]))
    save_config(cur_config)


def on_start(widget, data=None):
    return


def on_stop(widget, data=None):
    return


def on_awg_freq(widget: Gtk.SpinButton, scroll, data=None):
    val = int(widget.get_value())
    cur_config.awg_frequency = val
    cmd = HantekCommand(FUNC_AWG_SETTING, AWG_FREQ)
    cmd.vals = list(struct.pack('<I', val))
    send_command(handle, cmd)
    save_config(cur_config)


def on_awg_amp(widget: Gtk.SpinButton, scroll, data=None):
    val = widget.get_value()
    cur_config.awg_amplitude = val
    vals = [abs(int(val*1000)), int(val < 0), 0, 0]
    send_command(handle, HantekCommand(FUNC_AWG_SETTING, AWG_AMP, vals))
    save_config(cur_config)


def on_awg_offset(widget: Gtk.SpinButton, scroll, data=None):
    val = widget.get_value()
    cur_config.awg_offset = val
    vals = [abs(int(val*1000)), int(val < 0), 0, 0]
    send_command(handle, HantekCommand(FUNC_AWG_SETTING, AWG_OFF, vals))
    save_config(cur_config)


def on_awg_type(widget: Gtk.ComboBox, data=None):
    return


def on_awg_square_duty(widget: Gtk.SpinButton, scroll, data=None):
    return


def on_awg_ramp_duty(widget: Gtk.SpinButton, scroll, data=None):
    return


def on_awg_trap_duty(widget: Gtk.SpinButton, scroll, data=None):
    return


def on_awg_start(widget, data=None):
    send_command(handle, HantekCommand(FUNC_AWG_SETTING, AWG_START,
                                       [1, 0, 0, 0]))


def on_awg_stop(widget, data=None):
    send_command(handle, HantekCommand(FUNC_AWG_SETTING, AWG_START,
                                       [0, 0, 0, 0]))


def on_radio(button: Gtk.RadioButton, data=None):
    if button is scope_radio:
        val = SCREEN_VAL_SCOPE
    elif button is awg_radio:
        val = SCREEN_VAL_AWG
    else:
        val = SCREEN_VAL_DMM
    send_command(handle, HantekCommand(FUNC_SCREEN_SETTING, 0, [val, 0, 0, 0]))


capture_buffer = bytearray(6000)


def on_capture_button_clicked(widget, data=None):
    num_channels = int(cur_config.channel_enable[0]) + int(cur_config.channel_enable[1])
    total_samples = cur_config.num_samples * num_channels
    # Prepare capture command once with per-channel sample counts
    ch1_samples = cur_config.num_samples if cur_config.channel_enable[0] else 0
    ch2_samples = cur_config.num_samples if cur_config.channel_enable[1] else 0
    cmd = HantekCommand(FUNC_SCOPE_CAPTURE, SCOPE_START_RECV)
    cmd.vals = list(struct.pack('<HH', ch1_samples, ch2_samples))
    send_command(handle, cmd)

    count = 0
    while count < total_samples:
        length = min(total_samples - count, 64)
        data_read = handle.read(0x81, length)
        capture_buffer[count:count+len(data_read)] = data_read
        count += len(data_read)
    drawing_area.queue_draw()


def draw_callback(widget, cr, data=None):
    width = widget.get_allocated_width()
    height = widget.get_allocated_height()
    num_channels = int(cur_config.channel_enable[0]) + int(cur_config.channel_enable[1])
    num_samples = cur_config.num_samples * num_channels

    cr.set_source_rgb(0, 0, 0)
    cr.paint()
    cr.set_source_rgb(0.9, 0.9, 0.9)
    cr.set_dash([5.0, 5.0], 0)
    cr.set_line_width(0.3)
    num_sector = cur_config.num_samples // 100
    for i in range(1, num_sector):
        x = i * width / num_sector
        cr.move_to(x, 0)
        cr.line_to(x, height)
    for i in range(1, 8):
        y = i * height / 8
        cr.move_to(0, y)
        cr.line_to(width, y)
    cr.stroke()

    cr.set_dash([], 0)
    cr.set_line_width(0.5)
    for ch in range(2):
        if not cur_config.channel_enable[ch]:
            continue
        if ch == 0:
            cr.set_source_rgb(1, 1, 0)
        else:
            cr.set_source_rgb(0, 1, 0)
        start = capture_buffer[ch]
        cr.move_to(0, height - (start - 29) * height / 202)
        for x in range(1, cur_config.num_samples):
            idx = x * num_channels + ch
            val = capture_buffer[idx]
            cr.line_to(x * width / cur_config.num_samples,
                       height - (val - 29) * height / 202)
        cr.stroke()
    return False


def on_capture_samples(widget: Gtk.SpinButton, scroll, data=None):
    cur_config.num_samples = widget.get_value_as_int()
    save_config(cur_config)
# ---------------------------------------------------------------------------
# GUI setup and application entry point
# ---------------------------------------------------------------------------

def setup_gui(builder: Gtk.Builder) -> None:
    global scope_radio, awg_radio, dmm_radio
    global channel_enable_switch_ch1, channel_enable_switch_ch2
    global time_scale_combobox, time_offset_spinbutton
    global trigger_source_combobox, trigger_level_spinbutton
    global awg_frequency_spinbutton, awg_amplitude_spinbutton, awg_offset_spinbutton
    global capture_samples_spinbutton, drawing_area

    scope_radio = builder.get_object("scope_radio")
    awg_radio = builder.get_object("awg_radio")
    dmm_radio = builder.get_object("dmm_radio")
    channel_enable_switch_ch1 = builder.get_object("channel_enable_switch_ch1")
    channel_enable_switch_ch2 = builder.get_object("channel_enable_switch_ch2")
    time_scale_combobox = builder.get_object("time_scale_combobox")
    time_offset_spinbutton = builder.get_object("time_offset_spinbutton")
    trigger_source_combobox = builder.get_object("trigger_source_combobox")
    trigger_level_spinbutton = builder.get_object("trigger_level_spinbutton")
    awg_frequency_spinbutton = builder.get_object("awg_frequency_spinbutton")
    awg_amplitude_spinbutton = builder.get_object("awg_amplitude_spinbutton")
    awg_offset_spinbutton = builder.get_object("awg_offset_spinbutton")
    capture_samples_spinbutton = builder.get_object("capture_samples_spinbutton")
    drawing_area = builder.get_object("drawing_area")


handlers = {
    "on_window_main_destroy": on_window_main_destroy,
    "on_channel_enable": on_channel_enable,
    "on_channel_offset": on_channel_offset,
    "on_channel_bwlimit": on_channel_bwlimit,
    "on_channel_coupling": on_channel_coupling,
    "on_channel_scale": on_channel_scale,
    "on_channel_probe": on_channel_probe,
    "on_time_scale": on_time_scale,
    "on_time_offset": on_time_offset,
    "on_trigger_source": on_trigger_source,
    "on_trigger_slope": on_trigger_slope,
    "on_trigger_mode": on_trigger_mode,
    "on_trigger_level": on_trigger_level,
    "on_start": on_start,
    "on_stop": on_stop,
    "on_awg_type": on_awg_type,
    "on_awg_square_duty": on_awg_square_duty,
    "on_awg_ramp_duty": on_awg_ramp_duty,
    "on_awg_trap_duty": on_awg_trap_duty,
    "on_awg_freq": on_awg_freq,
    "on_awg_amp": on_awg_amp,
    "on_awg_offset": on_awg_offset,
    "on_awg_start": on_awg_start,
    "on_awg_stop": on_awg_stop,
    "on_radio": on_radio,
    "on_capture_button_clicked": on_capture_button_clicked,
    "draw_callback": draw_callback,
    "on_capture_samples": on_capture_samples,
}


def main() -> None:
    global handle, cur_config
    handle = find_device(VENDOR, PRODUCT)
    claim_interfaces(handle)

    cur_config = load_config()

    builder = Gtk.Builder()
    builder.add_from_file("Hantek.glade")
    builder.connect_signals(handlers)
    setup_gui(builder)

    window = builder.get_object("window_main")
    window.show_all()
    Gtk.main()

    save_config(cur_config)
    release_interfaces(handle)


if __name__ == "__main__":
    main()
