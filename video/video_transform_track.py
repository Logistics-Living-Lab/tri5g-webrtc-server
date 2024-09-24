import asyncio
import logging
from av import VideoFrame
from video.transformers.video_transformer import VideoTransformer
from video.video_track_with_telemetry import VideoTrackWithTelemetry


class VideoTransformTrack(VideoTrackWithTelemetry):
    def __init__(self, track, name, video_transformer: VideoTransformer):
        super().__init__(track, name)
        self.logger = logging.getLogger(__name__)
        self.video_transformer: VideoTransformer = video_transformer
        self.detection_time = 0
        self.fps_detected = 0

        self.__is_processing_frame = False
        self.__current_frame = None
        self.__transformation_task: asyncio.Task | None = None
        self.__transformed_frames_count = 0
        self.on("ended", self.on_track_ended)

    async def create_transformation_task(self, frame: VideoFrame):
        transformed_frame = await self.video_transformer.transform_frame_task(frame)
        transformed_frame.pts = frame.pts
        transformed_frame.dts = frame.dts
        transformed_frame.time_base = frame.time_base
        self.__current_frame = transformed_frame
        self.__is_processing_frame = False
        self.detection_time = self.video_transformer.measured_detection_time_ms
        self.__transformed_frames_count += 1

    def on_track_ended(self):
        self.__transformation_task.cancel()

    async def on_frame_received(self, frame) -> VideoFrame:
        if self.__current_frame is None:
            self.__current_frame = frame

        self.__current_frame.pts = frame.pts
        self.__current_frame.dts = frame.dts

        if self.__is_processing_frame:
            return self.__current_frame

        self.__is_processing_frame = True
        if not self.__transformation_task or self.__transformation_task.done():
            self.__transformation_task = asyncio.create_task(self.create_transformation_task(frame))

        return self.__current_frame

    def on_calculate_fps(self, passed_seconds):
        self.fps_detected = self.__transformed_frames_count / passed_seconds
        self.__transformed_frames_count = 0
