#!/bin/bash
# Chromium's SUID sandbox helper must be owned by root with mode 4755.
chown root:root /opt/QMMCRehab/chrome-sandbox 2>/dev/null || true
chmod 4755 /opt/QMMCRehab/chrome-sandbox 2>/dev/null || true
exit 0
