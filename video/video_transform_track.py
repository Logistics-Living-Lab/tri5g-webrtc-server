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


class VideoTransformTrack(MediaStreamTrack):
    kind = "video"

    def __init__(self, track, name, video_transformer: VideoTransformer):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.track = track
        self.name = name
        self.video_transformer: VideoTransformer = video_transformer

        self.__is_processing_frame = False
        self.__current_frame = None
        self.__transformation_task: asyncio.Task | None = None
        self.__telemetry_task: asyncio.Task | None = None
        self.__timestamp_start_ns = None
        self.__decoded_incoming_frames = 0
        self.__transformed_frames_count = 0
        self.__detection_time = 0
        self.__fps_decoding = 0
        self.__fps_detection = 0
        self.on("ended", self.on_track_ended)

    async def create_transformation_task(self, frame: VideoFrame):
        transformed_frame = await self.video_transformer.transform_frame_task(frame)
        self.__current_frame = transformed_frame
        self.__detection_time = self.video_transformer.measured_detection_time_ms
        self.__transformed_frames_count += 1
        self.__is_processing_frame = False

    def on_track_ended(self):
        self.__transformation_task.cancel()

        if self.__telemetry_task:
            self.__telemetry_task.cancel()

    async def recv(self):
        if self.__timestamp_start_ns is None:
            self.__timestamp_start_ns = time.time_ns()

        if not self.__telemetry_task:
            self.__telemetry_task = asyncio.create_task(self.check_for_garbage_collection())

        frame = await self.track.recv()
        self.__decoded_incoming_frames += 1

        # Only on first run, ensure that last_frame is not empty
        if self.__current_frame is None:
            self.__current_frame = frame

        if self.__is_processing_frame:
            return self.__current_frame

        self.__is_processing_frame = True
        if not self.__transformation_task or self.__transformation_task.done():
            self.__transformation_task = asyncio.create_task(self.create_transformation_task(frame))

        return self.__current_frame

    async def check_for_garbage_collection(self):
        while True:
            passed_seconds = (((time.time_ns() - self.__timestamp_start_ns) + 0.000000001) / 1_000_000_000)

            self.__fps_decoding = self.__decoded_incoming_frames / passed_seconds
            self.__fps_detection = self.__transformed_frames_count / passed_seconds

            logging.info("###############################")
            logging.info(f"Passed seconds: {passed_seconds}")
            logging.info(
                f"Frames per second (Decoding): {self.__decoded_incoming_frames}")
            logging.info(
                f"Frames per second (Decoding): {round(self.__fps_decoding, 1)}")
            logging.info(
                f"Frames per second (Detection): {round(self.__fps_detection, 1)}")

            App.telemetry_service.fps_decoding = self.__fps_decoding
            App.telemetry_service.fps_detection = self.__fps_detection
            App.telemetry_service.detection_time = self.__detection_time

            await asyncio.sleep(1)
