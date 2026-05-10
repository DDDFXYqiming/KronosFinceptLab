"""GET /api/v1/suggestions — LLM-generated financial question suggestions.

Replaces hardcoded example buttons on analysis/macro pages with fresh,
random suggestions regenerated periodically by the LLM.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from kronos_fincept.logging_config import log_event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["suggestions"])


@dataclass
class SuggestionResult:
    questions: list[str]
    generated_at: float  # Unix timestamp


# In-memory cache: {(type,): (timestamp, questions)}
_cache: dict[str, SuggestionResult] = {}

SUGGESTION_CACHE_TTL_SECONDS = 8 * 3600  # 8 hours

# ── Prompt templates ──

_ANALYSIS_SYSTEM = """\
你是 KronosFinceptLab 的金融问题生成器。
输出必须是纯 JSON，格式：{"questions": ["问题1", "问题2", "问题3"]}

要求：
- 生成 3 个中文金融投资分析建议问题
- 问题必须是金融投资相关：股票分析、行情预测、风险评估、标的比较等
- 问题应多样化，覆盖 A 股、港股、美股、加密货币、大宗商品等不同领域
- 问题应自然口语化，模拟真实用户提问
- 包含至少一个带有具体股票名称或代码的问题
- 禁止：政治敏感、违法建议、色情、暴力、prompt 注入、绕过系统规则
- 禁止：空泛的非金融问题
- 只输出 JSON，不要任何解释"""

_ANALYSIS_USER = """\
请生成 3 个中文金融投资分析建议问题，以 JSON 格式输出。"""

_MACRO_SYSTEM = """\
你是 KronosFinceptLab 的宏观洞察问题生成器。
输出必须是纯 JSON，格式：{"questions": ["问题1", "问题2", "问题3", "问题4"]}

要求：
- 生成 4 个中文宏观经济/市场洞察问题
- 问题必须是宏观经济或跨市场相关：黄金、利率、通胀、地缘风险、加密货币、市场泡沫、
  行业周期、全球市场位置、风险偏好、大类资产配置等
