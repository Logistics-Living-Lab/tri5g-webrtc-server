import os
from pathlib import Path

import torch
import yaml

from detector.src.detection_module import DetectionModule
from detector.src.utils.preprocessing import ImagePreprocessor

ROOT_DIR = Path(os.path.dirname(__file__)).parent


def load_detector() -> DetectionModule:
    with open(ROOT_DIR / "cfg.yaml") as file:
        config = yaml.safe_load(file)

    image_preprocessor = ImagePreprocessor(**config["transform"])
    detector = DetectionModule(
        image_preprocessor=image_preprocessor,
        **config["model"],
    )
    _load_weights_from_checkpoints(model=detector, **config["paths"])

    detector.eval()
    return detector


def _load_weights_from_checkpoints(
    model: DetectionModule, backbone: Path, head: Path
) -> None:
    backbone_checkpoint = torch.load(ROOT_DIR / str(backbone))
    model.backbone.load_state_dict(backbone_checkpoint)

    head_checkpoint = torch.load(ROOT_DIR / str(head))
    model.head.load_state_dict(head_checkpoint)
