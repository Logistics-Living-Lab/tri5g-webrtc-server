import asyncio
import gc
import logging

from memory_profiler import memory_usage

from services.connection_manager import ConnectionManager


class TelemetryService:
    def __init__(self, connection_manager: ConnectionManager):
        self.logger = logging.getLogger(__name__)
        self.__connection_manager = connection_manager
        self.rtt_camera = 0
        self.fps_decoding = 0
        self.fps_detection = 0
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
                coros.append(asyncio.create_task(connection.send_rtt_packet()))
                coros.append(asyncio.create_task(
                    connection.send_statistics(self.rtt_camera, self.fps_decoding, self.fps_detection,
                                               self.detection_time)))

            await asyncio.gather(*coros)
            if count % 10 == 0:
                gc.collect()
                self.logger.info("#################")
                self.logger.info(f"Memory usage: {memory_usage()[0]}")
                self.logger.info("#################")
            await asyncio.sleep(1)
