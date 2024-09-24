import asyncio
import gc
import logging

from memory_profiler import memory_usage

from services.connection_manager import ConnectionManager
from video.video_track_with_telemetry import VideoTrackWithTelemetry
from video.video_transform_track import VideoTransformTrack


class TelemetryService:
    def __init__(self, connection_manager: ConnectionManager):
        self.logger = logging.getLogger(__name__)
        self.__connection_manager = connection_manager
        self.rtt_camera = 0
        self.fps_decoded = 0
        self.fps_detected = 0
        self.detection_time = 0
        self.send_telemetry_task: asyncio.Task | None = None

    async def start(self):
        self.send_telemetry_task = asyncio.create_task(self.__send_statistics())

    def shutdown(self):
        if self.send_telemetry_task:
            self.send_telemetry_task.cancel()

    async def __send_statistics(self):
        count = 0
        while True:
            count += 1
            producer_connection = self.__connection_manager.get_primary_producer_connection()
            if producer_connection is not None:
                self.rtt_camera = producer_connection.rtt_ms

            coros = []
            for connection in self.__connection_manager.get_all_connections():

                # Update statistics
                if connection.connection_type == 'producer':
                    for subscription in connection.subscriptions:
                        if isinstance(subscription, VideoTrackWithTelemetry):
                            self.fps_decoded = subscription.fps_decoded
                        if isinstance(subscription, VideoTransformTrack):
                            self.detection_time = subscription.detection_time
                            self.fps_detected = subscription.fps_detected

                # Send statistics
                coros.append(
                    asyncio.create_task(
                        connection.send_statistics(self.rtt_camera,
                                                   self.fps_decoded,
                                                   self.fps_detected,
                                                   self.detection_time)
                    )
                )
                coros.append(asyncio.create_task(connection.send_rtt_packet()))

            await asyncio.gather(*coros)
            if count % 100 == 0:
                gc.collect()
            await asyncio.sleep(1)
