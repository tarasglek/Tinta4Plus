#!/usr/bin/env python3
"""
Copyright (c) 2025 Jon Cox (joncox123). All rights reserved.

WARNING: This software is provided "AS IS", without any warranty of any kind. It may contain bugs or other defects
that result in data loss, corruption, hardware damage or other issues. Use at your own risk.
It may temporarily or permanently render your hardware inoperable.
It may corrupt or damage the Embedded Controller or eInk T-CON controller in your laptop.
The author is not responsible for any damage, data loss or lost productivity caused by use of this software. 
By downloading and using this software you agree to these terms and acknowledge the risks involved.
"""

"""
ThinkBook Plus Gen 4 IRU E-Ink Control GUI (tkinter version)
Unprivileged GUI that communicates with privileged helper daemon

No root/sudo required for this GUI
Communicates via Unix socket with helper daemon
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import subprocess
import sys
import os
import time
import logging
import webbrowser
import json
import grp
from multiprocessing import Process, Pipe
from datetime import datetime

from event_watcher import watch_events

from HelperClient import HelperClient
from DisplayManager import DisplayManager
from mode_switch import (
    _apply_input_mode,
    ensure_touch_available,
    get_display_state,
    save_orientation_preference,
    switch_to_eink,
    switch_to_oled,
)

class FloatingRefreshButton:
    """Floating refresh button window that stays on top"""

    def __init__(self, parent, on_refresh_callback, logger):
        """Initialize the floating refresh button

        Args:
            parent: Parent tkinter window
            on_refresh_callback: Function to call when button is pressed
            logger: Logger instance
        """
        self.parent = parent
        self.on_refresh_callback = on_refresh_callback
        self.logger = logger

        # Drag state
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._is_dragging = False

        # Create a new top-level window
        self.window = tk.Toplevel(parent)
        self.window.title("")  # Empty title

        # Remove window decorations (titlebar, close button, etc.)
        self.window.overrideredirect(True)

        # Set size to 75x75
        self.window.geometry("75x75")

        # Make window always stay on top
        self.window.attributes('-topmost', True)

        # Make window semi-transparent (0.5 = 50% opacity)
        self.window.attributes('-alpha', 0.5)

        # Position window on left side, halfway down
        # Get screen height to calculate vertical center
        screen_height = self.window.winfo_screenheight()
        y_position = (screen_height // 2) - 37  # Center the 75px button
        x_position = 0  # Left edge of screen

        self.window.geometry(f"75x75+{x_position}+{y_position}")

        # Set window background to light blue
        self.window.config(bg='lightblue')

        # Create the refresh button that fills the entire window
        # Using a unicode circular arrow character as refresh icon
        # Note: highlightthickness=0 removes focus border, bd=0 removes button border
        self.button = tk.Button(
            self.window,
            text="⟳",  # Circular arrow refresh symbol
            font=('TkDefaultFont', 54),  # Scaled down from 72 to fit 75x75
            command=self._on_click,
            relief=tk.FLAT,
            bd=0,
            bg='lightblue',
            activebackground='skyblue',
            highlightthickness=0
        )
        self.button.pack(fill=tk.BOTH, expand=True)

        # Bind hover effects
        self.button.bind("<Enter>", self._on_hover_enter)
        self.button.bind("<Leave>", self._on_hover_leave)

        # Bind drag events
        self.button.bind("<ButtonPress-1>", self._on_drag_start)
        self.button.bind("<B1-Motion>", self._on_drag_motion)
        self.button.bind("<ButtonRelease-1>", self._on_drag_release)

        self.logger.info("Floating refresh button created")

    def _on_click(self):
        """Handle button click (only if not dragging)"""
        if not self._is_dragging:
            self.logger.info("Floating refresh button clicked")
            if self.on_refresh_callback:
                self.on_refresh_callback()

    def _on_drag_start(self, event):
        """Handle start of drag operation"""
        self._drag_start_x = event.x
        self._drag_start_y = event.y
        self._is_dragging = False

    def _on_drag_motion(self, event):
        """Handle drag motion"""
        # Calculate distance moved
        dx = event.x - self._drag_start_x
        dy = event.y - self._drag_start_y

        # If moved more than a few pixels, consider it a drag (not a click)
        if abs(dx) > 3 or abs(dy) > 3:
            self._is_dragging = True

            # Get current window position
            x = self.window.winfo_x() + dx
            y = self.window.winfo_y() + dy

            # Move the window
            self.window.geometry(f"+{x}+{y}")

    def _on_drag_release(self, _event):
        """Handle end of drag operation"""
        # Reset drag flag after a short delay to prevent click from firing
        self.window.after(100, self._reset_drag_flag)

    def _reset_drag_flag(self):
        """Reset the dragging flag"""
        self._is_dragging = False

    def _on_hover_enter(self, event):
        """Handle mouse hover enter"""
        self.button.config(bg='skyblue')
        self.window.config(bg='skyblue')

    def _on_hover_leave(self, event):
        """Handle mouse hover leave"""
        self.button.config(bg='lightblue')
        self.window.config(bg='lightblue')

    def destroy(self):
        """Destroy the floating button window"""
        self.logger.info("Destroying floating refresh button")
        if self.window:
            self.window.destroy()
            self.window = None


class EInkControlGUI:
    # Version
    VERSION = "0.1.0 alpha"

    # Configuration
    SOCKET_PATH = '/run/tinta4plus.sock'
    SOCKET_TIMEOUT = 10.0  # seconds
    CONFIG_DIR = os.path.expanduser("~/.config/Tinta4Plus")
    SETTINGS_FILE = os.path.join(os.path.expanduser("~/.config/Tinta4Plus"), "settings")

    # Display names (ThinkBook Plus Gen 4 has eDP-1=OLED, eDP-2=E-Ink)
    DISPLAY_OLED = "eDP-1"
    DISPLAY_EINK = "eDP-2"

    # E-Ink privacy image (displayed when disabling E-Ink to clear private data)
    # NOTE: must install feh and imv for this to work!
    EINK_DISABLED_IMAGE = "eink-disable.jpg"

    # XFCE theme names
    THEME_HIGH_CONTRAST = "HighContrast"
    THEME_ADWAITA_DARK = "Adwaita-dark"

    """Main GUI application using tkinter"""

    def __init__(self, root, HELPER_SCRIPT, logger):
        self.HELPER_SCRIPT = HELPER_SCRIPT
        self.logger = logger
        self.root = root
        self.root.title("ThinkBook E-Ink Control")
        self.root.geometry("600x700")
        self._set_window_icon()

        # Helper client
        self.helper = HelperClient(logger)

        # Managers
        self.display_mgr = DisplayManager(logger)

        # Brightness timer for debouncing
        self.brightness_timer = None

        # Periodic refresh timer
        self.refresh_timer = None

        # Image viewer process for E-Ink privacy screen
        self.eink_image_process = None

        # Floating refresh button
        self.floating_refresh_button = None

        # Load settings from file (or use defaults)
        settings = self.load_settings()

        # Display scaling (from settings)
        self.display_scale = settings['display_scale']
        self.orientation_rotation = None

        # Live state reconciliation + helper notifications
        self._live_sync_state = {
            "display_mode": None,
            "lid_closed": None,
            "inhibitor_running": False,
            "last_eink_orientation": None,
        }
        self._event_watcher_conn = None
        self._event_watcher_process = None
        self._event_watcher_poll_job = None
        self._lid_inhibitor_process = None

        # Build UI
        self.build_ui()

        # Apply loaded settings to UI controls after they're created
        self.scale_var.set(self.display_scale)
        self.scale_label.config(text=f"{self.display_scale:.2f}")
        self.refresh_period_var.set(settings['refresh_period'])
        self.refresh_period_label.config(text=str(settings['refresh_period']))
        self.autoswitch_theme_var.set(settings['autoswitch_theme'])
        
        # Set up window close handler
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Initialize helper after short delay
        self.root.after(500, self.initialize_helper)

    def load_settings(self):
        """Load settings from configuration file"""
        # Default settings
        defaults = {
            'display_scale': 1.75,
            'refresh_period': 15,
            'autoswitch_theme': True
        }

        if not os.path.exists(self.SETTINGS_FILE):
            self.logger.info(f"Settings file not found, using defaults")
            return defaults

        try:
            with open(self.SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
            self.logger.info(f"Loaded settings from {self.SETTINGS_FILE}")

            # Merge with defaults to handle missing keys
            for key in defaults:
                if key not in settings:
                    settings[key] = defaults[key]

            return settings

        except Exception as e:
            self.logger.error(f"Failed to load settings: {e}")
            return defaults

    def save_settings(self):
        """Save current settings to configuration file"""
        try:
            # Ensure config directory exists
            os.makedirs(self.CONFIG_DIR, exist_ok=True)

            # Gather current settings
            settings = {
                'display_scale': self.display_scale,
                'refresh_period': self.refresh_period_var.get(),
                'autoswitch_theme': self.autoswitch_theme_var.get()
            }

            # Write to file
            with open(self.SETTINGS_FILE, 'w') as f:
                json.dump(settings, f, indent=2)

            self.logger.info(f"Saved settings to {self.SETTINGS_FILE}")

        except Exception as e:
            self.logger.error(f"Failed to save settings: {e}")

    def build_ui(self):
        """Build the tkinter user interface"""

        # Configure style
        style = ttk.Style()
        style.theme_use('clam')  # Modern look

        # Main frame with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        
        row = 0

        # Status bar
        self.status_var = tk.StringVar(value="Status: Initializing...")
        status_label = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_label.grid(row=row, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        row += 1

        # Secure Boot status indicator
        self.secureboot_frame = tk.Frame(main_frame, bg='gray', relief=tk.RIDGE, bd=2)
        self.secureboot_frame.grid(row=row, column=0, sticky=tk.W, pady=(0, 10))

        self.secureboot_label = tk.Label(self.secureboot_frame, text="Secure Boot: Unknown",
                                         bg='gray', fg='white', font=('TkDefaultFont', 9, 'bold'),
                                         padx=10, pady=3)
        self.secureboot_label.pack()
        row += 1
        
        # === Display Control Section ===
        display_frame = ttk.LabelFrame(main_frame, text="Display Control", padding="10")
        display_frame.grid(row=row, column=0, sticky=(tk.W, tk.E), pady=5)
        display_frame.columnconfigure(0, weight=1)
        display_frame.columnconfigure(1, weight=1)
        row += 1
        
        # E-Ink toggle control
        eink_toggle_frame = ttk.Frame(display_frame)
        eink_toggle_frame.grid(row=0, column=0, columnspan=2, padx=5, pady=5, sticky=(tk.W, tk.E))

        self.eink_enabled_var = tk.BooleanVar(value=False)
        self.eink_toggle_btn = tk.Button(eink_toggle_frame, text="eInk Disabled",
                                         bg="yellow", fg="black",
                                         font=('TkDefaultFont', 10, 'bold'),
                                         relief=tk.RAISED, bd=3,
                                         command=self.on_eink_toggled,
                                         activebackground="#b8aa00",  # Darker yellow
                                         activeforeground="black",
                                         padx=20, pady=10)
        self.eink_toggle_btn.pack(expand=True, fill=tk.X)

        # Bind hover effects for eInk toggle button
        self.eink_toggle_btn.bind("<Enter>", lambda e: self._on_eink_btn_hover(e, True))
        self.eink_toggle_btn.bind("<Leave>", lambda e: self._on_eink_btn_hover(e, False))

        # Refresh button
        self.btn_refresh = ttk.Button(display_frame, text="Refresh eInk (Clear Ghosts)",
                                      command=self.on_refresh_full,
                                      state='disabled')
        self.btn_refresh.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky=(tk.W, tk.E))

        # Orientation button
        self.orientation_toggle_btn = ttk.Button(
            display_frame,
            text="Orientation: Landscape",
            command=self.on_orientation_toggled,
            state='disabled',
        )
        self.orientation_toggle_btn.grid(row=2, column=0, columnspan=2, padx=5, pady=5, sticky=(tk.W, tk.E))

        # Mode buttons (Dynamic and Reading)
        mode_frame = ttk.Frame(display_frame)
        mode_frame.grid(row=3, column=0, columnspan=2, padx=5, pady=5, sticky=(tk.W, tk.E))
        mode_frame.columnconfigure(0, weight=1)
        mode_frame.columnconfigure(1, weight=1)

        self.btn_set_dynamic = ttk.Button(mode_frame, text="Set Dynamic",
                                          command=self.on_set_dynamic,
                                          state='disabled')
        self.btn_set_dynamic.grid(row=0, column=0, padx=(0, 2), sticky=(tk.W, tk.E))

        self.btn_set_reading = ttk.Button(mode_frame, text="Set Reading",
                                          command=self.on_set_reading,
                                          state='disabled')
        self.btn_set_reading.grid(row=0, column=1, padx=(2, 0), sticky=(tk.W, tk.E))

        # Refresh period slider
        refresh_period_label = ttk.Label(display_frame, text="Refresh period (s):")
        refresh_period_label.grid(row=4, column=0, sticky=tk.W, padx=5, pady=5)

        refresh_period_container = ttk.Frame(display_frame)
        refresh_period_container.grid(row=4, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        refresh_period_container.columnconfigure(0, weight=1)

        self.refresh_period_var = tk.IntVar(value=15)
        self.refresh_period_slider = ttk.Scale(refresh_period_container, from_=0, to=60,
                                              orient=tk.HORIZONTAL,
                                              variable=self.refresh_period_var,
                                              command=self.on_refresh_period_changed)
        self.refresh_period_slider.grid(row=0, column=0, sticky=(tk.W, tk.E))

        self.refresh_period_label = ttk.Label(refresh_period_container, text="15")
        self.refresh_period_label.grid(row=0, column=1, padx=(5, 0))

        # Display scale slider
        scale_label = ttk.Label(display_frame, text="Display Scale:")
        scale_label.grid(row=5, column=0, sticky=tk.W, padx=5, pady=5)

        scale_container = ttk.Frame(display_frame)
        scale_container.grid(row=5, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)

        # Autoswitch theme checkbox
        self.autoswitch_theme_var = tk.BooleanVar(value=True)
        self.autoswitch_theme_checkbox = ttk.Checkbutton(
            display_frame,
            text="Autoswitch theme (HighContrast ↔ Adwaita-dark)",
            variable=self.autoswitch_theme_var,
            command=self.on_autoswitch_theme_changed
        )
        self.autoswitch_theme_checkbox.grid(row=6, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)
        scale_container.columnconfigure(0, weight=1)

        self.scale_var = tk.DoubleVar(value=1.75)
        self.scale_slider = ttk.Scale(scale_container, from_=1.0, to=2.0,
                                     orient=tk.HORIZONTAL,
                                     variable=self.scale_var,
                                     command=self.on_scale_changed)
        self.scale_slider.grid(row=0, column=0, sticky=(tk.W, tk.E))

        self.scale_label = ttk.Label(scale_container, text="1.75")
        self.scale_label.grid(row=0, column=1, padx=(5, 0))

        # === Frontlight Control Section ===
        frontlight_frame = ttk.LabelFrame(main_frame, text="Frontlight Control", padding="10")
        frontlight_frame.grid(row=row, column=0, sticky=(tk.W, tk.E), pady=5)
        frontlight_frame.columnconfigure(1, weight=1)
        row += 1

        # Brightness slider (frontlight auto-enables with eInk)
        ttk.Label(frontlight_frame, text="Brightness (0-8):").grid(row=0, column=0,
                                                                    sticky=tk.W, padx=5, pady=5)

        brightness_container = ttk.Frame(frontlight_frame)
        brightness_container.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        brightness_container.columnconfigure(0, weight=1)

        self.brightness_var = tk.IntVar(value=4)
        self.brightness_scale = ttk.Scale(brightness_container, from_=0, to=8,
                                         orient=tk.HORIZONTAL,
                                         variable=self.brightness_var,
                                         command=self.on_brightness_changed)
        self.brightness_scale.grid(row=0, column=0, sticky=(tk.W, tk.E))

        self.brightness_label = ttk.Label(brightness_container, text="4")
        self.brightness_label.grid(row=0, column=1, padx=(5, 0))

        # Warning label for Secure Boot (initially hidden)
        self.secure_boot_warning = ttk.Label(frontlight_frame,
                                             text="⚠ Secure Boot is enabled. Frontlight controls disabled.\nPlease disable Secure Boot in BIOS (Press ENTER during boot).",
                                             foreground='red', font=('TkDefaultFont', 9, 'bold'))
        # Don't grid it yet - will be shown if needed

        # === Activity Log Section ===
        log_frame = ttk.LabelFrame(main_frame, text="Activity Log", padding="10")
        log_frame.grid(row=row, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        main_frame.rowconfigure(row, weight=1)
        row += 1
        
        # Scrolled text widget
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, wrap=tk.WORD,
                                                   state=tk.DISABLED, font=('Courier', 9))
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure text tags for colored output
        self.log_text.tag_config('success', foreground='green')
        self.log_text.tag_config('error', foreground='red')
        self.log_text.tag_config('info', foreground='blue')

        # Version and Buy Me A Coffee button row
        version_coffee_frame = ttk.Frame(main_frame)
        version_coffee_frame.grid(row=row, column=0, sticky=(tk.W, tk.E), padx=10, pady=5)
        version_coffee_frame.columnconfigure(0, weight=1)  # Allow space to expand between elements

        # Version label (left side)
        version_label = ttk.Label(version_coffee_frame, text=f"Version {self.VERSION}",
                                 font=('TkDefaultFont', 8))
        version_label.grid(row=0, column=0, sticky=tk.W)

        # Buy Me A Coffee button (right side)
        self.coffee_btn = tk.Button(version_coffee_frame, text="Buy Me A Coffee",
                                   bg="yellow", fg="black",
                                   font=('TkDefaultFont', 8),
                                   relief=tk.RAISED, bd=2,
                                   command=self.on_buy_coffee,
                                   activebackground="#b8aa00",  # Darker yellow
                                   activeforeground="black",
                                   padx=8, pady=4)
        self.coffee_btn.grid(row=0, column=1, sticky=tk.E)

        # Bind hover effects for coffee button
        self.coffee_btn.bind("<Enter>", lambda e: self.coffee_btn.config(bg="#b8aa00"))
        self.coffee_btn.bind("<Leave>", lambda e: self.coffee_btn.config(bg="yellow"))

        # Initial log message
        self.log_message("Application started")
    
    def log_message(self, message, level='info'):
        """Add a message to the log view and logger"""
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Determine tag based on message content or level
        if '✓' in message or 'success' in message.lower():
            tag = 'success'
            logger_level = 'info'
        elif '✗' in message or 'error' in message.lower() or 'failed' in message.lower():
            tag = 'error'
            logger_level = 'error'
        else:
            tag = level
            logger_level = level

        log_line = f"[{timestamp}] {message}\n"

        # Insert into text widget
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, log_line, tag)
        self.log_text.see(tk.END)  # Auto-scroll
        self.log_text.config(state=tk.DISABLED)

        # Also log via logger
        if logger_level == 'error':
            self.logger.error(message)
        elif logger_level == 'warning':
            self.logger.warning(message)
        else:
            self.logger.info(message)
    
    def update_status(self, message, error=False):
        """Update status bar"""
        self.status_var.set(f"Status: {message}")
    
    def show_error_dialog(self, message):
        """Show error dialog"""
        messagebox.showerror("Error", message)
    
    def show_info_dialog(self, message):
        """Show info dialog"""
        messagebox.showinfo("Information", message)

    def _set_window_icon(self):
        """Set window icon from common system icon paths if available."""
        icon_candidates = [
            "/usr/share/icons/elementary-xfce/apps/48/preferences-desktop-display.png",
            "/usr/share/icons/HighContrast/48x48/apps/preferences-desktop-display.png",
            "/usr/share/icons/HighContrast/32x32/apps/preferences-desktop-display.png",
            "/usr/share/icons/hicolor/48x48/status/display-brightness.png",
        ]

        for icon_path in icon_candidates:
            if os.path.exists(icon_path):
                try:
                    icon_image = tk.PhotoImage(file=icon_path)
                    self.root.iconphoto(True, icon_image)
                    self.root._tinta_icon_image = icon_image
                    self.logger.info(f"Using window icon: {icon_path}")
                    return
                except Exception:
                    continue
    
    def _get_script_dir(self):
        return os.path.dirname(os.path.abspath(__file__))

    def _get_installer_path(self):
        return os.path.join(self._get_script_dir(), 'scripts', 'install-systemd-helper-root.sh')

    def _needs_helper_install_or_upgrade(self):
        """Use installer --check mode to detect drift or missing setup."""
        installer = self._get_installer_path()
        if not os.path.exists(installer):
            return True, f"Installer not found: {installer}"

        user_name = os.environ.get('SUDO_USER') or os.environ.get('USER') or 'taras'
        command = [installer, '--check', '--source-dir', self._get_script_dir(), '--user', user_name]
        result = subprocess.run(command, capture_output=True, text=True)

        if result.returncode == 0:
            return False, None

        if result.returncode == 1:
            return True, None

        details = (result.stderr or result.stdout or '').strip()
        return True, details or f"Check failed with exit code {result.returncode}"

    def _is_current_process_in_helper_group(self):
        """Return True when this running process has tinta4plus group in its group list."""
        try:
            helper_group = grp.getgrnam('tinta4plus')
        except KeyError:
            return False

        return helper_group.gr_gid in os.getgroups()

    def _run_helper_installer(self):
        installer = self._get_installer_path()
        if not os.path.exists(installer):
            return False, f"Installer not found: {installer}"

        user_name = os.environ.get('SUDO_USER') or os.environ.get('USER') or 'taras'
        command = ['pkexec', installer, '--user', user_name, '--source-dir', self._get_script_dir()]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            details = (result.stderr or result.stdout or '').strip()
            return False, details or f"Installer failed with exit code {result.returncode}"

        return True, None

    def _prompt_install_or_upgrade(self):
        needs_install, check_error = self._needs_helper_install_or_upgrade()
        if check_error:
            self.log_message(f"WARNING: Helper check failed: {check_error}", level='warning')

        if not needs_install and self._is_current_process_in_helper_group():
            return True

        if needs_install:
            prompt = (
                "Tinta4Plus needs to install or update the system helper service.\n\n"
                "This is a one-time privileged action using pkexec.\n"
                "Install now?"
            )
        else:
            prompt = (
                "Your user is not active in the 'tinta4plus' group in this session.\n\n"
                "Tinta4Plus can refresh permissions via installer now, then you'll need to re-login\n"
                "and restart the app. Continue?"
            )

        install_now = messagebox.askyesno("Install privileged helper", prompt)
        if not install_now:
            return False

        self.update_status("Installing/updating helper service (password required)...")
        self.log_message("Installing/updating helper service via pkexec...")
        ok, error = self._run_helper_installer()
        if not ok:
            self.log_message(f"ERROR: Helper install failed - {error}", level='error')
            self.show_error_dialog(f"Helper install failed:\n\n{error}")
            return False

        if not self._is_current_process_in_helper_group():
            self.show_info_dialog(
                "Helper service installed/updated.\n\n"
                "You must log out and log back in (or run 'newgrp tinta4plus' from a shell)\n"
                "then restart Tinta4Plus."
            )
            self.log_message("Group membership update requires re-login before reconnect", level='warning')
            return False

        self.log_message("✓ Helper service installed/updated")
        return True

    def initialize_helper(self):
        """Initialize connection to systemd socket-activated helper daemon."""
        if not self._prompt_install_or_upgrade():
            self.update_status("Helper service not installed")
            return

        try:
            if self.helper.connect(self.SOCKET_PATH, timeout=self.SOCKET_TIMEOUT):
                self.update_status("Connected to helper daemon")
                self.log_message("Connected to helper daemon")
                self.sync_ui_from_display_state()
                EInkControlGUI.sync_orientation_from_display_state(self)
                EInkControlGUI._start_event_watcher(self)
                if getattr(self, "_event_watcher_poll_job", None) is None:
                    EInkControlGUI._schedule_event_watcher_poll(self)
                self.root.after(500, self.check_ec_status)
                return
        except Exception as e:
            self.log_message(f"Failed to connect to helper socket: {e}", level='error')

        self.update_status("Failed to connect to helper daemon", error=True)
        self.show_error_dialog(
            "Could not connect to helper daemon at /run/tinta4plus.sock.\n\n"
            "Run installer or check:\n"
            "  systemctl status tinta4plus-helper.socket"
        )

    def attempt_helper_restart(self):
        """Attempt to reconnect to systemd socket-activated helper."""
        self.log_message("Attempting to reconnect to helper daemon...")

        try:
            if self.helper.is_connected():
                self.helper.disconnect()
        except Exception as e:
            self.logger.debug(f"Error during disconnect: {e}")

        time.sleep(0.5)

        try:
            if self.helper.connect(self.SOCKET_PATH, timeout=self.SOCKET_TIMEOUT):
                self.log_message("✓ Reconnected to helper daemon")
                self.update_status("Reconnected to helper daemon")
                self.sync_ui_from_display_state()
                EInkControlGUI.sync_orientation_from_display_state(self)
                EInkControlGUI._start_event_watcher(self)
                if getattr(self, "_event_watcher_poll_job", None) is None:
                    EInkControlGUI._schedule_event_watcher_poll(self)
                self.root.after(500, self.check_ec_status)
                return
        except Exception as e:
            self.logger.debug(f"Failed to reconnect helper socket: {e}")

        self.log_message("ERROR: Helper reconnection failed", level='error')
        self.update_status("Helper disconnected", error=True)
        self.show_error_dialog(
            "Lost connection to helper daemon.\n\n"
            "Check service status:\n"
            "  systemctl status tinta4plus-helper.socket\n"
            "  systemctl status tinta4plus-helper.service"
        )
    
    def check_ec_status(self):
        """Check EC access status and disable frontlight controls if Secure Boot enabled"""
        try:
            response = self.helper.send_command('get-ec-status')

            if response and response.get('success'):
                ec_status = response.get('ec_status', {})

                # Update Secure Boot status indicator
                if ec_status.get('secure_boot_enabled'):
                    self.secureboot_label.config(text="Secure Boot: ON", bg='red')
                    self.secureboot_frame.config(bg='red')
                else:
                    self.secureboot_label.config(text="Secure Boot: OFF", bg='green')
                    self.secureboot_frame.config(bg='green')

                if ec_status.get('secure_boot_enabled') or not ec_status.get('available'):
                    # Secure Boot enabled or EC not available - disable frontlight controls
                    error_msg = ec_status.get('error_message', 'EC access not available')
                    self.log_message(f"⚠ {error_msg}", level='error')

                    # Show warning label
                    self.secure_boot_warning.grid(row=1, column=0, columnspan=2,
                                                 sticky=(tk.W, tk.E), padx=5, pady=10)

                    # Disable brightness slider (frontlight checkbox is already always disabled)
                    self.brightness_scale.config(state='disabled')

                    # Show dialog
                    if ec_status.get('secure_boot_enabled'):
                        messagebox.showwarning(
                            "Secure Boot Enabled",
                            "Secure Boot is currently enabled in your BIOS.\n\n"
                            "Frontlight controls require direct hardware access which is blocked by Secure Boot.\n\n"
                            "To enable frontlight controls:\n"
                            "1. Reboot your computer\n"
                            "2. Press ENTER (or F2) during boot to enter BIOS\n"
                            "3. Navigate to Security → Secure Boot\n"
                            "4. Set Secure Boot to 'Disabled'\n"
                            "5. Save and exit (F10)\n\n"
                            "Note: E-Ink display controls will continue to work normally."
                        )
                    else:
                        self.log_message(f"EC access not available: {error_msg}", level='error')
                else:
                    self.log_message("EC access verified - frontlight controls enabled")
                    self.brightness_scale.config(state='normal')
                    self.secure_boot_warning.grid_remove()
                    # Sync GUI with actual EC state
                    self.sync_frontlight_state()

        except Exception as e:
            self.logger.error(f"Failed to check EC status: {e}")
            self.log_message(f"Warning: Could not verify EC status: {e}", level='error')

    def sync_frontlight_state(self):
        """Query EC and update GUI to match actual frontlight state"""
        try:
            response = self.helper.send_command('get-frontlight-state')

            if response and response.get('success'):
                brightness = response.get('brightness_level')

                if brightness is not None:
                    self.brightness_var.set(brightness)
                    self.brightness_label.config(text=str(brightness))
                    self.log_message(f"Synced brightness level: {brightness}")

        except Exception as e:
            self.logger.warning(f"Failed to sync frontlight state: {e}")
            self.log_message(f"Warning: Could not sync frontlight state from EC", level='error')


    def execute_helper_command(self, command, **params):
        """Execute a command via helper and handle response with retry logic"""
        if not self.helper.is_connected():
            error_msg = "Not connected to helper daemon"
            last_error = self.helper.get_last_error()
            if last_error:
                error_msg += f"\n\nLast error: {last_error}"
            self.show_error_dialog(error_msg)
            return None

        try:
            response = self.helper.send_command(command, **params)

            if response and response.get('success'):
                message = response.get('message', 'Command completed')
                self.log_message(f"✓ {message}")

                # Log readback value if present
                if 'readback' in response:
                    self.log_message(f"  Readback value: {response['readback']}")

                return response
            else:
                error = response.get('error', 'Unknown error') if response else 'No response'
                self.log_message(f"✗ Command '{command}' failed: {error}", level='error')
                self.show_error_dialog(f"Command '{command}' failed:\n\n{error}")
                return None

        except RuntimeError as e:
            # Connection errors - trigger reconnection
            self.log_message(f"✗ Connection error during '{command}': {e}", level='error')
            self.update_status("Connection error - attempting restart...", error=True)
            self.attempt_helper_restart()
            self.show_error_dialog(f"Connection error:\n\n{e}\n\nAttempting to reconnect...")
            return None
        
        except Exception as e:
            self.log_message(f"✗ Command '{command}' error: {e}", level='error')
            self.logger.error(f"Command error details: {e}", exc_info=True)
            self.show_error_dialog(f"Command '{command}' error:\n\n{e}")
            return None
    
    def _ensure_floating_refresh_button(self):
        if self.floating_refresh_button:
            return

        self.log_message("Creating floating refresh button...")
        self.floating_refresh_button = FloatingRefreshButton(self.root, self.on_refresh_full, self.logger)

    def _destroy_floating_refresh_button(self):
        if not self.floating_refresh_button:
            return

        self.log_message("Destroying floating refresh button...")
        self.floating_refresh_button.destroy()
        self.floating_refresh_button = None

    def _orientation_label_from_rotation(self, rotation):
        return "Portrait" if rotation == "left" else "Landscape"

    def sync_orientation_from_display_state(self):
        button = getattr(self, "orientation_toggle_btn", None)
        if button is None:
            return None

        active_display = self.display_mgr.get_active_display()
        if not active_display:
            button.config(state='disabled')
            self.log_message("⚠ No active display for orientation sync", level='warning')
            return None

        rotation = self.display_mgr.get_display_rotation(active_display)
        if rotation not in ("normal", "left"):
            button.config(state='disabled')
            self.log_message(f"⚠ Unsupported live rotation '{rotation}' on {active_display}", level='warning')
            return None

        self.orientation_rotation = rotation
        label = EInkControlGUI._orientation_label_from_rotation(self, rotation)
        button.config(text=f"Orientation: {label}", state='normal')
        return rotation

    def on_orientation_toggled(self):
        active_display = self.display_mgr.get_active_display()
        if not active_display:
            self.log_message("⚠ Cannot rotate: no active display", level='error')
            return

        current_rotation = self.display_mgr.get_display_rotation(active_display)
        if current_rotation not in ("normal", "left"):
            current_rotation = self.orientation_rotation

        if current_rotation not in ("normal", "left"):
            self.log_message("⚠ Cannot rotate: unknown current orientation", level='error')
            return

        target_rotation = "left" if current_rotation == "normal" else "normal"
        if not self.display_mgr.set_display_rotation(active_display, target_rotation):
            self.log_message("⚠ Failed to apply orientation rotation", level='error')
            return

        confirmed_rotation = self.display_mgr.get_display_rotation(active_display)
        if confirmed_rotation not in ("normal", "left"):
            self.log_message("⚠ Rotation applied but live orientation could not be confirmed", level='error')
            return

        self.orientation_rotation = confirmed_rotation
        label = EInkControlGUI._orientation_label_from_rotation(self, confirmed_rotation)
        self.orientation_toggle_btn.config(text=f"Orientation: {label}", state='normal')

        mode = get_display_state(self.display_mgr).get("mode")
        remap_target = mode if mode in ("eink", "oled") else None
        if remap_target is None or not _apply_input_mode(self.logger, remap_target):
            self.log_message("⚠ Rotation succeeded but input remap failed", level='warning')
        else:
            ensure_touch_available(self.logger, remap_target)

        save_orientation_preference(self.logger, confirmed_rotation)
        self.update_status(f"Orientation set to {label}")
        self.log_message(f"✓ Orientation set to {label}")

    def sync_ui_from_display_state(self):
        state = get_display_state(self.display_mgr)
        mode = state["mode"]

        if mode == "eink":
            self.eink_enabled_var.set(True)
            self.eink_toggle_btn.config(text="eInk Enabled", bg="green", fg="white")
            self.btn_refresh.config(state='normal')
            self.btn_set_dynamic.config(state='normal')
            self.btn_set_reading.config(state='normal')
            self._start_refresh_timer()
            self._ensure_floating_refresh_button()
            self.update_status("E-Ink display enabled")
            EInkControlGUI.sync_orientation_from_display_state(self)
            return state

        self.eink_enabled_var.set(False)
        self.eink_toggle_btn.config(text="eInk Disabled", bg="yellow", fg="black")
        self.btn_refresh.config(state='disabled')
        self.btn_set_dynamic.config(state='disabled')
        self.btn_set_reading.config(state='disabled')
        self._stop_refresh_timer()
        self._destroy_floating_refresh_button()

        if mode == "oled":
            self.update_status("E-Ink display disabled")
        else:
            self.log_message(f"⚠ Detected display mode '{mode}', disabling eInk UI controls", level='warning')
            self.update_status("Display state uncertain - controls disabled")

        EInkControlGUI.sync_orientation_from_display_state(self)
        return state

    def _read_live_lid_state(self):
        candidates = [
            "/proc/acpi/button/lid/LID0/state",
            "/proc/acpi/button/lid/LID/state",
        ]
        for path in candidates:
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    text = handle.read().lower()
                if "closed" in text:
                    return True
                if "open" in text:
                    return False
            except FileNotFoundError:
                continue
            except Exception as e:
                self.logger.debug(f"Failed reading lid state from {path}: {e}")

        return False

    def _start_lid_inhibitor(self):
        process = getattr(self, "_lid_inhibitor_process", None)
        if process is not None and process.poll() is None:
            return

        command = [
            "systemd-inhibit",
            "--what=handle-lid-switch",
            "--who=Tinta4Plus",
            "--why=Keep E-Ink active while lid events are managed by GUI",
            "sleep",
            "infinity",
        ]

        try:
            self._lid_inhibitor_process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.log_message("Lid-close suspend inhibitor enabled")
        except Exception as e:
            self._lid_inhibitor_process = None
            self.log_message(f"Failed to start lid-close inhibitor: {e}", level='warning')

    def _stop_lid_inhibitor(self):
        process = getattr(self, "_lid_inhibitor_process", None)
        if process is None:
            return

        try:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=1.0)
            self.log_message("Lid-close suspend inhibitor disabled")
        except Exception as e:
            self.log_message(f"Failed to stop lid-close inhibitor cleanly: {e}", level='warning')
        finally:
            self._lid_inhibitor_process = None

    def _reconcile_from_live_state(self):
        state = get_display_state(self.display_mgr)
        mode = state.get("mode", "unknown")
        lid_closed = bool(EInkControlGUI._read_live_lid_state(self))

        if not hasattr(self, "_live_sync_state") or not isinstance(self._live_sync_state, dict):
            self._live_sync_state = {
                "display_mode": None,
                "lid_closed": None,
                "inhibitor_running": False,
                "last_eink_orientation": None,
            }

        if mode == "eink":
            EInkControlGUI._start_lid_inhibitor(self)
        else:
            EInkControlGUI._stop_lid_inhibitor(self)

        previous_mode = self._live_sync_state.get("display_mode")
        previous_lid_closed = self._live_sync_state.get("lid_closed")

        active_display = self.display_mgr.get_active_display()
        if active_display:
            rotation = self.display_mgr.get_display_rotation(active_display)
            if rotation in ("normal", "left"):
                self._live_sync_state["last_eink_orientation"] = rotation

            if mode == "eink":
                desired_rotation = "left" if lid_closed else "normal"
                no_effective_change = (
                    previous_mode == mode
                    and previous_lid_closed == lid_closed
                    and rotation == desired_rotation
                    and self._live_sync_state.get("last_eink_orientation") == desired_rotation
                )

                if not no_effective_change and rotation != desired_rotation:
                    if self.display_mgr.set_display_rotation(active_display, desired_rotation):
                        confirmed_rotation = self.display_mgr.get_display_rotation(active_display)
                        if confirmed_rotation in ("normal", "left"):
                            self._live_sync_state["last_eink_orientation"] = confirmed_rotation
                        else:
                            confirmed_rotation = desired_rotation
                            self._live_sync_state["last_eink_orientation"] = confirmed_rotation

                        if _apply_input_mode(self.logger, "eink"):
                            ensure_touch_available(self.logger, "eink")
                        else:
                            self.log_message("⚠ Lid-driven rotation succeeded but input remap failed", level='warning')

                        save_orientation_preference(self.logger, confirmed_rotation)
                    else:
                        self.log_message("⚠ Failed to apply lid-driven E-Ink rotation", level='warning')

        process = getattr(self, "_lid_inhibitor_process", None)
        inhibitor_running = bool(process is not None and process.poll() is None)

        self._live_sync_state["display_mode"] = mode
        self._live_sync_state["lid_closed"] = lid_closed
        self._live_sync_state["inhibitor_running"] = inhibitor_running

        # GUI is still updated from live state on Tk thread.
        self.sync_ui_from_display_state()
        return dict(self._live_sync_state)

    def _start_event_watcher(self):
        if getattr(self, "_event_watcher_process", None):
            return

        parent_conn, child_conn = Pipe(duplex=False)
        process = Process(target=watch_events, args=(child_conn,), daemon=True)
        process.start()
        child_conn.close()

        self._event_watcher_conn = parent_conn
        self._event_watcher_process = process

    def _stop_event_watcher(self):
        conn = getattr(self, "_event_watcher_conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            self._event_watcher_conn = None

        process = getattr(self, "_event_watcher_process", None)
        if process is not None:
            try:
                if process.is_alive():
                    process.terminate()
                process.join(timeout=1.0)
            except Exception as e:
                self.logger.debug(f"Failed stopping event watcher process: {e}")
            self._event_watcher_process = None

    def _drain_event_watcher_notifications(self):
        conn = getattr(self, "_event_watcher_conn", None)
        if conn is None:
            return

        while conn.poll():
            message = conn.recv()
            event_type, payload = message if isinstance(message, tuple) and len(message) == 2 else (None, None)
            if event_type in ("lid", "randr"):
                self.root.after(0, self._reconcile_from_live_state)
                continue
            if event_type == "error":
                self.log_message(f"Event watcher error: {payload}", level='error')

    def _schedule_event_watcher_poll(self):
        EInkControlGUI._drain_event_watcher_notifications(self)
        self._event_watcher_poll_job = self.root.after(250, lambda: EInkControlGUI._schedule_event_watcher_poll(self))

    # === Event Handlers ===
    
    def on_eink_toggled(self):
        """Handle E-Ink display toggle with shared switch logic."""
        enabling = not self.eink_enabled_var.get()

        if enabling:
            ok = switch_to_eink(
                self.display_mgr,
                self.helper,
                self.logger,
                scale=self.display_scale,
                autoswitch_theme=self.autoswitch_theme_var.get(),
                enable_frontlight=True,
                brightness_level=self.brightness_var.get(),
            )
            if ok:
                self.sync_ui_from_display_state()
            else:
                self.log_message("⚠ Failed to switch to E-Ink", level='error')
            return

        ok = switch_to_oled(
            self.display_mgr,
            self.helper,
            self.logger,
            scale=self.display_scale,
            autoswitch_theme=self.autoswitch_theme_var.get(),
            script_dir=os.path.dirname(os.path.abspath(__file__)),
        )
        if ok:
            self.sync_ui_from_display_state()
        else:
            self.log_message("⚠ Failed to switch to OLED", level='error')
    
    def on_refresh_full(self):
        """Perform full E-Ink refresh"""
        self.log_message("Performing full E-Ink refresh (clearing ghosting)...")
        self.update_status("Refreshing E-Ink display...")
        response = self.execute_helper_command('refresh-eink')
        if response:
            self.update_status("E-Ink refresh complete")

    def on_set_dynamic(self):
        """Set E-Ink to Dynamic Mode (fast refresh)"""
        self.log_message("Setting E-Ink to Dynamic Mode (fast refresh)...")
        self.update_status("Setting Dynamic Mode...")
        response = self.execute_helper_command('set-dynamic')
        if response:
            self.update_status("E-Ink set to Dynamic Mode")

    def on_set_reading(self):
        """Set E-Ink to Reading Mode (high-quality refresh)"""
        self.log_message("Setting E-Ink to Reading Mode (high-quality refresh)...")
        self.update_status("Setting Reading Mode...")
        response = self.execute_helper_command('set-reading')
        if response:
            self.update_status("E-Ink set to Reading Mode")

    def on_brightness_changed(self, value):
        """Handle brightness slider change"""
        level = int(float(value))
        self.brightness_label.config(text=str(level))
        
        # Debounce: use timer to avoid too many commands while dragging
        if self.brightness_timer:
            self.root.after_cancel(self.brightness_timer)
        
        self.brightness_timer = self.root.after(300, self._set_brightness, level)
    
    def _set_brightness(self, level):
        """Actually set the brightness after debounce"""
        self.log_message(f"Setting brightness to level {level}...")
        response = self.execute_helper_command('set-brightness', level=level)

        if response:
            self.update_status(f"Brightness set to {level}")

        self.brightness_timer = None

    def on_scale_changed(self, value):
        """Handle display scale slider change"""
        # Round to nearest 0.05
        scale = round(float(value) / 0.05) * 0.05
        self.scale_var.set(scale)
        self.display_scale = scale
        self.scale_label.config(text=f"{scale:.2f}")
        self.log_message(f"Display scale set to {scale:.2f}x (will apply on next display switch)")

        # Save settings
        self.save_settings()

    def on_refresh_period_changed(self, value):
        """Handle refresh period slider change"""
        # Round to nearest 5 seconds
        period = int(round(float(value) / 5.0) * 5)
        self.refresh_period_var.set(period)
        self.refresh_period_label.config(text=str(period))

        # Restart the refresh timer if eInk is active
        if self.eink_enabled_var.get():
            self._start_refresh_timer()
            if period == 0:
                self.log_message("Periodic refresh disabled")
            else:
                self.log_message(f"Periodic refresh set to {period}s")

        # Save settings
        self.save_settings()

    def on_autoswitch_theme_changed(self):
        """Handle autoswitch theme checkbox change"""
        enabled = self.autoswitch_theme_var.get()
        if enabled:
            self.log_message("Theme auto-switching enabled")
        else:
            self.log_message("Theme auto-switching disabled")

        # Save settings
        self.save_settings()

    def _start_refresh_timer(self):
        """Start or restart the periodic refresh timer"""
        # Cancel existing timer if any
        if self.refresh_timer:
            self.root.after_cancel(self.refresh_timer)
            self.refresh_timer = None

        # Get current period
        period = self.refresh_period_var.get()

        # Only start timer if period > 0 and eInk is active
        if period > 0 and self.eink_enabled_var.get():
            self.refresh_timer = self.root.after(period * 1000, self._periodic_refresh)
            self.logger.info(f"Started periodic refresh timer ({period}s)")

    def _stop_refresh_timer(self):
        """Stop the periodic refresh timer"""
        if self.refresh_timer:
            self.root.after_cancel(self.refresh_timer)
            self.refresh_timer = None
            self.logger.info("Stopped periodic refresh timer")

    def _periodic_refresh(self):
        """Execute a periodic refresh and reschedule"""
        if self.eink_enabled_var.get():
            self.log_message("Performing periodic refresh...")
            self.execute_helper_command('refresh-eink')

            # Reschedule the next refresh
            period = self.refresh_period_var.get()
            if period > 0:
                self.refresh_timer = self.root.after(period * 1000, self._periodic_refresh)
        else:
            # eInk is no longer active, stop the timer
            self.refresh_timer = None

    def _on_eink_btn_hover(self, event, entering):
        """Handle hover effects for eInk toggle button"""
        if entering:
            # Mouse entering - darken the current color
            if self.eink_enabled_var.get():
                # Currently green (enabled) - use darker green
                self.eink_toggle_btn.config(bg="#006400")  # Dark green
            else:
                # Currently yellow (disabled) - use darker yellow
                self.eink_toggle_btn.config(bg="#b8aa00")  # Darker yellow
        else:
            # Mouse leaving - restore original color
            if self.eink_enabled_var.get():
                self.eink_toggle_btn.config(bg="green")
            else:
                self.eink_toggle_btn.config(bg="yellow")

    def on_buy_coffee(self):
        """Handle Buy Me A Coffee button click"""
        try:
            webbrowser.open('https://buymeacoffee.com/joncox')
            self.log_message("Opening Buy Me A Coffee page...")
        except Exception as e:
            self.logger.error(f"Failed to open browser: {e}")
            self.log_message(f"Failed to open browser: {e}", level='error')

    def on_closing(self):
        """Handle window close"""
        self.logger.info("Application closing")

        # Do not change hardware display mode on exit.
        # Persisted user preferences are already saved when changed.

        # Stop refresh timer
        self._stop_refresh_timer()

        poll_job = getattr(self, "_event_watcher_poll_job", None)
        if poll_job:
            self.root.after_cancel(poll_job)
            self._event_watcher_poll_job = None
        EInkControlGUI._stop_event_watcher(self)
        EInkControlGUI._stop_lid_inhibitor(self)

        # Disconnect from helper client socket
        if self.helper.is_connected():
            self.helper.disconnect()

        self.root.destroy()


def show_disclaimer_dialog(parent=None):
    """Show disclaimer dialog on first launch. Returns True if user agrees, False otherwise."""
    # Load EULA text from external file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    eula_file = os.path.join(script_dir, "README_EULA_INSTRUCTIONS_WARNINGS.txt")

    try:
        with open(eula_file, 'r') as f:
            DISCLAIMER_TEXT = f.read()
    except FileNotFoundError:
        # Show error message and terminate
        if parent:
            messagebox.showerror("EULA Not Found",
                               "EULA file not found:\n" + eula_file +
                               "\n\nThe application will now exit.")
        else:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("EULA Not Found",
                               "EULA file not found:\n" + eula_file +
                               "\n\nThe application will now exit.")
            root.destroy()
        sys.exit(1)
    except Exception as e:
        # Show error message for other read errors and terminate
        error_msg = f"Failed to read EULA file:\n{eula_file}\n\nError: {str(e)}\n\nThe application will now exit."
        if parent:
            messagebox.showerror("EULA Not Found", error_msg)
        else:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("EULA Not Found", error_msg)
            root.destroy()
        sys.exit(1)

    # Check if agreement file exists
    config_dir = os.path.expanduser("~/.config/Tinta4Plus")
    agree_file = os.path.join(config_dir, "agree")

    if os.path.exists(agree_file):
        return True  # User has already agreed

    # Create a custom EULA dialog
    dialog = tk.Toplevel(parent)
    dialog.title("End User License Agreement")
    dialog.geometry("900x750")
    dialog.resizable(False, False)

    # Disable the close button (X) - user must click Agree or Disagree
    dialog.protocol("WM_DELETE_WINDOW", lambda: None)

    # Make it modal
    dialog.grab_set()
    dialog.focus_set()

    # Center the dialog on screen
    dialog.update_idletasks()
    x = (dialog.winfo_screenwidth() // 2) - (650 // 2)
    y = (dialog.winfo_screenheight() // 2) - (600 // 2)
    dialog.geometry(f'900x750+{x}+{y}')

    # Result variable
    result = {'agreed': False}

    def on_agree():
        result['agreed'] = True
        dialog.destroy()

    def on_disagree():
        result['agreed'] = False
        dialog.destroy()

    # Top frame with warning icon and title
    top_frame = tk.Frame(dialog, bg='white', pady=10)
    top_frame.pack(fill=tk.X)

    # Warning icon (using text emoji)
    icon_label = tk.Label(top_frame, text="⚠", font=('TkDefaultFont', 48),
                         bg='white', fg='orange')
    icon_label.pack(side=tk.LEFT, padx=20)

    # Title
    title_label = tk.Label(top_frame, text="End User License Agreement\n\nPlease read carefully",
                          font=('TkDefaultFont', 12, 'bold'), bg='white', justify=tk.LEFT)
    title_label.pack(side=tk.LEFT, padx=10)

    # Separator
    separator = ttk.Separator(dialog, orient=tk.HORIZONTAL)
    separator.pack(fill=tk.X, padx=5, pady=5)

    # Button frame (pack this BEFORE the text so it stays at bottom)
    button_frame = tk.Frame(dialog)
    button_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)

    # Bottom separator (pack before text frame)
    separator2 = ttk.Separator(dialog, orient=tk.HORIZONTAL)
    separator2.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=5)

    # Scrolled text widget for EULA (pack last so it fills remaining space)
    text_frame = tk.Frame(dialog)
    text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    # Create ScrolledText with vertical scrollbar
    eula_text = scrolledtext.ScrolledText(text_frame, wrap=tk.WORD,
                                         font=('TkDefaultFont', 11),
                                         relief=tk.SUNKEN, bd=2,
                                         width=1, height=1)  # Dummy size, will expand
    eula_text.pack(fill=tk.BOTH, expand=True)
    eula_text.insert('1.0', DISCLAIMER_TEXT)
    eula_text.config(state=tk.DISABLED)  # Make read-only

    # Agree button (left side, initially disabled)
    agree_btn = ttk.Button(button_frame, text="Agree",
                          command=on_agree,
                          state='disabled')
    agree_btn.pack(side=tk.LEFT, padx=5)

    # Disagree button (right side, default)
    disagree_btn = ttk.Button(button_frame, text="Disagree",
                             command=on_disagree)
    disagree_btn.pack(side=tk.RIGHT, padx=5)

    # Make Disagree the default button (focused)
    disagree_btn.focus_set()

    # Function to check if user has scrolled to the bottom
    def on_scroll(*args):
        # Get the current position of the scrollbar
        # yview() returns (top, bottom) as fractions of the total content
        pos = eula_text.yview()
        # If bottom is at or near 1.0 (end of document), enable Agree button
        if pos[1] >= 0.99:  # Allow small margin for rounding
            agree_btn.config(state='normal')

    # Bind scroll event to check position
    eula_text.bind('<Configure>', on_scroll)
    eula_text.bind('<MouseWheel>', on_scroll)
    eula_text.bind('<Button-4>', on_scroll)  # Linux scroll up
    eula_text.bind('<Button-5>', on_scroll)  # Linux scroll down
    eula_text.bind('<Key>', on_scroll)  # Arrow keys, Page Down, etc.

    # Also monitor the scrollbar directly - get the vbar widget
    vbar = eula_text.vbar  # ScrolledText has a vbar attribute for the scrollbar
    if vbar:
        original_set = vbar.set
        def scrollbar_set(*args):
            original_set(*args)
            on_scroll()
        vbar.set = scrollbar_set

    # Handle Enter key on buttons
    disagree_btn.bind('<Return>', lambda e: on_disagree())
    agree_btn.bind('<Return>', lambda e: on_agree())

    # Wait for dialog to close
    dialog.wait_window()

    if result['agreed']:
        # User agreed - create agreement file
        try:
            os.makedirs(config_dir, exist_ok=True)
            with open(agree_file, 'w') as f:
                f.write('')  # Empty file
            return True
        except Exception as e:
            print(f"Error creating agreement file: {e}")
            return False
    else:
        # User declined
        return False


def main():
    """Entry point"""
    HELPER_SCRIPT = '/usr/local/lib/tinta4plus/HelperDaemon.py'

    # Setup logging
    log_handlers = [
        logging.StreamHandler(),  # Console output
        logging.FileHandler('/tmp/tinta4plus.log', mode='w')  # File output (overwrite mode)
    ]

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=log_handlers
    )
    logger = logging.getLogger('tinta4plus-gui')

    # Setup exception hook to log uncaught exceptions
    def handle_exception(exc_type, exc_value, exc_traceback):
        """Log uncaught exceptions"""
        if issubclass(exc_type, KeyboardInterrupt):
            # Allow keyboard interrupt to exit normally
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception

    root = tk.Tk()
    root.withdraw()  # Hide the main window initially

    # Check disclaimer agreement BEFORE showing the main window
    if not show_disclaimer_dialog(root):
        print("User declined disclaimer. Exiting.")
        root.destroy()
        sys.exit(0)

    # User agreed, show the main window
    root.deiconify()
    app = EInkControlGUI(root, HELPER_SCRIPT, logger)

    try:
        root.mainloop()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        app.on_closing()


if __name__ == '__main__':
    main()
