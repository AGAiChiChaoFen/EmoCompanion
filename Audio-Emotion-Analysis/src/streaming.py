"""流式输出支持：增量 XML 标签分流器 + 流式事件发射器。"""

from typing import Callable, Optional

_OPENERS = ("<think>", "<answer>", "<retrieve>")
_CLOSERS = {"think": "</think>", "answer": "</answer>", "retrieve": "</retrieve>"}


def _find_tag(text: str, start: int, tags: tuple[str, ...]) -> tuple[int, str] | None:
    """在 text[start:] 中找第一个完整标签；返回 (位置, 标签)；无则 None。"""
    i = text.find("<", start)
    while i != -1:
        for tag in tags:
            if text.startswith(tag, i):
                return i, tag
        i = text.find("<", i + 1)
    return None


def _tag_prefix_at_end(text: str, tags: tuple[str, ...]) -> int:
    """text 末尾是某个标签的真前缀时返回该前缀长度（需等下一块）；否则 0。"""
    best = 0
    for tag in tags:
        for k in range(1, len(tag)):
            if text.endswith(tag[:k]):
                best = max(best, k)
    return best


class IncrementalTagSplitter:
    """把 LLM 流式 token 按 XML 标签增量分成 think / answer / retrieve 段。

    feed(chunk) 返回 (section, text) 事件列表；section ∈
    {"think", "answer", "retrieve", "outside"}。标签可被 chunk 任意截断
    （内部缓冲前缀匹配）。调用方用 finalize() 丢弃残余缓冲。
    """

    def __init__(self) -> None:
        self._section = "outside"
        self._buf = ""

    def feed(self, chunk: str) -> list[tuple[str, str]]:
        events: list[tuple[str, str]] = []
        text = self._buf + chunk
        carry = len(self._buf)  # 本次拼接中属于标签前缀的字符数（并入标签或被吸收，不作为正文 emit）
        self._buf = ""
        while text:
            if self._section == "outside":
                found = _find_tag(text, 0, _OPENERS)
                if found is None:
                    pfx = _tag_prefix_at_end(text, _OPENERS)
                    if pfx:
                        self._buf, text = text[-pfx:], text[:-pfx]
                    if text:
                        events.append(("outside", text))
                    break
                idx, tag = found
                if idx > carry:
                    # 标签从缓冲区之后开始：缓冲区内字符（[0, carry)）必为正文，
                    # 与 idx 前的正文一并 emit，避免正文中的 "<" 落在 chunk 边界被丢弃。
                    events.append(("outside", text[0:idx]))
                carry = 0
                self._section = tag[1:-1]
                text = text[idx + len(tag):]
            else:
                closer = _CLOSERS[self._section]
                found = _find_tag(text, 0, (closer,))
                if found is None:
                    pfx = _tag_prefix_at_end(text, (closer,))
                    if pfx:
                        self._buf, text = text[-pfx:], text[:-pfx]
                    if text:
                        events.append((self._section, text))
                    break
                idx, tag = found
                if idx > carry:
                    # 同 outside 分支：缓冲的标签前缀实为正文，与 idx 前正文一并 emit。
                    events.append((self._section, text[0:idx]))
                carry = 0
                self._section = "outside"
                text = text[idx + len(tag):]
        return events

    def finalize(self) -> str:
        """流结束：返回残余缓冲（未匹配完的标签前缀），并清空内部状态。"""
        tail, self._buf = self._buf, ""
        return tail


class StreamEmitter:
    """流式回调集合；回调为 None 表示未启用对应事件流。

    - emit_think(step_index, delta)：第 step_index 轮推理链增量文本
    - emit_answer(delta)：最终回答增量文本
    - emit_step(step)：一轮完整 step（dict：step/think/action/response/retrieve_info）
    """

    def __init__(
        self,
        emit_think: Optional[Callable[[int, str], None]] = None,
        emit_answer: Optional[Callable[[str], None]] = None,
        emit_step: Optional[Callable[[dict], None]] = None,
    ) -> None:
        self.emit_think = emit_think
        self.emit_answer = emit_answer
        self.emit_step = emit_step
