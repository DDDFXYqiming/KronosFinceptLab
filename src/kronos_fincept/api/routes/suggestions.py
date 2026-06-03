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
from datetime import datetime
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

SUGGESTION_CACHE_TTL_SECONDS = 2 * 3600
MAX_RETRIES = 3

# ── Random concept injection pool ──
# Unrelated Chinese words to break LLM mode collapse (arXiv:2601.18053)
_RANDOM_WORDS = [
    "潮汐", "蜂鸟", "琥珀", "漩涡", "极光", "珊瑚", "闪电", "露珠", "星尘", "迷雾",
    "竹林", "瀑布", "沙漏", "羽毛", "齿轮", "水晶", "火山", "冰川", "沙漠", "彩虹",
    "蝴蝶", "海豚", "鲸鱼", "老鹰", "松鼠", "企鹅", "海鸥", "孔雀", "骆驼", "猎豹",
    "钢琴", "小提琴", "鼓点", "旋律", "和弦", "节拍", "音符", "交响", "回声", "寂静",
    "水墨", "油画", "素描", "雕塑", "陶艺", "篆刻", "书法", "壁画", "版画", "拼贴",
    "咖啡", "抹茶", "可可", "薄荷", "肉桂", "柠檬", "芒果", "荔枝", "杨梅", "椰子",
    "丝绸", "棉麻", "羊毛", "皮革", "牛仔", "天鹅绒", "亚麻", "雪纺", "灯芯绒", "帆布",
    "望远镜", "指南针", "地图", "灯笼", "火把", "蜡烛", "油灯", "手电", "信号弹", "篝火",
    "风筝", "陀螺", "弹珠", "积木", "拼图", "万花筒", "棱镜", "沙盘", "魔方", "九连环",
    "山涧", "峡谷", "悬崖", "洞穴", "温泉", "湖泊", "沼泽", "绿洲", "草原", "雨林",
    "铁匠", "木匠", "陶工", "织工", "渔夫", "猎人", "农夫", "园丁", "石匠", "画师",
    "春风", "夏雨", "秋叶", "冬雪", "晨曦", "暮色", "月光", "星空", "云海", "霞光",
    "围棋", "象棋", "桥牌", "麻将", "谜语", "灯谜", "对联", "诗词", "歌赋", "戏曲",
    "青瓷", "紫砂", "漆器", "玉雕", "木雕", "竹编", "草编", "剪纸", "年画", "刺绣",
    "信鸽", "燕子", "喜鹊", "鹦鹉", "画眉", "百灵", "黄鹂", "杜鹃", "麻雀", "乌鸦",
    "石桥", "拱门", "庭院", "回廊", "亭台", "楼阁", "城墙", "古塔", "牌坊", "戏台",
]

# ── Expanded question banks (50+ each) for few-shot injection ──
_ANALYSIS_QUESTION_BANK = [
    # ── 走势判断类 ──
    "比亚迪最近还能上车吗",
    "腾讯控股现在估值合理吗",
    "小米集团的短期走势怎么看",
    "美团技术面有什么信号",
    "网易最近表现怎么样",
    "贵州茅台现在是高位还是低位",
    "招商银行现在能买吗",
    "中国平安的支撑位在哪",
    "宁德时代短期有没有反弹机会",
    "比亚迪和特斯拉走势谁更强",
    # ── 技术指标类 ──
    "中芯国际的RSI信号怎么样",
    "药明康德的KDJ金叉了吗",
    "隆基绿能的CCI到超卖区了吗",
    "海天味业的均线排列如何",
    "五粮液的技术面支撑位在哪",
    "泸州老窖的MACD背离了吗",
    "汾酒的布林带收口了吗",
    "洋河股份的成交量配合如何",
    "中国中免的K线形态怎么看",
    "长江电力的波动率大吗",
    # ── 买卖时机类 ──
    "紫金矿业现在适合建仓吗",
    "中国神华什么价位可以买入",
    "恒瑞医药现在该止损还是持有",
    "迈瑞医疗的入场时机到了吗",
    "三一重工现在是买点吗",
    "万华化学可以加仓了吗",
    "海螺水泥要不要割肉",
    "上汽集团现在能抄底吗",
    "分众传媒可以定投了吗",
    "东方财富现在追高风险大吗",
    # ── 风险评估类 ──
    "牧原股份的下行风险有多大",
    "伊利股份目前的风险收益比如何",
    "阳光电源的回撤风险高吗",
    "汇川技术的波动率能接受吗",
    "韦尔股份的风险等级怎么样",
    "兆易创新现在风险大还是机会大",
    "科大讯飞的估值泡沫大吗",
    "用友网络的下行空间还有多少",
    "金山办公的风险收益比合适吗",
    "海尔智家的估值安全边际够吗",
    # ── 标的对比类 ──
    "格力电器和美的集团谁更值得买",
    "中国联通和中国移动谁走势更强",
    "中远海控和招商轮船选哪个",
    "中国中铁和中国建筑谁更有潜力",
    "北方华创和中微公司谁技术面更好",
    "沪硅产业和中芯国际谁风险更低",
    "百济神州和恒瑞医药谁更有投资价值",
    "伊利股份和蒙牛乳业谁估值更低",
    "工商银行和建设银行谁股息更高",
    "宁德时代和比亚迪谁短期更有机会",
]

