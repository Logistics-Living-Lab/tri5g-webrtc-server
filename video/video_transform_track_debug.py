import asyncio
import gc
import logging
import time
from asyncio import Task

from aiortc import MediaStreamTrack
from av import VideoFrame
from memory_profiler import profile

from config.app import App
from video.transformers.video_transformer import VideoTransformer
from video.video_track_with_telemetry import VideoTrackWithTelemetry


class VideoTransformTrackDebug(VideoTrackWithTelemetry):
    kind = "video"

    def __init__(self, track, name):
        super().__init__(track, name)
