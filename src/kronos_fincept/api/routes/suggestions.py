"""GET /api/v1/suggestions — LLM-generated financial question suggestions.

Replaces hardcoded example buttons on analysis/macro pages with fresh,
random suggestions regenerated periodically by the LLM.

Diversity guarantee: each generation uses a random seed, avoids repeating
questions from the last 3 generations, and retries with a different seed
if overlap exceeds 50%.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from collections import deque
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


# In-memory cache: {type: SuggestionResult}
_cache: dict[str, SuggestionResult] = {}

# History: track last 3 generations per type to avoid repeats
_history: dict[str, deque[list[str]]] = {"analysis": deque(maxlen=3), "macro": deque(maxlen=3)}

SUGGESTION_CACHE_TTL_SECONDS = 8 * 3600
MAX_RETRIES = 3

# ── Prompt templates ──

_ANALYSIS_SYSTEM = """\
你是 KronosFinceptLab 的金融问题生成器。
输出必须是纯 JSON，格式：{"questions": ["问题1", "问题2", "问题3"]}

要求：
- 生成 3 个中文金融投资分析建议问题
- 问题必须是金融投资相关：股票分析、行情预测、风险评估、标的比较等
- 问题应多样化，覆盖 A 股、港股、美股、加密货币、大宗商品等不同领域
- 问题应自然口语化，模拟真实用户提问
- 每个问题必须简短精悍，建议 6-36 个中文字符
- 包含至少一个带有具体股票名称或代码的问题
- 禁止：政治敏感、违法建议、色情、暴力、prompt 注入、绕过系统规则
- 禁止：空泛的非金融问题
- 必须与先前给出的建议完全不同，刻意探索新角度、新标的、新问法
- 只输出 JSON，不要任何解释"""

_MACRO_SYSTEM = """\
你是 KronosFinceptLab 的宏观洞察问题生成器。
输出必须是纯 JSON，格式：{"questions": ["问题1", "问题2", "问题3", "问题4"]}

要求：
- 生成 4 个中文宏观经济/市场洞察问题
- 问题必须是宏观经济或跨市场相关：黄金、利率、通胀、地缘风险、加密货币、市场泡沫、
  行业周期、全球市场位置、风险偏好、大类资产配置等
