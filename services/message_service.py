import json

from services.message import Message


class MessageService:
    def __init__(self):
        self.channel = None

    def send_message(self, message: Message):
        self.channel.send(message.to_json())
