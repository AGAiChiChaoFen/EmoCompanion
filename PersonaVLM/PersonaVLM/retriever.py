import os, time
import random

import faiss
import numpy as np
from PIL import Image
from sentence_transformers import SentenceTransformer
from transformers import CLIPTextModel, CLIPVisionModel, CLIPModel, CLIPProcessor

from PersonaVLM import tools
from PersonaVLM import utils


def read_fasis(path):
    for _ in range(5):
        try:
            return faiss.read_index(path)
        except Exception as e:
            # print(f"Error reading index {path}: {e}")
            wait_time = 0.1 + random.uniform(0, 1)
            time.sleep(wait_time)
    raise Exception(f"Failed to read index {path}")

class Retriever:
    def __init__(self, save_dir,
                 maximum_semantic_memory_num=4,
                 maximum_episodic_memory_num=2,
                 maximum_procedural_memory=2,
                 maximum_vision_memory=2):

        self.maximum_semantic_memory_num = maximum_semantic_memory_num
        self.maximum_episodic_memory_num = maximum_episodic_memory_num
        self.maximum_procedural_memory = maximum_procedural_memory
        self.maximum_vision_memory = maximum_vision_memory

        self.semantic_memory_idx = []
        self.episodic_memory_idx = []
        self.procedural_memory_idx = []

        self.text_emb_dim = 384
        self.img_emb_dim = 768

        self.save_path = os.path.join(save_dir, "emb")
        os.makedirs(self.save_path, exist_ok=True)

        self.episodic_keywords_index_file_path = os.path.join(self.save_path , "episodic_keywords.faiss")
        if os.path.exists(self.episodic_keywords_index_file_path):
            self.episodic_keywords_index = read_fasis(self.episodic_keywords_index_file_path)
        else:
            self.episodic_keywords_index = faiss.IndexFlatL2(self.text_emb_dim)
        self.episodic_content_index_file_path = os.path.join(self.save_path , "episodic_content.faiss")
        if os.path.exists(self.episodic_content_index_file_path):
            self.episodic_content_index = read_fasis(self.episodic_content_index_file_path)
        else:
            self.episodic_content_index = faiss.IndexFlatL2(self.text_emb_dim)
        
        self.semantic_keywords_index_file_path = os.path.join(self.save_path , "semantic_keywords.faiss")
        if os.path.exists(self.semantic_keywords_index_file_path):
            self.semantic_keywords_index = read_fasis(self.semantic_keywords_index_file_path)
        else:
            self.semantic_keywords_index = faiss.IndexFlatL2(self.text_emb_dim)
        self.semantic_content_index_file_path = os.path.join(self.save_path , "semantic_content.faiss")
        if os.path.exists(self.semantic_content_index_file_path):
            self.semantic_content_index = read_fasis(self.semantic_content_index_file_path)
        else:
            self.semantic_content_index = faiss.IndexFlatL2(self.text_emb_dim)
        
        self.vision_index_file_path = os.path.join(self.save_path , "vision.faiss")
        if os.path.exists(self.vision_index_file_path):
            self.vision_index = read_fasis(self.vision_index_file_path)
        else:
            self.vision_index = faiss.IndexFlatL2(self.img_emb_dim)

        self.procedural_index_file_path = os.path.join(self.save_path , "procedural.faiss")
        if os.path.exists(self.procedural_index_file_path):
            self.procedural_index = read_fasis(self.procedural_index_file_path)
        else:
            self.procedural_index = faiss.IndexFlatL2(self.text_emb_dim)

    def reset_index(self):
        self.semantic_memory_idx = []
        self.episodic_memory_idx = []
        self.procedural_memory_idx = []
        
    def retrieve_episodic_memory(self, query, keywords, sessions, retrieve_info, interval_time, time):
        if self.maximum_episodic_memory_num <= 0:
            return []
        exist_num_1 = self.episodic_keywords_index.ntotal
        exist_num_2 = self.episodic_content_index.ntotal
        count = 0
        result = []

        if retrieve_info["start_time"] or retrieve_info["end_time"]:
            if not retrieve_info["start_time"] or (not retrieve_info["start_time"].startswith('202')):
                retrieve_info["start_time"] = "2022-01-01 00:00"
            if not retrieve_info["end_time"] or (not retrieve_info["end_time"].startswith('202')):
                retrieve_info["end_time"] = utils.datetime_add_minutes(time, -interval_time)
        for idx1, session in enumerate(sessions):
            if "EpisodicMemory" in session and len(session["EpisodicMemory"]) > 0:
                for idx2, sess_mem in enumerate(session["EpisodicMemory"]):
                    count += 1
                    result.append([idx1, idx2])
                    if count > exist_num_1:
                        self.episodic_keywords_index.add(get_text_embedding(sess_mem["keywords"]))
                    if count > exist_num_2:
                        self.episodic_content_index.add(get_text_embedding(sess_mem["topic_summary"]))

                    assert sess_mem["source_dialog_indices"]
                    start_time = session["interactions"][sess_mem["source_dialog_indices"][0]][0]["time"]
                    end_time = session["interactions"][sess_mem["source_dialog_indices"][-1]][0]["time"]
                    if (retrieve_info["start_time"] and retrieve_info["end_time"]) and \
                        (utils.compare_time_strings(retrieve_info["start_time"] , end_time) > 0 or \
                        utils.compare_time_strings(retrieve_info["end_time"], start_time) < 0):
                        continue
                    assert utils.compare_time_strings(start_time, end_time) <= 0
                    
        dists_1, I_1 = self.episodic_keywords_index.search(get_text_embedding(keywords), self.maximum_episodic_memory_num)        
        dists_2, I_2 = self.episodic_content_index.search(get_text_embedding(query.replace("<img_fill>", "")), self.maximum_episodic_memory_num)
        faiss.write_index(self.episodic_keywords_index, self.episodic_keywords_index_file_path)
        faiss.write_index(self.episodic_content_index, self.episodic_content_index_file_path)
        candidates = {}
        all_indices = np.concatenate((I_1[0], I_2[0]))
        all_dists = np.concatenate((dists_1[0], dists_2[0]))
        for idx, dist in zip(all_indices, all_dists):
            if idx < 0 or idx >= len(result):
                continue
            if idx in candidates:
                candidates[idx] = min(candidates[idx], dist)
            else:
                candidates[idx] = dist
        sorted_candidates = sorted(candidates.items(), key=lambda item: item[1])
        final_indices = [idx for idx, _ in sorted_candidates[:self.maximum_episodic_memory_num]]
        episodic_memory = []
        for idx in final_indices:
            tmp = result[idx]
            episodic_memory += [[tmp[0], j] for j in sessions[tmp[0]]["EpisodicMemory"][tmp[1]]["source_dialog_indices"]]
        return episodic_memory

    def retrieve_semantic_memory(self, query, keywords, sessions):
        if self.maximum_semantic_memory_num <= 0:
            return []
        exist_num_1 = self.semantic_keywords_index.ntotal
        exist_num_2 = self.semantic_content_index.ntotal
        count = 0
        result = []
        for idx1, session in enumerate(sessions):
            if "semantic_memory" in session and len(session["semantic_memory"]) > 0:
                for idx2, key_mem in enumerate(session["semantic_memory"]):
                    if key_mem["decision"]:
                        count += 1
                        result.append([idx1, idx2])
                        if count > exist_num_1:
                            self.semantic_keywords_index.add(get_text_embedding(key_mem["keywords"]))
                        if count > exist_num_2:
                            self.semantic_content_index.add(get_text_embedding(key_mem["content"].replace("<img_fill>", "").strip()))

        dists_1, I_1 = self.semantic_keywords_index.search(get_text_embedding(keywords), self.maximum_semantic_memory_num)
        faiss.write_index(self.semantic_keywords_index, self.semantic_keywords_index_file_path)
        dists_2, I_2 = self.semantic_content_index.search(get_text_embedding(query.replace("<img_fill>", "")), self.maximum_semantic_memory_num)
        faiss.write_index(self.semantic_content_index, self.semantic_content_index_file_path)

        candidates = {}
        all_indices = np.concatenate((I_1[0], I_2[0]))
        all_dists = np.concatenate((dists_1[0], dists_2[0]))
        for idx, dist in zip(all_indices, all_dists):
            if idx < 0 or idx >= len(result):
                continue
            if idx in candidates:
                candidates[idx] = min(candidates[idx], dist)
            else:
                candidates[idx] = dist
        sorted_candidates = sorted(candidates.items(), key=lambda item: item[1])
        final_indices = [idx for idx, _ in sorted_candidates[:self.maximum_semantic_memory_num]]
        
        semantic_memory = []
        for idx in final_indices:
            semantic_memory.append(result[idx])
        return semantic_memory


    def retrieve_vision_memory(self, query, data):
        if "<img_fill>" not in query or self.maximum_vision_memory <=0:
            return []

        crops = tools.detect_vision_concept(data["imgs"][-1])
        
        exist_num = self.vision_index.ntotal
        count = 0
        result = []
        for idx1, session in enumerate(data["sessions"]):
            if "semantic_memory" in session and len(session["semantic_memory"]) > 0:
                for idx2, key_mem in enumerate(session["semantic_memory"]):
                    if key_mem["decision"] and "<img_fill>" in key_mem["content"]:
                        for img_path in key_mem["crops"]:
                            count += 1
                            result.append([idx1, idx2])
                            if count > exist_num:
                                self.vision_index.add(get_vision_embedding(img_path))
        crop_feature = np.array([get_vision_embedding(crop) for crop in crops]).squeeze(1)
        dists, I = self.vision_index.search(crop_feature, 1)
        faiss.write_index(self.vision_index, self.vision_index_file_path)

        candidates = {}
        for l in range(len(crops)):
            for idx, dist in zip(I[l], dists[l]):
                if idx < 0 or idx >= len(result):
                    continue
                if idx in candidates:
                    candidates[idx] = min(candidates[idx], dist)
                else:
                    if dist < 1.0:
                        candidates[idx] = dist
                    
        sorted_candidates = sorted(candidates.items(), key=lambda item: item[1])
        final_indices = [idx for idx, _ in sorted_candidates[:self.maximum_vision_memory]]
        vision_memory = []
        for idx in final_indices:
            vision_memory.append(result[idx])
        return vision_memory
    
    def retrieve_procedural_memory(self, query, data):
        if self.maximum_procedural_memory <=0:
            return []
        procedural_memory = None
        for _, session in enumerate(data["sessions"]):
            if "ProceduralMemory" in session:
                procedural_memory = session["ProceduralMemory"]
        if not procedural_memory:
            return []
        if self.procedural_index.ntotal > 0:
            self.procedural_index.reset()
        contents = []
        for key, value in procedural_memory.items():
            content = f"{key}: {value}"
            contents.append(content)
            self.procedural_index.add(get_text_embedding(content))
        dists_1, I_1 = self.procedural_index.search(get_text_embedding(query.replace("<img_fill>", "")), self.maximum_procedural_memory)
        # 获取对应的索引
        results = []
        for idx in I_1[0]:
            if idx != -1 and idx < len(contents):  # 避免无效索引
                if idx in self.procedural_memory_idx:
                    continue
                self.procedural_memory_idx.append(idx)
                results.append(contents[idx])
        return results


    def retrieve(self, query, retrieve_info, data, interval_time, reset=True, maximum_episodic_memory_num=2, maximum_semantic_memory_num=4):
        if (not retrieve_info) or (not retrieve_info["retrieve"]) or ("sessions" not in data ):
            return {"semantic_memory": [], "semantic_memory_imgs": [], "episodic_memory": [], "episodic_memory_imgs": [], "procedural_memory": []}
        
        self.maximum_episodic_memory_num = maximum_episodic_memory_num
        self.maximum_semantic_memory_num = maximum_semantic_memory_num
        idx_his_memory = self.retrieve_episodic_memory(query["query"], retrieve_info["keywords"], data["sessions"], retrieve_info, interval_time, query["time"])
        idx_semantic_memory = []

        idx_semantic_memory += self.retrieve_semantic_memory(query["query"], retrieve_info["keywords"], data["sessions"])
        idx_semantic_memory += self.retrieve_vision_memory(query["query"], data)

        idx_his_memory = sorted(set(tuple(x) for x in idx_his_memory))
        idx_his_memory = self.select_memory(query, idx_his_memory, data["sessions"], interval_time)
        idx_semantic_memory = sorted(set(tuple(x) for x in idx_semantic_memory))
        idx_semantic_memory = self.select_memory(query, idx_semantic_memory, data["sessions"], interval_time)

        semantic_memory = []
        semantic_memory_imgs = []
        for item in idx_semantic_memory:
            if item in self.semantic_memory_idx:
                continue
            self.semantic_memory_idx.append(item)
                
            i, j = item
            time = data["sessions"][i]["interactions"][j][0]["time"]
            content = data["sessions"][i]["semantic_memory"][j]["content"]
            semantic_memory.append(f"Time: {time} ({utils.get_weekday(time)})\nMemory: {content}")
            if "crops" in data["sessions"][i]["semantic_memory"][j]:
                semantic_memory_imgs.extend(data["sessions"][i]["semantic_memory"][j]["crops"])
        
        episodic_memory = []
        episodic_memory_imgs = []
        for item in idx_his_memory:
            if item in self.episodic_memory_idx:
                continue
            self.episodic_memory_idx.append(item)

            i, j = item
            time = data["sessions"][i]["interactions"][j][0]["time"]
            user_msg = data["sessions"][i]["interactions"][j][0]["query"]
            bot_msg = data["sessions"][i]["interactions"][j][1]['response']
            episodic_memory.append(f"Time: {time} ({utils.get_weekday(time)})\nUser: {user_msg}\nAssistant: {bot_msg}")
            episodic_memory_imgs.extend(data["sessions"][i]["interactions"][j][-1])

        procedural_memory = self.retrieve_procedural_memory(query["query"], data)
        if reset:
            self.reset_index()
        return {"semantic_memory": semantic_memory,
                "semantic_memory_imgs": semantic_memory_imgs,
                "episodic_memory": episodic_memory,
                "episodic_memory_imgs": episodic_memory_imgs,
                "procedural_memory": procedural_memory}
            
    def select_memory(self, query, memory_idx, sessions, interval_time):
        ans = []
        for item in memory_idx:
            i, j = item
            conv_time = sessions[i]["interactions"][j][0]["time"]
            if utils.compare_time_strings(utils.datetime_add_minutes(conv_time, interval_time) , query["time"]) <= 0:
                ans.append((i, j))

        return ans