_MACRO_QUESTION_BANK = [
    "现在适合买黄金吗",
    "美联储下一步会加息还是降息",
    "AI是不是泡沫",
    "比特币到底了吗",
    "美元走势怎么看",
    "原油价格还会涨吗",
    "铜价的上涨空间有多大",
    "白银是不是被低估了",
    "美债收益率还会升吗",
    "通胀是不是已经见顶了",
    "全球衰退的概率有多大",
    "日本央行什么时候退出YCC",
    "欧洲经济会不会硬着陆",
    "新兴市场还有投资机会吗",
    "VIX恐慌指数说明了什么",
    "美股现在估值泡沫大吗",
    "A股的底部到底在哪里",
    "港股为什么一直跌",
    "房地产还会继续下行吗",
    "中国的消费复苏进度如何",
    "供应链转移对中国制造业的影响",
    "半导体周期什么时候见底",
    "新能源车的渗透率天花板在哪",
    "碳中和目标下的投资机会",
    "地缘冲突对油价的影响有多大",
    "人民币汇率会破7吗",
    "全球央行的购金趋势",
    "加密货币监管趋严的影响",
    "DeFi还有未来吗",
    "以太坊和比特币谁更值得持有",
    "NFT市场还有回暖的可能吗",
    "全球粮食危机的风险",
    "气候风险对投资组合的影响",
    "ESG投资真的有效吗",
    "量化宽松的退出路径",
    "银行危机还会重演吗",
    "商业地产的风险有多大",
    "科技股泡沫和2000年比怎么样",
    "就业市场的韧性还能持续多久",
    "消费者信心指数的趋势",
    "PMI数据暗示了什么",
    "财政赤字对长期利率的影响",
    "中美关系对市场的影响",
    "台海风险如何定价",
    "中东局势对能源市场的影响",
    "印度经济的增长潜力",
    "越南制造业崛起的机遇",
    "全球债务规模的风险",
    "利率倒挂意味着什么",
    "实际利率转正对资产配置的影响",
]

