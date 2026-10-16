from enum import Enum
import numpy as np

from ..utils.load_model import load_model
from .blaze_face import BlazeFace
from .face_mesh import FaceMesh


class SizeMode(Enum):
    DEFAULT = 0
    SQUARE_LONG = 1
    SQUARE_SHORT = 2


def _select_roi_size(
    bbox: np.ndarray, image_size, size_mode: SizeMode 
):
    """
    功能说明：执行当前步骤的核心计算流程，参数语义与边界条件请结合函数体内注释理解。
    """
    width, height = bbox[2] - bbox[0], bbox[3] - bbox[1]
    image_width, image_height = image_size
    if size_mode == SizeMode.SQUARE_LONG:
        long_size = max(width, height)
        width, height = long_size, long_size
    elif size_mode == SizeMode.SQUARE_SHORT:
        short_side = min(width, height)
        width, height = short_side, short_side
    return width, height


def bbox_to_roi(
    bbox: np.ndarray,
    image_size, 
    rotation_keypoints=None,
    scale=(1.0, 1.0), 
    size_mode: SizeMode = SizeMode.SQUARE_LONG,
):
    PI = np.pi
    TWO_PI = 2 * np.pi
   
    width, height = _select_roi_size(bbox, image_size, size_mode)
    scale_x, scale_y = scale
   
    width, height = width * scale_x, height * scale_y
    cx = (bbox[0] + bbox[2]) / 2
    cy = (bbox[1] + bbox[3]) / 2
   
    if rotation_keypoints is None or len(rotation_keypoints) < 2:
        return np.array([cx, cy, width, height, 0])
    x0, y0 = rotation_keypoints[0]
    x1, y1 = rotation_keypoints[1]
    angle = -np.atan2(y0 - y1, x1 - x0)
   
    rotation = angle - TWO_PI * np.floor((angle + PI) / TWO_PI)
    return np.array([cx, cy, width, height, rotation])


class Landmark478:
    def __init__(self, blaze_face_model_path="", face_mesh_model_path="", device="cuda", **kwargs):
        if kwargs.get("force_ori_type", False):
            assert "task_path" in kwargs
            kwargs["module_name"] = "Landmark478"
            kwargs["package_name"] = "..aux_models.modules"
            self.model, self.model_type = load_model("", device=device, **kwargs)
        else:
            self.blaze_face = BlazeFace(blaze_face_model_path, device)
            self.face_mesh = FaceMesh(face_mesh_model_path, device)
            self.model_type = ""

    def get(self, image):
        bboxes = self.blaze_face(image)
        if len(bboxes) == 0:
            return None
        bbox = bboxes[0]
        scale = (image.shape[1] / 128.0, image.shape[0] / 128.0)

       
        #
       
       
       
        #
       
       
       
       
       
       
       
       

        bbox[0] = bbox[0] * scale[1]
        bbox[1] = bbox[1] * scale[0]
        bbox[2] = bbox[2] * scale[1]
        bbox[3] = bbox[3] * scale[0]
        left_eye = (bbox[4], bbox[5])
        right_eye = (bbox[6], bbox[7])

        roi = bbox_to_roi(
            bbox,
            (image.shape[1], image.shape[0]),
            rotation_keypoints=[left_eye, right_eye],
            scale=(1.5, 1.5),
            size_mode=SizeMode.SQUARE_LONG,
        )

        mesh = self.face_mesh(image, roi)
        mesh = mesh / (image.shape[1], image.shape[0], image.shape[1])
        return mesh

    def __call__(self, image):
        if self.model_type == "ori":
            det = self.model.detect_from_npimage(image.copy())
            lmk = self.model.mplmk_to_nplmk(det)
            return lmk
        else:
            lmk = self.get(image)
            lmk = lmk.reshape(1, -1, 3).astype(np.float32)
            return lmk
