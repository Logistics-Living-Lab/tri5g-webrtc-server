import torch
import cv2
import numpy as np
import numpy.typing as npt

from ultralytics import YOLO
from ultralytics.engine.results import Results

from config.app import App
from detector import detector
from typing import Literal


class DetectionService:

    def __init__(self):
        self.device = "cpu"
        self.yolo_model = YOLO(f"{App.root_path}/detector/checkpoints/2024-07-18.pt")
        if torch.cuda.is_available():
            self.device = "cuda:0"
            detector.cuda(device=self.device)

    def detect(self, image, conf_th):
        return detector(image, conf_th=conf_th, device=self.device)

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
            "names" : yolo_result.names,
        }
        return results  # type: ignore[return-value]


