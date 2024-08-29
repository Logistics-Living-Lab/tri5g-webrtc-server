import asyncio
import json
import logging
import os.path
from functools import partial
from typing import Literal

import cv2
import numpy as np
import numpy.typing as npt
import torch
from ultralytics import YOLO
from ultralytics.engine.results import Results

from ai.unet_model import UnetModel
from ai.yolo_model import YoloModel
from config.app_config import AppConfig
from detector import DetectionModule


class DetectionService:

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.device = "cpu"
        self.unet_detector: DetectionModule | None = None
        self.models = []

    def get_model_by_id(self, model_id: str):
        return next((model for model in self.models if model.model_id == model_id), None)

    def load_models(self):
        with open(os.path.join(AppConfig.root_path, 'model-config.json'), 'r') as file:
            data = json.load(file)
            for model_config in data:
                if model_config['type'] == 'yolo':
                    self.models.append(
                        YoloModel(
                            model_config['id'],
                            model_config['name'],
                            os.path.join(AppConfig.root_path, model_config['path']))
                    )
                elif model_config['type'] == 'unet':
                    self.models.append(
                        UnetModel(
                            model_config['id'],
                            model_config['name'],
                            os.path.join(AppConfig.root_path, model_config['path']))
                    )

    def load_unet_detector(self, model_dir_path, config_file_name="cfg.yaml"):
        self.unet_detector = DetectionModule.load_unet_detector(model_dir_path, config_file_name)
        if torch.cuda.is_available():
            self.device = "cuda:0"
            self.unet_detector.cuda(device=self.device)
        self.logger.info(f"Loaded unet model config: {model_dir_path}/{config_file_name}")

    def detect_unet(self, image, conf_th):
        return self.unet_detector.forward(image, conf_th=conf_th, device=self.device)
