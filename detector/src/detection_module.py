from typing import Any, Literal

import numpy as np
import numpy.typing as npt
import torch
from torch import Tensor, nn

from detector.src.nn.detection_head import YOLOv3Head
from detector.src.utils.map import get_mAP_arguments
from detector.src.utils.preprocessing import ImagePreprocessor

from .nn.unet_backbone import (
    UNSTRUCTURED_BLOCK_ARGS,
    UnetEncoder,
    standarize_blocks_args,
)


class DetectionModule(nn.Module):
    def __init__(
            self,
            n_channels: int,
            blocks_args: UNSTRUCTURED_BLOCK_ARGS,
            n_classes: int,
            image_preprocessor: ImagePreprocessor,
            anchors: list[list[tuple[float, float]]] | npt.NDArray[np.float32],
            scale_output_channels: list[int],
            backbone_output_key: str | None = None,
    ) -> None:
        super().__init__()
        self.image_preprocessor = image_preprocessor
        self.backbone_output_key = backbone_output_key

        # backbone setup
        encoder_blocks = standarize_blocks_args(blocks_args)
        self.backbone = UnetEncoder(
            n_channels=n_channels, blocks_args=encoder_blocks
        )

        # detection head setup
        self.head = YOLOv3Head(
            n_classes=n_classes,
            anchors=anchors,
            scale_output_channels=scale_output_channels,
        )

    def forward(
            self,
            img: npt.NDArray[np.uint8],
            conf_th: float | None = None,
            device: int | str = "cpu",
    ) -> list[
        dict[
            Literal["boxes", "scores", "labels"],
            npt.NDArray[np.float32 | np.uint8],
        ]
    ]:
        batch = self.image_preprocessor(img=img, device=device)
        with torch.no_grad():
            bboxes, objectness, classes = self._forward_batch(batch)
        map_result = get_mAP_arguments(
            bboxes_matrices=bboxes,
            obj_matrices=objectness,
            classes_matrices=classes,
            conf_th=conf_th,
            anchors=self.head.anchors,
        )

        return _mAP2numpy(map_result)

    def _forward_batch(
            self, *args: Any, **kwargs: Any
    ) -> tuple[list[Tensor], list[Tensor], list[Tensor]]:
        if self.backbone_output_key is None:
            feature_map = self.backbone(*args, **kwargs)
        else:
            feature_map = self.backbone(*args, **kwargs)[
                self.backbone_output_key
            ]
        if isinstance(feature_map, Tensor):
            result = self.head([feature_map])
        else:
            result = self.head(feature_map)
        bboxes = [scale_result[..., :4] for scale_result in result]
        objectness = [scale_result[..., 4] for scale_result in result]
        classes = [scale_result[..., 5:] for scale_result in result]
        return bboxes, objectness, classes


def _mAP2numpy(
        map_result: list[
            dict[
                Literal["boxes", "scores", "labels"],
                Tensor,
            ]
        ],
) -> list[
    dict[
        Literal["boxes", "scores", "labels"],
        npt.NDArray[np.float32 | np.uint8],
    ]
]:
    map_np_result = [
        {key: val.cpu().numpy() for key, val in r.items()} for r in map_result
    ]
    return map_np_result
