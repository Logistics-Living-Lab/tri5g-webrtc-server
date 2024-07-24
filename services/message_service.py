import json

from services.message import Message


class MessageService:
    def __init__(self):
        self.channel = None

    def send_message(self, message: Message):
        if self.channel is not None:
            self.channel.send(message.to_json())
