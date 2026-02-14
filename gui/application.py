"""
Main GTK4 Application for OMOMatrix.
"""

import asyncio
import logging
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, GLib, Gio

from matrix.client import MatrixClient
from matrix.storage import CredentialStorage
from matrix.avatar_manager import AvatarManager
from .login_window import LoginWindow
from .main_window import MainWindow

logger = logging.getLogger(__name__)


class OMOMatrixApp(Adw.Application):
    """Main application class."""
    
    def __init__(self):
        """Initialize the application."""
        super().__init__(
            application_id='org.omomatrix.OMOMatrixClient',
            flags=Gio.ApplicationFlags.NON_UNIQUE
        )
        
        self.matrix_client = MatrixClient()
        self.storage = CredentialStorage()
        self.avatar_manager = AvatarManager()
        self.main_window = None
        self.login_window = None
        
        # Event loop for asyncio
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
    
    def do_activate(self):
        """Called when the application is activated."""
        logger.info("Application activated")
        # Check if we have stored credentials
        if self.storage.has_credentials():
            # Try to restore session
            logger.info("Credentials found, restoring session")
            self.hold()  # Keep app alive during async operation
            self.loop.create_task(self._restore_session())
        else:
            # Show login window
            logger.info("No credentials, showing login window")
            self.show_login_window()
    
    async def _restore_session(self):
        """Restore session from stored credentials."""
        logger.info("Attempting to restore session...")
        
        try:
            success = await self.matrix_client.restore_session()
            
            if success:
                logger.info("Session restored successfully")
                self.show_main_window()
            else:
                logger.warning("Failed to restore session, showing login")
                self.show_login_window()
        finally:
            self.release()  # Release hold
    
    def show_login_window(self):
        """Show the login window."""
        logger.info("Displaying login window")
        if self.login_window is None:
            self.login_window = LoginWindow(application=self)
            self.login_window.connect('login-success', self.on_login_success)
        
        self.login_window.set_visible(True)
        self.login_window.present()
    
    def show_main_window(self):
        """Show the main window."""
        logger.info("Displaying main window")
        if self.main_window is None:
            self.main_window = MainWindow(
                application=self,
                matrix_client=self.matrix_client,
                avatar_manager=self.avatar_manager
            )
        
        # Hide login window if visible
        if self.login_window:
            self.login_window.close()
            self.login_window = None
        
        self.main_window.set_visible(True)
        self.main_window.present()
        
        # Start sync loop
        self.loop.create_task(self.matrix_client.start_sync())
    
    def on_login_success(self, _widget):
        """Handle successful login."""
        logger.info("Login successful, showing main window")
        self.show_main_window()
    
    def do_shutdown(self):
        """Called when the application is shutting down."""
        logger.info("Application shutting down")
        
        # Stop sync and close client
        if self.matrix_client:
            try:
                # We can't use create_task here as loop might be stopping
                # But we can try to close if loop is running
                if self.loop.is_running():
                    future = asyncio.run_coroutine_threadsafe(
                        self.matrix_client.close(), 
                        self.loop
                    )
                    # We can't easily wait for it during shutdown without hanging
            except Exception as e:
                logger.error(f"Error during shutdown: {e}")
        
        Adw.Application.do_shutdown(self)
