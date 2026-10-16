
"""
工具函数模块：提供预处理、后处理与推理辅助能力。
"""

import numpy as np
import os.path as osp
from math import sin, cos, acos, degrees
import cv2

DTYPE = np.float32
CV2_INTERP = cv2.INTER_LINEAR


def _transform_img(img, M, dsize, flags=CV2_INTERP, borderMode=None):
    """
    功能说明：执行当前步骤的核心计算流程，参数语义与边界条件请结合函数体内注释理解。
    """
    if isinstance(dsize, tuple) or isinstance(dsize, list):
        _dsize = tuple(dsize)
    else:
        _dsize = (dsize, dsize)

    if borderMode is not None:
        return cv2.warpAffine(
            img,
            M[:2, :],
            dsize=_dsize,
            flags=flags,
            borderMode=borderMode,
            borderValue=(0, 0, 0),
        )
    else:
        return cv2.warpAffine(img, M[:2, :], dsize=_dsize, flags=flags)


def _transform_pts(pts, M):
    """
    功能说明：执行当前步骤的核心计算流程，参数语义与边界条件请结合函数体内注释理解。
    """
    return pts @ M[:2, :2].T + M[:2, 2]


def parse_pt2_from_pt101(pt101, use_lip=True):
    """
    功能说明：执行当前步骤的核心计算流程，参数语义与边界条件请结合函数体内注释理解。
    """
   
    pt_left_eye = np.mean(pt101[[39, 42, 45, 48]], axis=0) 
    pt_right_eye = np.mean(pt101[[51, 54, 57, 60]], axis=0) 

    if use_lip:
       
        pt_center_eye = (pt_left_eye + pt_right_eye) / 2
        pt_center_lip = (pt101[75] + pt101[81]) / 2
        pt2 = np.stack([pt_center_eye, pt_center_lip], axis=0)
    else:
        pt2 = np.stack([pt_left_eye, pt_right_eye], axis=0)
    return pt2


def parse_pt2_from_pt106(pt106, use_lip=True):
    """
    功能说明：执行当前步骤的核心计算流程，参数语义与边界条件请结合函数体内注释理解。
    """
    pt_left_eye = np.mean(pt106[[33, 35, 40, 39]], axis=0) 
    pt_right_eye = np.mean(pt106[[87, 89, 94, 93]], axis=0) 

    if use_lip:
       
        pt_center_eye = (pt_left_eye + pt_right_eye) / 2
        pt_center_lip = (pt106[52] + pt106[61]) / 2
        pt2 = np.stack([pt_center_eye, pt_center_lip], axis=0)
    else:
        pt2 = np.stack([pt_left_eye, pt_right_eye], axis=0)
    return pt2


def parse_pt2_from_pt203(pt203, use_lip=True):
    """
    功能说明：执行当前步骤的核心计算流程，参数语义与边界条件请结合函数体内注释理解。
    """
    pt_left_eye = np.mean(pt203[[0, 6, 12, 18]], axis=0) 
    pt_right_eye = np.mean(pt203[[24, 30, 36, 42]], axis=0) 
    if use_lip:
       
        pt_center_eye = (pt_left_eye + pt_right_eye) / 2
        pt_center_lip = (pt203[48] + pt203[66]) / 2
        pt2 = np.stack([pt_center_eye, pt_center_lip], axis=0)
    else:
        pt2 = np.stack([pt_left_eye, pt_right_eye], axis=0)
    return pt2


def parse_pt2_from_pt68(pt68, use_lip=True):
    """
    功能说明：执行当前步骤的核心计算流程，参数语义与边界条件请结合函数体内注释理解。
    """
    lm_idx = np.array([31, 37, 40, 43, 46, 49, 55], dtype=np.int32) - 1
    if use_lip:
        pt5 = np.stack(
            [
                np.mean(pt68[lm_idx[[1, 2]], :], 0), 
                np.mean(pt68[lm_idx[[3, 4]], :], 0), 
                pt68[lm_idx[0], :], 
                pt68[lm_idx[5], :], 
                pt68[lm_idx[6], :], 
            ],
            axis=0,
        )

        pt2 = np.stack([(pt5[0] + pt5[1]) / 2, (pt5[3] + pt5[4]) / 2], axis=0)
    else:
        pt2 = np.stack(
            [
                np.mean(pt68[lm_idx[[1, 2]], :], 0), 
                np.mean(pt68[lm_idx[[3, 4]], :], 0), 
            ],
            axis=0,
        )

    return pt2


def parse_pt2_from_pt5(pt5, use_lip=True):
    """
    功能说明：执行当前步骤的核心计算流程，参数语义与边界条件请结合函数体内注释理解。
    """
    if use_lip:
        pt2 = np.stack([(pt5[0] + pt5[1]) / 2, (pt5[3] + pt5[4]) / 2], axis=0)
    else:
        pt2 = np.stack([pt5[0], pt5[1]], axis=0)
    return pt2


