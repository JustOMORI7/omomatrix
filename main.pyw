import sys
import asyncio
import logging
# Monkeypatch inspect.getargspec for Python 3.14 compatibility (removed in 3.11)
import inspect
if not hasattr(inspect, 'getargspec'):
    inspect.getargspec = inspect.getfullargspec

# Monkeypatch collections.Iterable for Python 3.14 compatibility (moved to collections.abc)
import collections
import collections.abc
if not hasattr(collections, 'Iterable'):
    collections.Iterable = collections.abc.Iterable

from utils.qt import QtWidgets
import qasync

from core.client import MatrixWorker
from gui.window import MainWindow

async def main_setup(app):
    # Initialize Core
    worker = MatrixWorker()
    
    # Initialize GUI
    window = MainWindow(worker)
    window.show()
    
    # Keep reference to worker
    app._worker = worker
    
    # Wait until the app exits
    # QEventLoop.run_forever() handles the Qt events, but here we are in asyncio land.
    # We need a future that stays pending until the app quits.
    future = asyncio.get_running_loop().create_future()
    app.aboutToQuit.connect(lambda: future.set_result(None))
    await future

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    app = QtWidgets.QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    try:
        with loop:
            loop.run_until_complete(main_setup(app))
    except asyncio.CancelledError:
        pass
