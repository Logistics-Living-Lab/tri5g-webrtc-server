import asyncio
from functools import partial
from typing import Literal

import cv2
import numpy as np
import numpy.typing as npt
import torch
from ultralytics import YOLO
from ultralytics.engine.results import Results

from ai.ai_model import AiModel
from detector import load_segmentator


class UnetModel(AiModel):

    def __init__(self, model_id: str, model_name: str, model_config_file: str):
        super().__init__(model_id, model_name, 'unet')
        self.model_config_file = ""
        self.detector = None
        self.segmentator = None
        self.device = "cpu"
        cls2bgr = {
            1: (255, 221, 51),  # wire
            2: (195, 177, 241),  # post
            3: (49, 147, 245),  # tensioner
            4: (102, 255, 102),  # other
        }
        self.__load_segmentator(cls2bgr=cls2bgr, model_config_file=model_config_file)

    def __load_segmentator(self, cls2bgr, model_config_file):
        self.segmentator = load_segmentator(model_config_file, cls2bgr=cls2bgr)
        if torch.cuda.is_available():
            self.device = "cuda:0"
            self.segmentator.to(self.device)

        self.logger.info(f"Loaded UNet model: {model_config_file}")

    def detect_yolo(self, image):
        result = self.segmentator(image, device=self.device)
        return result

    async def detect_yolo_as_image(self, img, font_scale=1, thickness=2):
        resized_img = cv2.resize(img, (960, 960))
        detection_result = await asyncio.to_thread(
            partial(self.detect_yolo, image=resized_img)
        )
        return detection_result