def parse_pt2_from_pt9(pt9, use_lip=True):
    """
    功能说明：执行当前步骤的核心计算流程，参数语义与边界条件请结合函数体内注释理解。
    """
    if use_lip:
        pt9 = np.stack(
            [
                (pt9[2] + pt9[3]) / 2, 
                (pt9[0] + pt9[1]) / 2, 
                pt9[4],
                (pt9[5] + pt9[6]) / 2, 
            ],
            axis=0,
        )
        pt2 = np.stack([(pt9[0] + pt9[1]) / 2, pt9[3]], axis=0) 
    else:
        pt2 = np.stack(
            [
                (pt9[2] + pt9[3]) / 2,
                (pt9[0] + pt9[1]) / 2,
            ],
            axis=0,
        )

    return pt2


def parse_pt2_from_pt_x(pts, use_lip=True):
    if pts.shape[0] == 101:
        pt2 = parse_pt2_from_pt101(pts, use_lip=use_lip)
    elif pts.shape[0] == 106:
        pt2 = parse_pt2_from_pt106(pts, use_lip=use_lip)
    elif pts.shape[0] == 68:
        pt2 = parse_pt2_from_pt68(pts, use_lip=use_lip)
    elif pts.shape[0] == 5:
        pt2 = parse_pt2_from_pt5(pts, use_lip=use_lip)
    elif pts.shape[0] == 203:
        pt2 = parse_pt2_from_pt203(pts, use_lip=use_lip)
    elif pts.shape[0] > 101:
       
        pt2 = parse_pt2_from_pt101(pts[:101], use_lip=use_lip)
    elif pts.shape[0] == 9:
        pt2 = parse_pt2_from_pt9(pts, use_lip=use_lip)
    else:
        raise Exception(f"Unknow shape: {pts.shape}")

    if not use_lip:
       
        v = pt2[1] - pt2[0]
        pt2[1, 0] = pt2[0, 0] - v[1]
        pt2[1, 1] = pt2[0, 1] + v[0]

    return pt2


def parse_rect_from_landmark(
    pts,
    scale=1.5,
    need_square=True,
    vx_ratio=0,
    vy_ratio=0,
    use_deg_flag=False,
    **kwargs,
):
    """
    功能说明：执行当前步骤的核心计算流程，参数语义与边界条件请结合函数体内注释理解。
    """
    pt2 = parse_pt2_from_pt_x(pts, use_lip=kwargs.get("use_lip", True))

    uy = pt2[1] - pt2[0]
    l = np.linalg.norm(uy)
    if l <= 1e-3:
        uy = np.array([0, 1], dtype=DTYPE)
    else:
        uy /= l
    ux = np.array((uy[1], -uy[0]), dtype=DTYPE)

   
   
   
    angle = acos(ux[0])
    if ux[1] < 0:
        angle = -angle

   
    M = np.array([ux, uy])

   
    center0 = np.mean(pts, axis=0)
    rpts = (pts - center0) @ M.T 
    lt_pt = np.min(rpts, axis=0)
    rb_pt = np.max(rpts, axis=0)
    center1 = (lt_pt + rb_pt) / 2

    size = rb_pt - lt_pt
    if need_square:
        m = max(size[0], size[1])
        size[0] = m
        size[1] = m

    size *= scale 
    center = (
        center0 + ux * center1[0] + uy * center1[1]
    ) 
    center = (
        center + ux * (vx_ratio * size) + uy * (vy_ratio * size)
    ) 

    if use_deg_flag:
        angle = degrees(angle)

    return center, size, angle


def parse_bbox_from_landmark(pts, **kwargs):
    center, size, angle = parse_rect_from_landmark(pts, **kwargs)
    cx, cy = center
    w, h = size

   
    bbox = np.array(
        [
            [cx - w / 2, cy - h / 2], 
            [cx + w / 2, cy - h / 2],
            [cx + w / 2, cy + h / 2], 
            [cx - w / 2, cy + h / 2],
        ],
        dtype=DTYPE,
    )

   
    bbox_rot = bbox.copy()
    R = np.array(
        [[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]], dtype=DTYPE
    )

   
    bbox_rot = (bbox_rot - center) @ R.T + center

    return {
        "center": center, 
        "size": size, 
        "angle": angle, 
        "bbox": bbox, 
        "bbox_rot": bbox_rot, 
    }


