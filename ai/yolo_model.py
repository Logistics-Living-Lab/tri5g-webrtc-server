import asyncio
from functools import partial
from typing import Literal

import cv2
import numpy as np
import numpy.typing as npt
from ultralytics import YOLO
from ultralytics.engine.results import Results

from ai.ai_model import AiModel


class YoloModel(AiModel):

    def __init__(self, model_id: str, model_file_path: str, conf_th: float = 0.5):
        super().__init__(model_id, 'yolo')
        self.yolo_model: YOLO | None = None
        self.conf_th = conf_th
        self.__load_yolo(model_file_path)

    def __load_yolo(self, model_file_path: str):
        self.yolo_model = YOLO(model_file_path, task='detect', verbose=False)
        self.logger.info(f"Loaded YOLO model: {model_file_path}")

    def detect_yolo(self, image, conf_th):
        yolo_result = self.yolo_model.predict(image, conf=conf_th, verbose=False)[0]

        # postprocessing output
        results = self.__adjust_output(yolo_result)
        return results

    def __adjust_output(self, yolo_result: Results) -> dict[
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

    async def detect_yolo_as_image(self, img, font_scale=1, thickness=2):
        resized_img = cv2.resize(img, (960, 960))
        detection_result = await asyncio.to_thread(
            partial(self.detect_yolo, image=resized_img, conf_th=self.conf_th)
        )
        # detection_result = await self.detect_yolo(image=resized_img, conf_th=self.conf_th)

        boxes = detection_result["boxes"]
        for index, box in enumerate(boxes):
            label = detection_result["names"][detection_result["labels"][index]]
            score = round(detection_result['scores'][index] * 100.0)
            self.logger.info(f"Detected: {label} - {score}")

            width_factor = img.shape[1] / resized_img.shape[1]
            height_factor = img.shape[0] / resized_img.shape[0]

            cv2.rectangle(img,
                          (int(box[0] * width_factor), int(box[1] * height_factor)),
                          (int(box[2] * width_factor), int(box[3] * height_factor)),
                          (0, 255, 0), thickness)
            cv2.putText(img,
                        f"{label} - {score}%",
                        (int(box[0] * width_factor), int(box[1] * height_factor) - 10), cv2.FONT_HERSHEY_SIMPLEX,
                        font_scale,
                        (0, 255, 0), thickness)
        return img
