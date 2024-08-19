import cv2
import numpy as np
import numpy.typing as npt
import torch
from torch import Tensor


class ImagePreprocessor:
    def __init__(
            self,
            mean: tuple[float, float, float],
            std: tuple[float, float, float],
            image_size: tuple[int, int] | None,
    ) -> None:
        self.mean = np.array(mean, dtype=np.float32)
        self.std = np.array(std, dtype=np.float32)
        self.image_size = image_size

    def __call__(
            self,
            img: npt.NDArray[np.uint8 | np.float32],
            device: int | str,
    ) -> Tensor:
        img = (img.astype(np.float32) - self.mean) / self.std
        if self.image_size is not None:
            img = cv2.resize(  # type: ignore[assignment]
                img, dsize=self.image_size
            )
        img = img.transpose(2, 0, 1)
        img = np.expand_dims(img, axis=0)  # packing img into batch
        batch = torch.tensor(img, device=device)
        return batch