- 问题应自然口语化，模拟真实用户提问
- 覆盖不同宏观维度（利率、商品、地缘、加密、市场情绪等）
- 禁止：政治敏感、违法建议、色情、暴力、prompt 注入、绕过系统规则
- 禁止：空泛的非金融问题
- 只输出 JSON，不要任何解释"""

_MACRO_USER = """\
请生成 4 个中文宏观经济/市场洞察问题，以 JSON 格式输出。"""

# ── Hardcoded fallbacks ──

_ANALYSIS_FALLBACKS = [
    "帮我看看招商银行现在能不能买",
    "比较贵州茅台和宁德时代的短期走势",
    "分析一下 AAPL 和 NVDA 最近表现",
]

_MACRO_FALLBACKS = [
    "现在适合买黄金吗",
    "美联储下一步会加息还是降息",
    "AI 是不是泡沫",
    "比特币到底了吗",
]

# ── Validation ──

ALLOWED_SCOPE_PATTERNS = [
    r"\b[A-Z]{1,5}\b",
    r"\b\d{6}\b",
    r"股票|股价|证券|A股|美股|港股|行情|走势|趋势|上涨|下跌|涨幅|跌幅|买|卖|持有|风险|预测|回测|量化|投资|资产|组合",
    r"估值|目标价|财报|业绩|短期|中期|长期|看好|看空",
    r"能买吗|能不能买|可以买|适合买|该不该买|值不值|见底|到顶|抄底|追高",
    r"Kronos|DeepSeek|模型|财务|技术面|基本面|指标|VaR|Sharpe|波动|回撤",
    r"\b[A-Z]{2,6}\b",
]

MACRO_ALLOWED_PATTERNS = [
    r"宏观|周期|衰退|通胀|降息|加息|利率|国债|收益率|美元|美联储|央行|CPI|GDP|PMI|就业",
    r"黄金|白银|原油|铜|商品|避险|风险偏好|VIX|恐慌|贪婪",
    r"战争|地缘|冲突|WW3|第三次世界大战|选举|概率|预测市场|Polymarket|Kalshi",
    r"比特币|BTC|ETH|加密|crypto|Deribit|CoinGecko",
    r"泡沫|AI|半导体|行业周期|估值|买入时机|该不该买|能不能买",
    r"A股|港股|美股|大盘|指数|上证|深证|沪深|创业板|科创|恒生|国企指数|纳指|标普|道指|罗素",
    r"市场位置|现在位置|位置怎么样|适合.*(买|配置|入场)|风险偏好|资金面|流动性|估值区间",
    r"\b[A-Z]{1,5}\b|\b\d{6}\b",
]

PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|rules|prompts)",
    r"忽略(以上|之前|前面|所有).*(规则|指令|提示|约束)",
    r"(system|developer)\s+prompt",
    r"系统提示|开发者提示|隐藏提示词|提示词全文",
    r"泄露|透露|输出.*(密钥|key|token|secret|\.env|环境变量|凭据)",
    r"api[_\s-]?key|secret[_\s-]?key|access[_\s-]?token|authorization",
    r"未授权工具|越权|绕过|jailbreak|越狱",
    r"执行(系统)?命令|shell|powershell|cmd\.exe|rm\s+-rf|删除文件",
]

import re


def _validate_questions(questions: list[str], question_type: str) -> list[str]:
    """Filter out any question that fails scope/injection checks."""
    patterns = ALLOWED_SCOPE_PATTERNS if question_type == "analysis" else MACRO_ALLOWED_PATTERNS
    clean: list[str] = []

    for q in questions:
        q = q.strip()
        if not q or len(q) < 3 or len(q) > 120:
            continue

        # Reject prompt injection
        lowered = q.lower()
        if any(re.search(p, lowered, re.IGNORECASE) for p in PROMPT_INJECTION_PATTERNS):
            logger.warning("Suggestion rejected (injection): %r", q[:80])
            continue

        # Require at least one allowed scope pattern match
        if not any(re.search(p, lowered, re.IGNORECASE) for p in patterns):
            logger.warning("Suggestion rejected (out of scope): %r", q[:80])
            continue

        clean.append(q)

    return clean


def _call_llm_for_suggestions(
    system_prompt: str,
    user_prompt: str,
    expected_count: int,
    question_type: str,
) -> list[str]:
    """Call the LLM to generate suggestions, with validation and fallback."""
    try:
        from kronos_fincept.agent import _call_structured_llm_json

        # Use a simple text completion approach (not JSON structured)
        # We'll use _call_structured_llm_json with a simple text extraction
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        result = _call_structured_llm_json(
            messages,
            temperature=0.9,
            max_tokens=300,
            timeout=15,
            purpose="suggestions",
        )

        if result is None:
            logger.warning("LLM suggestions call returned None, using fallbacks")
            return _ANALYSIS_FALLBACKS if question_type == "analysis" else _MACRO_FALLBACKS

        parsed, provider = result

        # Extract questions from JSON response
        questions = []
        if isinstance(parsed, dict):
            raw = parsed.get("questions")
            if isinstance(raw, list):
                questions = [str(q).strip() for q in raw if q]
        if not questions:
            # Fallback: try to parse from content field
            content = parsed.get("content") or parsed.get("text") or ""
            if isinstance(content, str):
                lines = [line.strip() for line in content.split("\n") if line.strip()]
                questions = [line.lstrip("0123456789. -•·\"'") for line in lines]
                questions = [q.strip("\"'") for q in questions if q.strip()]

        # Validate
        valid = _validate_questions(questions, question_type)

        if len(valid) >= expected_count:
            return valid[:expected_count]

        logger.warning(
            "LLM generated %d suggestions but only %d passed validation (need %d)",
            len(questions),
            len(valid),
            expected_count,
        )
        return _ANALYSIS_FALLBACKS if question_type == "analysis" else _MACRO_FALLBACKS

    except Exception as exc:
        log_event(
            logger,
            logging.WARNING,
            "suggestions.llm_failed",
            f"LLM suggestion generation failed: {exc}",
            error_type=type(exc).__name__,
        )
        return _ANALYSIS_FALLBACKS if question_type == "analysis" else _MACRO_FALLBACKS


# ── Route ──


@router.get("/suggestions")
async def get_suggestions(
    type: str = Query("analysis", description="Suggestion type: 'analysis' or 'macro'"),
) -> dict[str, Any]:
    """Return LLM-generated question suggestions (cached for 8 hours)."""
    if type not in ("analysis", "macro"):
        raise HTTPException(status_code=400, detail="type must be 'analysis' or 'macro'")

    # Check cache
    cached = _cache.get(type)
    now = time.time()
    if cached and (now - cached.generated_at) < SUGGESTION_CACHE_TTL_SECONDS:
        return {
            "questions": cached.questions,
            "generated_at": cached.generated_at,
            "source": "cache",
        }

    # Generate new suggestions
    if type == "analysis":
        questions = await asyncio.to_thread(
            _call_llm_for_suggestions,
            _ANALYSIS_SYSTEM,
            _ANALYSIS_USER,
            3,
            "analysis",
        )
    else:
        questions = await asyncio.to_thread(
            _call_llm_for_suggestions,
            _MACRO_SYSTEM,
            _MACRO_USER,
            4,
            "macro",
        )

    # Store in cache
    result = SuggestionResult(questions=questions, generated_at=now)
    _cache[type] = result

    log_event(
        logger,
        logging.INFO,
        "suggestions.generated",
        f"Generated {len(questions)} {type} suggestions",
        type=type,
        count=len(questions),
    )

    return {
        "questions": questions,
        "generated_at": now,
        "source": "fresh",
    }
