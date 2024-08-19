import asyncio
import logging
from functools import partial

from av import VideoFrame

from video.transformers.video_transformer import VideoTransformer


class DummyFrameTransformer(VideoTransformer):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)

    async def transform_frame_task(self, frame) -> VideoFrame:
        detection_result = await asyncio.to_thread(
            partial(self.__dummy_task, frame=frame)
        )
        return detection_result

    async def __dummy_task(self, frame):
        await asyncio.sleep(1)
        return frame
