import logging
 
# 本模块用于提供项目统一日志对象。
# 设计目标：
# 1) 任何文件都通过 `from logger import logger` 获取同一 logger；
# 2) 日志默认写入磁盘文件，便于线上排障与历史追踪；
# 3) 通过等级控制避免 DEBUG 级别日志污染线上输出。
logger = logging.getLogger(__name__)

# logger 的总开关等级设为 DEBUG，表示“允许”接收 DEBUG 及以上的消息。
# 但最终是否真正写出，还要看各个 handler 自己的等级阈值。
logger.setLevel(logging.DEBUG)

# 统一日志格式：时间 + 模块名 + 级别 + 消息。
# 该格式便于后续按时间线回放问题现场。
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 文件输出 handler：将日志持久化到项目目录下的 emocompanion.log。
# 如需按日期切分或按大小轮转，可替换为 RotatingFileHandler/TimedRotatingFileHandler。
fhandler = logging.FileHandler('emocompanion.log')  # 可以改为StreamHandler输出到控制台或多个Handler组合使用等。
fhandler.setFormatter(formatter)

# 文件 handler 仅记录 INFO 及以上级别，减少磁盘写入量。
# DEBUG 日志仍可通过额外的控制台 handler 打开（见下方示例）。
fhandler.setLevel(logging.INFO)
logger.addHandler(fhandler)

# 下面是可选的控制台输出配置模板，默认关闭。
# 开启后可在开发调试时实时查看详细日志。
# handler = logging.StreamHandler()
# handler.setLevel(logging.DEBUG)
# sformatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
# handler.setFormatter(sformatter)
# logger.addHandler(handler)