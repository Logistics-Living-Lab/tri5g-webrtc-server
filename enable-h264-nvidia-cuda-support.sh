#!/usr/bin/env bash
cp ./venv/lib/python3.10/site-packages/aiortc/codecs/h264.py ./codecs/h264_original.py
cp ./venv/lib/python3.10/site-packages/aiortc/contrib/media.py ./codecs/media_original.py
cp ./codecs/h264_nvidia.py ./venv/lib/python3.10/site-packages/aiortc/codecs/h264.py
cp ./codecs/media_nvidia.py ./venv/lib/python3.10/site-packages/aiortc/contrib/media.py

./venv/bin/pip uninstall av -y
./venv/bin/pip install av --no-binary av
