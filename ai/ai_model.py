import logging
from abc import ABC


class AiModel(ABC):

    def __init__(self, id: str, model_type: str):
        self.logger = logging.getLogger(__name__)
        self.id = id
        self.model_type = model_type
