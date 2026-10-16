import numpy as np
import cv2
from ..utils.load_model import load_model


def intersect(box_a, box_b):
    """
    功能说明：执行当前步骤的核心计算流程，参数语义与边界条件请结合函数体内注释理解。
    """
    A = box_a.shape[0]
    B = box_b.shape[0]
    max_xy = np.minimum(
        np.expand_dims(box_a[:, 2:], axis=1).repeat(B, axis=1),
        np.expand_dims(box_b[:, 2:], axis=0).repeat(A, axis=0),
    )
    min_xy = np.maximum(
        np.expand_dims(box_a[:, :2], axis=1).repeat(B, axis=1),
        np.expand_dims(box_b[:, :2], axis=0).repeat(A, axis=0),
    )
    inter = np.clip((max_xy - min_xy), a_min=0, a_max=None)
    return inter[:, :, 0] * inter[:, :, 1]


def jaccard(box_a, box_b):
    """
    功能说明：执行当前步骤的核心计算流程，参数语义与边界条件请结合函数体内注释理解。
    """
    inter = intersect(box_a, box_b)
    area_a = (
        ((box_a[:, 2] - box_a[:, 0]) * (box_a[:, 3] - box_a[:, 1]))
        .reshape(-1, 1)
        .repeat(box_b.shape[0], axis=1)
    ) 
    area_b = (
        ((box_b[:, 2] - box_b[:, 0]) * (box_b[:, 3] - box_b[:, 1]))
        .reshape(1, -1)
        .repeat(box_a.shape[0], axis=0)
    ) 
    union = area_a + area_b - inter
    return inter / union 


def overlap_similarity(box, other_boxes):
    """
    功能说明：执行当前步骤的核心计算流程，参数语义与边界条件请结合函数体内注释理解。
    """
    box = np.expand_dims(box, axis=0) 
    iou = jaccard(box, other_boxes)
    return np.squeeze(iou, axis=0) 