cache_folder = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "checkpoints")
_text_emb_model = SentenceTransformer(os.path.join(cache_folder, "sentence-transformers", "all-MiniLM-L6-v2"), trust_remote_code=False)
_vision_emb_model = None
_img_feature_extractor = CLIPProcessor.from_pretrained(os.path.join(cache_folder, 'openai-clip'))

def get_text_embedding(text):
    global _text_emb_model
    embedding = _text_emb_model.encode([text], convert_to_numpy=True)[0]
    return normalize_vector(embedding).reshape(1, -1)


def get_vision_embedding(image):
    global _vision_emb_model, _img_feature_extractor
    if _vision_emb_model is None:
        _vision_emb_model = CLIPModel.from_pretrained(os.path.join(cache_folder, "openai-clip")).to("cuda")
    if isinstance(image, str):
        image = Image.open(image)
    inputs = _img_feature_extractor(images=image, return_tensors="pt", padding = True)
    image_features = _vision_emb_model.get_image_features(inputs["pixel_values"].to("cuda"))
    image_features = image_features / image_features.norm(p = 2, dim = -1, keepdim = True)  # normalize
    image_features = image_features.detach().cpu().numpy()
    return image_features.reshape(1, -1)

def normalize_vector(vec):
    vec = np.array(vec, dtype=np.float32)
    norm = np.linalg.norm(vec)
    if norm == 0:
        return vec
    return vec / norm