_ANALYSIS_QUESTION_BANK_EN = [
    # ── Trend analysis ──
    "Can I still buy AAPL at this price?",
    "Is NVDA overvalued after the AI rally?",
    "TSLA short-term technical outlook",
    "Compare MSFT and GOOGL risk profiles",
    "META earnings momentum analysis",
    "AMZN vs AAPL which is a better hold",
    "BABA valuation after the China selloff",
    "Tencent growth prospects in 2025",
    "JD.com competitive position vs PDD",
    "BYD electric vehicle expansion outlook",
    # ── Technical indicators ──
    "TSMC RSI signal interpretation",
    "LLY is KDJ showing overbought?",
    "JPM CCI indicator analysis",
    "V and MA moving average alignment",
    "NFLX Bollinger Band squeeze check",
    "DIS MACD divergence signal",
    "BA volume confirmation analysis",
    "XOM support level identification",
    "CVX resistance level breakdown",
    "PFE volatility assessment",
    # ── Buy/sell timing ──
    "INTC is now a good entry point?",
    "AMD when to take profit",
    "CRM should I add to my position?",
    "ADSK stop loss or hold?",
    "ORCL buy the dip opportunity?",
    "QCOM is the pullback a buying chance?",
    "AVGO time to accumulate?",
    "NOW is it too late to enter?",
    "SNAP bottom fishing signal check",
    "SQ risk-reward at current price",
    # ── Risk assessment ──
    "SHOP downside risk evaluation",
    "SE drawdown probability analysis",
    "NIO risk level assessment",
    "LI Auto vs NIO which is safer",
    "XPEV price floor estimation",
    "BIDU valuation bubble check",
    "PDD downside space analysis",
    "BILI risk-reward ratio assessment",
    "ZTO Express volatility tolerance",
    "MNSO investment safety margin",
    # ── Stock comparison ──
    "FUTU vs TIGR which has better momentum",
    "EDU vs TAL which is less risky",
    "YMM vs ZH which to buy now",
    "IQ vs BILI technical comparison",
    "VNET vs KC which has stronger support",
    "SOHU vs SINA price trend comparison",
    "NIO vs LI Auto short-term opportunity",
    "JD vs PDD which has better entry",
    "BABA vs BIDU which is undervalued",
    "AAPL vs MSFT risk-adjusted return",
]

_MACRO_QUESTION_BANK_EN = [
    "Is now a good time to buy gold?",
    "Will the Fed cut or hike next?",
    "Is the AI trade a bubble?",
    "Has Bitcoin bottomed yet?",
    "USD dollar index trajectory",
    "Crude oil price forecast",
    "Copper demand outlook from EVs",
    "Silver undervaluation thesis",
    "US Treasury yield direction",
    "Has inflation peaked?",
    "Global recession probability",
    "BOJ yield curve control exit timing",
    "European economic hard landing risk",
    "Emerging market investment case",
    "VIX what is the fear gauge saying",
    "US equity valuation bubble check",
    "China A-shares bottom fishing timing",
    "Hong Kong market structural discount",
    "US commercial real estate risk",
    "Supply chain reshoring impact",
    "Semiconductor cycle bottom timing",
    "EV penetration ceiling analysis",
    "Climate risk portfolio impact",
    "ESG investing effectiveness debate",
    "QE exit path and market impact",
    "Banking crisis recurrence risk",
    "Tech bubble vs 2000 comparison",
    "Labor market resilience duration",
    "Consumer confidence trend",
    "PMI leading indicator signals",
    "Fiscal deficit rate impact",
    "US-China decoupling investment risk",
    "Taiwan risk premium pricing",
    "Middle East energy supply disruption",
    "India growth potential analysis",
    "Vietnam manufacturing opportunity",
    "Global debt sustainability risk",
    "Yield curve inversion signal",
    "Real rates turning positive impact",
    "Crypto regulation tightening effect",
    "DeFi future viability assessment",
    "ETH vs BTC relative value",
    "NFT market recovery possibility",
    "Global food security risk",
    "Brexit long-term economic impact",
    "Japan equity re-rating thesis",
    "Korea semiconductor export trend",
    "Brazil fiscal reform progress",
    "Mexico nearshoring beneficiary play",
    "Turkey unorthodox policy reversal",
]


