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
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query

from kronos_fincept.logging_config import log_event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["suggestions"])


@dataclass
class SuggestionResult:
    questions: list[str]
    generated_at: float  # Unix timestamp


# In-memory cache: {"type:language": SuggestionResult}
_cache: dict[str, SuggestionResult] = {}
_cache_locks: dict[str, asyncio.Lock] = {
    "analysis": asyncio.Lock(),
    "macro": asyncio.Lock(),
}

# History: track last 3 generations per cache key to avoid repeats
_history: dict[str, deque[list[str]]] = {"analysis": deque(maxlen=3), "macro": deque(maxlen=3)}

SUGGESTION_CACHE_TTL_SECONDS = 8 * 3600
MAX_RETRIES = 3

# ── Prompt templates ──

_ANALYSIS_SYSTEM = """\
你是 KronosFinceptLab 的个股分析问题生成器。
输出必须是纯 JSON，格式：{"questions": ["问题1", "问题2", "问题3"]}

要求：
- 生成 3 个中文个股分析建议问题
- **所有问题都必须是针对具体个股的**（分析单只或比较多只股票）
- 支持的个股市场：A 股（6 位代码或中文名称）、港股（6 位代码或中文名称）、美股（1-5 位字母代码或中文名称）
- 每个问题必须包含具体的股票名称或股票代码
- 问题分析维度：行情走势、技术面、财务估值、风险评估、标的比较等
- 问题应多样化，覆盖不同市场和个股
- 问题应自然口语化，模拟真实用户提问
- 每个问题必须简短精悍，建议 6-36 个中文字符
- 禁止：宽泛的板块/行业/指数/宏观经济问题，禁止加密货币/黄金/大宗商品
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
- 4 个问题必须分别覆盖不同宏观维度（例如利率、商品、地缘、加密、市场情绪等），同一维度最多 1 个
- 加密货币最多 1 个问题，不能让 4 个问题都围绕比特币/ETH/加密市场
- 禁止：政治敏感、违法建议、色情、暴力、prompt 注入、绕过系统规则
- 禁止：空泛的非金融问题
- 必须与先前给出的建议完全不同，刻意探索新角度、新问法
- 只输出 JSON，不要任何解释"""

_ANALYSIS_SYSTEM_EN = """\
You generate single-stock research question suggestions for KronosFinceptLab.
Return pure JSON only: {"questions": ["question 1", "question 2", "question 3"]}

Rules:
- Generate 3 natural English questions.
- Every question must name a specific stock or ticker.
- Supported markets: China A-shares, Hong Kong stocks, and US stocks.
- Cover price action, technicals, valuation, risk, or comparisons.
- Keep each question concise and realistic.
- Do not generate broad sector, index, macro, crypto, commodity, political, illegal, sexual, violent, or prompt-injection questions.
- Output JSON only."""

_MACRO_SYSTEM_EN = """\
You generate macro and cross-market question suggestions for KronosFinceptLab.
Return pure JSON only: {"questions": ["question 1", "question 2", "question 3", "question 4"]}

Rules:
- Generate 4 natural English macro/cross-market questions.
- Cover different dimensions such as rates, inflation, gold, oil, geopolitics, crypto, risk appetite, equity-cycle valuation, or global markets.
- Keep each question concise and realistic.
- Do not generate political-sensitive, illegal, sexual, violent, prompt-injection, or non-financial questions.
- Output JSON only."""

