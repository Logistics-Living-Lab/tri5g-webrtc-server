import asyncio
import logging
import time

import cv2
from aiortc import MediaStreamTrack
from av import VideoFrame


class VideoTrackWithTelemetry(MediaStreamTrack):
    MAX_WIDTH = 1280
    MAX_HEIGHT = 720

    PRINT_TELEMETRY_DATA_IN_SECONDS = 10
    kind = "video"

    def __init__(self, track, name, max_fps=24):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.track = track
        self.name = name
        self.fps_received = 0
        self.fps_decoded = 0
        self.__last_frame = None
        self.__received_frames = 0
        self.__decoded_incoming_frames = 0
        self.__dropped_frames = 0
        self.__timestamp_start_ns = time.time_ns()
        self.__telemetry_task = asyncio.create_task(self.calculate_fps())
        self.__max_fps = max_fps
        self.__frame_interval = float(f"{1.0 / self.__max_fps:.3f}") * 0.9
        self.__next_expected_seconds = 0
        self.__pts_factor = 0
        self.on("ended", self.on_track_ended)

    def on_track_ended(self):
        if self.__telemetry_task:
            self.__telemetry_task.cancel()

    async def recv(self):
        self.__received_frames += 1
        frame: VideoFrame = await self.track.recv()

        if self.__last_frame is None:
            self.__last_frame = frame
            if self.__received_frames <= 1:
                return self.__last_frame

        if self.__pts_factor == 0:
            self.__pts_factor = self.get_pts_factor(frame.time)

        frame_time_now = frame.time / self.__pts_factor
        logging.info(f"FRAME: {self.__received_frames}")
        logging.info(f"Now: {frame_time_now}")
        logging.info(f"Frame time (original): {frame.time}")
        logging.info(f"Expected: {self.__next_expected_seconds}")
        logging.info(f"Drop: {frame_time_now < self.__next_expected_seconds}")
        logging.info(f"PTS factor: {self.__pts_factor}")
        logging.info(f"Max FPS: {self.__max_fps}")
        logging.info(f"FPS interval: {self.__frame_interval}")
        logging.info("#################")

        # If frame is too early drop
        if frame_time_now >= self.__next_expected_seconds:

            # Check max size
            if frame.width > self.MAX_WIDTH or frame.height > self.MAX_HEIGHT:
                img = frame.to_ndarray(format="bgr24")
                aspect_ratio = img.shape[1] / img.shape[0]
                if aspect_ratio > 1:  # Width greater than height
                    new_width = self.MAX_WIDTH
                    new_height = int(new_width / aspect_ratio)
                else:  # Height greater than width
                    new_height = self.MAX_HEIGHT
                    new_width = int(new_height * aspect_ratio)

                # Resize the image
                resized_img = cv2.resize(img, (new_width, new_height))
                transformed_frame = frame.from_ndarray(resized_img, format="bgr24")
                transformed_frame.pts = frame.pts
                transformed_frame.dts = frame.dts
                transformed_frame.time_base = frame.time_base

                frame = transformed_frame

            self.__next_expected_seconds = self.__next_expected_seconds + self.__frame_interval  # pts is wrong?
            self.__decoded_incoming_frames += 1
            self.__last_frame = await self.on_frame_received(frame)
            return self.__last_frame

        self.__dropped_frames += 1
        self.__last_frame.pts = frame.pts
        self.__last_frame.dts = frame.dts
        return self.__last_frame

    async def on_frame_received(self, frame) -> VideoFrame:
        return frame

    async def calculate_fps(self):
        while True:
            passed_seconds = (((time.time_ns() - self.__timestamp_start_ns) + 0.000000001) / 1_000_000_000)

            self.fps_received = self.__received_frames / passed_seconds
            self.fps_decoded = self.__decoded_incoming_frames / passed_seconds

            self.on_calculate_fps(passed_seconds)

            logging.info("###############################")
            logging.info(f"{self.name}")
            logging.info(f"Passed seconds: {passed_seconds}")
            logging.info(
                f"Frames per second (Received): {self.fps_received}")
            logging.info(
                f"Frames per second (Decoded): {round(self.fps_decoded, 1)}")
            logging.info(
                f"Frames per second (Dropped): {round(self.__dropped_frames / passed_seconds, 1)}")

            self.__received_frames = 0
            self.__decoded_incoming_frames = 0
            self.__dropped_frames = 0
            self.__timestamp_start_ns = time.time_ns()

            # App.telemetry_service.fps_decoding = self.__fps_decoding
            # App.telemetry_service.fps_detection = self.__fps_detection
            # App.telemetry_service.detection_time = self.__detection_time

            await asyncio.sleep(VideoTrackWithTelemetry.PRINT_TELEMETRY_DATA_IN_SECONDS)

    def on_calculate_fps(self, passed_seconds):
        return None

    # PTS has different units per stream - can only be guessed
    def get_pts_factor(self, frame_time):
        if frame_time > 10_000_000:
            # Assume frame_time unit is nanoseconds
            return 1_000_000_000
        elif frame_time > 10_000:
            # Assume frame_time unit is microseconds (used by Windows)
            return 1_000_000
        elif frame_time > 10:
            # Assume PTS is milliseconds
            return 1_000
        else:
            # Assume PTS is seconds (used by Jetson)
            return 1
