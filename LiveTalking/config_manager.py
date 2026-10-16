###############################################################################
#  项目：EmoCompanion（基于 LiveTalking）
#  文件：config_manager.py
#  说明：音色和形象配置管理器,负责加载、验证、缓存和提供配置数据
#  许可证：Apache License 2.0
###############################################################################

from __future__ import annotations
import json
import os
import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from pathlib import Path

from logger import logger

BASE_DIR = Path(__file__).resolve().parent


def _resolve_local_path(path_value: str | Path) -> Path:
    """Resolve project-local paths against the LiveTalking directory."""
    candidate = Path(path_value)
    if candidate.is_absolute():
        return candidate
    return BASE_DIR / candidate


@dataclass
class VoiceConfig:
    """音色配置数据类"""
    voice_id: str
    name: str
    description: str
    type: str  # "preset" | "described" | "cloned"
    qwen_config: Dict[str, Any]
    icon: str = "bi bi-mic"
    
    def validate(self) -> tuple[bool, str]:
        """
        验证音色配置的有效性
        
        返回:
            (是否有效, 错误消息)
        """
        # 验证必需字段
        if not self.voice_id or not isinstance(self.voice_id, str):
            return False, "voice_id 必须是非空字符串"
        
        if not self.name or not isinstance(self.name, str):
            return False, "name 必须是非空字符串"
        
        if not self.type or self.type not in ["preset", "described", "cloned"]:
            return False, f"type 必须是 preset/described/cloned 之一,当前值: {self.type}"
        
        if not isinstance(self.qwen_config, dict):
            return False, "qwen_config 必须是字典类型"
        
        # 根据类型验证 qwen_config
        if self.type == "preset":
            if "voice" not in self.qwen_config:
                return False, "preset 类型的音色必须包含 voice 字段"
        
        elif self.type == "described":
            if "instructions" not in self.qwen_config:
                return False, "described 类型的音色必须包含 instructions 字段"
        
        elif self.type == "cloned":
            if "voice" not in self.qwen_config:
                return False, "cloned 类型的音色必须包含 voice 字段"
            if "audio_path" not in self.qwen_config:
                return False, "cloned 类型的音色必须包含 audio_path 字段"
        
        return True, ""
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Optional[VoiceConfig]:
        """
        从字典创建 VoiceConfig 对象
        
        参数:
            data: 配置字典
            
        返回:
            VoiceConfig 对象,如果数据无效返回 None
        """
        try:
            return cls(
                voice_id=data.get("voice_id", ""),
                name=data.get("name", ""),
                description=data.get("description", ""),
                type=data.get("type", "preset"),
                qwen_config=data.get("qwen_config", {}),
                icon=data.get("icon", "bi bi-mic")
            )
        except Exception as e:
            logger.error(f"Failed to create VoiceConfig from dict: {e}")
            return None
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典格式
        
        返回:
            配置字典
        """
        return {
            "voice_id": self.voice_id,
            "name": self.name,
            "description": self.description,
            "type": self.type,
            "qwen_config": self.qwen_config,
            "icon": self.icon
        }


class VoiceConfigManager:
    """音色配置管理器"""
    
    def __init__(self, config_path: str = "data/voice_config.json"):
        """
        初始化音色配置管理器
        
        参数:
            config_path: 配置文件路径
        """
        self.config_path = _resolve_local_path(config_path)
        self.voices: List[VoiceConfig] = []
        self.last_modified: float = 0.0
        self._default_voices = self._create_default_voices()
        
        # 初始加载配置
        self.load_config()
    
    def _create_default_voices(self) -> List[VoiceConfig]:
        """
        创建默认音色配置
        
        返回:
            默认音色列表
        """
        return [
            VoiceConfig(
                voice_id="preset_cherry",
                name="温柔女声",
                description="柔和亲切的女性声音",
                type="preset",
                qwen_config={"voice": "Cherry"},
                icon="bi bi-person-heart"
            ),
            VoiceConfig(
                voice_id="preset_serena",
                name="活力女声",
                description="明快活泼的女性声音",
                type="preset",
                qwen_config={"voice": "Serena"},
                icon="bi bi-emoji-smile"
            ),
            VoiceConfig(
                voice_id="preset_ethan",
                name="沉稳男声",
                description="稳重可靠的男性声音",
                type="preset",
                qwen_config={"voice": "Ethan"},
                icon="bi bi-shield-check"
            ),
            VoiceConfig(
                voice_id="preset_mason",
                name="磁性男声",
                description="低沉有力的男性声音",
                type="preset",
                qwen_config={"voice": "Mason"},
                icon="bi bi-soundwave"
            )
        ]

    
    def load_config(self) -> bool:
        """
        加载音色配置文件
        
        返回:
            加载成功返回 True,失败返回 False
        """
        try:
            # 检查配置文件是否存在
            if not self.config_path.exists():
                logger.warning(f"Voice config file not found: {self.config_path}, creating default config")
                self._create_default_config_file()
                self.voices = self._default_voices.copy()
                self.last_modified = time.time()
                return True
            
            # 读取配置文件
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 验证配置文件格式
            if not isinstance(data, dict) or "voices" not in data:
                logger.error(f"Invalid voice config format: missing 'voices' key")
                self.voices = self._default_voices.copy()
                return False
            
            if not isinstance(data["voices"], list):
                logger.error(f"Invalid voice config format: 'voices' must be a list")
                self.voices = self._default_voices.copy()
                return False
            
            # 解析音色配置
            voices = []
            for idx, voice_data in enumerate(data["voices"]):
                logger.debug(f"Parsing voice config {idx + 1}/{len(data['voices'])}: {voice_data.get('voice_id', 'unknown')}")
                
                voice = VoiceConfig.from_dict(voice_data)
                if voice is None:
                    logger.warning(f"Skipping invalid voice config at index {idx}: {voice_data.get('voice_id', 'unknown')}")
                    continue
                
                # 验证音色配置
                is_valid, error_msg = voice.validate()
                if not is_valid:
                    logger.warning(f"Skipping invalid voice {voice.voice_id} at index {idx}: {error_msg}")
                    continue
                
                logger.debug(f"Successfully parsed voice: {voice.voice_id}")
                voices.append(voice)
            
            # 如果没有有效的音色配置,使用默认配置
            if not voices:
                logger.warning("No valid voice configs found, using default voices")
                self.voices = self._default_voices.copy()
            else:
                self.voices = voices
            
            # 更新最后修改时间
            self.last_modified = self.config_path.stat().st_mtime
            
            logger.info(f"Loaded {len(self.voices)} voice configs from {self.config_path}")
            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse voice config JSON: {e}")
            self.voices = self._default_voices.copy()
            return False
        
        except PermissionError as e:
            logger.error(f"Permission denied reading voice config: {e}")
            self.voices = self._default_voices.copy()
            return False
        
        except Exception as e:
            logger.error(f"Unexpected error loading voice config: {e}")
            self.voices = self._default_voices.copy()
            return False
    
    def _create_default_config_file(self) -> None:
        """
        创建默认配置文件
        """
        try:
            # 确保目录存在
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 创建默认配置
            config_data = {
                "version": "1.0",
                "voices": [voice.to_dict() for voice in self._default_voices]
            }
            
            # 写入文件
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Created default voice config file: {self.config_path}")
            
        except Exception as e:
            logger.error(f"Failed to create default voice config file: {e}")

    def _check_and_reload(self) -> None:
        """
        检查配置文件是否被修改,如果修改则重新加载
        """
        try:
            if not self.config_path.exists():
                logger.warning(f"Voice config file disappeared: {self.config_path}")
                return
            
            current_mtime = self.config_path.stat().st_mtime
            
            # 如果文件被修改,重新加载
            if current_mtime > self.last_modified:
                logger.info(f"Voice config file modified, reloading: {self.config_path}")
                self.load_config()
        
        except Exception as e:
            logger.error(f"Error checking voice config file modification: {e}")
    
    def get_all_voices(self) -> List[Dict[str, Any]]:
        """
        获取所有音色配置
        
        返回:
            音色配置字典列表
        
        抛出:
            RuntimeError: 当配置加载失败时
        """
        # 检查并重新加载配置
        self._check_and_reload()
        
        # 如果使用的是默认配置，说明配置文件加载失败
        if len(self.voices) == 4 and all(v.voice_id.startswith('preset_') for v in self.voices):
            # 检查是否是因为配置文件不存在或解析失败
            if not self.config_path.exists():
                raise RuntimeError(f"配置文件不存在: {self.config_path}")
            
            # 尝试读取文件内容来判断是否是解析错误
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if "voices" in data and len(data["voices"]) > 4:
                        raise RuntimeError(f"配置文件解析失败，已回退到默认配置。请检查配置文件格式: {self.config_path}")
            except json.JSONDecodeError as e:
                raise RuntimeError(f"配置文件 JSON 格式错误: {str(e)}")
            except Exception as e:
                raise RuntimeError(f"读取配置文件失败: {str(e)}")
        
        return [voice.to_dict() for voice in self.voices]
    
    def get_voice_by_id(self, voice_id: str) -> Optional[Dict[str, Any]]:
        """
        根据 voice_id 获取音色配置
        
        参数:
            voice_id: 音色 ID
            
        返回:
            音色配置字典,如果未找到返回 None
        """
        # 检查并重新加载配置
        self._check_and_reload()
        
        for voice in self.voices:
            if voice.voice_id == voice_id:
                return voice.to_dict()
        
        logger.warning(f"Voice not found: {voice_id}")
        return None
    
    def add_voice(self, voice_config: Dict[str, Any]) -> tuple[bool, str]:
        """
        添加新的音色配置并保存到文件
        
        参数:
            voice_config: 音色配置字典
            
        返回:
            (是否成功, 错误消息或成功消息)
        """
        try:
            # 创建 VoiceConfig 对象
            voice = VoiceConfig.from_dict(voice_config)
            if voice is None:
                return False, "Invalid voice config format"
            
            # 验证配置
            is_valid, error_msg = voice.validate()
            if not is_valid:
                return False, f"Voice config validation failed: {error_msg}"
            
            # 检查是否已存在相同 voice_id
            for existing_voice in self.voices:
                if existing_voice.voice_id == voice.voice_id:
                    return False, f"Voice ID already exists: {voice.voice_id}"
            
            # 添加到内存中的配置列表
            self.voices.append(voice)
            
            # 保存到文件
            config_data = {
                "version": "1.0",
                "voices": [v.to_dict() for v in self.voices]
            }
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
            
            # 更新最后修改时间
            self.last_modified = self.config_path.stat().st_mtime
            
            logger.info(f"Added new voice config: {voice.voice_id}")
            return True, f"Successfully added voice: {voice.name}"
            
        except Exception as e:
            logger.error(f"Failed to add voice config: {e}")
            return False, f"Failed to add voice: {str(e)}"



@dataclass
class AvatarConfig:
    """形象配置数据类"""
    avatar_id: str
    name: str
    description: str
    type: str  # "preset" | "custom"
    image_path: str
    image_url: str = ""
    icon: str = "bi bi-person-circle"
    
    def validate(self) -> tuple[bool, str]:
        """
        验证形象配置的有效性
        
        返回:
            (是否有效, 错误消息)
        """
        # 验证必需字段
        if not self.avatar_id or not isinstance(self.avatar_id, str):
            return False, "avatar_id 必须是非空字符串"
        
        if not self.name or not isinstance(self.name, str):
            return False, "name 必须是非空字符串"
        
        if not self.type or self.type not in ["preset", "custom"]:
            return False, f"type 必须是 preset/custom 之一,当前值: {self.type}"
        
        if not self.image_path or not isinstance(self.image_path, str):
            return False, "image_path 必须是非空字符串"
        
        return True, ""
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Optional[AvatarConfig]:
        """
        从字典创建 AvatarConfig 对象
        
        参数:
            data: 配置字典
            
        返回:
            AvatarConfig 对象,如果数据无效返回 None
        """
        try:
            return cls(
                avatar_id=data.get("avatar_id", ""),
                name=data.get("name", ""),
                description=data.get("description", ""),
                type=data.get("type", "preset"),
                image_path=data.get("image_path", ""),
                image_url=data.get("image_url", ""),
                icon=data.get("icon", "bi bi-person-circle")
            )
        except Exception as e:
            logger.error(f"Failed to create AvatarConfig from dict: {e}")
            return None
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典格式
        
        返回:
            配置字典
        """
        return {
            "avatar_id": self.avatar_id,
            "name": self.name,
            "description": self.description,
            "type": self.type,
            "image_path": self.image_path,
            "image_url": self.image_url,
            "icon": self.icon
        }


