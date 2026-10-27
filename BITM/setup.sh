#!/usr/bin/env bash
# setup.sh -- BitM dependency installation on a Linux server (Debian/Ubuntu)
#
# Usage:
#   chmod +x setup.sh && sudo bash setup.sh
#
# Installed components:
#   - Xvfb       : virtual X server (framebuffer)
#   - x11vnc     : VNC sharing of the Xvfb display
#   - noVNC      : web VNC client (HTML5/WebSocket)
#   - websockify : VNC <-> WebSocket bridge
#   - Playwright  : Chrome headful automation
#   - Chrome      : system browser
set -euo pipefail

echo "============================================"
echo " BitM installation - Playwright + noVNC"
echo "============================================"

# -- System packages ----------------------------------------------
echo "[1/5] System packages..."
apt-get update -qq
apt remove python3-cryptography
# If libasound2 cannot be found, change it for liboss4-salsa-asound2
apt-get install -y -qq \
    xvfb \
    x11vnc \
    python3 \
    python3-pip \
    python3-venv \
    git \
    wget \
    unzip \
    fonts-liberation \
    libgtk-3-0 \
    libnotify4 \
    libnss3 \
    libxss1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libgbm1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2

# -- noVNC --------------------------------------------------------
echo "[2/5] noVNC..."
NOVNC_DIR="/opt/noVNC"
if [ ! -d "$NOVNC_DIR" ]; then
    git clone --depth 1 https://github.com/novnc/noVNC.git "$NOVNC_DIR"
    echo "    installed in $NOVNC_DIR"
else
    echo "    already present in $NOVNC_DIR"
fi

# -- websockify (via pip) -----------------------------------------
echo "[3/5] websockify..."
pip3 install --quiet websockify --break-system-packages

# -- Python deps + Playwright -------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "[4/5] Python dependencies..."
pip3 install --quiet -r "$SCRIPT_DIR/requirements.txt" --break-system-packages
playwright install --with-deps chromium
playwright install --with-deps chrome

# -- System Chrome (optional, for DBSC) ---------------------------
echo "[5/5] System Chrome (optional)..."
if command -v google-chrome &>/dev/null; then
    CHROME_VER=$(google-chrome --version 2>/dev/null || echo "?")
    echo "    Chrome already installed: $CHROME_VER"
else
    echo "    Chrome not installed."
    echo "    For DBSC support, install Chrome >= 127:"
    echo "      wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb"
    echo "      apt install -y ./google-chrome-stable_current_amd64.deb"
fi

echo ""
echo "============================================"
echo " Installation complete"
echo "============================================"
echo ""
echo " Launch:"
echo "   python3 bitm_server.py"
echo ""
echo " With system Chrome (DBSC):"
echo "   python3 bitm_server.py --chrome-path /usr/bin/google-chrome-stable"
echo ""