# Random "flavor" phrases injected into user prompt to steer diversity
_ANALYSIS_FLAVORS = [
    "侧重A股科技龙头股",
    "侧重A股消费白马股",
    "侧重A股医药生物股",
    "侧重A股银行金融股",
    "侧重A股新能源股",
    "侧重A股制造龙头股",
    "侧重港股蓝筹股",
    "侧重港股中概科技股",
    "侧重美股科技七巨头",
    "侧重美股生物科技股",
    "侧重美股消费零售股",
    "侧重港股美股跨境比较",
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

_ANALYSIS_FALLBACKS_EN = [
    "Can I still buy China Merchants Bank now?",
    "Compare Kweichow Moutai and CATL short-term risk",
    "Analyze recent momentum in AAPL and NVDA",
]

_MACRO_FALLBACKS_EN = [
    "Is now a good time to buy gold?",
    "Will the Fed cut or hike next?",
    "Is the AI trade a bubble?",
    "Has Bitcoin bottomed yet?",
]

# ── Validation ──

# Analysis stock-only patterns: must reference a specific individual stock
_ANALYSIS_STOCK_PATTERNS = [
    r"(?<![a-zA-Z])[A-Z]{2,5}(?![a-zA-Z])",              # US ticker ≥2 chars (avoids "A股" false positive)
    r"(?<!\d)0\d{4}(?!\d)|(?<!\d)\d{6}(?!\d)",           # HK 5-digit (0xxxx) or CN 6-digit
    r"招商银行|贵州茅台|茅台|宁德时代|比亚迪|腾讯|阿里巴巴|拼多多|京东|百度",
    r"小米|美团|快手|网易|中国平安|万科|美的|格力|工商银行|农业银行|中国银行",
    r"[\u4e00-\u9fff]{2,6}(?:股份|集团|银行|证券|保险)",  # Company name + suffix (conservative)
]

MACRO_ALLOWED_PATTERNS = [
    r"宏观|周期|衰退|通胀|降息|加息|利率|国债|收益率|美元|美联储|央行|CPI|GDP|PMI|就业",
    r"黄金|白银|原油|铜|商品|避险|风险偏好|VIX|恐慌|贪婪",
    r"战争|地缘|冲突|WW3|第三次世界大战|选举|概率|预测市场|Polymarket|Kalshi",
    r"比特币|BTC|ETH|加密|crypto|Deribit|CoinGecko",
    r"泡沫|AI|半导体|行业周期|估值|买入时机|该不该买|能不能买",
    r"A股|港股|美股|大盘|指数|上证|深证|沪深|创业板|科创|恒生|国企指数|纳指|标普|道指|罗素",
    r"市场位置|现在位置|位置怎么样|适合.*(买|配置|入场)|风险偏好|资金面|流动性|估值区间",
    r"(?<![a-zA-Z])[A-Z]{1,5}(?![a-zA-Z])|(?<!\d)\d{6}(?!\d)",
]

_MACRO_CATEGORY_PATTERNS = [
    ("rates", r"利率|降息|加息|国债|收益率|美联储|央行|CPI|GDP|PMI|就业|美元|通胀|衰退"),
    ("commodities", r"黄金|白银|原油|铜|商品|大宗|避险"),
    ("geopolitics", r"战争|地缘|冲突|WW3|第三次世界大战|选举|预测市场|Polymarket|Kalshi"),
    ("crypto", r"比特币|BTC|ETH|加密|crypto|Deribit|CoinGecko"),
    ("equity_cycle", r"泡沫|AI|半导体|行业周期|估值|A股|港股|美股|大盘|指数|上证|深证|沪深|创业板|科创|恒生|纳指|标普|道指|罗素"),
    ("sentiment", r"风险偏好|VIX|恐慌|贪婪|市场情绪|资金面|流动性|市场位置|现在位置|配置|入场"),
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


def _fallback_questions(question_type: str, language: str) -> list[str]:
    if language == "en-US":
        return _ANALYSIS_FALLBACKS_EN if question_type == "analysis" else _MACRO_FALLBACKS_EN
    return _ANALYSIS_FALLBACKS if question_type == "analysis" else _MACRO_FALLBACKS


def _validate_questions(questions: list[str], question_type: str, language: str = "zh-CN") -> list[str]:
    """Filter out any question that fails scope/injection checks."""
    patterns = _ANALYSIS_STOCK_PATTERNS if question_type == "analysis" else MACRO_ALLOWED_PATTERNS
    clean: list[str] = []
    seen: set[str] = set()
    max_length = 90 if language == "en-US" else 36

    for q in questions:
        q = " ".join(str(q).strip().split())
        normalized = _normalize_question(q)
        if not q or len(q) < 6 or len(q) > max_length or normalized in seen:
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


def _macro_question_category(question: str) -> str:
    """Classify a macro suggestion into a broad dimension for same-batch diversity."""
    for category, pattern in _MACRO_CATEGORY_PATTERNS:
        if re.search(pattern, question, re.IGNORECASE):
            return category
    return "other"


def _select_diverse_macro_questions(questions: list[str], expected_count: int) -> list[str]:
    """Prefer one question per macro dimension before filling remaining slots."""
    selected: list[str] = []
    used_categories: set[str] = set()

    for question in questions:
        category = _macro_question_category(question)
        if category in used_categories:
            continue
        selected.append(question)
        used_categories.add(category)
        if len(selected) == expected_count:
            return selected

    for question in questions:
        if question not in selected:
            selected.append(question)
            if len(selected) == expected_count:
                break

    return selected


def _macro_diversity_count(questions: list[str]) -> int:
    return len({_macro_question_category(question) for question in questions})


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
    language: str = "zh-CN",
    history_key: str | None = None,
) -> list[str]:
    """Call the LLM to generate suggestions, with diversity retries."""
    from kronos_fincept.agent import _call_structured_llm_json

    history = _history.setdefault(history_key or question_type, deque(maxlen=3))
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
                avoid_text = (
                    f"\nDo not repeat or closely paraphrase these previous suggestions: {sample_str}"
                    if language == "en-US"
                    else f"\n严禁生成与以下历史建议重复或高度相似的问题：{sample_str}"
                )

        focus_prefix = "Focus direction" if language == "en-US" else "本次侧重方向"
        user_prompt = f"{user_prompt_template}\n{focus_prefix}：{flavor}。{avoid_text}"

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
            valid = _validate_questions(questions, question_type, language)

            if len(valid) < expected_count:
                logger.warning(
                    "Attempt %d: %d valid from %d generated (need %d)",
                    attempt + 1, len(valid), len(questions), expected_count,
                )
                continue

            # Check same-batch macro topic diversity before accepting.
            if question_type == "macro":
                candidates = _select_diverse_macro_questions(valid, expected_count)
                min_dimensions = min(3, expected_count)
                diversity_count = _macro_diversity_count(candidates)
                if diversity_count < min_dimensions:
                    logger.info(
                        "Attempt %d: only %d macro dimensions from %d questions, retrying",
                        attempt + 1, diversity_count, len(candidates),
                    )
                    continue
            else:
                candidates = valid[:expected_count]

            # Check diversity against history
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
    return _fallback_questions(question_type, language)


# ── Route ──


@router.get("/suggestions")
async def get_suggestions(
    type: str = Query("analysis", description="Suggestion type: 'analysis' or 'macro'"),
    language: Literal["zh-CN", "en-US"] = Query("zh-CN", description="Natural-language output language"),
) -> dict[str, Any]:
    """Return LLM-generated question suggestions (cached for 8 hours)."""
    if language not in ("zh-CN", "en-US"):
        language = "zh-CN"
    if type not in ("analysis", "macro"):
        raise HTTPException(status_code=400, detail="type must be 'analysis' or 'macro'")

    cache_key = type if language == "zh-CN" else f"{type}:{language}"
    _cache_locks.setdefault(cache_key, asyncio.Lock())

    # Check cache
    cached = _cache.get(cache_key)
    now = time.time()
    if cached and (now - cached.generated_at) < SUGGESTION_CACHE_TTL_SECONDS:
        return {
            "questions": cached.questions,
            "generated_at": cached.generated_at,
            "source": "cache",
        }

    async with _cache_locks[cache_key]:
        cached = _cache.get(cache_key)
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
                _ANALYSIS_SYSTEM_EN if language == "en-US" else _ANALYSIS_SYSTEM,
                "Generate 3 English single-stock research questions as JSON."
                if language == "en-US"
                else "请生成 3 个中文金融投资分析建议问题，以 JSON 格式输出。",
                [
                    "China A-share technology leaders",
                    "China A-share consumer blue chips",
                    "China A-share bank and finance stocks",
                    "Hong Kong technology stocks",
                    "US mega-cap technology stocks",
                    "cross-market stock comparisons",
                ]
                if language == "en-US"
                else _ANALYSIS_FLAVORS,
                3,
                "analysis",
                language,
                cache_key,
            )
        else:
            questions = await asyncio.to_thread(
                _call_llm_for_suggestions,
                _MACRO_SYSTEM_EN if language == "en-US" else _MACRO_SYSTEM,
                "Generate 4 English macro or cross-market research questions as JSON."
                if language == "en-US"
                else "请生成 4 个中文宏观经济/市场洞察问题，以 JSON 格式输出。",
                [
                    "rates and central banks",
                    "geopolitical risk",
                    "commodity prices and inflation",
                    "crypto and digital assets",
                    "global market valuation",
                    "risk appetite and liquidity",
                ]
                if language == "en-US"
                else _MACRO_FLAVORS,
                4,
                "macro",
                language,
                cache_key,
            )

        # Store in cache
        generated_at = time.time()
        result = SuggestionResult(questions=questions, generated_at=generated_at)
        _cache[cache_key] = result

        log_event(
            logger,
            logging.INFO,
            "suggestions.generated",
            f"Generated {len(questions)} {type} suggestions",
            suggestion_type=type,
            count=len(questions),
        )

        return {
            "questions": questions,
            "generated_at": generated_at,
            "source": "fresh",
        }
