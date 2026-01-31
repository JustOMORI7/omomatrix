import sys
import os

# Ultra-low RAM usage goal: Try to import the most lightweight/native binding available.
# Preference: PySide2 (Win7 target) -> PyQt5 (Fallback)

qt_binding = None

try:
    import PySide2
    from PySide2 import QtCore, QtGui, QtWidgets
    qt_binding = "PySide2"
except ImportError:
    try:
        import PyQt5
        from PyQt5 import QtCore, QtGui, QtWidgets
        qt_binding = "PyQt5"
    except ImportError:
        raise ImportError("No Qt binding found. Please install PySide2 or PyQt5.")

print(f"Using Qt Binding: {qt_binding}")

# Re-export key modules for easy access throughout the app
QtCore = QtCore
QtGui = QtGui
QtWidgets = QtWidgets

if qt_binding == "PySide2":
    Signal = QtCore.Signal
    Slot = QtCore.Slot
elif qt_binding == "PyQt5":
    Signal = QtCore.pyqtSignal
    Slot = QtCore.pyqtSlot

