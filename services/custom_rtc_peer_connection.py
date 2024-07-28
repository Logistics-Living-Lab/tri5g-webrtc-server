import logging
import time
from typing import Literal

from aiortc import RTCPeerConnection, RTCDataChannel

from services.message import Message


class CustomRTCPeerConnection(RTCPeerConnection):
    def __init__(self, id: str, connection_type: Literal['producer', 'consumer'], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger(__name__)
        self.id = id
        self.connection_type = connection_type
        self.subscriptions = list()
        self.data_channels = dict[str, RTCDataChannel]()
        self.rtt_ms: int | None = None

        self.createDataChannel('telemetry')

    def createDataChannel(
            self,
            label,
            **kwargs,
    ):
        data_channel = super().createDataChannel(label, **kwargs)
        if label == 'telemetry':
            data_channel.on('message', self.__on_telemetry_message)
        self.data_channels[label] = data_channel
        return data_channel

    async def send_rtt_packet(self):
        payload = {
            'timestamp': self.__current_timestamp_millis(),
            'type': 'rtt-packet'
        }
        self.__send_on_telemetry_channel(Message(payload))

    def __current_timestamp_millis(self):
        return time.time_ns() // 1_000_000

    def __on_telemetry_message(self, message_json):
        message = Message.from_json(message_json)
        if message.payload["type"] == "rtt-packet":
            elapsed_ms = self.__current_timestamp_millis() - message.payload["timestamp"]
            self.rtt_ms = elapsed_ms

    async def send_statistics(self, rtt_producer, fps_decoding, fps_detection, detection_time):
        payload = {
            'type': 'telemetry',
            'rttProducer': rtt_producer,
            'rttConsumer': self.rtt_ms,
            'fpsDecoding': fps_decoding,
            'fpsDetection': fps_detection,
            'detectionTime': detection_time
        }
        self.__send_on_telemetry_channel(Message(payload))

    def __send_on_telemetry_channel(self, message: Message):
        if 'telemetry' in self.data_channels:
            telemetry_data_channel = self.data_channels['telemetry']
            if telemetry_data_channel is not None and telemetry_data_channel.readyState == 'open':
                message.payload['connectionId'] = self.id
                telemetry_data_channel.send(message.to_json())
