from typing import Literal, List, Dict, Union, Tuple

import numpy as np
import numpy.typing as npt
import torch
from torch import Tensor


def get_mAP_arguments(
    bboxes_matrices: List[Tensor],
    obj_matrices: List[Tensor],
    classes_matrices: List[Tensor],
    anchors: npt.NDArray[np.float32],
    conf_th: Union [float, None] = None,
    n_max_obj: Union [int, None] = None,
) -> List[Dict[Literal["boxes", "scores", "labels"], Tensor]]:
    n_scales = len(obj_matrices)
    batch_size = obj_matrices[0].size(0)
    records: List[Dict[Literal["boxes", "scores", "labels"], List[Tensor]]] = [
        dict(boxes=[], scores=[], labels=[]) for _ in range(batch_size)
    ]

    for scale_id in range(n_scales):
        obj_m = obj_matrices[scale_id].detach()  # .cpu()
        box_m = bboxes_matrices[scale_id].detach()  # .cpu()
        cls_m = classes_matrices[scale_id].detach()  # .cpu()
        for b_id in range(batch_size):
            h, w, na = obj_m[b_id].shape
            # mask selecting anchors
            # h, w, na
            mask = torch.zeros_like(obj_m[b_id]).scatter(
                dim=-1,
                index=obj_m[b_id].argmax(-1, keepdim=True),
                value=True,
            )
            if conf_th is not None:
                mask[obj_m[b_id] < conf_th] = 0

            best_boxes = box_m[b_id, mask == 1]
            best_boxes = best_boxes.view(-1, 4)
            best_boxes = _preds2xywh(
                bboxes=best_boxes,
                mask=mask,
                grid_shape=(h, w),
                scale_id=scale_id,
                anchors=anchors,
            )

            max_scores = obj_m[b_id, mask == 1]
            max_scores = max_scores.view(-1)

            labels = torch.argmax(cls_m[b_id, mask == 1], dim=-1)
            labels = labels.view(-1)

            records[b_id]["boxes"] += [best_boxes]
            records[b_id]["scores"] += [max_scores]
            records[b_id]["labels"] += [labels]

    output: list[dict[Literal["boxes", "scores", "labels"], Tensor]] = [
        {
            "boxes": torch.concat(records[b_id]["boxes"]),
            "scores": torch.concat(records[b_id]["scores"]),
            "labels": torch.concat(records[b_id]["labels"]),
        }
        for b_id in range(batch_size)
    ]

    for b_id in range(batch_size):
        if n_max_obj is not None and output[b_id]["scores"].size(0) > n_max_obj:
            _, indices = torch.topk(
                output[b_id]["scores"], n_max_obj, largest=True, sorted=True
            )
            output[b_id]["boxes"] = output[b_id]["boxes"][indices]
            output[b_id]["labels"] = output[b_id]["labels"][indices]
            output[b_id]["scores"] = output[b_id]["scores"][indices]

    return output


def _preds2xywh(
    bboxes: Tensor,
    mask: Tensor,
    grid_shape: Tuple[int, int],
    scale_id: int,
    anchors: npt.NDArray[np.float32],
) -> Tensor:
    """_summary_

    Parameters
    ----------
    bboxes : Tensor
        n, 4
    indices : Tensor
        n, 2
    grid_shape : tuple[int, int]
        _description_

    Returns
    -------
    Tensor
        _description_
    """
    if bboxes.get_device() == -1:
        device = "cpu"
    else:
        device = f"cuda:{bboxes.get_device()}"

    indices = torch.argwhere(mask == 1)
    xy, wh = bboxes[..., 0:2], bboxes[..., 2:4]
    # Formula for xy
    # (internal_offset + cell_offest) *  scaling_factor
    xy = (xy.sigmoid() + indices[:, :2]) / torch.tensor(
        grid_shape, device=device
    ).view(-1, 2)
    # Formula for wh
    # e^wh * anchor_sizes
    wh = torch.exp(wh) * anchors[scale_id, indices[..., 2]]
    return torch.concat([xy, wh], dim=-1)
