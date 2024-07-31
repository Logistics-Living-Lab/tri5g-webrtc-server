#!/usr/bin/env bash
cp ./codecs/h264_original.py ./venv/lib/python3.10/site-packages/aiortc/codecs/h264.py
# Reinstall with binaries
./venv/bin/pip uninstall av
./venv/bin/pip install av
