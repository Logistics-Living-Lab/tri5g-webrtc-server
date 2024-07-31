#!/usr/bin/env bash
cp ./venv/lib/python3.10/site-packages/aiortc/codecs/h264.py ./codecs/h264_original.py
cp ./codecs/h264_nvidia.py ./venv/lib/python3.10/site-packages/aiortc/codecs/h264.py

./venv/bin/pip uninstall av -y
./venv/bin/pip install av --no-binary av
