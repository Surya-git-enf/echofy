#!/usr/bin/env bash
set -e

# Render's build image already ships a full-featured ffmpeg preinstalled —
# no need to download/compile one (confirmed: ffmpeg 5.1.9, Debian build,
# already on PATH). The old johnvansickle.com download step is removed —
# that site was timing out from Render's network and had no purpose anyway.

pip install -r requirements.txt
