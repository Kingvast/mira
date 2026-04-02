#!/usr/bin/env python3
"""
费用跟踪 - 按模型累计 API 调用成本
"""

from dataclasses import dataclass, field
from typing import Dict

from mira.utils.context import calculate_cost


@dataclass
class _UsageRecord:
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    calls: int = 0

    @property
    def cost_usd(self) -> float:
        return calculate_cost(
            self.model, self.input_tokens,
            self.output_tokens, self.cache_read_tokens
        )


class CostTracker:
    """追踪当前会话的 API 调用费用（线程安全地累加）"""

    def __init__(self):
        self._records: Dict[str, _UsageRecord] = {}
        self.total_input      = 0
        self.total_output     = 0
        self.total_cache_read = 0

    def add(self, model: str, input_tokens: int = 0,
            output_tokens: int = 0, cache_read: int = 0):
        """记录一次 API 调用的 token 用量"""
        if model not in self._records:
            self._records[model] = _UsageRecord(model)
        rec = self._records[model]
        rec.input_tokens      += input_tokens
        rec.output_tokens     += output_tokens
        rec.cache_read_tokens += cache_read
        rec.calls             += 1
        self.total_input      += input_tokens
        self.total_output     += output_tokens
        self.total_cache_read += cache_read

    @property
    def total_usd(self) -> float:
        return sum(r.cost_usd for r in self._records.values())

    @property
    def total_tokens(self) -> int:
        return self.total_input + self.total_output

    def summary(self) -> dict:
        return {
            "total_usd":        round(self.total_usd, 6),
            "total_input":      self.total_input,
            "total_output":     self.total_output,
            "total_cache_read": self.total_cache_read,
            "models": {
                m: {
                    "calls":       r.calls,
                    "input":       r.input_tokens,
                    "output":      r.output_tokens,
                    "cache_read":  r.cache_read_tokens,
                    "cost_usd":    round(r.cost_usd, 6),
                }
                for m, r in self._records.items()
            },
        }

    def format_display(self) -> str:
        if not self._records:
            return "暂无费用记录"
        lines = []
        for m, r in self._records.items():
            lines.append(
                f"  {m}\n"
                f"    调用 {r.calls} 次 │ 输入 {r.input_tokens:,} │ "
                f"输出 {r.output_tokens:,} │ 缓存读 {r.cache_read_tokens:,}\n"
                f"    费用 ≈ ${r.cost_usd:.5f}"
            )
        total = self.total_usd
        cost_str = f"${total:.5f}" if total < 1 else f"${total:.4f}"
        lines.append(
            f"\n  合计: {cost_str}  "
            f"({self.total_input:,} 输入 + {self.total_output:,} 输出 tokens)"
        )
        return "\n".join(lines)

    def reset(self):
        self._records.clear()
        self.total_input = self.total_output = self.total_cache_read = 0
