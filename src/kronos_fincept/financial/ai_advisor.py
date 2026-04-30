"""
AI Investment Advisor module using DeepSeek LLM.
"""
import os
import json
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime

from ..config import settings


@dataclass
class AIAnalysisResult:
    """AI analysis result."""
    symbol: str
    analysis_type: str
    summary: str
    detailed_analysis: str
    recommendation: str
    confidence: float
    risk_level: str
    timestamp: str
    
    @property
    def is_buy(self) -> bool:
        """Check if recommendation is buy."""
        return 'buy' in self.recommendation.lower()
    
    @property
    def is_sell(self) -> bool:
        """Check if recommendation is sell."""
        return 'sell' in self.recommendation.lower()


class AIInvestmentAdvisor:
    """
    AI Investment Advisor using DeepSeek LLM.
    
    Features:
    - Natural language stock analysis
    - Investment recommendations
    - Risk assessment
    - Market sentiment analysis
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        """
        Initialize AI Investment Advisor.
        
        Args:
            api_key: DeepSeek API key
            base_url: DeepSeek API base URL
            model: Model name
        """
        self.api_key = api_key or settings.llm.deepseek.api_key
        self.base_url = base_url or settings.llm.deepseek.base_url
        self.model = model or settings.llm.deepseek.model
        
        if not self.api_key:
            raise ValueError("DeepSeek API key not configured. Set DEEPSEEK_API_KEY in .env")
    
    def _call_llm(self, prompt: str, max_tokens: int = 2000) -> str:
        """
        Call DeepSeek LLM API.
        
        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            
        Returns:
            Generated text
        """
        try:
            import requests
            
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            data = {
                'model': self.model,
                'messages': [
                    {'role': 'system', 'content': 'You are a professional financial analyst and investment advisor. Provide accurate, data-driven analysis in Chinese.'},
                    {'role': 'user', 'content': prompt}
                ],
                'max_tokens': max_tokens,
                'temperature': 0.7
            }
            
            response = requests.post(
                f'{self.base_url}/chat/completions',
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return result['choices'][0]['message']['content']
            else:
                return f"API调用失败: {response.status_code} - {response.text}"
                
        except Exception as e:
            return f"调用DeepSeek API时出错: {str(e)}"
    
    def analyze_stock(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        risk_metrics: Optional[Dict[str, Any]] = None,
        prediction: Optional[Dict[str, Any]] = None
    ) -> AIAnalysisResult:
        """
        Analyze a stock using AI.
        
        Args:
            symbol: Stock symbol
            market_data: Market data dictionary
            risk_metrics: Risk metrics (optional)
            prediction: Kronos prediction (optional)
            
        Returns:
            AIAnalysisResult
        """
        prompt = f"""请分析股票 {symbol} 的投资价值。

市场数据：
{json.dumps(market_data, indent=2, ensure_ascii=False)}

"""
        
        if risk_metrics:
            prompt += f"""风险指标：
{json.dumps(risk_metrics, indent=2, ensure_ascii=False)}

"""
        
        if prediction:
            prompt += f"""Kronos模型预测：
{json.dumps(prediction, indent=2, ensure_ascii=False)}

"""
        
        prompt += """请提供：
1. 简要总结（50字以内）
2. 详细分析（包括基本面、技术面、风险因素）
3. 投资建议（买入/持有/卖出）
4. 置信度（0-100%）
5. 风险等级（低/中/高）

请用JSON格式输出，包含以下字段：
{
  "summary": "简要总结",
  "detailed_analysis": "详细分析",
  "recommendation": "买入/持有/卖出",
  "confidence": 75,
  "risk_level": "中"
}"""
        
        response = self._call_llm(prompt)
        
        # Parse response
        try:
            # Try to extract JSON from response
            import re
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if json_match:
                result_data = json.loads(json_match.group())
            else:
                result_data = {
                    'summary': response[:100],
                    'detailed_analysis': response,
                    'recommendation': '持有',
                    'confidence': 50,
                    'risk_level': '中'
                }
        except:
            result_data = {
                'summary': response[:100],
                'detailed_analysis': response,
                'recommendation': '持有',
                'confidence': 50,
                'risk_level': '中'
            }
        
        return AIAnalysisResult(
            symbol=symbol,
            analysis_type='stock_analysis',
            summary=result_data.get('summary', ''),
            detailed_analysis=result_data.get('detailed_analysis', ''),
            recommendation=result_data.get('recommendation', '持有'),
            confidence=result_data.get('confidence', 50) / 100,
            risk_level=result_data.get('risk_level', '中'),
            timestamp=datetime.now().isoformat()
        )
    
    def generate_report(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        technical_indicators: Optional[Dict[str, Any]] = None,
        prediction: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate a natural language analysis report.
        
        Args:
            symbol: Stock symbol
            market_data: Market data
            technical_indicators: Technical indicators (optional)
            prediction: Kronos prediction (optional)
            
        Returns:
            Natural language report
        """
        prompt = f"""请为股票 {symbol} 生成一份完整的投资分析报告。

市场数据：
{json.dumps(market_data, indent=2, ensure_ascii=False)}

"""
        
        if technical_indicators:
            prompt += f"""技术指标：
{json.dumps(technical_indicators, indent=2, ensure_ascii=False)}

"""
        
        if prediction:
            prompt += f"""Kronos模型预测：
{json.dumps(prediction, indent=2, ensure_ascii=False)}

"""
        
        prompt += """请生成一份专业的投资分析报告，包括：
1. 市场概况
2. 技术分析
3. 基本面分析
4. 风险评估
5. 投资建议
6. 总结

请用中文撰写，语言专业但易懂。"""
        
        return self._call_llm(prompt, max_tokens=3000)
    
    def answer_question(
        self,
        question: str,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Answer investment-related questions.
        
        Args:
            question: User question
            context: Additional context (optional)
            
        Returns:
            Answer text
        """
        prompt = f"""用户问题：{question}

"""
        
        if context:
            prompt += f"""相关数据：
{json.dumps(context, indent=2, ensure_ascii=False)}

"""
        
        prompt += """请根据提供的数据和你的专业知识回答这个问题。如果数据不足，请说明。"""
        
        return self._call_llm(prompt)
    
    def compare_stocks(
        self,
        symbols: List[str],
        market_data: Dict[str, Dict[str, Any]]
    ) -> str:
        """
        Compare multiple stocks.
        
        Args:
            symbols: List of stock symbols
            market_data: Market data for each symbol
            
        Returns:
            Comparison analysis
        """
        prompt = f"""请比较以下股票的投资价值：

"""
        
        for symbol in symbols:
            if symbol in market_data:
                prompt += f"""{symbol}:
{json.dumps(market_data[symbol], indent=2, ensure_ascii=False)}

"""
        
        prompt += """请提供：
1. 各股票的优缺点对比
2. 投资价值排名
3. 推荐投资的股票及理由

请用表格形式对比，然后给出结论。"""
        
        return self._call_llm(prompt, max_tokens=2500)