class AvatarConfigManager:
    """形象配置管理器"""
    
    def __init__(self, config_path: str = "data/avatar_config.json"):
        """
        初始化形象配置管理器
        
        参数:
            config_path: 配置文件路径
        """
        self.config_path = _resolve_local_path(config_path)
        self.avatars: List[AvatarConfig] = []
        self.last_modified: float = 0.0
        self._default_avatars = self._create_default_avatars()
        
        # 初始加载配置
        self.load_config()
    
    def _create_default_avatars(self) -> List[AvatarConfig]:
        """
        创建默认形象配置
        
        返回:
            默认形象列表
        """
        return [
            AvatarConfig(
                avatar_id="preset_female_01",
                name="温柔女性",
                description="亲切温和的女性形象",
                type="preset",
                image_path="data/avatars/female_01.png",
                image_url="/data/avatars/female_01.png",
                icon="bi bi-person-heart"
            ),
            AvatarConfig(
                avatar_id="preset_male_01",
                name="专业男性",
                description="稳重专业的男性形象",
                type="preset",
                image_path="data/avatars/male_01.png",
                image_url="/data/avatars/male_01.png",
                icon="bi bi-person-badge"
            )
        ]
    
    def _validate_image_path(self, image_path: str) -> bool:
        """
        验证图片文件路径是否存在
        
        参数:
            image_path: 图片文件路径
            
        返回:
            路径有效返回 True,否则返回 False
        """
        try:
            path = _resolve_local_path(image_path)
            if not path.exists():
                logger.warning(f"Image file not found: {image_path}")
                return False
            
            if not path.is_file():
                logger.warning(f"Image path is not a file: {image_path}")
                return False
            
            # 检查文件扩展名
            valid_extensions = {'.png', '.jpg', '.jpeg', '.webp'}
            if path.suffix.lower() not in valid_extensions:
                logger.warning(f"Invalid image file extension: {image_path}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating image path {image_path}: {e}")
            return False
    
    def load_config(self) -> bool:
        """
        加载形象配置文件
        
        返回:
            加载成功返回 True,失败返回 False
        """
        try:
            # 检查配置文件是否存在
            if not self.config_path.exists():
                logger.warning(f"Avatar config file not found: {self.config_path}, creating default config")
                self._create_default_config_file()
                self.avatars = self._default_avatars.copy()
                self.last_modified = time.time()
                return True
            
            # 读取配置文件
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 验证配置文件格式
            if not isinstance(data, dict) or "avatars" not in data:
                logger.error(f"Invalid avatar config format: missing 'avatars' key")
                self.avatars = self._default_avatars.copy()
                return False
            
            if not isinstance(data["avatars"], list):
                logger.error(f"Invalid avatar config format: 'avatars' must be a list")
                self.avatars = self._default_avatars.copy()
                return False
            
            # 解析形象配置
            avatars = []
            for avatar_data in data["avatars"]:
                avatar = AvatarConfig.from_dict(avatar_data)
                if avatar is None:
                    logger.warning(f"Skipping invalid avatar config: {avatar_data.get('avatar_id', 'unknown')}")
                    continue
                
                # 验证形象配置
                is_valid, error_msg = avatar.validate()
                if not is_valid:
                    logger.warning(f"Skipping invalid avatar {avatar.avatar_id}: {error_msg}")
                    continue
                
                # 验证图片路径(仅警告,不跳过)
                if not self._validate_image_path(avatar.image_path):
                    logger.warning(f"Avatar {avatar.avatar_id} has invalid image path, but keeping config")
                
                avatars.append(avatar)
            
            # 如果没有有效的形象配置,使用默认配置
            if not avatars:
                logger.warning("No valid avatar configs found, using default avatars")
                self.avatars = self._default_avatars.copy()
            else:
                self.avatars = avatars
            
            # 更新最后修改时间
            self.last_modified = self.config_path.stat().st_mtime
            
            logger.info(f"Loaded {len(self.avatars)} avatar configs from {self.config_path}")
            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse avatar config JSON: {e}")
            self.avatars = self._default_avatars.copy()
            return False
        
        except PermissionError as e:
            logger.error(f"Permission denied reading avatar config: {e}")
            self.avatars = self._default_avatars.copy()
            return False
        
        except Exception as e:
            logger.error(f"Unexpected error loading avatar config: {e}")
            self.avatars = self._default_avatars.copy()
            return False
    
    def _create_default_config_file(self) -> None:
        """
        创建默认配置文件
        """
        try:
            # 确保目录存在
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 创建默认配置
            config_data = {
                "version": "1.0",
                "avatars": [avatar.to_dict() for avatar in self._default_avatars]
            }
            
            # 写入文件
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Created default avatar config file: {self.config_path}")
            
        except Exception as e:
            logger.error(f"Failed to create default avatar config file: {e}")
    
    def _check_and_reload(self) -> None:
        """
        检查配置文件是否被修改,如果修改则重新加载
        """
        try:
            if not self.config_path.exists():
                logger.warning(f"Avatar config file disappeared: {self.config_path}")
                return
            
            current_mtime = self.config_path.stat().st_mtime
            
            # 如果文件被修改,重新加载
            if current_mtime > self.last_modified:
                logger.info(f"Avatar config file modified, reloading: {self.config_path}")
                self.load_config()
        
        except Exception as e:
            logger.error(f"Error checking avatar config file modification: {e}")
    
    def get_all_avatars(self) -> List[Dict[str, Any]]:
        """
        获取所有形象配置
        
        返回:
            形象配置字典列表
        """
        # 检查并重新加载配置
        self._check_and_reload()
        
        return [avatar.to_dict() for avatar in self.avatars]
    
    def get_avatar_by_id(self, avatar_id: str) -> Optional[Dict[str, Any]]:
        """
        根据 avatar_id 获取形象配置
        
        参数:
            avatar_id: 形象 ID
            
        返回:
            形象配置字典,如果未找到返回 None
        """
        # 检查并重新加载配置
        self._check_and_reload()
        
        for avatar in self.avatars:
            if avatar.avatar_id == avatar_id:
                return avatar.to_dict()
        
        logger.warning(f"Avatar not found: {avatar_id}")
        return None
    
    def add_avatar(self, avatar_config: Dict[str, Any]) -> tuple[bool, str]:
        """
        添加新的形象配置并保存到文件
        
        参数:
            avatar_config: 形象配置字典
            
        返回:
            (是否成功, 错误消息或成功消息)
        """
        try:
            # 创建 AvatarConfig 对象
            avatar = AvatarConfig.from_dict(avatar_config)
            if avatar is None:
                return False, "Invalid avatar config format"
            
            # 验证配置
            is_valid, error_msg = avatar.validate()
            if not is_valid:
                return False, f"Avatar config validation failed: {error_msg}"
            
            # 验证图片路径
            if not self._validate_image_path(avatar.image_path):
                return False, f"Invalid image path: {avatar.image_path}"
            
            # 检查是否已存在相同 avatar_id
            for existing_avatar in self.avatars:
                if existing_avatar.avatar_id == avatar.avatar_id:
                    return False, f"Avatar ID already exists: {avatar.avatar_id}"
            
            # 添加到内存中的配置列表
            self.avatars.append(avatar)
            
            # 保存到文件
            config_data = {
                "version": "1.0",
                "avatars": [a.to_dict() for a in self.avatars]
            }
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
            
            # 更新最后修改时间
            self.last_modified = self.config_path.stat().st_mtime
            
            logger.info(f"Added new avatar config: {avatar.avatar_id}")
            return True, f"Successfully added avatar: {avatar.name}"
            
        except Exception as e:
            logger.error(f"Failed to add avatar config: {e}")
            return False, f"Failed to add avatar: {str(e)}"

    def remove_avatar(self, avatar_id: str, delete_file: bool = True) -> tuple[bool, str, Optional[str]]:
        """
        删除自定义形象配置并可选删除对应图片文件。

        参数:
            avatar_id: 形象 ID
            delete_file: 是否删除本地图片文件

        返回:
            (是否成功, 错误消息或成功消息, 删除的图片路径)
        """
        try:
            self._check_and_reload()

            target_index = -1
            target_avatar = None
            for index, avatar in enumerate(self.avatars):
                if avatar.avatar_id == avatar_id:
                    target_index = index
                    target_avatar = avatar
                    break

            if target_avatar is None:
                return False, f"Avatar not found: {avatar_id}", None

            if target_avatar.type != "custom":
                return False, "Only custom avatars can be deleted", None

            removed_avatar = self.avatars.pop(target_index)
            config_data = {
                "version": "1.0",
                "avatars": [a.to_dict() for a in self.avatars]
            }

            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)

            self.last_modified = self.config_path.stat().st_mtime

            removed_image_path = removed_avatar.image_path
            if delete_file and removed_image_path:
                image_path = _resolve_local_path(removed_image_path)
                try:
                    if image_path.exists() and image_path.is_file():
                        image_path.unlink()
                        logger.info(f"Deleted custom avatar image: {image_path}")
                except Exception as file_error:
                    logger.warning(f"Failed to delete custom avatar image {image_path}: {file_error}")

            logger.info(f"Removed custom avatar config: {avatar_id}")
            return True, f"Successfully removed avatar: {removed_avatar.name}", removed_image_path

        except Exception as e:
            logger.error(f"Failed to remove avatar config: {e}")
            return False, f"Failed to remove avatar: {str(e)}", None
