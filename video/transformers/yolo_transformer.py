import asyncio
import logging
import time
from functools import partial

import cv2
import numpy as np
from av import VideoFrame

from video.transformers.video_transformer import VideoTransformer


class YoloTransformer(VideoTransformer):

    def __init__(self, detection_service):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.detection_service = detection_service

    async def transform_frame_task(self, frame) -> VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        resized_img = cv2.resize(img, (960, 960))
        return await self.detect_dummy(frame, img, resized_img)

    async def detect_dummy(self, frame : VideoFrame, img, resized_img):
        await asyncio.sleep(1)
        return frame

    async def detect(self, frame, img, resized_img) -> VideoFrame:
        self.logger.info("Detecting damages...")
        self._start_detection_time = time.time_ns()

        detection_result = await asyncio.to_thread(
            partial(self.detection_service.detect_yolo, image=resized_img, conf_th=0.4))

        self.frames_detection_count += 1
        self.measured_detection_time_ms = (time.time_ns() - self._start_detection_time) // 1_000_000

        boxes = detection_result["boxes"]
        for index, box in enumerate(boxes):
            label = detection_result["names"][detection_result["labels"][index]]
            score = round(detection_result['scores'][index] * 100.0)
            self.logger.info(f"Detected: {label} - {score}")

            width_factor = img.shape[1] / resized_img.shape[1]
            height_factor = img.shape[0] / resized_img.shape[0]

            cv2.rectangle(img,
                          (int(box[0] * width_factor), int(box[1] * height_factor)),
                          (int(box[2] * width_factor), int(box[3] * height_factor)),
                          (0, 255, 0), 2)
            cv2.putText(img,
                        f"{label} - {score}%",
                        (int(box[0]), int(box[1]) - 10), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        transformed_frame = VideoFrame.from_ndarray(np.uint8(img), format="bgr24")
        transformed_frame.pts = frame.pts
        transformed_frame.time_base = frame.time_base
        return transformed_frame
