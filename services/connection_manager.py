import asyncio
import json
import logging
import uuid
from typing import Literal

from aiohttp import web
from aiortc import RTCPeerConnection, RTCConfiguration, RTCIceServer, RTCDataChannel, RTCRtpSender
from aiortc.contrib.media import MediaRelay
from memory_profiler import memory_usage

from services.custom_rtc_peer_connection import CustomRTCPeerConnection


class ConnectionManager:
    MAX_PRODUCER_CONNECTIONS = 1
    STUN_SERVERS = "ec2-15-145-19-244.eu-central-1.compute.amazonaws.com:3478"

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.__peer_connections_producer = list[CustomRTCPeerConnection]()
        self.__peer_connections_consumer = list[CustomRTCPeerConnection]()
        self.media_relay: MediaRelay = MediaRelay()

    def get_consumer_peer_connections(self):
        return self.__peer_connections_consumer

    def get_all_connections(self):
        return self.__peer_connections_consumer + self.__peer_connections_producer

    def register_peer_connection(self, peer_connection: CustomRTCPeerConnection):
        if peer_connection.connection_type == "consumer":
            self.__peer_connections_consumer.append(peer_connection)
        elif peer_connection.connection_type == "producer":
            self.__peer_connections_producer.append(peer_connection)
        self.__print_connections_info()

    def unregister_peer_connection(self, peer_connection: CustomRTCPeerConnection):
        if peer_connection.connection_type == "consumer":
            self.__peer_connections_consumer.remove(peer_connection)
        elif peer_connection.connection_type == "producer":
            self.__peer_connections_producer.remove(peer_connection)
        self.__print_connections_info()

    async def shutdown(self):
        all_connections = self.__peer_connections_consumer + self.__peer_connections_producer
        await asyncio.gather(*[peer_connection.close() for peer_connection in all_connections])
        self.__peer_connections_producer.clear()
        self.__peer_connections_consumer.clear()

    def is_producer_connection_limit_reached(self) -> bool:
        return len(self.__peer_connections_producer) >= ConnectionManager.MAX_PRODUCER_CONNECTIONS

    def create_peer_connection(self, connection_type: Literal['producer', 'consumer']) -> CustomRTCPeerConnection:
        configuration = RTCConfiguration(
            iceServers=[RTCIceServer(urls=ConnectionManager.STUN_SERVERS)]
        )
        peer_connection = CustomRTCPeerConnection(id=str(uuid.uuid4()), connection_type=connection_type,
                                                  configuration=configuration)
        self.__register_connection_state_change_listener(peer_connection)
        self.__register_peer_connection_incoming_data_channel_listener(peer_connection)
        self.register_peer_connection(peer_connection)
        return peer_connection

    async def create_sdp_response_for_peer_connection(self, peer_connection: CustomRTCPeerConnection):
        answer = await peer_connection.createAnswer()
        await peer_connection.setLocalDescription(answer)

        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"sdp": peer_connection.localDescription.sdp, "type": peer_connection.localDescription.type}
            ),
        )

    def __register_connection_state_change_listener(self, peer_connection: CustomRTCPeerConnection):
        @peer_connection.on('connectionstatechange')
        async def on_connection_state_change():
            self.logger.info(
                f"Peer Connection: {peer_connection.id} - Connection state: {peer_connection.connectionState}")
            if peer_connection.connectionState == "closed" or peer_connection.connectionState == "failed":
                await peer_connection.close()
                self.unregister_peer_connection(peer_connection)

        @peer_connection.on('iceConnectionState')
        async def on_ice_connection_state_change():
            self.logger.info(
                f"Peer Connection: {peer_connection.id} - ICE Connection state: {peer_connection.iceConnectionState}")

    def __register_peer_connection_incoming_data_channel_listener(self, peer_connection: CustomRTCPeerConnection):
        @peer_connection.on("datachannel")
        def on_datachannel(channel: RTCDataChannel):
            self.__register_data_channel_listeners(peer_connection, channel)

    def get_primary_producer_connection(self):
        if len(self.__peer_connections_producer) == 0:
            return None
        return self.__peer_connections_producer[0]

    def __print_connections_info(self):
        self.logger.info(f"Producers: {len(self.__peer_connections_producer)}")
        self.logger.info(f"Consumers: {len(self.__peer_connections_consumer)}")

    def __register_data_channel_listeners(self, peer_connection, channel):
        @channel.on("open")
        def on_channel_open():
            self.logger.info(f"Peer Connection: {peer_connection.id} - Data channel {channel.label} - open")
            peer_connection.data_channels[channel.label] = channel

        @channel.on("close")
        def on_channel_close():
            self.logger.info(f"Peer Connection: {peer_connection.id} - Data channel {channel.label} - close")
            peer_connection.data_channels.pop(channel.label)

        # If datachannel is initiated by remote peer - it is already open - handler has to be called manually
        if channel.readyState == 'open':
            on_channel_open()

    @staticmethod
    def force_codec(pc, forced_codec):
        codecs = RTCRtpSender.getCapabilities('video').codecs
        h264_codecs = [codec for codec in codecs if codec.mimeType == forced_codec]
        if len(h264_codecs) == 0:
            logging.info("No H264 codecs found.")
            return

        for transceiver in pc.getTransceivers():
            if transceiver.kind == "video":
                transceiver.setCodecPreferences(h264_codecs)
