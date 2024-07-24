import asyncio
import concurrent.futures
import gc
import logging
import time
from functools import partial

import cv2
import numpy as np
from aiortc import MediaStreamTrack
from av import VideoFrame

from config.app import App
from config.config import Config
from services.message import Message
from video.detection_service import DetectionService


class VideoTransformTrack(MediaStreamTrack):
    kind = "video"
    frameCounter = 0
    logger = logging.getLogger("VideoTransformTrack")

    def __init__(self, track, transform, name, detection_service: DetectionService):
        super().__init__()
        self.track = track
        self.transform = transform
        self.name = name
        self.is_processing_frame = False
        self.last_frame = None
        self.manipulated_frame = None
        self.manipulation_task = None
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self.detection_service = detection_service
        self.start_time = 0
        self.detection_time = 0
        self.frame_monitoring_time = None
        self.frames_decoded_count = 0
        self.frames_detection_count = 0
        self.fps_decoding = 0
        self.fps_detection = 0

    async def recv(self):
        if self.frame_monitoring_time is None:
            self.frame_monitoring_time = time.time_ns()

        self.check_for_garbage_collection()

        self.start_time = time.time() * 1000
        # logging.info(f"Before receive: [{self.name}] {time.time() * 1000 - self.start_time}")
        frame = await self.track.recv()
        self.frameCounter += 1
        self.frames_decoded_count += 1
        logging.info(f"{self.id} VideoStreamTrack | FRAME: {frame.index}")
        # logging.info(f"{self.track.id}")
        # logging.info(
        #     f"#### After receive Frame[{frame.index}]: [{self.name}] {time.time() * 1000 - self.start_time}")

        # Only on first run, ensure that last_frame is not empty
        if self.last_frame is None:
            self.last_frame = frame

        if self.is_processing_frame:
            #     logging.info("Skip frame")
            return self.last_frame

        self.is_processing_frame = True

        if self.transform == "fence-detection":
            img = frame.to_ndarray(format="bgr24")
            np_mean = np.array(Config.FENCE_DETECTION_MEAN, dtype=np.float32)
            np_std = np.array(Config.FENCE_DETECTION_STD, dtype=np.float32)
            normalized_img = (img - np_mean) / np_std

            if not self.manipulation_task or self.manipulation_task.done():
                self.manipulation_task = asyncio.create_task(self.start_manipulation_task(frame, normalized_img, img))
        elif self.transform == "airplane-damage":
            img = frame.to_ndarray(format="bgr24")
            img = cv2.resize(img, (960, 960))
            if not self.manipulation_task or self.manipulation_task.done():
                self.manipulation_task = asyncio.create_task(self.detect_airplane_damages(frame, img))
        else:
            self.last_frame = frame
            self.is_processing_frame = False

        # VideoTransformTrack.logger.info("Frame time: [" + self.name + "]" + str(time.time() * 1000 - self.start_time))
        return self.last_frame

    async def manipulate_frame(self, img, threshold_confidence):
        # Run the synchronous frame manipulation function in a separate thread
        return await asyncio.to_thread(
            partial(self.detection_service.detect_unet, image=img, conf_th=threshold_confidence))

    async def manipulate_frame_dummy(self, img, threshold_confidence):
        await asyncio.sleep(2)
        return await asyncio.to_thread(self.fake_detect)

    def fake_detect(self):
        return {
            'boxes': []
        }

    async def detect_airplane_damages(self, frame, img):
        logging.info("Detecting airplane damages.")
        self.detection_time = time.time_ns()
        detection_result = await asyncio.to_thread(
            partial(self.detection_service.detect_yolo, image=img, conf_th=0.4))
        self.frames_detection_count += 1
        self.detection_time = time.time_ns() - self.detection_time

        boxes = detection_result["boxes"]
        logging.info(detection_result)
        for index, box in enumerate(boxes):
            logging.info(box)
            logging.info(detection_result["names"][index])
            cv2.rectangle(img, (int(box[0]), int(box[1])), (int(box[2]), int(box[3])), (0, 255, 0), 2)
            cv2.putText(img,
                        f"{detection_result['names'][index]} - {round(detection_result['scores'][index] * 100.0)}%",
                        (int(box[0]), int(box[1]) - 10), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        img_width = img.shape[1]
        img_height = img.shape[0]

        App.message_service.send_message(Message({"type": "statistics", "fpsDecoding": self.fps_decoding}))

        text = f"Boxes: {len(boxes)} - Decoding: {round(self.fps_decoding, 1)} FPS - Detection: {round(self.fps_detection, 1)} FPS"
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 1
        color = (0, 255, 0)  # Green
        thickness = 2

        (text_width, text_height), baseline = cv2.getTextSize(text, font, font_scale, thickness)

        cv2.putText(img, text, (img_width - (text_width + 20), img_height - text_height), font, 1, (0, 255, 0), 2)

        new_frame = VideoFrame.from_ndarray(np.uint8(img), format="bgr24")
        new_frame.pts = frame.pts
        new_frame.time_base = frame.time_base
        self.last_frame = new_frame
        VideoTransformTrack.logger.info("Manipulated frame received")
        self.is_processing_frame = False

    async def start_manipulation_task(self, frame, normalized_img, img):
        self.detection_time = time.time_ns()
        detection_result = await self.manipulate_frame(normalized_img, Config.THRESHOLD_CONFIDENCE)
        self.frames_detection_count += 1
        self.detection_time = time.time_ns() - self.detection_time

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

        text = f"Boxes: {len(boxes)} - Decoding: {round(self.fps_decoding, 1)} FPS - Detection: {round(self.fps_detection, 1)} FPS"
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 1
        color = (0, 255, 0)  # Green
        thickness = 2

        (text_width, text_height), baseline = cv2.getTextSize(text, font, font_scale, thickness)

        cv2.putText(img, text, (img_width - (text_width + 20), img_height - text_height), font, 1, (0, 255, 0),
                    2)

        new_frame = VideoFrame.from_ndarray(np.uint8(img), format="bgr24")
        new_frame.pts = frame.pts
        new_frame.time_base = frame.time_base
        self.last_frame = new_frame
        VideoTransformTrack.logger.info("Manipulated frame received")
        self.is_processing_frame = False

    def check_for_garbage_collection(self):
        if self.frameCounter % 100 == 0:
            self.fps_decoding = self.frames_decoded_count / (
                    ((time.time_ns() - self.frame_monitoring_time) + 0.000000001) / 1_000_000_000)
            self.fps_detection = self.frames_detection_count / (
                    ((time.time_ns() - self.frame_monitoring_time) + 0.000000001) / 1_000_000_000)

            logging.info("###############################")
            logging.info(
                f"Frames per second (Decoding): {round(self.fps_decoding, 1)}")
            logging.info(
                f"Frames per second (Detection): {round(self.fps_detection, 1)}")

            self.frames_decoded_count = 0
            self.frames_detection_count = 0
            self.frame_monitoring_time = time.time_ns()

        if self.frameCounter % 1000 == 0:
            gc.collect()