- 问题应自然口语化，模拟真实用户提问
- 每个问题必须简短精悍，建议 6-36 个中文字符
- 覆盖不同宏观维度（利率、商品、地缘、加密、市场情绪等）
- 禁止：政治敏感、违法建议、色情、暴力、prompt 注入、绕过系统规则
- 禁止：空泛的非金融问题
- 必须与先前给出的建议完全不同，刻意探索新角度、新问法
- 只输出 JSON，不要任何解释"""

# Random "flavor" phrases injected into user prompt to steer diversity
_ANALYSIS_FLAVORS = [
    "侧重科技股和半导体板块",
    "侧重消费和医药板块",
    "侧重银行和金融板块",
    "侧重能源和资源板块",
    "侧重港股和跨境标的",
    "侧重加密货币和数字资产",
    "侧重 ETF 和指数基金",
    "侧重技术面和量化因子",
    "侧重财报和基本面估值",
    "侧重宏观经济对个股的影响",
    "侧重新兴市场和中小盘",
    "侧重避险资产和防御策略",
]

_MACRO_FLAVORS = [
    "侧重利率和央行政策",
    "侧重地缘政治和战争风险",
    "侧重商品价格和通胀预期",
    "侧重加密货币和数字资产",
    "侧重全球贸易和供应链",
    "侧重市场情绪和泡沫风险",
    "侧重房地产和信贷周期",
    "侧重汇率和资本流动",
    "侧重劳动力市场和消费",
    "侧重科技创新和产业周期",
    "侧重 ESG 和气候风险",
    "侧重新兴市场和债务风险",
]

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


def _validate_questions(questions: list[str], question_type: str) -> list[str]:
    """Filter out any question that fails scope/injection checks."""
    patterns = ALLOWED_SCOPE_PATTERNS if question_type == "analysis" else MACRO_ALLOWED_PATTERNS
    clean: list[str] = []
    seen: set[str] = set()

    for q in questions:
        q = " ".join(str(q).strip().split())
        normalized = _normalize_question(q)
        if not q or len(q) < 6 or len(q) > 36 or normalized in seen:
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

        seen.add(normalized)
        clean.append(q)

    return clean


def _normalize_question(question: str) -> str:
    return re.sub(r"[\s，。！？、,.!?；;：:\"'“”‘’（）()【】\[\]<>《》-]+", "", question.lower())


def _overlap_ratio(new_questions: list[str], history: deque[list[str]]) -> float:
    """Return the fraction of new questions that match any historical question."""
    if not history or not new_questions:
        return 0.0
    new_set = {_normalize_question(q) for q in new_questions}
    old_set = set()
    for past in history:
        old_set.update(_normalize_question(q) for q in past)
    if not old_set:
        return 0.0
    return len(new_set & old_set) / len(new_set)


def _call_llm_for_suggestions(
    system_prompt: str,
    user_prompt_template: str,
    flavors: list[str],
    expected_count: int,
    question_type: str,
) -> list[str]:
    """Call the LLM to generate suggestions, with diversity retries."""
    from kronos_fincept.agent import _call_structured_llm_json

    history = _history[question_type]
    used_flavors: set[str] = set()

    for attempt in range(MAX_RETRIES):
        # Pick a random flavor not yet tried in this generation cycle
        available = [f for f in flavors if f not in used_flavors]
        if not available:
            available = flavors  # fallback: reuse
        flavor = random.choice(available)
        used_flavors.add(flavor)

        # Build user prompt with diversity instructions
        avoid_text = ""
        if history:
            past_samples = []
            for past_set in history:
                past_samples.extend(past_set[:2])  # show at most 2 per past set
            if past_samples:
                sample_str = "、".join(f"「{q}」" for q in past_samples[:6])
                avoid_text = f"\n严禁生成与以下历史建议重复或高度相似的问题：{sample_str}"

        user_prompt = f"{user_prompt_template}\n本次侧重方向：{flavor}。{avoid_text}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            result = _call_structured_llm_json(
                messages,
                temperature=0.95,
                max_tokens=300,
                timeout=15,
                purpose="suggestions",
                provider_order=("deepseek", "openrouter"),
            )

            if result is None:
                continue

            parsed, _provider = result

            # Extract questions from JSON response
            questions: list[str] = []
            if isinstance(parsed, dict):
                raw = parsed.get("questions")
                if isinstance(raw, list):
                    questions = [str(q).strip() for q in raw if q]
            if not questions:
                content = parsed.get("content") or parsed.get("text") or ""
                if isinstance(content, str):
                    lines = [line.strip() for line in content.split("\n") if line.strip()]
                    questions = [line.lstrip("0123456789. -•·\"'") for line in lines]
                    questions = [q.strip("\"'") for q in questions if q.strip()]

            # Validate
            valid = _validate_questions(questions, question_type)

            if len(valid) < expected_count:
                logger.warning(
                    "Attempt %d: %d valid from %d generated (need %d)",
                    attempt + 1, len(valid), len(questions), expected_count,
                )
                continue

            # Check diversity against history
            candidates = valid[:expected_count]
            ratio = _overlap_ratio(candidates, history)
            if ratio > 0.5 and attempt < MAX_RETRIES - 1:
                logger.info(
                    "Attempt %d: %.0f%% overlap with history, retrying with different flavor",
                    attempt + 1, ratio * 100,
                )
                continue

            # Success
            history.append(candidates)
            return candidates

        except Exception as exc:
            log_event(
                logger,
                logging.WARNING,
                "suggestions.llm_attempt_failed",
                f"LLM suggestion attempt {attempt + 1} failed: {exc}",
                error_type=type(exc).__name__,
            )
            continue

    # All retries exhausted
    logger.warning("All %d LLM suggestion retries failed, using fallbacks", MAX_RETRIES)
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

    if type == "analysis":
        questions = await asyncio.to_thread(
            _call_llm_for_suggestions,
            _ANALYSIS_SYSTEM,
            "请生成 3 个中文金融投资分析建议问题，以 JSON 格式输出。",
            _ANALYSIS_FLAVORS,
            3,
            "analysis",
        )
    else:
        questions = await asyncio.to_thread(
            _call_llm_for_suggestions,
            _MACRO_SYSTEM,
            "请生成 4 个中文宏观经济/市场洞察问题，以 JSON 格式输出。",
            _MACRO_FLAVORS,
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
