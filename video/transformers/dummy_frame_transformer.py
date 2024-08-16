import logging

from av import VideoFrame

from video.transformers.video_transformer import VideoTransformer


class DummyFrameTransformer(VideoTransformer):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)

    async def transform_frame_task(self, frame) -> VideoFrame:
        return frame
