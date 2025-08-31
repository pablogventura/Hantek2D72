# Hantek

Hantek 2D72 handheld oscilloscope tool for Linux written in Python.

This repository now provides a Python implementation of the graphical tool
using [PyUSB](https://github.com/pyusb/pyusb) and GTK via PyGObject.  It is a
port of the original C version and offers a simple way to control the
oscilloscope on Linux.

## Running

```bash
python3 Hantek.py
```

The application relies on the `Hantek.glade` file for its user interface and
will automatically create `Hantek.cfg` to store settings.

Use of this tool is at your own risk; it has only been tested with a single
oscilloscope unit.
