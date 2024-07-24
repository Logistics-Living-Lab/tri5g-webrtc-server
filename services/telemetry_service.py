import asyncio
import logging

from services.message import Message
from services.message_service import MessageService


class TelemetryService:
    def __init__(self, message_service: MessageService):
        self.message_service: MessageService = message_service
        self.rtt_camera = 0
        self.fps_decoding = 0
        self.fps_detection = 0
        self.detection_time = 0
        self.send_telemetry_task: asyncio.Task | None = None

    async def start(self):
        self.send_telemetry_task = self._send_statistics()
        await self.send_telemetry_task

    def shutdown(self):
        self.send_telemetry_task.cancel()

    async def _send_statistics(self):
        while True:
            message = {
                'type': 'telemetry',
                'rttCamera': self.rtt_camera,
                'fpsDecoding': self.fps_decoding,
                'fpsDetection': self.fps_detection,
                'detectionTime': self.detection_time
            }
            logging.info(message)
            self.message_service.send_message(Message(message))
            await asyncio.sleep(1)
