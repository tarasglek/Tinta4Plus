"""
Copyright (c) 2025 Jon Cox (joncox123). All rights reserved.

WARNING: This software is provided "AS IS", without any warranty of any kind. It may contain bugs or other defects
that result in data loss, corruption, hardware damage or other issues. Use at your own risk.
It may temporarily or permanently render your hardware inoperable.
It may corrupt or damage the Embedded Controller or eInk T-CON controller in your laptop.
The author is not responsible for any damage, data loss or lost productivity caused by use of this software. 
By downloading and using this software you agree to these terms and acknowledge the risks involved.
"""

import subprocess
import os
import re
import time
import math


class DisplayManager:
    """Manage display switching and configuration (no root required)"""

    # ThinkBook Plus Gen 4 IRU hardware specifications
    OLED_RESOLUTION_WH = [2880, 1800]
    EINK_RESOLUTION_WH = [2560, 1600]
    
    # Display name to resolution mapping for easy extension
    DISPLAY_RESOLUTIONS = {
        'eDP-1': [2880, 1800],  # OLED
        'eDP-2': [2560, 1600],  # E-Ink
    }
    
    # Timing constants (seconds)
    XRANDR_APPLY_DELAY = 0.2
    IMAGE_DISPLAY_DELAY = 0.5
    XRANDR_TIMEOUT = 5
    WHICH_TIMEOUT = 2
    
    # Cache timeout for xrandr queries (seconds)
    XRANDR_CACHE_TTL = 0.5

    SUPPORTED_ROTATIONS = {"normal", "left"}
    XRANDR_ROTATIONS = {"normal", "left", "right", "inverted"}

    def __init__(self, logger):
        self.logger = logger
        self._xrandr_cache = None
        self._xrandr_cache_time = 0
    
    def _get_xrandr_output(self):
        """Get cached xrandr output to reduce subprocess overhead"""
        current_time = time.time()
        if self._xrandr_cache is not None and (current_time - self._xrandr_cache_time) < self.XRANDR_CACHE_TTL:
            return self._xrandr_cache
        
        try:
            result = subprocess.run(
                ['xrandr', '--query'],
                capture_output=True,
                text=True,
                timeout=self.XRANDR_TIMEOUT
            )
            
            if result.returncode != 0:
                self.logger.error(f"xrandr error: {result.stderr}")
                return None
            
            self._xrandr_cache = result.stdout
            self._xrandr_cache_time = current_time
            return result.stdout
            
        except subprocess.TimeoutExpired:
            self.logger.error(f"xrandr query timed out after {self.XRANDR_TIMEOUT}s")
            return None
        except Exception as e:
            self.logger.error(f"Failed to query xrandr: {e}")
            return None
    
    def get_displays(self):
        """Get list of connected displays using xrandr"""
        xrandr_output = self._get_xrandr_output()
        if not xrandr_output:
            return []
        
        displays = []
        for line in xrandr_output.split('\n'):
            if ' connected' in line:
                parts = line.split()
                name = parts[0]
                primary = 'primary' in line
                displays.append({'name': name, 'primary': primary})
        
        return displays
    
    def is_display_active(self, display_name):
        """Check if a display is currently active (enabled and has geometry)"""
        xrandr_output = self._get_xrandr_output()
        if not xrandr_output:
            return False
        
        for line in xrandr_output.split('\n'):
            if display_name in line and ' connected' in line:
                # Display is active if it has geometry info (e.g., 1920x1080+0+0)
                for part in line.split():
                    if 'x' in part and '+' in part:
                        return True
                return False
        
        return False

    def get_active_display(self):
        """Return currently active connected display name, or None."""
        xrandr_output = self._get_xrandr_output()
        if not xrandr_output:
            return None

        for line in xrandr_output.split('\n'):
            if ' connected' not in line:
                continue
            parts = line.split()
            if not parts:
                continue
            if any(re.match(r"^\d+x\d+\+\d+\+\d+$", part) for part in parts):
                return parts[0]

        return None

    def get_display_rotation(self, display_name):
        """Return raw xrandr rotation for display when supported, else None."""
        xrandr_output = self._get_xrandr_output()
        if not xrandr_output:
            return None

        for line in xrandr_output.split('\n'):
            if display_name in line and ' connected' in line:
                match = re.search(r" connected(?:\s+primary)?(?:\s+\d+x\d+\+\d+\+\d+)?\s+\(?(normal|left|right|inverted)\b", line)
                rotation = match.group(1) if match else None
                if rotation in self.SUPPORTED_ROTATIONS:
                    return rotation
                if rotation is not None:
                    self.logger.warning(f"Unsupported rotation '{rotation}' for {display_name}")
                return None

        return None

    def set_display_rotation(self, display_name, rotation):
        """Set display rotation using xrandr."""
        if rotation not in self.SUPPORTED_ROTATIONS:
            self.logger.warning(f"Unsupported requested rotation '{rotation}'")
            return False

        try:
            result = subprocess.run(
                ['xrandr', '--output', display_name, '--rotate', rotation],
                capture_output=True,
                timeout=self.XRANDR_TIMEOUT
            )
            if result.returncode != 0:
                self.logger.warning(f"xrandr returned {result.returncode}: {result.stderr}")
                return False

            self._xrandr_cache = None
            return True
        except subprocess.TimeoutExpired:
            self.logger.error(f"xrandr rotation command timed out after {self.XRANDR_TIMEOUT}s")
            return False
        except Exception as e:
            self.logger.error(f"Failed to set display rotation: {e}")
            return False

    def get_effective_display_scale(self, display_name):
        """Return current app-convention scale for a display, or None when ambiguous."""
        xrandr_output = self._get_xrandr_output()
        if not xrandr_output:
            return None

        native_resolution = self.DISPLAY_RESOLUTIONS.get(display_name)
        if not native_resolution:
            return None

        native_width, native_height = native_resolution

        for line in xrandr_output.split('\n'):
            if not re.search(rf"^{re.escape(display_name)}\\s+connected\\b", line):
                continue

            geometry_match = re.search(r"\b(\d+)x(\d+)\+\d+\+\d+\b", line)
            if not geometry_match:
                return None

            current_width = int(geometry_match.group(1))
            current_height = int(geometry_match.group(2))
            if current_width <= 0 or current_height <= 0:
                return None

            width_scale = native_width / current_width
            height_scale = native_height / current_height

            # Conservative parsing: width/height must agree closely.
            if abs(width_scale - height_scale) > 0.05:
                return None

            return (width_scale + height_scale) / 2.0

        return None

    def _build_display_target_state(self, display_name, scale=None):
        """Build one explicit target state for display apply/verify operations."""
        native_resolution = self.DISPLAY_RESOLUTIONS.get(display_name)
        if not native_resolution:
            return None

        requested_scale = 1.0 if scale is None else float(scale)
        if requested_scale <= 0:
            self.logger.error(f"Invalid scale {scale} for {display_name}")
            return None

        native_width, native_height = native_resolution
        transform_scale_x = 1.0 / requested_scale
        transform_scale_y = 1.0 / requested_scale

        logical_width = max(1, math.ceil(native_width * transform_scale_x))
        logical_height = max(1, math.ceil(native_height * transform_scale_y))
        if transform_scale_x == 1.0 and transform_scale_y == 1.0:
            transform_matrix = '1,0,0,0,1,0,0,0,1'
        else:
            transform_matrix = (
                f'{transform_scale_x},0,0,'
                f'0,{transform_scale_y},0,'
                '0,0,1'
            )

        return {
            'display_name': display_name,
            'native_width': native_width,
            'native_height': native_height,
            'requested_scale': requested_scale,
            'transform_scale_x': transform_scale_x,
            'transform_scale_y': transform_scale_y,
            'transform_matrix': transform_matrix,
            'logical_width': logical_width,
            'logical_height': logical_height,
            'panning_width': logical_width,
            'panning_height': logical_height,
            'framebuffer_width': logical_width,
            'framebuffer_height': logical_height,
        }

    def _run_xrandr_apply_command(self, display_name, cmd):
        cmd_text = " ".join(cmd)
        self.logger.info(f"Running xrandr apply for {display_name}: {cmd_text}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=self.XRANDR_TIMEOUT
            )
            if result.returncode != 0:
                self.logger.warning(
                    f"xrandr apply returned {result.returncode} for {display_name}: {result.stderr}; "
                    "continuing and verifying display state"
                )
            else:
                self.logger.info(f"xrandr apply succeeded for {display_name}")
        except subprocess.TimeoutExpired:
            self.logger.error(f"xrandr enable command timed out after {self.XRANDR_TIMEOUT}s")
            return False
        except Exception as e:
            self.logger.error(f"Failed to run xrandr enable command: {e}")
            return False

        self._xrandr_cache = None
        return True

    def _apply_display_target_state(self, target_state):
        """Apply xrandr using one coherent target state (mode, transform, panning, fb)."""
        display_name = target_state['display_name']

        cmd = [
            'xrandr', '--output', display_name,
            '--mode', f"{target_state['native_width']}x{target_state['native_height']}",
            '--transform', target_state['transform_matrix'],
            '--panning', f"{target_state['panning_width']}x{target_state['panning_height']}",
            '--fb', f"{target_state['framebuffer_width']}x{target_state['framebuffer_height']}",
        ]

        return self._run_xrandr_apply_command(display_name, cmd)

    def _extract_actual_randr_state(self, display_name, xrandr_output=None):
        """Extract framebuffer and output geometry from xrandr output."""
        output = xrandr_output if xrandr_output is not None else self._get_xrandr_output()
        if not output:
            return None

        framebuffer_width = None
        framebuffer_height = None
        output_active = False
        output_width = None
        output_height = None

        for line in output.split('\n'):
            stripped = line.strip()
            if stripped.startswith('Screen '):
                match = re.search(r"current\s+(\d+)\s+x\s+(\d+)", stripped)
                if match:
                    framebuffer_width = int(match.group(1))
                    framebuffer_height = int(match.group(2))
                continue

            if not re.search(rf"^{re.escape(display_name)}\s+connected\b", stripped):
                continue

            geo_match = re.search(r"\b(\d+)x(\d+)\+\d+\+\d+\b", stripped)
            if geo_match:
                output_active = True
                output_width = int(geo_match.group(1))
                output_height = int(geo_match.group(2))

        return {
            'framebuffer_width': framebuffer_width,
            'framebuffer_height': framebuffer_height,
            'output_active': output_active,
            'output_width': output_width,
            'output_height': output_height,
        }

    def _verify_display_target_state(self, display_name, target_state, xrandr_output=None):
        """Verify post-apply RandR state matches the expected target state."""
        actual = self._extract_actual_randr_state(display_name, xrandr_output=xrandr_output)
        if not actual:
            self.logger.warning(f"Could not read post-apply xrandr state for {display_name}")
            return False

        expected_width = target_state['logical_width']
        expected_height = target_state['logical_height']

        mismatches = {}

        if not actual['output_active']:
            mismatches['output_active'] = {'expected': True, 'actual': False}

        fb_width = actual['framebuffer_width']
        fb_height = actual['framebuffer_height']
        if fb_width is None or fb_height is None:
            mismatches['framebuffer'] = {'expected': 'present', 'actual': None}
        elif fb_width != expected_width or fb_height != expected_height:
            mismatches['framebuffer_size'] = {
                'expected': f"{expected_width}x{expected_height}",
                'actual': f"{fb_width}x{fb_height}",
            }

        if actual['output_width'] != expected_width or actual['output_height'] != expected_height:
            mismatches['output_geometry'] = {
                'expected': f"{expected_width}x{expected_height}",
                'actual': (
                    f"{actual['output_width']}x{actual['output_height']}"
                    if actual['output_width'] is not None and actual['output_height'] is not None
                    else None
                ),
            }

        if mismatches:
            self.logger.warning(f"Display state mismatch for {display_name}: {mismatches}")
            return False

        self.logger.info(
            f"Verified display state for {display_name}: "
            f"logical={expected_width}x{expected_height}, "
            f"framebuffer={fb_width}x{fb_height}"
        )
        return True

    def _apply_display_scale(self, display_name, scale=None):
        """Apply one full xrandr target state to the provided display."""
        target_state = self._build_display_target_state(display_name, scale)
        if target_state:
            self.logger.info(f"Target state for {display_name}: {target_state}")
            return self._apply_display_target_state(target_state)

        self.logger.warning(f"Unknown display {display_name}, using auto mode")
        cmd = ['xrandr', '--output', display_name, '--auto']
        return self._run_xrandr_apply_command(display_name, cmd)

    def _activate_display_transition_safe(self, display_name, scale=None):
        """Activate output without forcing a compact single-output framebuffer."""
        target_state = self._build_display_target_state(display_name, scale)
        if not target_state:
            self.logger.warning(f"Unknown display {display_name}, using auto mode")
            return self._run_xrandr_apply_command(display_name, ['xrandr', '--output', display_name, '--auto'])

        cmd = [
            'xrandr', '--output', display_name,
            '--mode', f"{target_state['native_width']}x{target_state['native_height']}",
            '--transform', target_state['transform_matrix'],
        ]
        return self._run_xrandr_apply_command(display_name, cmd)

    def enable_display(self, display_name, scale=None):
        """Enable/turn on a display with optional scaling.

        Args:
            display_name: Name of the display (e.g., 'eDP-1', 'eDP-2')
            scale: Optional scale factor (e.g., 1.60 means UI appears 1.6x larger, lower DPI)
        """
        try:
            if not self._activate_display_transition_safe(display_name, scale):
                return False

            self._xrandr_cache = None
            time.sleep(self.XRANDR_APPLY_DELAY)

            if not self.is_display_active(display_name):
                self.logger.error(f"Failed to enable display: {display_name} (display not active after apply)")
                return False

            scale_info = f" with {scale}x scale" if scale and scale != 1.0 else ""
            self.logger.info(f"Enabled display: {display_name}{scale_info}")

            xrandr_output = self._get_xrandr_output()
            if xrandr_output:
                lines = xrandr_output.split('\n')
                screen_line = next((line.strip() for line in lines if line.startswith('Screen ')), None)
                active_line = next(
                    (
                        line.strip()
                        for line in lines
                        if re.search(rf"^{re.escape(display_name)}\\s+connected\\b", line)
                    ),
                    None,
                )
                if screen_line:
                    self.logger.info(f"Post-enable xrandr screen: {screen_line}")
                if active_line:
                    self.logger.info(f"Post-enable xrandr output: {active_line}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to enable display: {e}")
            return False
    def finalize_single_display(self, display_name, scale=None):
        """Apply and verify the final compact single-output RandR state."""
        try:
            target_state = self._build_display_target_state(display_name, scale)
            if not target_state:
                self.logger.error(f"Cannot finalize unknown display: {display_name}")
                return False

            self.logger.info(f"Finalizing single-display layout for {display_name}: {target_state}")
            if not self._apply_display_target_state(target_state):
                return False

            self._xrandr_cache = None
            time.sleep(self.XRANDR_APPLY_DELAY)

            if not self._verify_display_target_state(display_name, target_state):
                self.logger.error(f"Failed to finalize single-display layout for {display_name}")
                return False

            self.logger.info(
                f"Finalized single-display layout for {display_name}: "
                f"{target_state['logical_width']}x{target_state['logical_height']}"
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to finalize display layout: {e}")
            return False
    
    def disable_display(self, display_name):
        """Disable/turn off a display"""
        try:
            # Run xrandr command (may produce spurious BadMatch errors on stderr)
            try:
                result = subprocess.run(
                    ['xrandr', '--output', display_name, '--off'],
                    capture_output=True,
                    timeout=self.XRANDR_TIMEOUT
                )
                if result.returncode != 0:
                    self.logger.warning(f"xrandr returned {result.returncode}: {result.stderr}")
            except subprocess.TimeoutExpired:
                self.logger.error(f"xrandr disable command timed out after {self.XRANDR_TIMEOUT}s")
                return False
            
            # Invalidate cache since display state changed
            self._xrandr_cache = None
            
            # Verify the display is actually disabled by checking its state
            # Give X11 a moment to apply the change
            time.sleep(self.XRANDR_APPLY_DELAY)

            if not self.is_display_active(display_name):
                self.logger.info(f"Disabled display: {display_name}")
                return True
            else:
                self.logger.error(f"Failed to disable display: {display_name} (display still active after command)")
                return False

        except Exception as e:
            self.logger.error(f"Failed to disable display: {e}")
            return False

    def get_display_geometry(self, display_name):
        """Get the geometry (position and size) of a display using xrandr"""
        try:
            xrandr_output = self._get_xrandr_output()
            if not xrandr_output:
                return None

            # Parse xrandr output to find the display geometry
            # Format: "eDP-2 connected 1200x1920+1920+0 ..."
            for line in xrandr_output.split('\n'):
                if display_name in line and 'connected' in line:
                    # Look for the geometry pattern: WIDTHxHEIGHT+X+Y
                    parts = line.split()
                    for part in parts:
                        if 'x' in part and '+' in part:
                            # Parse geometry: 1200x1920+1920+0
                            geo = part.split('+')
                            size = geo[0].split('x')
                            width = int(size[0])
                            height = int(size[1])
                            x_offset = int(geo[1]) if len(geo) > 1 else 0
                            y_offset = int(geo[2]) if len(geo) > 2 else 0

                            return {
                                'width': width,
                                'height': height,
                                'x': x_offset,
                                'y': y_offset
                            }

            self.logger.warning(f"Could not find geometry for {display_name}")
            return None

        except Exception as e:
            self.logger.error(f"Failed to get display geometry: {e}")
            return None

    def display_fullscreen_image(self, display_name, image_path):
        """
        Display a fullscreen image on a specific display.
        Works on X11 using feh, or falls back to imv for Wayland support.

        Args:
            display_name: Name of the display (e.g., 'eDP-2')
            image_path: Path to the PNG image file

        Returns:
            subprocess.Popen object if successful, None otherwise
        """
        if not os.path.exists(image_path):
            self.logger.error(f"Image file not found: {image_path}")
            return None

        # Get display geometry
        geometry = self.get_display_geometry(display_name)
        if not geometry:
            self.logger.error(f"Could not determine geometry for {display_name}")
            return None

        self.logger.info(f"Display {display_name} geometry: {geometry['width']}x{geometry['height']}+{geometry['x']}+{geometry['y']}")

        # Try feh first (works great on X11)
        if self._command_exists('feh'):
            try:
                # feh command with fullscreen flag - simpler and more reliable
                # The --fullscreen flag should make feh a top-level window
                cmd = [
                    'feh',
                    '--fullscreen',           # Make it fullscreen
                    '--auto-zoom',            # Auto-zoom to fit
                    '--no-menus',             # No right-click menu
                    '--hide-pointer',         # Hide mouse cursor
                    image_path
                ]

                self.logger.info(f"Displaying fullscreen image on {display_name} using feh")
                process = subprocess.Popen(cmd)

                # Give it a moment to display
                time.sleep(self.IMAGE_DISPLAY_DELAY)

                return process

            except Exception as e:
                self.logger.error(f"Failed to display image with feh: {e}")

        # Try imv as fallback (works on both X11 and Wayland)
        elif self._command_exists('imv'):
            try:
                cmd = [
                    'imv',
                    '-f',  # fullscreen
                    image_path
                ]

                self.logger.info(f"Displaying image using imv (fullscreen mode)")
                self.logger.warning("imv may not position on correct display automatically")
                process = subprocess.Popen(cmd)

                time.sleep(self.IMAGE_DISPLAY_DELAY)
                return process

            except Exception as e:
                self.logger.error(f"Failed to display image with imv: {e}")

        else:
            self.logger.error("Neither feh nor imv is installed. Please install one:")
            self.logger.error("  For X11: sudo apt install feh")
            self.logger.error("  For Wayland: sudo apt install imv")
            return None

        return None

    def _command_exists(self, command):
        """Check if a command exists in PATH"""
        try:
            subprocess.run(
                ['which', command],
                capture_output=True,
                check=True,
                timeout=self.WHICH_TIMEOUT
            )
            return True
        except subprocess.CalledProcessError:
            return False
        except subprocess.TimeoutExpired:
            self.logger.warning(f"Command check for '{command}' timed out")
            return False