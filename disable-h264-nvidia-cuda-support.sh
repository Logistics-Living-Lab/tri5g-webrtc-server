#!/usr/bin/env bash
cp ./codecs/h264_original.py ./venv/lib/site-packages/aiortc/codecs/h264.py
# Reinstall with binaries
./venv/bin/pip uninstall av
./venv/bin/pip install av
