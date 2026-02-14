#!/usr/bin/env python3
"""
OMOMatrix - Modern Matrix Client

Entry point for the application.
"""

import sys
import asyncio
import logging
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, Gio, GLib, Gdk
from gui import OMOMatrixApp

# Set up logging early to capture startup errors
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(
    level=logging.DEBUG,
    format=log_format,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("omomatrix.log", mode='w')
    ]
)

logger = logging.getLogger(__name__)

def handle_exception(exc_type, exc_value, exc_traceback):
    """Log unhandled exceptions."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = handle_exception

def async_event_loop(loop):
    """Run asyncio event loop in GTK main loop.
    
    Args:
        loop: asyncio event loop
    """
    try:
        # Run one step of the loop without blocking
        loop.run_until_complete(asyncio.sleep(0))
    except Exception as e:
        logger.error(f"Event loop error: {e}")
    
    return True  # Continue calling


def main():
    """Main entry point."""
    logger.info("Starting OMOMatrix...")
    
    # Create application
    app = OMOMatrixApp()
    
    # Load CSS
    try:
        from pathlib import Path
        css_path = Path(__file__).parent / 'gui' / 'style.css'
        css_provider = Gtk.CssProvider()
        css_provider.load_from_path(str(css_path))
        
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(
                display,
                css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
            logger.info(f"Loaded custom CSS from {css_path}")
        else:
            logger.warning("No default display found, skipping CSS")
            
    except Exception as e:
        logger.warning(f"Failed to load CSS: {e}")
    
    # Integrate asyncio with GLib main loop
    GLib.timeout_add(1, async_event_loop, app.loop)
    
    # Run application
    try:
        exit_status = app.run(sys.argv)
        logger.info(f"OMOMatrix exited with status {exit_status}")
        return exit_status
    except Exception as e:
        logger.critical("Application crashed", exc_info=e)
        return 1


if __name__ == '__main__':
    sys.exit(main())
