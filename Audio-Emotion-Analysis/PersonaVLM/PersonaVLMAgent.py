import os
import json
import shutil
import copy

from PersonaVLM import prompts
from PersonaVLM import utils
from PersonaVLM import tools
from PersonaVLM import retriever
from src import create_adapter
from src.streaming import IncrementalTagSplitter, StreamEmitter


class PersonaVLM:
    def __init__(self,
                 config,
                 force_retrieve=False,
                 reasoning_mode=True,
                 session_interval_time=60,
                 agent_model=None):

        self.init_user(config)
        self.session_interval_time = session_interval_time
        self.force_retrieve = force_retrieve
        self.reasoning_mode = reasoning_mode
        self.EMA_moving_factor = None
        # 供 reasoning_response 独立调用时使用（send_message 会覆盖）
        self.personality_input = None
        # 默认通过第三方 API 适配器驱动，也可显式注入自定义模型后端
        self.mllm = agent_model if agent_model is not None else create_adapter()
        self.retriever = retriever.Retriever(self.save_dir)

    def init_user(self, config):
        self.config = config
        self.save_dir = self.config.DATA_STORAGE_PATH
        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir, exist_ok=True)
            os.makedirs(os.path.join(self.save_dir, "media"), exist_ok=True)

        # load user data
        self.user_data_path = os.path.join(self.save_dir, 'user_data.json')
        if not os.path.exists(self.user_data_path):
            self.data = {}
            self.data["init_profile"] = {}
            self.data["init_profile"]["name"] = self.config.USER_NAME
            for key in self.config.PROFILE.keys():
                if isinstance(self.config.PROFILE[key], dict):
                    for sub_key in self.config.PROFILE[key].keys():
                        self.data["init_profile"][sub_key] = self.config.PROFILE[key][sub_key]
                else:
                    self.data["init_profile"][key] = self.config.PROFILE[key]
        else:
            with open(self.user_data_path, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
            self.data["imgs"] = [os.path.join(self.save_dir, 'media/imgs', os.path.basename(path)) for path in self.data.get("imgs", [])]
        
        self.big_five_personality = self.data.get("big_five_personality", {
                                                                            'openness': 3,
                                                                            'conscientiousness': 3,
                                                                            'extraversion': 3,
                                                                            'agreeableness': 3,
                                                                            'neuroticism': 3
                                                                        })
        self.imgs = self.data.get("imgs", [])
        # 认知/情绪时间序列（每轮消息追加一条；老数据缺失视为空）
        self.trend_history = self.data.get("trend_history", [])
        self.sessions = self.data.get("sessions", [{}])
        self.data["current_interactions"] = sum([len(session.get("interactions", [])) for session in self.sessions])
        if "profile" not in self.sessions[-1]:
            self.sessions[-1]["profile"] = self.data["init_profile"]
        # 活动会话指针：-1 = 最新（最后一个）会话；显式切换后指向具体索引
        self.active_session_index = -1

    def prepare_query(self, message):
        if "imgs" in message and message["imgs"]:
            if "<img>" in message["query"]:
                message["query"] = message["query"].replace("<img>", "<img_fill>")
            if isinstance(message["imgs"], str):
                message["imgs"] = [message["imgs"]]
            if "<img_fill>" not in message["query"]:
                message["query"] = "<img_fill>\n" * len(message["imgs"]) + message["query"]
            for img_path in message["imgs"]:
                if not os.path.exists(img_path):
                    raise ValueError("Image path does not exist")
                resave_path = os.path.join(self.save_dir, "media/imgs", f"{len(self.imgs)}.png")
                os.makedirs(os.path.dirname(resave_path), exist_ok=True)
                shutil.copy(img_path, resave_path)
                self.imgs.append(resave_path)
        query = {
            "time": message["time"],
            "query": message["query"]
        }
        return query
    
    def update(self):
        self.data["imgs"] = self.imgs
        self.data["sessions"] = self.sessions
        self.data["big_five_personality"] = self.big_five_personality
        self.data["trend_history"] = self.trend_history
        with open(self.user_data_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=4)

    def send_message(self, message, personality_input=None, return_response_only=True, update=True,
                     with_default_response=None, new_session=False, session_id=None, stream_emitter=None):
        query = self.prepare_query(message)
        if session_id is not None:
            self.switch_session(session_id)
        if new_session:
            self.start_new_session(query)
        self.summerize_memory(query)
        self.personality_input = personality_input

        if with_default_response:
            response = with_default_response
            reasoning_chain = []
        else:
            if self.reasoning_mode:
                if stream_emitter is not None:
                    response, reasoning_chain = self.reasoning_response(query, stream_emitter=stream_emitter)
                else:
                    response, reasoning_chain = self.reasoning_response(query)
            else:
                retrieve_memory = self.retrieval_memory(query, {
                        "retrieve": True,
                        "start_time": None,
                        "end_time": None,
                        "keywords": query["query"]
                    }, reset=True)
                response, reasoning_chain = self.personalized_response(query, retrieve_memory), []

        personality_info = None
        if update:
            personality_info = self.get_personality_info(query)
            personality_info = utils.personality_info_to_json(query, personality_info)
            self.update_personality(personality_info)
            # 趋势时间序列：人格取 EMA 演化后快照，情绪取本轮推断（缺失兜底 neutral/3）
            self.trend_history.append({
                "time": query["time"],
                "personality": dict(self.big_five_personality),
                "emotion": {
                    "label": personality_info.get("emotion", "neutral"),
                    "intensity": personality_info.get("emotion_intensity", 3),
                },
            })
            semantic_memory = self.infer_semantic_memory(query)
            self.active_session()["semantic_memory"] = self.active_session().get("semantic_memory", [])
            self.active_session()["semantic_memory"].append(semantic_memory)
            self.active_session()["interactions"] = self.active_session().get("interactions", [])
            self.active_session()["interactions"].append([query,
                                                    {"response": response},
                                                    reasoning_chain,
                                                    [] if query["query"].count("<img_fill>") == 0 else
                                                    self.imgs[-query["query"].count("<img_fill>"):]])
            self.data["current_interactions"] += 1
            self.update()

        if return_response_only:
            return response
        return response, personality_info, reasoning_chain

    def set_personality(self, prompt):
        if self.personality_input is not None and isinstance(self.personality_input, dict):
            for trait in self.big_five_personality.keys():
                if trait in self.personality_input:
                    prompt = prompt.replace("{"+trait.capitalize()+"}", str(self.personality_input[trait])[:3])
        
        prompt = prompt.replace("{Openness}", str(self.big_five_personality["openness"])[:3])
        prompt = prompt.replace("{Conscientiousness}", str(self.big_five_personality["conscientiousness"])[:3])
        prompt = prompt.replace("{Extraversion}", str(self.big_five_personality["extraversion"])[:3])
        prompt = prompt.replace("{Agreeableness}", str(self.big_five_personality["agreeableness"])[:3])
        prompt = prompt.replace("{Neuroticism}", str(self.big_five_personality["neuroticism"])[:3])
        return prompt

    def reasoning_response(self, query, stream_emitter=None):
        query_week = copy.deepcopy(query)
        query_week["time"] = query["time"] + f' ({utils.get_weekday(query["time"])})'
        prompt_response = prompts.MLLM_REASONING_PROMPT_START
        
        prompt_response = prompt_response.replace("{UserProfile}", str(self.active_session()["profile"]))
        prompt_response = prompt_response.replace("{DialogHistory}", self.history_generation(only_last_session=False, cur_time=query["time"]))
        prompt_response = prompt_response.replace("{UserQuery}", str(query_week))
        prompt_response = self.set_personality(prompt_response)

        reasoning_chain = []
        call_emitter = self._stream_call_emitter(stream_emitter, len(reasoning_chain))
        response = self.get_response(prompt_response, self.imgs, json_format=False, clear_context=False, stream_emitter=call_emitter)
        ans = utils.parse_reasoning_output(response, query, force_retrieve=self.force_retrieve)
        reasoning_chain.append(ans)
        self._emit_step(stream_emitter, ans, len(reasoning_chain) - 1)
        while ans["action"] == "retrieve":
            retrieve_memory = self.retrieval_memory(query, copy.deepcopy(ans["retrieve_info"]), reset=False)
            reasoning_chain[-1]["retrieve_memory"] = retrieve_memory
            prompt_response = prompts.MLLM_REASONING_PROMPT_MID
            prompt_response = prompt_response.replace("{ProceduralMemory}", "\n".join(retrieve_memory.get("procedural_memory", [])))
            prompt_response = prompt_response.replace("{SemanticMemory}", "\n".join(retrieve_memory.get("semantic_memory", [])))
            dialog_history = "\n".join(retrieve_memory.get("episodic_memory", []))
            prompt_response = prompt_response.replace("{DialogHistory}", dialog_history.strip())
            reason_sample_imgs = copy.deepcopy(retrieve_memory["semantic_memory_imgs"]+retrieve_memory["episodic_memory_imgs"])
            call_emitter = self._stream_call_emitter(stream_emitter, len(reasoning_chain))
            response = self.get_response(prompt_response, reason_sample_imgs, clear_context=False, json_format=False, stream_emitter=call_emitter)
            ans = utils.parse_reasoning_output(response, query)
            reasoning_chain.append(ans)
            self._emit_step(stream_emitter, ans, len(reasoning_chain) - 1)
            if len(reasoning_chain) > 5:
                if "response" not in ans:
                    ans["response"] = ""
                break
        # 生成完整性守卫：answer 轮输出缺少 </answer> 说明 LLM 流中断/跑偏，
        # 静默返回碎片会让用户看到残缺回答——显式报错（流式端点转为 error 事件）
        if ans["action"] == "answer" and "</answer>" not in response:
            raise ValueError("回答生成不完整（LLM 输出中断），请重试")
        self.mllm.clear_conversation_history()
        self.retriever.reset_index()
        return ans["response"], reasoning_chain

    def _stream_call_emitter(self, stream_emitter, step_index):
        """构造单轮调用的发射器：think chunk 绑定当前 step 索引。"""
        if stream_emitter is None:
            return None
        return StreamEmitter(
            emit_think=(lambda d, i=step_index: stream_emitter.emit_think(i, d))
                       if stream_emitter.emit_think else None,
            emit_answer=stream_emitter.emit_answer,
        )

    def _emit_step(self, stream_emitter, ans, index):
        """一轮完成：回调完整 step（含 think 全文 / action / retrieve_info）。"""
        if stream_emitter is None or stream_emitter.emit_step is None:
            return
        stream_emitter.emit_step({
            "step": index,
            "think": ans.get("think", ""),
            "action": ans.get("action", ""),
            "response": ans.get("response", ""),
            "retrieve_info": ans.get("retrieve_info") or None,
        })

    def personalized_response(self, query, retrieve_memory):
        query_week = copy.deepcopy(query)
        query_week["time"] = query["time"] + f' ({utils.get_weekday(query["time"])})'
        prompt_response = prompts.MLLM_RESPONSE_PROMPT
        
        prompt_response = prompt_response.replace("{UserProfile}", str(self.active_session()["profile"]))
        prompt_response = prompt_response.replace("{ProceduralMemory}", "\n".join(retrieve_memory.get("procedural_memory", [])))
        prompt_response = prompt_response.replace("{RetrieveMemory}", "\n".join(retrieve_memory.get("semantic_memory", [])))
        dialog_history = "\n".join(retrieve_memory["episodic_memory"]) + '\n' + self.history_generation() # self.history_generation(query["time"])
        prompt_response = prompt_response.replace("{DialogHistory}", dialog_history.strip())
        prompt_response = prompt_response.replace("{UserQuery}", str(query_week))
        prompt_response = self.set_personality(prompt_response)
        response = self.get_response(prompt_response, self.imgs, json_format=False,
                                     memory_imgs=retrieve_memory["semantic_memory_imgs"]+retrieve_memory["episodic_memory_imgs"])
        return response

    def retrieval_memory(self, query, retrieve_info, reset=True):
        _query = copy.deepcopy(query)
        if "(" in _query["time"]:
            _query["time"] = _query["time"].split("(")[0].strip()
        start_time = retrieve_info.get("start_time", None)
        end_time = retrieve_info.get("end_time", None)
        if start_time and end_time:
            last_update_time = self.active_session()["profile"].get("update time", None)
            if utils.compare_time_strings(start_time, end_time) >= 0 or \
                (last_update_time and utils.compare_time_strings(start_time, utils.datetime_add_minutes(last_update_time, -self.session_interval_time)) >= 0):
                retrieve_info["start_time"] = None
                retrieve_info["end_time"] = None
        retrieve_memory = self.retriever.retrieve(_query, retrieve_info, self.data, self.session_interval_time, reset=reset)
        return retrieve_memory

    def get_personality_info(self, query):
        query_week = copy.deepcopy(query)
        query_week["time"] = query["time"] + f' ({utils.get_weekday(query["time"])})'
        prompt_retrieve = prompts.MLLM_INFERENCE_PERSONALITY_PROMPT
        prompt_retrieve = prompt_retrieve.replace("{UserProfile}", str(self.active_session()["profile"]))
        prompt_retrieve = prompt_retrieve.replace("{DialogHistory}", self.history_generation()) # self.history_generation(query["time"])
        prompt_retrieve = prompt_retrieve.replace("{UserQuery}", str(query_week))
        personality_response = self.get_response(prompt_retrieve, self.imgs, json_format=False)
        return personality_response

    def infer_semantic_memory(self, query):
        query_week = copy.deepcopy(query)
        query_week["time"] = query["time"] + f' ({utils.get_weekday(query["time"])})'

        prompt_semantic_memory = prompts.MLLM_SEMANTIC_MEMORY_PROMPT
        prompt_semantic_memory = prompt_semantic_memory.replace("{UserProfile}", str(self.active_session()["profile"]))
        prompt_semantic_memory = prompt_semantic_memory.replace("{DialogHistory}", self.history_generation())
        prompt_semantic_memory = prompt_semantic_memory.replace("{UserQuery}", str(query_week))

        semantic_memory = self.get_response(prompt_semantic_memory, self.imgs, json_format=False)
        semantic_memory = utils.semantic_memory_to_json(semantic_memory)        

        if "<img_fill>" in query["query"] and "(image object:" in semantic_memory["content"].lower():
            semantic_memory = tools.extract_memory(semantic_memory,
                                                    os.path.join(self.save_dir, "media/VisionConcept"),
                                                    self.imgs[-1])
        elif "(image" in semantic_memory["content"].lower():
                content = semantic_memory["content"].replace("(image", "(Image")
                semantic_memory["content"] = content.split("(Image", 1)[0]
        return semantic_memory

    def update_personality(self, retrieve_info):
        self.EMA_moving_factor = utils.cosine_decay_factor(self.data["current_interactions"])
        for trait in self.big_five_personality.keys():
            if retrieve_info[trait] != 3:
                self.big_five_personality[trait] = self.EMA_moving_factor * self.big_five_personality[trait] + (1 - self.EMA_moving_factor) * retrieve_info[trait]

    def active_session(self):
        """返回当前活动会话 dict。active_session_index 为 -1 时取最后一个；
        无会话时回退 {'profile': init_profile}（等价旧 [{}] 兜底语义）。"""
        if not self.sessions:
            return {"profile": self.data["init_profile"]}
        idx = self.active_session_index if self.active_session_index >= 0 else len(self.sessions) - 1
        return self.sessions[idx]

    def switch_session(self, session_id):
        """切换活动会话（sessions[] 索引；-1 = 最新；越界抛 ValueError）。"""
        if session_id < -1 or session_id >= len(self.sessions):
            raise ValueError(f"session_id {session_id} 超出范围（共 {len(self.sessions)} 个会话）")
        self.active_session_index = session_id

    def _induce(self, query):
        """归纳当前活动会话（情景/程序/画像），写回当前会话；无交互返回 None。

        供 finalize_current_session / start_new_session / 时间兜底复用。
        """
        session = self.active_session()
        if not session.get("interactions", []):
            return None

        imgs = copy.deepcopy(self.imgs)
        if "<img_fill>" in query["query"]:
            imgs = imgs[:-query["query"].count("<img_fill>")]

        # summerize episodic memory（写回当前会话）
        prompt_event_extractor = prompts.MLLM_EPISODIC_MEMORY_PROMPT
        prompt_event_extractor = prompt_event_extractor.replace("{UserProfile}", str(session["profile"]))
        prompt_event_extractor = prompt_event_extractor.replace("{DialogHistory}", self.history_generation(add_num=True))
        event_extractor = self.get_response(prompt_event_extractor, imgs, json_format=False)
        event_extractor = utils.topics_to_json(event_extractor, N=len(session["interactions"]))
        session["EpisodicMemory"] = event_extractor

        # update procedural memory（写回当前会话）
        prompt_update_procedural = prompts.MLLM_PROCEDURAL_MEMORY_PROMPT
        prompt_update_procedural = prompt_update_procedural.replace("{UserProfile}", str(session["profile"]))
        prompt_update_procedural = prompt_update_procedural.replace("{CurrentProceduralMemory}", str(session.get("ProceduralMemory", "")))
        prompt_update_procedural = prompt_update_procedural.replace("{DialogHistory}", self.history_generation())
        update_procedural = self.get_response(prompt_update_procedural, imgs, json_format=False)
        session["ProceduralMemory"] = utils.procedural_to_json(update_procedural)

        # update profile（写回当前会话）
        prompt_update_profile = prompts.MLLM_CORE_MEMORY_UPDATE_PROMPT
        prompt_update_profile = prompt_update_profile.replace("{UserProfile}", str(session["profile"]))
        prompt_update_profile = prompt_update_profile.replace("{DialogHistory}", self.history_generation())
        update_profile = self.get_response(prompt_update_profile, imgs, json_format=False)
        session["profile"] = utils.profile_to_json(update_profile, session["profile"])

        session["profile"]["update time"] = utils.datetime_add_minutes(
            session["interactions"][-1][0]['time'], self.session_interval_time)
        return session

    def finalize_current_session(self, query):
        """强制归纳当前会话记忆（写回），不 append 新会话。"""
        self._induce(query)
        self.update()

    def start_new_session(self, query):
        """主动开新会话：归纳当前会话 → append 新会话（继承画像/程序记忆）→ 切换。"""
        self._induce(query)
        current = self.active_session()
        new_session = {
            "profile": dict(current["profile"]),
            "ProceduralMemory": dict(current.get("ProceduralMemory", {})),
        }
        self.sessions.append(new_session)
        self.active_session_index = len(self.sessions) - 1
        self.update()

    def history_generation(self, cur_time=None, only_last_session=True, add_num=False):
        sessions = self.sessions
        response = []
        if only_last_session:
            sessions = [self.active_session()]
        for session in sessions:
            interactions = session.get("interactions", [])
            if len(interactions) > 0:
                for i in range(len(interactions)):
                    time = interactions[i][0]['time']
                    user_msg = interactions[i][0]['query']
                    bot_msg = interactions[i][1]['response']
                    if cur_time and utils.is_time_diff_over_minutes(cur_time, time, self.session_interval_time):
                        continue
                    if add_num:
                        response.append(f"Round {len(response)} of dialogues\nTime: {time} ({utils.get_weekday(time)})\nUser: {user_msg}\nAssistant: {bot_msg}")
                    else:
                        response.append(f"Time: {time} ({utils.get_weekday(time)})\nUser: {user_msg}\nAssistant: {bot_msg}")
        return "\n".join(response)

    def summerize_memory(self, query):
        """时间兜底：最新会话间隔超 60 分钟 → 归纳 + 开新会话。

        仅作用于最新会话（active_session_index == -1）；显式切换到的
        旧会话不自动滚动（尊重用户选择）。
        """
        if self.active_session_index != -1:
            return
        session = self.active_session()
        if not session.get("interactions", []):
            return
        latest_time = session["interactions"][-1][0]['time']
        cur_time = query['time']
        if utils.is_time_diff_over_minutes(cur_time, latest_time, self.session_interval_time):
            self.start_new_session(query)
    
    def format_normalize(self, text):
        text = text.strip().replace("json", "").replace("```", "").replace("'''", "").strip()
        return text

    def get_response(self, prompt, imgs=[], clear_context=True, json_format=True, memory_imgs=[], return_input=False, stream_emitter=None):
        _imgs = memory_imgs.copy()
        N = prompt.count("<img_fill>") - len(_imgs)
        assert N >= 0 and len(imgs) >= N
        if N > 0:
            _imgs += imgs[-N:]
        if return_input:
            return prompt, copy.deepcopy(_imgs)
        if stream_emitter is not None and not json_format:
            return self._get_response_stream(prompt, _imgs, clear_context, stream_emitter)
        response = self.mllm.send_message(self.mllm.prepare_input(prompt, copy.deepcopy(_imgs)), clear=clear_context)
        if clear_context:
            self.mllm.clear_conversation_history()
        if not json_format:
            return response
        try:
            response = self.format_normalize(response)
            response = json.loads(response)
            if isinstance(response, dict):
                for key in response:
                    if isinstance(response[key], list):
                        response[key] = ", ".join(response[key])
                    if isinstance(response[key], dict):
                        for subkey in response[key]:
                            if isinstance(response[key][subkey], list):
                                response[key][subkey] = ", ".join(response[key][subkey])

        except json.JSONDecodeError:
            print(f"Error: {response}")
            raise ValueError("Invalid JSON response")
        return response

    def _get_response_stream(self, prompt, imgs, clear_context, stream_emitter):
        """流式 LLM 调用：逐 chunk 按标签分流，think/answer 段实时回调。

        retrieve / outside 段不推送（控制流仍由完整文本解析驱动）。
        """
        splitter = IncrementalTagSplitter()

        def on_chunk(text):
            for section, seg in splitter.feed(text):
                if section == "think" and stream_emitter.emit_think:
                    stream_emitter.emit_think(seg)
                elif section == "answer" and stream_emitter.emit_answer:
                    stream_emitter.emit_answer(seg)

        response = self.mllm.send_message_stream(
            self.mllm.prepare_input(prompt, copy.deepcopy(imgs)),
            clear=clear_context,
            on_chunk=on_chunk,
        )
        splitter.finalize()
        if clear_context:
            self.mllm.clear_conversation_history()
        return response
