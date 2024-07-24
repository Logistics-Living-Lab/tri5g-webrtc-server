from typing import Literal

import numpy as np
import numpy.typing as npt
import torch
from ultralytics import YOLO
from ultralytics.engine.results import Results

from config.app_config import AppConfig
from detector import DetectionModule


class DetectionService:

    def __init__(self):
        self.device = "cpu"
        self.yolo_model = YOLO(f"{AppConfig.root_path}/models/{AppConfig.damage_detection_model_file}")
        self.unet_detector: DetectionModule | None = None

    def load_unet_detector(self, model_dir_path, config_file_name="cfg.yaml"):
        self.unet_detector = DetectionModule.load_unet_detector(model_dir_path, config_file_name)
        if torch.cuda.is_available():
            self.device = "cuda:0"
            self.unet_detector.cuda(device=self.device)

    def detect_unet(self, image, conf_th):
        return self.unet_detector.forward(image, conf_th=conf_th, device=self.device)

    def detect_yolo(self, image, conf_th):
        yolo_result = self.yolo_model(image, conf=conf_th)[0]

        # postprocessing output
        results = self.adjust_output(yolo_result)
        return results

    def adjust_output(self, yolo_result: Results) -> dict[
        Literal["boxes", "scores", "labels"], npt.NDArray[np.float32 | np.uint8]
    ]:
        """Returns detected objects as a dict of:
        - denormalized bounding boxes in xyxy format (left top, right bottom),
        - scores - values between 0-1,
        - labels - classes assign to objects.
        """
        results = {
            "boxes": yolo_result.boxes.xyxy.cpu().numpy(),
            "labels": yolo_result.boxes.cls.cpu().numpy(),
            "scores": yolo_result.boxes.conf.cpu().numpy(),
            "names": yolo_result.names,
        }
        return results  # type: ignore[return-value]
