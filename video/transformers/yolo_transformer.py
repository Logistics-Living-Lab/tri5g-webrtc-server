import asyncio
import logging
import time
from functools import partial

import cv2
import numpy as np
from av import VideoFrame

from ai.yolo_model import YoloModel
from video.detection_service import DetectionService
from video.transformers.video_transformer import VideoTransformer


class YoloTransformer(VideoTransformer):

    def __init__(self, model_id: str, detection_service):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.detection_service: DetectionService | None = detection_service
        self.__model: YoloModel | None = None
        self.__load_model(model_id)

    def __load_model(self, model_id: str):
        model = self.detection_service.get_model_by_id(model_id)
        if model is None:
            logging.error(f"No model found with ID: {model_id}")
            return
        if model.model_type != 'yolo':
            logging.error(f"Model with ID: {model_id} is not a YOLO model")
            return
        self.__model = model

    async def transform_frame_task(self, frame) -> VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        return await self.detect(frame, img)

    async def detect(self, frame, img) -> VideoFrame:
        self.logger.info(f"Detecting [{self.__model.model_id}]...")
        self._start_detection_time = time.time_ns()
        img = await self.__model.detect_yolo_as_image(img)
        self.frames_detection_count += 1
        self.measured_detection_time_ms = (time.time_ns() - self._start_detection_time) // 1_000_000

        transformed_frame = VideoFrame.from_ndarray(np.uint8(img), format="bgr24")
        transformed_frame.pts = frame.pts
        transformed_frame.time_base = frame.time_base
        return transformed_frame