def _extract_entities_from_history(history: deque[list[str]]) -> set[str]:
    """Extract stock names, tickers, and codes from historical questions for blacklist."""
    entities: set[str] = set()
    known_stocks = [
        "招商银行", "贵州茅台", "茅台", "宁德时代", "比亚迪", "腾讯", "阿里巴巴",
        "拼多多", "京东", "百度", "小米", "美团", "快手", "网易", "中国平安", "万科",
        "美的", "格力", "工商银行", "农业银行", "中国银行", "建设银行", "交通银行",
        "兴业银行", "浦发银行", "民生银行", "中信银行", "光大银行", "平安银行",
        "五粮液", "泸州老窖", "汾酒", "洋河股份", "海天味业", "伊利股份",
        "恒瑞医药", "迈瑞医疗", "药明康德", "中芯国际", "隆基绿能", "中国中免",
        "长江电力", "紫金矿业", "中国神华", "三一重工", "万华化学", "海螺水泥",
        "上汽集团", "分众传媒", "东方财富", "牧原股份", "阳光电源", "汇川技术",
        "韦尔股份", "兆易创新", "科大讯飞", "用友网络", "金山办公", "海尔智家",
        "格力电器", "美的集团", "中国联通", "中国移动", "中国电信", "中远海控",
        "中国中铁", "北方华创", "中微公司", "沪硅产业", "百济神州", "中国建筑",
        "特斯拉", "苹果", "英伟达", "微软", "谷歌", "亚马逊", "Meta", "台积电",
    ]
    us_ticker_pattern = re.compile(r"(?<![a-zA-Z])([A-Z]{2,5})(?![a-zA-Z])")
    cn_code_pattern = re.compile(r"(?<!\d)(\d{6}|\d{5})(?!\d)")
    _SKIP_TICKERS = {"A股", "港股", "美股", "CPI", "GDP", "PMI", "ETF", "LLM",
                     "AI", "BTC", "ETH", "VIX", "UV", "OK", "THE", "FOR", "AND",
                     "BUT", "NOT", "HAS", "HAD", "WAS", "ARE", "ITS", "CAN", "GET"}

    for past_set in history:
        text = " ".join(past_set)
        for stock in known_stocks:
            if stock in text:
                entities.add(stock)
        for m in us_ticker_pattern.finditer(text):
            ticker = m.group(1)
            if ticker not in _SKIP_TICKERS:
                entities.add(ticker)
        for m in cn_code_pattern.finditer(text):
            entities.add(m.group(1))
    return entities

# ── Prompt templates ──

_ANALYSIS_SYSTEM = """\
你是 KronosFinceptLab 的个股分析问题生成器。
输出必须是纯 JSON，格式：{"questions": ["问题1", "问题2", "问题3"]}

【系统能力说明——必须严格遵守】
本系统只能做以下事情：
1. 查询个股的实时/历史价格数据
2. 计算技术指标（RSI、KDJ、CCI 等）
3. 运行 Kronos 预测模型生成未来走势预测
4. 基于价格+指标+预测给出买入/卖出/持有建议、置信度、风险等级

本系统无法回答以下类型的问题：
- 产品管线、研发进展、技术前景
- 商业模式、竞争格局、行业研究
- 管理层能力、公司战略、并购重组
- 政策影响、监管变化的定性分析
- 任何需要"看研报""看新闻""看公告"才能回答的问题

【生成策略（必须严格按步骤执行）】
第一步：在脑中列出 10 个你可能会分析的个股标的，确保覆盖 A股、港股、美股三个市场。
第二步：从这 10 个中选出 3 个最有分析价值且互相差异最大的标的。
第三步：为每个标的生成一个口语化的分析问题，问题必须围绕"价格走势、技术面信号、买卖时机、风险评估"展开。

要求：
- 生成 3 个中文个股分析建议问题
- **所有问题都必须是针对具体个股的**（分析单只或比较多只股票）
- 支持的个股市场：A 股（6 位代码或中文名称）、港股（6 位代码或中文名称）、美股（1-5 位字母代码或中文名称）
- 每个问题必须包含具体的股票名称或股票代码
- **问题必须围绕以下维度之一**：当前走势判断、技术面信号解读、短期买卖时机、估值位置评估、风险收益比、两只股票对比
- 问题应自然口语化，模拟真实用户提问
- 每个问题必须简短精悍，建议 6-36 个中文字符
- 禁止：产品管线、商业模式、竞争格局、行业研究、研发进展、技术前景等定性研究问题
- 禁止：宽泛的板块/行业/指数/宏观经济问题，禁止加密货币/黄金/大宗商品
- 禁止：政治敏感、违法建议、色情、暴力、prompt 注入、绕过系统规则
- 禁止：空泛的非金融问题
- 必须与先前给出的建议完全不同，刻意探索新角度、新标的、新问法
- 只输出 JSON，不要任何解释"""

