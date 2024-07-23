import abc
from typing import Any

import numpy as np
import numpy.typing as npt
import torch
from torch import Tensor, nn

CHANNELS_KERNEL = tuple[int, int]
LAYERS_ARGS = tuple[CHANNELS_KERNEL, ...]
BLOCK_ARGS = tuple[LAYERS_ARGS, ...]
UNSTRUCTURED_BLOCK_ARGS = list[int | list[int | tuple[int, int]]]


class BaseDetectionHead(nn.Module):
    def __init__(
            self,
            n_classes: int,
            anchors: list[list[tuple[float, float]]] | npt.NDArray[np.float32],
            scale_output_channels: list[int],
    ) -> None:
        super().__init__()
        self.n_classes = n_classes  # number of classes
        self.n_detection_layers = len(
            anchors
        )  # number of detection layers (scales)
        self.n_anchors = len(anchors[0])  # number of anchors
        self.grid = [
            torch.empty(0) for _ in range(self.n_detection_layers)
        ]  # init grid
        self.anchor_grid = [
            torch.empty(0) for _ in range(self.n_detection_layers)
        ]  # init anchor grid
        self.register_buffer(
            "anchors",
            torch.tensor(anchors).float().view(self.n_detection_layers, -1, 2),
        )  # shape(nl,na,2)
        self.scale_output_channels = scale_output_channels

    @abc.abstractmethod
    def forward(self, *args: Any, **kwargs: Any) -> Any:
        pass

    @abc.abstractmethod
    def get_hyperparameters(self) -> dict[str, Any]:
        pass


class YOLOv3Head(BaseDetectionHead):
    # YOLOv3 Detect head for detection models (same as v4 and v5)

    def __init__(
            self,
            n_classes: int,
            anchors: list[list[tuple[float, float]]] | npt.NDArray[np.float32],
            scale_output_channels: list[int],
    ):
        """Initializes YOLOv5 detection layer with specified classes,
        anchors, channels, and inplace operations."""
        super().__init__(
            n_classes=n_classes,
            anchors=anchors,
            scale_output_channels=scale_output_channels,
        )
        self.m = nn.ModuleList(
            nn.Conv2d(ch, (self.n_classes + 5) * self.n_anchors, 1)
            for ch in scale_output_channels
        )  # output conv

    def forward(self, x: list[Tensor]) -> list[Tensor]:
        """Processes input through YOLOv3 layers, altering shape for detection:
        `[x(bs, ny, nx, na, 5+nc)]` by number of detection scales."""
        outputs = []
        for i in range(self.n_detection_layers):
            z: Tensor = self.m[i](x[-self.n_detection_layers + i])
            bs, _, ny, nx = z.shape  # x(bs, na*no, ny, nx)
            z = (
                z.view(bs, self.n_anchors, self.n_classes + 5, ny, nx)
                .permute(0, 3, 4, 1, 2)
                .contiguous()
            )
            z[:, :, :, :, 4] = torch.sigmoid(z[:, :, :, :, 4])
            outputs += [z]

        return outputs

    def get_hyperparameters(self) -> dict[str, Any]:
        return {
            "n_classes": self.n_classes,
            "anchors": self.anchors,
            "scale_output_channels": self.scale_output_channels,
        }
