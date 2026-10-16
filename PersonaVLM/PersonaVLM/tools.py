import re
import os

from PIL import Image
from autodistill_grounding_dino import GroundingDINO
from autodistill.detection import CaptionOntology

from PersonaVLM import utils


class DINODetector():
    def __init__(self):
        self.device = 'cuda'
        dummy_ontology = CaptionOntology({"object": "object"})
        self.model = GroundingDINO(ontology=dummy_ontology)

    def detect_and_crop(self, image_path, det_class, obj_count):
        if isinstance(image_path, str):
            image = Image.open(image_path)
        else:
            image = image_path
        self.model.ontology = CaptionOntology({det_class: det_class})
        results = self.model.predict(image)
        results = results[results.confidence > 0.1]

        width, height = image.size
        if len(results.xyxy) == 0:
            return [0, 0, width, height]

        best_box_xyxy = results.xyxy[min(obj_count, len(results)-1)]
        res = best_box_xyxy.astype(int).tolist()
        # 上下文边框外扩15%
        res[0] = max(0, res[0]-width*0.15)
        res[1] = max(0, res[1]-height*0.15)
        res[2] = min(width, res[2]+width*0.15)
        res[3] = min(height, res[3]+height*0.15)
        return res

    def detect_salient_objects(self, image_path):
        if isinstance(image_path, str):
            image = Image.open(image_path)
        else:
            image = image_path
        self.model.ontology = CaptionOntology({"object": "object"})
        results = self.model.predict(image)
        results = results[results.confidence > 0.2]

        bboxes = results.xyxy

        crops = []
        for box in bboxes:
            box_coords = [int(i) for i in box.tolist()]
            cropped_image = image.crop(box_coords)
            crops.append(cropped_image)
        if not crops:
            crops.append(image)
        return crops


def process_semantic_memory_vision_format(semantic_memory):
    semantic_memory["content"] = semantic_memory["content"].replace("(image object:", "(Image Object:")
    semantic_memory["content"] = semantic_memory["content"].replace("(Image object:", "(Image Object:")
    if "image object" in semantic_memory["keywords"]:
        pattern = re.compile(r"\s*\(Image Object: (.*?)\)")
        objects_to_detect = pattern.findall(semantic_memory["content"])
        _object = []
        for obj in objects_to_detect:
            _object.append(obj.split(',')[0].strip())
        objects_to_detect = [i for i in _object if i not in semantic_memory["keywords"]]
        semantic_memory["keywords"] = semantic_memory["keywords"].replace("image object", ",".join(objects_to_detect))
    return semantic_memory


def process_profile_format(profile):
    new_profile = {}
    for key in profile:
        if isinstance(profile[key], dict):
            for sub_key in profile[key]:
                new_profile[sub_key] = profile[key][sub_key]
        else:
            new_profile[key] = profile[key]
    return new_profile


def parse_text_and_extract_objects(text):
    text = text.replace("(image object:", "(Image Object:")
    text = text.replace("(Image object:", "(Image Object:")
    pattern = re.compile(r"\s*\(Image Object: (.*?)\)")
    objects_to_detect = pattern.findall(text)
    modified_text = pattern.sub("<img_fill>", text)
    return modified_text, objects_to_detect


def extract_memory(semantic_memory, save_dir, img_path):
    global _dino_detector_instance
    if _dino_detector_instance is None:
        _dino_detector_instance = DINODetector()

    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    content = semantic_memory["content"]
    modified_text, objects_to_detect = parse_text_and_extract_objects(content)
    _object = []
    for obj in objects_to_detect:
        _object.append(obj.split(',')[0].strip())
    objects_to_detect = _object
    semantic_memory["content"] = modified_text
    semantic_memory["keywords"] = semantic_memory["keywords"].replace("image object", ",".join(objects_to_detect))
    crops = []
    ori_img = Image.open(img_path)
    obj_count = 0
    for idx, obj in enumerate(objects_to_detect):
        if idx > 0 and obj == objects_to_detect[idx-1]:
            obj_count += 1
        else:
            obj_count = 0
        cropped_box = _dino_detector_instance.detect_and_crop(img_path, obj, obj_count)
        # print(cropped_box)
        box = [round(i, 2) for i in cropped_box]
        save_path = os.path.join(save_dir, f"{utils.generate_64bit_id()}.png")
        img = ori_img.crop(box)
        img.save(save_path)
        crops.append(save_path)

    semantic_memory["crops"] = crops
    return semantic_memory

def detect_vision_concept(image_path):
    global _dino_detector_instance
    if _dino_detector_instance is None:
        _dino_detector_instance = DINODetector()
    return _dino_detector_instance.detect_salient_objects(image_path)

_dino_detector_instance = None

