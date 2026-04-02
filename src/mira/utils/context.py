#!/usr/bin/env python3
"""
上下文窗口管理 - Token 预算、上下文限制、自动紧凑化触发
"""

from typing import List, Dict, Tuple

# ── 各模型上下文窗口 (tokens) ─────────────────────────────────────────────────

MODEL_CONTEXT_WINDOWS: Dict[str, int] = {
    # Anthropic
    "claude-opus-4-6":           200_000,
    "claude-sonnet-4-6":         200_000,
    "claude-haiku-4-5":          200_000,
    "claude-haiku-4-5-20251001": 200_000,
    "claude-3-opus-20240229":    200_000,
    "claude-3-sonnet-20240229":  200_000,
    "claude-3-haiku-20240307":   200_000,
    # OpenAI
    "gpt-4o":                    128_000,
    "gpt-4o-mini":               128_000,
    "gpt-4-turbo":               128_000,
    "gpt-4":                       8_192,
    "gpt-3.5-turbo":              16_385,
    # DeepSeek
    "deepseek-chat":              64_000,
    "deepseek-coder":             16_000,
    "deepseek-reasoner":          64_000,
    # Google
    "gemini-1.5-pro":          1_000_000,
    "gemini-1.5-flash":        1_000_000,
    "gemini-2.0-flash":        1_000_000,
    "gemini-1.0-pro":             32_760,
    # 智谱
    "glm-4-plus":                128_000,
    "glm-4":                     128_000,
    "glm-4-flash":               128_000,
    "glm-3-turbo":                 8_192,
    # 月之暗面
    "moonshot-v1-128k":          128_000,
    "moonshot-v1-32k":            32_000,
    "moonshot-v1-8k":              8_000,
    # 豆包
    "doubao-pro-32k":             32_000,
    "doubao-pro-4k":               4_000,
    "doubao-lite-4k":              4_000,
    # MiniMax
    "abab6.5s-chat":             245_760,
    "abab6.5-chat":              245_760,
}

# ── 定价 (USD / 1M tokens): (input, output, cache_read) ─────────────────────

MODEL_PRICING: Dict[str, Tuple[float, float, float]] = {
    "claude-opus-4-6":           (15.0,  75.0,  1.50),
    "claude-sonnet-4-6":         ( 3.0,  15.0,  0.30),
    "claude-haiku-4-5":          ( 0.8,   4.0,  0.08),
    "claude-haiku-4-5-20251001": ( 0.8,   4.0,  0.08),
    "claude-3-opus-20240229":    (15.0,  75.0,  1.50),
    "claude-3-sonnet-20240229":  ( 3.0,  15.0,  0.30),
    "claude-3-haiku-20240307":   ( 0.25,  1.25, 0.03),
    "gpt-4o":                    ( 2.5,  10.0,  1.25),
    "gpt-4o-mini":               ( 0.15,  0.60, 0.075),
    "gpt-4-turbo":               (10.0,  30.0,  0.00),
    "gpt-4":                     (30.0,  60.0,  0.00),
    "gpt-3.5-turbo":             ( 0.5,   1.5,  0.00),
    "deepseek-chat":             ( 0.27,  1.10, 0.014),
    "deepseek-reasoner":         ( 0.55,  2.19, 0.014),
    "gemini-1.5-pro":            ( 1.25,  5.0,  0.00),
    "gemini-1.5-flash":          ( 0.075, 0.30, 0.00),
    "gemini-2.0-flash":          ( 0.10,  0.40, 0.00),
    "glm-4-plus":                ( 0.14,  0.14, 0.00),
    "glm-4":                     ( 0.14,  0.14, 0.00),
    "glm-4-flash":               ( 0.00,  0.00, 0.00),
    "moonshot-v1-128k":          ( 1.68,  1.68, 0.00),
    "moonshot-v1-32k":           ( 0.42,  0.42, 0.00),
}

_DEFAULT_CONTEXT_WINDOW = 32_000
_COMPACT_THRESHOLD = 0.82   # 超过 82% 触发自动紧凑化
_WARN_THRESHOLD    = 0.70   # 超过 70% 发出警告


def get_context_window(model: str) -> int:
    """获取模型的上下文窗口大小（tokens）"""
    # 尝试精确匹配
    if model in MODEL_CONTEXT_WINDOWS:
        return MODEL_CONTEXT_WINDOWS[model]
    # 前缀匹配（处理带日期的模型 ID）
    for key, size in MODEL_CONTEXT_WINDOWS.items():
        if model.startswith(key) or key.startswith(model.split("-")[0]):
            return size
    return _DEFAULT_CONTEXT_WINDOW


def estimate_tokens(text: str) -> int:
    """
    估算文本的 token 数。
    中文字符约 1 token/字，英文约 4 字符/token。
    """
    if not text:
        return 0
    chinese = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other = len(text) - chinese
    return chinese + max(1, other // 4)


def estimate_messages_tokens(messages: list, system_prompt: str = "") -> int:
    """估算完整消息列表的 token 数（含系统提示）"""
    total = estimate_tokens(system_prompt) + 4  # system message overhead

    for msg in messages:
        total += 4  # per-message overhead
        content = msg.get("content", "")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    total += estimate_tokens(
                        block.get("text", "") or block.get("content", "")
                        or str(block.get("input", ""))
                    )
        else:
            total += estimate_tokens(str(content))

        # tool_calls 参数
        for tc in msg.get("tool_calls", []):
            total += estimate_tokens(tc.get("name", "")) + estimate_tokens(
                str(tc.get("args", {}))
            )
        # tool_results
        for tr in msg.get("tool_results", []):
            total += estimate_tokens(str(tr.get("content", "")))

    return total


def get_context_usage(messages: list, model: str, system_prompt: str = "") -> dict:
    """
    返回上下文使用情况。
    {used, window, ratio, warning, compact_needed}
    """
    used   = estimate_messages_tokens(messages, system_prompt)
    window = get_context_window(model)
    ratio  = used / window

    return {
        "used":           used,
        "window":         window,
        "ratio":          ratio,
        "warning":        ratio >= _WARN_THRESHOLD,
        "compact_needed": ratio >= _COMPACT_THRESHOLD,
    }


def should_compact(messages: list, model: str, system_prompt: str = "") -> Tuple[bool, float, int, int]:
    """
    检查是否需要紧凑化。
    返回 (should_compact, ratio, used_tokens, window_tokens)
    """
    ctx = get_context_usage(messages, model, system_prompt)
    return ctx["compact_needed"], ctx["ratio"], ctx["used"], ctx["window"]


def calculate_cost(model: str, input_tokens: int, output_tokens: int,
                   cache_read_tokens: int = 0) -> float:
    """计算单次 API 调用的费用（USD）"""
    pricing = MODEL_PRICING.get(model)
    if not pricing:
        # 未知模型用 Sonnet 价格估算
        pricing = (3.0, 15.0, 0.30)
    inp_price, out_price, cache_price = pricing
    return (
        input_tokens      * inp_price   / 1_000_000
        + output_tokens   * out_price   / 1_000_000
        + cache_read_tokens * cache_price / 1_000_000
    )


def format_context_bar(ratio: float, width: int = 20) -> str:
    """返回一个简单的进度条字符串"""
    filled = int(ratio * width)
    bar = "█" * filled + "░" * (width - filled)
    pct = f"{ratio*100:.0f}%"
    return f"[{bar}] {pct}"
