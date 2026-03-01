#!/usr/bin/env bash
set -euo pipefail

MODE="install"
USER_NAME=""
SOURCE_DIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check)
      MODE="check"
      shift
      ;;
    --user)
      USER_NAME="${2:-}"
      shift 2
      ;;
    --source-dir)
      SOURCE_DIR="${2:-}"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$SOURCE_DIR" ]]; then
  echo "Usage: $0 [--check] --source-dir <path> [--user <username>]" >&2
  exit 2
fi

if [[ "$MODE" == "install" && $EUID -ne 0 ]]; then
  echo "This script must run as root" >&2
  exit 1
fi

if [[ "$MODE" == "install" && -z "$USER_NAME" ]]; then
  echo "Install mode requires --user <username>" >&2
  exit 2
fi

HELPER_SRC="$SOURCE_DIR/HelperDaemon.py"
WATCHDOG_SRC="$SOURCE_DIR/WatchdogTimer.py"
EC_SRC="$SOURCE_DIR/ECController.py"
EINK_SRC="$SOURCE_DIR/EInkUSBController.py"
SOCKET_UNIT_SRC="$SOURCE_DIR/contrib/systemd/tinta4plus-helper.socket"
SERVICE_UNIT_SRC="$SOURCE_DIR/contrib/systemd/tinta4plus-helper.service"
INSTALL_DIR="/usr/local/lib/tinta4plus"
DESKTOP_FILE="/usr/share/applications/eink-tinta4plus.desktop"
APP_MAIN="$SOURCE_DIR/Tinta4Plus.py"

[[ -f "$HELPER_SRC" ]] || { echo "Missing $HELPER_SRC" >&2; exit 1; }
[[ -f "$WATCHDOG_SRC" ]] || { echo "Missing $WATCHDOG_SRC" >&2; exit 1; }
[[ -f "$EC_SRC" ]] || { echo "Missing $EC_SRC" >&2; exit 1; }
[[ -f "$EINK_SRC" ]] || { echo "Missing $EINK_SRC" >&2; exit 1; }
[[ -f "$SOCKET_UNIT_SRC" ]] || { echo "Missing $SOCKET_UNIT_SRC" >&2; exit 1; }
[[ -f "$SERVICE_UNIT_SRC" ]] || { echo "Missing $SERVICE_UNIT_SRC" >&2; exit 1; }
[[ -f "$APP_MAIN" ]] || { echo "Missing $APP_MAIN" >&2; exit 1; }

pick_icon_path() {
  local candidates=(
    "/usr/share/icons/elementary-xfce/apps/48/preferences-desktop-display.png"
    "/usr/share/icons/HighContrast/48x48/apps/preferences-desktop-display.png"
    "/usr/share/icons/HighContrast/32x32/apps/preferences-desktop-display.png"
    "/usr/share/icons/hicolor/48x48/status/display-brightness.png"
  )

  for icon in "${candidates[@]}"; do
    if [[ -f "$icon" ]]; then
      echo "$icon"
      return 0
    fi
  done

  echo "video-display-symbolic"
}

write_desktop_file() {
  local icon="$1"
  cat > "$2" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=EInk-Tinta4+
Comment=Control ThinkBook Plus E-Ink display
Exec=$APP_MAIN
TryExec=$APP_MAIN
Path=$SOURCE_DIR
Icon=$icon
Terminal=false
Categories=System;
StartupNotify=true
EOF
}

if [[ "$MODE" == "check" ]]; then
  status=0

  check_same() {
    local src="$1"
    local dst="$2"
    if [[ ! -f "$dst" ]] || ! cmp -s "$src" "$dst"; then
      status=1
    fi
  }

  check_same "$HELPER_SRC" "$INSTALL_DIR/HelperDaemon.py"
  check_same "$WATCHDOG_SRC" "$INSTALL_DIR/WatchdogTimer.py"
  check_same "$EC_SRC" "$INSTALL_DIR/ECController.py"
  check_same "$EINK_SRC" "$INSTALL_DIR/EInkUSBController.py"
  check_same "$SOCKET_UNIT_SRC" "/etc/systemd/system/tinta4plus-helper.socket"
  check_same "$SERVICE_UNIT_SRC" "/etc/systemd/system/tinta4plus-helper.service"

  tmp_desktop="$(mktemp)"
  write_desktop_file "$(pick_icon_path)" "$tmp_desktop"
  check_same "$tmp_desktop" "$DESKTOP_FILE"
  rm -f "$tmp_desktop"

  if ! getent group tinta4plus >/dev/null; then
    status=1
  fi

  if [[ -n "$USER_NAME" ]] && ! id -nG "$USER_NAME" | tr ' ' '\n' | grep -qx tinta4plus; then
    status=1
  fi

  if ! systemctl is-enabled tinta4plus-helper.socket >/dev/null 2>&1; then
    status=1
  fi

  exit $status
fi

install -d -m 0755 "$INSTALL_DIR"
install -m 0644 "$HELPER_SRC" "$INSTALL_DIR/HelperDaemon.py"
install -m 0644 "$WATCHDOG_SRC" "$INSTALL_DIR/WatchdogTimer.py"
install -m 0644 "$EC_SRC" "$INSTALL_DIR/ECController.py"
install -m 0644 "$EINK_SRC" "$INSTALL_DIR/EInkUSBController.py"
rm -f /usr/local/bin/HelperDaemon.py
install -m 0644 "$SOCKET_UNIT_SRC" /etc/systemd/system/tinta4plus-helper.socket
install -m 0644 "$SERVICE_UNIT_SRC" /etc/systemd/system/tinta4plus-helper.service
write_desktop_file "$(pick_icon_path)" "$DESKTOP_FILE"
chmod 0644 "$DESKTOP_FILE"

if ! getent group tinta4plus >/dev/null; then
  groupadd --system tinta4plus
fi

usermod -a -G tinta4plus "$USER_NAME"

systemctl daemon-reload
systemctl stop tinta4plus-helper.service tinta4plus-helper.socket 2>/dev/null || true
systemctl reset-failed tinta4plus-helper.service tinta4plus-helper.socket 2>/dev/null || true
rm -f /run/tinta4plus.sock /tmp/tinta4plus.pid
systemctl enable --now tinta4plus-helper.socket
systemctl restart tinta4plus-helper.socket
update-desktop-database /usr/share/applications >/dev/null 2>&1 || true

echo "Installed and enabled tinta4plus-helper.socket"
echo "Installed desktop launcher: $DESKTOP_FILE"
echo "User '$USER_NAME' added to group 'tinta4plus' (re-login may be required)."
