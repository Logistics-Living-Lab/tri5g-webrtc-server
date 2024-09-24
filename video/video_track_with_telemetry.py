import asyncio
import logging
import time

from aiortc import MediaStreamTrack
from av import VideoFrame


class VideoTrackWithTelemetry(MediaStreamTrack):
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
        self.__frame_interval = (1.0 / self.__max_fps)  # '* 1.10  # 10% tolerance
        self.__next_expected_pts = 0
        self.on("ended", self.on_track_ended)

    def on_track_ended(self):
        if self.__telemetry_task:
            self.__telemetry_task.cancel()

    async def recv(self):
        self.__received_frames += 1
        frame: VideoFrame = await self.track.recv()

        if self.__last_frame is None:
            self.__last_frame = frame

        now_pts_seconds = frame.time / 1_000_000
        if now_pts_seconds >= self.__next_expected_pts:
            self.__next_expected_pts = now_pts_seconds + (self.__frame_interval * 0.5)  # pts is wrong?
            self.__last_frame = frame
            self.__decoded_incoming_frames += 1
            return await self.on_frame_received(frame)

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
