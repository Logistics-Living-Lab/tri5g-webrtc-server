import logging
from abc import ABC


class AiModel(ABC):

    def __init__(self, model_id: str, model_name: str, model_type: str):
        self.logger = logging.getLogger(__name__)
        self.model_id = model_id
        self.model_name = model_name
        self.model_type = model_type
