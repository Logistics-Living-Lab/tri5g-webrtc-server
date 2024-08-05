import asyncio
import logging
import time
from functools import partial

import cv2
import numpy as np
from av import VideoFrame

from video.detection_service import DetectionService
from video.transformers.video_transformer import VideoTransformer


class YoloTransformer(VideoTransformer):

    def __init__(self, detection_service):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.detection_service: DetectionService | None = detection_service

    async def transform_frame_task(self, frame) -> VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        return await self.detect(frame, img)

    async def detect_dummy(self, frame: VideoFrame, img, resized_img):
        await asyncio.sleep(1)
        return frame

    async def detect(self, frame, img, resized_img) -> VideoFrame:
        self.logger.info("Detecting damages...")
        self._start_detection_time = time.time_ns()
        img = await self.detection_service.detect_yolo_as_image(img)
        self.frames_detection_count += 1
        self.measured_detection_time_ms = (time.time_ns() - self._start_detection_time) // 1_000_000

        transformed_frame = VideoFrame.from_ndarray(np.uint8(img), format="bgr24")
        transformed_frame.pts = frame.pts
        transformed_frame.time_base = frame.time_base
        return transformed_frame
