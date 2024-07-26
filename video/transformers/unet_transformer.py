import asyncio
import logging
import time
from functools import partial

import cv2
import numpy as np
from av import VideoFrame

from video.transformers.video_transformer import VideoTransformer


class UnetTransformer(VideoTransformer):
    def __init__(self, detection_service, confidence_threshold: float):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.detection_service = detection_service
        self.confidence_threshold = confidence_threshold

    async def transform_frame_task(self, frame) -> VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        normalized_img = img
        return await self.detect(frame, img, normalized_img)

    async def detect(self, frame, img, normalized_img):
        self._start_detection_time = time.time_ns()
        detection_result = await asyncio.to_thread(
            partial(self.detection_service.detect_unet, image=img, conf_th=self.confidence_threshold)
        )
        self.frames_detection_count += 1
        self.measured_detection_time_ms = (time.time_ns() - self._start_detection_time) // 1_000_000

        img_width = img.shape[1]
        img_height = img.shape[0]

        mask = np.random.randint(0, len(detection_result[0]["boxes"]), 30)
        boxes = {key: val[mask] for key, val in detection_result[0].items()}['boxes']

        for box in boxes:
            x_center = box[0]
            y_center = box[1]
            width = box[2]
            height = box[3]

            top_left_x = (x_center - (width / 2.0)) * img_width
            top_left_x = 0 if top_left_x < 0 else top_left_x

            top_left_y = (y_center + (height / 2.0)) * img_height
            top_left_y = 0 if top_left_y < 0 else top_left_y

            top_left = (int(top_left_x), int(top_left_y))

            bottom_right_x = (x_center + (width / 2.0)) * img_width
            bottom_right_x = 0 if bottom_right_x < 0 else bottom_right_x

            bottom_right_y = (y_center - (height / 2.0)) * img_height
            bottom_right_y = 0 if bottom_right_y < 0 else bottom_right_y

            bottom_right = (int(bottom_right_x), int(bottom_right_y))

            cv2.rectangle(img, top_left, bottom_right, (0, 255, 0), 2)

        transformed_frame = VideoFrame.from_ndarray(np.uint8(img), format="bgr24")
        transformed_frame.pts = frame.pts
        transformed_frame.time_base = frame.time_base
        return transformed_frame
