import json

from services.connection_manager import ConnectionManager
from services.message import Message


class MessageService:
    def __init__(self, connection_manager: ConnectionManager):
        self.__connection_manager = connection_manager

    def send_message(self, message: Message):
        for peer_connection in self.__connection_manager.get_consumer_peer_connections():
            for channel in peer_connection.data_channels:
                if channel is not None:
                    channel.send(message.to_json())
