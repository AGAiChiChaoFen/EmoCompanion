import torch
from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor
from qwen_vl_utils import process_vision_info


class Qwenvl7B:
    def __init__(self, model_path="", cuda_device=0):
        self.cuda_device = cuda_device
        if not model_path:
            model_path = "Qwen/Qwen2.5-VL-7B-Instruct"
        self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(model_path, torch_dtype=torch.bfloat16, device_map=f"cuda:{self.cuda_device}")
        self.processor = AutoProcessor.from_pretrained(model_path)
        self.conversation_history = []

    def clear_conversation_history(self):
        self.conversation_history = []

    def send_message(self, message, clear=True, omit_content='', update=True):
        self.update_conversation_history(message, "user")
        if omit_content:
            instructions = omit_content
        else:
            text = self.processor.apply_chat_template(self.conversation_history, tokenize=False, add_generation_prompt=True)
            image_inputs, video_inputs = process_vision_info(self.conversation_history)
            inputs = self.processor(
                text=[text],
                images=image_inputs,
                videos=video_inputs,
                padding=True,
                return_tensors="pt",
            )
            inputs = inputs.to(f"cuda:{self.cuda_device}")
            generated_ids = self.model.generate(**inputs, max_new_tokens=1024, do_sample=False)
            generated_ids_trimmed = [
                out_ids[len(in_ids) :] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
            ]
            instructions = self.processor.batch_decode(
                generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]
        if update:
            self.update_conversation_history([{"type": "text", "text": instructions}], "assistant")
        else:
            self.conversation_history = self.conversation_history[:-1]
        if clear:
            self.clear_conversation_history()
        return instructions

    def update_conversation_history(self, content, role):
        self.conversation_history.append({
            "role": role,
            "content": content
        })
    
    def preprocess(self, prompt):
        if "<img_fill>" in prompt:
            prompt = prompt.replace("<img_fill>", "<image>")
        while "<image>\n" in prompt:
            prompt = prompt.replace("<image>\n", "<image>")
        prompt = prompt.replace("<image>", "<image>\n")
        prompt = prompt.replace("\\n", "\n")
        return prompt
    
    def prepare_input(self, prompt, imgs=[]):
        prompt = self.preprocess(prompt)
        assert "<img_fill>" not in prompt and prompt.count("<image>\n") == len(imgs)
        content = []
        if not isinstance(imgs, list):
            imgs = [imgs]
        for img in imgs:
            content.append({
                "type": "image",
                "image": img
            })
        content.append({
                "type": "text",
                "text": prompt
            })
        return content
    