def crop_image_by_bbox(
    img, bbox, lmk=None, dsize=512, angle=None, flag_rot=False, **kwargs
):
    left, top, right, bot = bbox
    if int(right - left) != int(bot - top):
        print(f"right-left {right-left} != bot-top {bot-top}")
    size = right - left

    src_center = np.array([(left + right) / 2, (top + bot) / 2], dtype=DTYPE)
    tgt_center = np.array([dsize / 2, dsize / 2], dtype=DTYPE)

    s = dsize / size 
    if flag_rot and angle is not None:
        costheta, sintheta = cos(angle), sin(angle)
        cx, cy = src_center[0], src_center[1] 
        tcx, tcy = tgt_center[0], tgt_center[1] 
       
        M_o2c = np.array(
            [
                [s * costheta, s * sintheta, tcx - s * (costheta * cx + sintheta * cy)],
                [
                    -s * sintheta,
                    s * costheta,
                    tcy - s * (-sintheta * cx + costheta * cy),
                ],
            ],
            dtype=DTYPE,
        )
    else:
        M_o2c = np.array(
            [
                [s, 0, tgt_center[0] - s * src_center[0]],
                [0, s, tgt_center[1] - s * src_center[1]],
            ],
            dtype=DTYPE,
        )

   
   

    img_crop = _transform_img(
        img, M_o2c, dsize=dsize, borderMode=kwargs.get("borderMode", None)
    )
    lmk_crop = _transform_pts(lmk, M_o2c) if lmk is not None else None

    M_o2c = np.vstack([M_o2c, np.array([0, 0, 1], dtype=DTYPE)])
    M_c2o = np.linalg.inv(M_o2c)

   

    return {
        "img_crop": img_crop,
        "lmk_crop": lmk_crop,
        "M_o2c": M_o2c,
        "M_c2o": M_c2o,
    }


def _estimate_similar_transform_from_pts(
    pts, dsize, scale=1.5, vx_ratio=0, vy_ratio=-0.1, flag_do_rot=True, **kwargs
):
    """
    功能说明：执行当前步骤的核心计算流程，参数语义与边界条件请结合函数体内注释理解。
    """
    center, size, angle = parse_rect_from_landmark(
        pts,
        scale=scale,
        vx_ratio=vx_ratio,
        vy_ratio=vy_ratio,
        use_lip=kwargs.get("use_lip", True),
    )

    s = dsize / size[0] 
    tgt_center = np.array([dsize / 2, dsize / 2], dtype=DTYPE) 

    if flag_do_rot:
        costheta, sintheta = cos(angle), sin(angle)
        cx, cy = center[0], center[1] 
        tcx, tcy = tgt_center[0], tgt_center[1] 
       
        M_INV = np.array(
            [
                [s * costheta, s * sintheta, tcx - s * (costheta * cx + sintheta * cy)],
                [
                    -s * sintheta,
                    s * costheta,
                    tcy - s * (-sintheta * cx + costheta * cy),
                ],
            ],
            dtype=DTYPE,
        )
    else:
        M_INV = np.array(
            [
                [s, 0, tgt_center[0] - s * center[0]],
                [0, s, tgt_center[1] - s * center[1]],
            ],
            dtype=DTYPE,
        )

    M_INV_H = np.vstack([M_INV, np.array([0, 0, 1])])
    M = np.linalg.inv(M_INV_H)

   
    return M_INV, M[:2, ...]


def crop_image(img, pts: np.ndarray, **kwargs):
    dsize = kwargs.get("dsize", 224)
    scale = kwargs.get("scale", 1.5)  # 1.5 | 1.6
    vy_ratio = kwargs.get("vy_ratio", -0.1)  # -0.0625 | -0.1

    pt_crop_flag = kwargs.get("pt_crop_flag", True)

    M_INV, _ = _estimate_similar_transform_from_pts(
        pts,
        dsize=dsize,
        scale=scale,
        vy_ratio=vy_ratio,
        flag_do_rot=kwargs.get("flag_do_rot", True),
    )

    img_crop = _transform_img(img, M_INV, dsize) 
    if pt_crop_flag:
        pt_crop = _transform_pts(pts, M_INV)
    else:
        pt_crop = None

    M_o2c = np.vstack([M_INV, np.array([0, 0, 1], dtype=DTYPE)])
    M_c2o = np.linalg.inv(M_o2c)

    ret_dct = {
        "M_o2c": M_o2c, 
        "M_c2o": M_c2o, 
        "img_crop": img_crop, 
        "pt_crop": pt_crop, 
    }

    return ret_dct


def average_bbox_lst(bbox_lst):
    if len(bbox_lst) == 0:
        return None
    bbox_arr = np.array(bbox_lst)
    return np.mean(bbox_arr, axis=0).tolist()


def prepare_paste_back(mask_crop, crop_M_c2o, dsize):
    """
    功能说明：执行当前步骤的核心计算流程，参数语义与边界条件请结合函数体内注释理解。
    """
    mask_ori = _transform_img(mask_crop, crop_M_c2o, dsize)
    mask_ori = mask_ori.astype(np.float32) / 255.0
    return mask_ori


def paste_back(img_crop, M_c2o, img_ori, mask_ori):
    """
    功能说明：执行当前步骤的核心计算流程，参数语义与边界条件请结合函数体内注释理解。
    """
    dsize = (img_ori.shape[1], img_ori.shape[0])
    result = _transform_img(img_crop, M_c2o, dsize=dsize)
    result = np.clip(mask_ori * result + (1 - mask_ori) * img_ori, 0, 255).astype(
        np.uint8
    )
    return result
