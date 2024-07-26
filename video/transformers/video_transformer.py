from abc import ABC, abstractmethod

from av import VideoFrame


class VideoTransformer(ABC):

    def __init__(self):
        self._start_detection_time = 0
        self.measured_detection_time_ms = 0
        self.frames_detection_count = 0

    @abstractmethod
    async def transform_frame_task(self, frame) -> VideoFrame:
        pass
