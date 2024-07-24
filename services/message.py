import json


class Message:
    def __init__(self, payload: dict):
        self.payload = payload

    @staticmethod
    def from_json(message_json: str):
        return Message(json.loads(message_json))

    def to_json(self):
        return json.dumps(self.payload)
