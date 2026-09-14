#!/usr/bin/env bash
set -e

# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Download static FFmpeg binary (Required for Render)
wget https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz
tar -xf ffmpeg-release-amd64-static.tar.xz
rm ffmpeg-release-amd64-static.tar.xz

# Move binaries to a folder in the system PATH
mkdir -p $HOME/.local/bin
cp ffmpeg-*-static/ffmpeg $HOME/.local/bin/
cp ffmpeg-*-static/ffprobe $HOME/.local/bin/