class BlazeFace:
    def __init__(self, model_path, device="cuda"):
        self.anchor_options = {
            "num_layers": 4,
            "min_scale": 0.1484375,
            "max_scale": 0.75,
            "input_size_height": 128,
            "input_size_width": 128,
            "anchor_offset_x": 0.5,
            "anchor_offset_y": 0.5,
            "strides": [8, 16, 16, 16],
            "aspect_ratios": [1.0],
            "reduce_boxes_in_lowest_layer": False,
            "interpolated_scale_aspect_ratio": 1.0,
            "fixed_anchor_size": True,
        }
        self.num_classes = 1
        self.num_anchors = 896
        self.num_coords = 16
        self.x_scale = 128.0
        self.y_scale = 128.0
        self.h_scale = 128.0
        self.w_scale = 128.0
        self.min_score_thresh = 0.5
        self.min_suppression_threshold = 0.3
        self.anchors = self.generate_anchors(self.anchor_options)
        self.anchors = np.array(self.anchors)
        assert len(self.anchors) == 896
        self.model, self.model_type = load_model(model_path, device=device)
        self.output_names = ["regressors", "classificators"]

    def __call__(self, image: np.ndarray):
        """
        功能说明：执行当前步骤的核心计算流程，参数语义与边界条件请结合函数体内注释理解。
        """
        image = cv2.resize(image, (128, 128))
        image = image[np.newaxis, :, :, :].astype(np.float32)
        image = image / 127.5 - 1.0
        outputs = {}
        if self.model_type == "onnx":
            out_list = self.model.run(None, {"input": image})
            for i, name in enumerate(self.output_names):
                outputs[name] = out_list[i]
        elif self.model_type == "tensorrt":
            self.model.setup({"input": image})
            self.model.infer()
            for name in self.output_names:
                outputs[name] = self.model.buffer[name][0]
        else:
            raise ValueError(f"Unsupported model type: {self.model_type}")
        boxes = self.postprocess(outputs["regressors"], outputs["classificators"])
        return boxes

    def calculate_scale(self, min_scale, max_scale, stride_index, num_strides):
        return min_scale + (max_scale - min_scale) * stride_index / (num_strides - 1.0)

    def generate_anchors(self, options):
        strides_size = len(options["strides"])
        assert options["num_layers"] == strides_size

        anchors = []
        layer_id = 0
        while layer_id < strides_size:
            anchor_height = []
            anchor_width = []
            aspect_ratios = []
            scales = []

           
            last_same_stride_layer = layer_id
            while (last_same_stride_layer < strides_size) and (
                options["strides"][last_same_stride_layer]
                == options["strides"][layer_id]
            ):
                scale = self.calculate_scale(
                    options["min_scale"],
                    options["max_scale"],
                    last_same_stride_layer,
                    strides_size,
                )

                if (
                    last_same_stride_layer == 0
                    and options["reduce_boxes_in_lowest_layer"]
                ):
                   
                    aspect_ratios.append(1.0)
                    aspect_ratios.append(2.0)
                    aspect_ratios.append(0.5)
                    scales.append(0.1)
                    scales.append(scale)
                    scales.append(scale)
                else:
                    for aspect_ratio in options["aspect_ratios"]:
                        aspect_ratios.append(aspect_ratio)
                        scales.append(scale)

                    if options["interpolated_scale_aspect_ratio"] > 0.0:
                        scale_next = (
                            1.0
                            if last_same_stride_layer == strides_size - 1
                            else self.calculate_scale(
                                options["min_scale"],
                                options["max_scale"],
                                last_same_stride_layer + 1,
                                strides_size,
                            )
                        )
                        scales.append(np.sqrt(scale * scale_next))
                        aspect_ratios.append(options["interpolated_scale_aspect_ratio"])

                last_same_stride_layer += 1

            for i in range(len(aspect_ratios)):
                ratio_sqrts = np.sqrt(aspect_ratios[i])
                anchor_height.append(scales[i] / ratio_sqrts)
                anchor_width.append(scales[i] * ratio_sqrts)

            stride = options["strides"][layer_id]
            feature_map_height = int(np.ceil(options["input_size_height"] / stride))
            feature_map_width = int(np.ceil(options["input_size_width"] / stride))

            for y in range(feature_map_height):
                for x in range(feature_map_width):
                    for anchor_id in range(len(anchor_height)):
                        x_center = (x + options["anchor_offset_x"]) / feature_map_width
                        y_center = (y + options["anchor_offset_y"]) / feature_map_height

                        new_anchor = [x_center, y_center, 0, 0]
                        if options["fixed_anchor_size"]:
                            new_anchor[2] = 1.0
                            new_anchor[3] = 1.0
                        else:
                            new_anchor[2] = anchor_width[anchor_id]
                            new_anchor[3] = anchor_height[anchor_id]
                        anchors.append(new_anchor)

            layer_id = last_same_stride_layer

        return anchors

    def _tensors_to_detections(self, raw_box_tensor, raw_score_tensor, anchors):
        """
        功能说明：执行当前步骤的核心计算流程，参数语义与边界条件请结合函数体内注释理解。
        """
        assert raw_box_tensor.ndim == 3
        assert raw_box_tensor.shape[1] == self.num_anchors
        assert raw_box_tensor.shape[2] == self.num_coords

        assert raw_score_tensor.ndim == 3
        assert raw_score_tensor.shape[1] == self.num_anchors
        assert raw_score_tensor.shape[2] == self.num_classes

        assert raw_box_tensor.shape[0] == raw_score_tensor.shape[0]

        detection_boxes = self._decode_boxes(raw_box_tensor, anchors)

        raw_score_tensor = np.clip(raw_score_tensor, -50, 100)
        detection_scores = 1 / (1 + np.exp(-raw_score_tensor))
        mask = detection_scores >= self.min_score_thresh
        mask = mask[0, :, 0]
        boxes = detection_boxes[0, mask, :]
        scores = detection_scores[0, mask, :]
        return np.concatenate((boxes, scores), axis=-1)

    def _decode_boxes(self, raw_boxes, anchors):
        """
        功能说明：执行当前步骤的核心计算流程，参数语义与边界条件请结合函数体内注释理解。
        """
        boxes = np.zeros_like(raw_boxes)

        x_center = raw_boxes[..., 0] / self.x_scale * anchors[:, 2] + anchors[:, 0]
        y_center = raw_boxes[..., 1] / self.y_scale * anchors[:, 3] + anchors[:, 1]

        w = raw_boxes[..., 2] / self.w_scale * anchors[:, 2]
        h = raw_boxes[..., 3] / self.h_scale * anchors[:, 3]

        boxes[..., 0] = self.x_scale * (x_center - w / 2.0) 
        boxes[..., 1] = self.y_scale * (y_center - h / 2.0) 
        boxes[..., 2] = self.w_scale * (x_center + w / 2.0) 
        boxes[..., 3] = self.h_scale * (y_center + h / 2.0) 

        for k in range(6):
            offset = 4 + k * 2
            keypoint_x = (
                raw_boxes[..., offset] / self.x_scale * anchors[:, 2] + anchors[:, 0]
            )
            keypoint_y = (
                raw_boxes[..., offset + 1] / self.y_scale * anchors[:, 3]
                + anchors[:, 1]
            )
            boxes[..., offset] = keypoint_x
            boxes[..., offset + 1] = keypoint_y

        return boxes

    def _weighted_non_max_suppression(self, detections):
        """
        功能说明：执行当前步骤的核心计算流程，参数语义与边界条件请结合函数体内注释理解。
        """
        if len(detections) == 0:
            return []

        output_detections = []

       
        remaining = np.argsort(detections[:, 16])[::-1]

        while len(remaining) > 0:
            detection = detections[remaining[0]]

           
           
           
            first_box = detection[:4]
            other_boxes = detections[remaining, :4]
            ious = overlap_similarity(first_box, other_boxes)

           
           
            mask = ious > self.min_suppression_threshold
            overlapping = remaining[mask]
            remaining = remaining[~mask]

           
           
            weighted_detection = detection.copy()
            if len(overlapping) > 1:
                coordinates = detections[overlapping, :16]
                scores = detections[overlapping, 16:17]
                total_score = scores.sum()
                weighted = (coordinates * scores).sum(axis=0) / total_score
                weighted_detection[:16] = weighted
                weighted_detection[16] = total_score / len(overlapping)

            output_detections.append(weighted_detection)

        return output_detections

    def postprocess(self, raw_boxes, scores):
        detections = self._tensors_to_detections(raw_boxes, scores, self.anchors)

        detections = self._weighted_non_max_suppression(detections)
        detections = np.array(detections)
        return detections


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="")
    parser.add_argument("--image", type=str, default=None)
    args = parser.parse_args()

    blaze_face = BlazeFace(args.model)
    image = cv2.imread(args.image)
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    image = cv2.resize(image, (128, 128))
    image = image[np.newaxis, :, :, :].astype(np.float32)
    image = image / 127.5 - 1.0
    boxes = blaze_face(image)
    print(boxes)