_MACRO_SYSTEM = """\
你是 KronosFinceptLab 的宏观洞察问题生成器。
输出必须是纯 JSON，格式：{"questions": ["问题1", "问题2", "问题3", "问题4"]}

生成策略（必须严格按步骤执行）：
第一步：在脑中列出 8 个不同的宏观/跨市场主题方向，确保覆盖：利率政策、大宗商品、
       地缘政治、加密货币、权益市场、汇率、房地产、新兴市场、气候/ESG、
       消费/就业、科技周期等（不能只选最热门的 2-3 个）。
第二步：从这 8 个方向中选出 4 个差异最大的方向。
第三步：为每个方向生成一个口语化的宏观洞察问题，确保问题涉及的具体资产/指标各不相同。

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

【System capabilities — strictly enforced】
This system can ONLY:
1. Fetch real-time/historical stock price data
2. Calculate technical indicators (RSI, KDJ, CCI, etc.)
3. Run Kronos prediction model for future price forecasts
4. Generate buy/sell/hold recommendation with confidence and risk level

This system CANNOT answer questions about:
- Product pipelines, R&D progress, technology outlook
- Business models, competitive landscape, industry research
- Management quality, corporate strategy, M&A
- Qualitative policy/regulatory impact analysis
- Anything requiring "read the research report/news/announcements"

Rules:
- Generate 3 natural English questions.
- Every question must name a specific stock or ticker.
- Supported markets: China A-shares, Hong Kong stocks, and US stocks.
- Questions MUST focus on: price trend, technical signals, buy/sell timing, valuation position, risk-reward, stock comparison.
- Do NOT generate: product pipeline, business model, competitive analysis, industry research, R&D outlook questions.
- Keep each question concise and realistic.
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
    "侧重短期走势判断和买卖时机",
    "侧重技术指标（RSI/KDJ/CCI）信号解读",
    "侧重支撑位和阻力位分析",
    "侧重风险评估和止损策略",
    "侧重两只标的对比选优",
    "侧重估值位置和安全边际",
    "侧重成交量和动量分析",
    "侧重均线和趋势线判断",
    "侧重超买超卖信号识别",
    "侧重波动率和风险收益比",
    "侧重A股龙头标的走势",
    "侧重美股科技巨头技术面",
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
    "分析一下 AAPL 和 NVDA 最近技术面信号",
]

_MACRO_FALLBACKS = [
    "现在适合买黄金吗",
    "美联储下一步会加息还是降息",
    "AI 是不是泡沫",
    "比特币到底了吗",
]

_ANALYSIS_FALLBACKS_EN = [
    "Can I still buy China Merchants Bank now?",
    "Compare Kweichow Moutai and CATL short-term trend",
    "Analyze recent technical signals in AAPL and NVDA",
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

# Research-style question rejection patterns (these questions the system cannot answer)
_RESEARCH_REJECT_PATTERNS = [
    r"管线|pipeline|研发进展|R&D|技术前景|technology outlook",
    r"商业模式|business model|竞争格局|competitive landscape|行业研究|industry research",
    r"管理层|management|公司战略|corporate strategy|并购|merger|acquisition",
    r"政策影响|regulatory|监管变化|定性分析|qualitative",
    r"研报|research report|公告|announcement|新闻|news",
    r"前景如何|prospect|outlook(?!.*price|.*technical|.*signal)",
    r"护城河|moat|壁垒|barrier|生态|ecosystem",
    r"增长点|growth point|商业化|commercialization|落地情况|implementation",
    r"转型|transformation|升级|upgrade|布局|deployment",
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

        # Reject research-style questions for analysis type
        if question_type == "analysis":
            if any(re.search(p, lowered, re.IGNORECASE) for p in _RESEARCH_REJECT_PATTERNS):
                logger.warning("Suggestion rejected (research-style): %r", q[:80])
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
    """Call the LLM to generate suggestions, with diversity retries.

    Diversity techniques applied:
    1. Random concept injection (arXiv:2601.18053) — 3 unrelated random words prepended
    2. Entity blacklist — stock names/codes from recent history explicitly excluded
    3. CoT two-step prompting (Wharton 2024) — system prompt instructs think-before-generate
    4. Few-shot from question bank — different examples each time
    5. Flavor rotation — different thematic direction per attempt
    """
    from kronos_fincept.agent import _call_structured_llm_json

    history = _history.setdefault(history_key or question_type, deque(maxlen=3))
    used_flavors: set[str] = set()

    # Select few-shot examples from question bank (different each call)
    bank = (_ANALYSIS_QUESTION_BANK if question_type == "analysis" else _MACRO_QUESTION_BANK) \
        if language != "en-US" else \
        (_ANALYSIS_QUESTION_BANK_EN if question_type == "analysis" else _MACRO_QUESTION_BANK_EN)
    few_shot_count = min(5, len(bank))
    few_shot_examples = random.sample(bank, few_shot_count)

    for attempt in range(MAX_RETRIES):
        # Pick a random flavor not yet tried in this generation cycle
        available = [f for f in flavors if f not in used_flavors]
        if not available:
            available = flavors  # fallback: reuse
        flavor = random.choice(available)
        used_flavors.add(flavor)

        # ── Random concept injection (breaks LLM mode collapse) ──
        random_concepts = random.sample(_RANDOM_WORDS, 3)
        concept_str = "、".join(random_concepts)

        # ── Entity blacklist from history ──
        blacklist_text = ""
        if history:
            entities = _extract_entities_from_history(history)
            if entities:
                entity_list = "、".join(sorted(entities)[:20])  # cap at 20
                if language == "en-US":
                    blacklist_text = f"\nDO NOT generate questions about these already-mentioned entities: {entity_list}"
                else:
                    blacklist_text = f"\n严禁再次生成涉及以下已出现过的标的/主体的问题：{entity_list}"

        # ── Historical question blacklist (full text) ──
        avoid_text = ""
        if history:
            past_samples = []
            for past_set in history:
                past_samples.extend(past_set[:2])
            if past_samples:
                sample_str = "、".join(f"「{q}」" for q in past_samples[:6])
                avoid_text = (
                    f"\nDo not repeat or closely paraphrase these previous suggestions: {sample_str}"
                    if language == "en-US"
                    else f"\n严禁生成与以下历史建议重复或高度相似的问题：{sample_str}"
                )

        # ── Build few-shot section ──
        if language == "en-US":
            few_shot_label = "Here are examples of good questions (for reference style only, DO NOT copy these):"
        else:
            few_shot_label = "以下是一些示例问题（仅供参考风格，不允许抄袭）："
        few_shot_text = "\n".join(f"- {q}" for q in few_shot_examples)

        # ── Compose final prompt ──
        focus_prefix = "Focus direction" if language == "en-US" else "本次侧重方向"
        if language == "en-US":
            concept_prefix = "Creative seed words (use as inspiration, not as topic):"
        else:
            concept_prefix = "创意种子词（仅作为灵感触发，不是主题）："

        user_prompt = (
            f"{user_prompt_template}\n"
            f"{focus_prefix}：{flavor}。\n"
            f"{concept_prefix}{concept_str}。\n"
            f"{few_shot_label}\n{few_shot_text}\n"
            f"{blacklist_text}{avoid_text}"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            result = _call_structured_llm_json(
                messages,
                temperature=0.95,
                max_tokens=500,
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


# ── Pre-generated file support ──

import json as _json
from pathlib import Path as _Path

_PREGEN_FILE = _Path(__file__).resolve().parents[3] / "data" / "suggestions_pregen.json"
_PREGEN_MAX_AGE = 24 * 3600  # pregen file valid for 24 hours

_pregen_cache: dict[str, Any] | None = None
_pregen_loaded_at: float = 0.0


def _read_pregen_file() -> dict[str, Any] | None:
    """Read and cache the pre-generated suggestions file."""
    global _pregen_cache, _pregen_loaded_at
    if not _PREGEN_FILE.exists():
        return None
    try:
        mtime = _PREGEN_FILE.stat().st_mtime
        if _pregen_cache and (time.time() - _pregen_loaded_at) < 60:
            return _pregen_cache  # in-memory cache for 60s
        data = _json.loads(_PREGEN_FILE.read_text(encoding="utf-8"))
        if (time.time() - data.get("generated_ts", 0)) > _PREGEN_MAX_AGE:
            return None  # file too old
        _pregen_cache = data
        _pregen_loaded_at = time.time()
        return data
    except Exception:
        return None


def _pick_pregen_slot(
    pregen: dict[str, Any],
    cache_key: str,
) -> tuple[list[str], float] | None:
    """Pick the current time-slot from pre-generated data."""
    slots = pregen.get("slots", {}).get(cache_key)
    if not slots or not isinstance(slots, list):
        return None
    now = datetime.now()
    slot_idx = (now.hour * 60 + now.minute) // (24 * 60 // len(slots))
    slot_idx = min(slot_idx, len(slots) - 1)
    questions = slots[slot_idx]
    if not questions:
        return None
    return questions, pregen.get("generated_ts", time.time())


# ── Route ──


@router.get("/suggestions")
async def get_suggestions(
    type: str = Query("analysis", description="Suggestion type: 'analysis' or 'macro'"),
    language: Literal["zh-CN", "en-US"] = Query("zh-CN", description="Natural-language output language"),
) -> dict[str, Any]:
    """Return question suggestions. Prefers pre-generated file, falls back to lazy LLM."""
    if language not in ("zh-CN", "en-US"):
        language = "zh-CN"
    if type not in ("analysis", "macro"):
        raise HTTPException(status_code=400, detail="type must be 'analysis' or 'macro'")

    cache_key = type if language == "zh-CN" else f"{type}:{language}"
    _cache_locks.setdefault(cache_key, asyncio.Lock())

    # ── 1. Try pre-generated file (fastest path) ──
    pregen = await asyncio.to_thread(_read_pregen_file)
    if pregen:
        picked = _pick_pregen_slot(pregen, cache_key)
        if picked:
            questions, gen_ts = picked
            return {
                "questions": questions,
                "generated_at": gen_ts,
                "source": "pregen",
            }

    # ── 2. In-memory cache ──
    cached = _cache.get(cache_key)
    now = time.time()
    if cached and (now - cached.generated_at) < SUGGESTION_CACHE_TTL_SECONDS:
        return {
            "questions": cached.questions,
            "generated_at": cached.generated_at,
            "source": "cache",
        }

    # ── 3. Lazy LLM generation (fallback) ──
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
                "Generate 3 English single-stock analysis questions as JSON. Focus on price trend, technical signals, buy/sell timing, valuation, risk."
                if language == "en-US"
                else "请生成 3 个中文个股分析建议问题，必须围绕价格走势、技术面、买卖时机、风险评估，以 JSON 格式输出。",
                [
                    "short-term trend and buy/sell timing",
                    "technical indicator signals (RSI/KDJ/CCI)",
                    "support and resistance levels",
                    "risk assessment and stop-loss strategy",
                    "two-stock comparison for entry",
                    "valuation position and safety margin",
                    "volume and momentum analysis",
                    "moving average and trend line",
                    "overbought/oversold signal identification",
                    "volatility and risk-reward ratio",
                    "China A-share leaders technical outlook",
                    "US mega-cap technical analysis",
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

        generated_at = time.time()
        result = SuggestionResult(questions=questions, generated_at=generated_at)
        _cache[cache_key] = result

        log_event(
            logger,
            logging.INFO,
            "suggestions.generated",
            f"Generated {len(questions)} {type} suggestions (fallback)",
            suggestion_type=type,
            count=len(questions),
        )

        return {
            "questions": questions,
            "generated_at": generated_at,
            "source": "fresh",
        }
