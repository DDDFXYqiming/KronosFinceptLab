"""
CLI commands for financial analysis (v4.0).
v7.0: 支持全球股票 (港股/美股) 和大宗商品
"""
import click
import json
import time
from typing import Optional


@click.group()
def analyze_group():
    """Financial analysis commands."""
    pass


def _echo_macro_coverage(payload: dict) -> None:
    data_quality = payload.get("macro_data_quality") or {}
    dimension_coverage = payload.get("macro_dimension_coverage") or {}
    provider_coverage = payload.get("macro_provider_coverage") or {}
    insufficiency = payload.get("macro_evidence_insufficiency") or {}
    if not any([data_quality, dimension_coverage, provider_coverage, insufficiency]):
        return

    click.echo("\nMacro Coverage:")
    if data_quality:
        click.echo(
            "- Providers: "
            f"{data_quality.get('provider_total', 0)} total, "
            f"{data_quality.get('success_count', 0)} completed, "
            f"{data_quality.get('empty_count', 0)} empty, "
            f"{data_quality.get('failed_count', 0)} failed, "
            f"{data_quality.get('skipped_count', 0)} skipped, "
            f"{data_quality.get('unavailable_count', 0)} unavailable"
        )
        click.echo(
            "- Signals: "
            f"{data_quality.get('signal_count', 0)}"
            + (f"; updated {data_quality.get('last_updated')}" if data_quality.get("last_updated") else "")
        )
    if dimension_coverage:
        click.echo(
            "- Evidence dimensions: "
            f"{dimension_coverage.get('dimension_count', 0)}/"
            f"{dimension_coverage.get('required_dimension_count', 3)} "
            f"({'sufficient' if dimension_coverage.get('sufficient_evidence') else 'insufficient'})"
        )
        labels = dimension_coverage.get("dimension_labels") or []
        if labels:
            click.echo("- Dimensions: " + ", ".join(str(item) for item in labels))
    if insufficiency.get("insufficient") and insufficiency.get("reason"):
        click.echo(f"- Evidence warning: {insufficiency['reason']}")
    if provider_coverage:
        click.echo("- Provider status:")
        for provider_id, row in sorted(provider_coverage.items()):
            if not isinstance(row, dict):
                continue
            reason = row.get("reason") or row.get("error") or ""
            reason_suffix = f" ({reason})" if reason else ""
            click.echo(
                f"  - {provider_id}: {row.get('status', 'unknown')}, "
                f"signals={row.get('signal_count', 0)}, "
                f"elapsed={row.get('elapsed_ms', 0)}ms{reason_suffix}"
            )


@analyze_group.command()
@click.option('--symbol', required=True, help='Stock symbol')
@click.option('--shares', type=float, default=1000000000, help='Shares outstanding')
@click.option('--beta', type=float, default=1.0, help='Stock beta')
@click.option('--debt', type=float, default=0.0, help='Total debt')
@click.option('--cash', type=float, default=0.0, help='Cash and equivalents')
@click.option('--tax-rate', type=float, default=0.25, help='Tax rate')
@click.option('--output', 'output_format', type=click.Choice(['json', 'table']), default='json')
@click.pass_context
def dcf(ctx, symbol, shares, beta, debt, cash, tax_rate, output_format):
    """DCF valuation analysis."""
    try:
        from kronos_fincept.financial import DCFModel, FinancialDataManager
        from kronos_fincept.data_sources import DataSourceManager
        
        # Get financial data
        fin_manager = FinancialDataManager()
        financial_data = fin_manager.get_financial_data(symbol)
        
        if not financial_data:
            click.echo(f"Error: Could not get financial data for {symbol}")
            return 1
        
        # Run DCF valuation
        dcf_model = DCFModel()
        result = dcf_model.value_company(
            financial_data=financial_data,
            shares_outstanding=shares,
            beta=beta,
            debt_value=debt,
            cash_value=cash,
            tax_rate=tax_rate
        )
        
        if not result:
            click.echo(f"Error: DCF valuation failed for {symbol}")
            return 1
        
        # Format output
        if output_format == 'json':
            output = {
                'symbol': result.symbol,
                'enterprise_value': result.enterprise_value,
                'equity_value': result.equity_value,
                'per_share_value': result.per_share_value,
                'wacc': result.wacc,
                'terminal_growth_rate': result.terminal_growth_rate,
                'projection_years': result.projection_years
            }
            click.echo(json.dumps(output, indent=2))
        else:
            click.echo(f"DCF Valuation for {symbol}")
            click.echo("-" * 40)
            click.echo(f"Enterprise Value: {result.enterprise_value:,.2f}")
            click.echo(f"Equity Value: {result.equity_value:,.2f}")
            click.echo(f"Per Share Value: {result.per_share_value:,.2f}")
            click.echo(f"WACC: {result.wacc:.2%}")
            click.echo(f"Terminal Growth Rate: {result.terminal_growth_rate:.2%}")
        
        return 0
        
    except Exception as e:
        click.echo(f"Error: {e}")
        return 1


@analyze_group.command()
@click.option('--symbol', required=True, help='Stock symbol')
@click.option('--market-symbol', default='000300', help='Market index symbol for beta')
@click.option('--days', type=int, default=252, help='Trading days for calculation')
@click.option('--output', 'output_format', type=click.Choice(['json', 'table']), default='json')
@click.pass_context
def risk(ctx, symbol, market_symbol, days, output_format):
    """Risk metrics analysis."""
    try:
        from kronos_fincept.financial import RiskCalculator
        from kronos_fincept.data_sources import DataSourceManager
        
        # Get price data
        data_manager = DataSourceManager()
        
        # Get asset prices
        asset_data = data_manager.get_data(symbol, period=days)
        if not asset_data or len(asset_data) == 0:
            click.echo(f"Error: Could not get price data for {symbol}")
            return 1
        
        asset_prices = [row['close'] for row in asset_data]
        
        # Get market prices for beta
        market_prices = None
        if market_symbol:
            market_data = data_manager.get_data(market_symbol, period=days)
            if market_data and len(market_data) > 0:
                market_prices = [row['close'] for row in market_data]
        
        # Calculate risk metrics
        calculator = RiskCalculator()
        metrics = calculator.calculate_risk_metrics(
            symbol=symbol,
            prices=asset_prices,
            market_prices=market_prices
        )
        
        # Format output
        if output_format == 'json':
            output = {
                'symbol': metrics.symbol,
                'var_95': metrics.var_95,
                'var_99': metrics.var_99,
                'sharpe_ratio': metrics.sharpe_ratio,
                'sortino_ratio': metrics.sortino_ratio,
                'max_drawdown': metrics.max_drawdown,
                'volatility': metrics.volatility,
                'downside_deviation': metrics.downside_deviation,
                'beta': metrics.beta,
                'alpha': metrics.alpha
            }
            click.echo(json.dumps(output, indent=2))
        else:
            click.echo(f"Risk Metrics for {symbol}")
            click.echo("-" * 40)
            click.echo(f"VaR (95%): {metrics.var_95:.2%}")
            click.echo(f"VaR (99%): {metrics.var_99:.2%}")
            click.echo(f"Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
            click.echo(f"Sortino Ratio: {metrics.sortino_ratio:.2f}")
            click.echo(f"Max Drawdown: {metrics.max_drawdown:.2%}")
            click.echo(f"Volatility: {metrics.volatility:.2%}")
            if metrics.beta is not None:
                click.echo(f"Beta: {metrics.beta:.2f}")
            if metrics.alpha is not None:
                click.echo(f"Alpha: {metrics.alpha:.2%}")
        
        return 0
        
    except Exception as e:
        click.echo(f"Error: {e}")
        return 1


@analyze_group.command()
@click.option('--symbols', required=True, help='Comma-separated list of symbols')
@click.option('--method', type=click.Choice(['max_sharpe', 'min_vol', 'risk_parity']), 
              default='max_sharpe', help='Optimization method')
@click.option('--risk-free-rate', type=float, default=0.03, help='Risk-free rate')
@click.option('--days', type=int, default=252, help='Trading days for calculation')
@click.option('--output', 'output_format', type=click.Choice(['json', 'table']), default='json')
@click.pass_context
def portfolio(ctx, symbols, method, risk_free_rate, days, output_format):
    """Portfolio optimization."""
    try:
        import pandas as pd
        from kronos_fincept.financial import PortfolioOptimizer
        from kronos_fincept.data_sources import DataSourceManager
        
        # Parse symbols
        symbol_list = [s.strip() for s in symbols.split(',')]
        
        if len(symbol_list) < 2:
            click.echo("Error: At least 2 symbols required for portfolio optimization")
            return 1
        
        # Get price data for all symbols
        data_manager = DataSourceManager()
        price_data = {}
        
        for symbol in symbol_list:
            data = data_manager.get_data(symbol, period=days)
            if data and len(data) > 0:
                price_data[symbol] = [row['close'] for row in data]
        
        if len(price_data) < 2:
            click.echo("Error: Could not get price data for at least 2 symbols")
            return 1
        
        # Create DataFrame
        min_length = min(len(prices) for prices in price_data.values())
        prices_df = pd.DataFrame({
            symbol: prices[:min_length] for symbol, prices in price_data.items()
        })
        
        # Optimize portfolio
        optimizer = PortfolioOptimizer(risk_free_rate=risk_free_rate)
        result = optimizer.optimize_portfolio(
            prices=prices_df,
            asset_names=list(price_data.keys()),
            optimization_method=method
        )
        
        # Format output
        if output_format == 'json':
            output = {
                'weights': result.weights,
                'expected_return': result.expected_return,
                'volatility': result.volatility,
                'sharpe_ratio': result.sharpe_ratio,
                'method': method
            }
            click.echo(json.dumps(output, indent=2))
        else:
            click.echo(f"Portfolio Optimization ({method})")
            click.echo("-" * 40)
            click.echo("Weights:")
            for asset, weight in result.weights.items():
                click.echo(f"  {asset}: {weight:.2%}")
            click.echo(f"\nExpected Return: {result.expected_return:.2%}")
            click.echo(f"Volatility: {result.volatility:.2%}")
            click.echo(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
        
        return 0
        
    except Exception as e:
        click.echo(f"Error: {e}")
        return 1


@analyze_group.command()
@click.option('--underlying', type=float, required=True, help='Underlying price')
@click.option('--strike', type=float, required=True, help='Strike price')
@click.option('--expiry', type=float, required=True, help='Time to expiration (years)')
@click.option('--volatility', type=float, required=True, help='Volatility (annualized)')
@click.option('--rate', type=float, default=0.03, help='Risk-free rate')
@click.option('--type', 'option_type', type=click.Choice(['call', 'put']), default='call')
@click.option('--output', 'output_format', type=click.Choice(['json', 'table']), default='json')
@click.pass_context
def derivative(ctx, underlying, strike, expiry, volatility, rate, option_type, output_format):
    """Option pricing (Black-Scholes)."""
    try:
        from kronos_fincept.financial import DerivativesPricer
        
        pricer = DerivativesPricer(risk_free_rate=rate)
        
        result = pricer.black_scholes(
            underlying_price=underlying,
            strike_price=strike,
            time_to_expiration=expiry,
            volatility=volatility,
            option_type=option_type
        )
        
        # Format output
        if output_format == 'json':
            output = {
                'option_type': result.option_type,
                'underlying_price': result.underlying_price,
                'strike_price': result.strike_price,
                'time_to_expiration': result.time_to_expiration,
                'volatility': result.volatility,
                'option_price': result.option_price,
                'delta': result.delta,
                'gamma': result.gamma,
                'theta': result.theta,
                'vega': result.vega,
                'rho': result.rho,
                'intrinsic_value': result.intrinsic_value,
                'time_value': result.time_value
            }
            click.echo(json.dumps(output, indent=2))
        else:
            click.echo(f"{option_type.upper()} Option")
            click.echo("-" * 40)
            click.echo(f"Underlying: {underlying}")
            click.echo(f"Strike: {strike}")
            click.echo(f"Expiry: {expiry} years")
            click.echo(f"Volatility: {volatility:.2%}")
            click.echo(f"Rate: {rate:.2%}")
            click.echo(f"\nOption Price: {result.option_price:.4f}")
            click.echo(f"Intrinsic Value: {result.intrinsic_value:.4f}")
            click.echo(f"Time Value: {result.time_value:.4f}")
            click.echo(f"\nGreeks:")
            click.echo(f"  Delta: {result.delta:.4f}")
            click.echo(f"  Gamma: {result.gamma:.4f}")
            click.echo(f"  Theta: {result.theta:.4f}")
            click.echo(f"  Vega: {result.vega:.4f}")
            click.echo(f"  Rho: {result.rho:.4f}")
        
        return 0
        
    except Exception as e:
        click.echo(f"Error: {e}")
        return 1


@analyze_group.command()
@click.option('--symbol', required=True, help='Stock symbol')
@click.option('--indicator', type=click.Choice(['sma', 'ema', 'rsi', 'macd', 'bollinger', 'kdj', 'atr', 'obv', 'all']), 
              default='all', help='Technical indicator to calculate')
@click.option('--period', type=int, default=20, help='Indicator period')
@click.option('--days', type=int, default=100, help='Trading days for calculation')
@click.option('--output', 'output_format', type=click.Choice(['json', 'table']), default='json')
@click.pass_context
def indicator(ctx, symbol, indicator, period, days, output_format):
    """Calculate technical indicators."""
    try:
        from kronos_fincept.financial import TechnicalIndicators
        from kronos_fincept.akshare_adapter import fetch_a_stock_ohlcv
        
        # Get price data
        price_data = fetch_a_stock_ohlcv(
            symbol=symbol,
            start_date="20250101",
            end_date="20260430"
        )
        
        if not price_data or len(price_data) == 0:
            click.echo(f"Error: Could not get price data for {symbol}")
            return 1
        
        closes = [row['close'] for row in price_data]
        highs = [row['high'] for row in price_data]
        lows = [row['low'] for row in price_data]
        volumes = [row.get('volume', 0) for row in price_data]
        
        # Calculate indicators
        ti = TechnicalIndicators()
        
        if indicator == 'all':
            result = ti.calculate_all_indicators(closes, highs, lows, volumes)
            result = {k: v.__dict__ if hasattr(v, '__dict__') else v for k, v in result.items()}
        elif indicator == 'sma':
            sma = ti.calculate_sma(closes, period)
            result = {'sma': sma.__dict__, 'current': sma.current}
        elif indicator == 'ema':
            ema = ti.calculate_ema(closes, period)
            result = {'ema': ema.__dict__, 'current': ema.current}
        elif indicator == 'rsi':
            rsi = ti.calculate_rsi(closes, period)
            result = {'rsi': rsi.__dict__, 'current': rsi.current, 'overbought': rsi.is_overbought, 'oversold': rsi.is_oversold}
        elif indicator == 'macd':
            macd = ti.calculate_macd(closes)
            result = {'macd': macd.__dict__}
        elif indicator == 'bollinger':
            bollinger = ti.calculate_bollinger_bands(closes, period)
            result = {'bollinger': bollinger.__dict__}
        elif indicator == 'kdj':
            kdj = ti.calculate_kdj(highs, lows, closes, period)
            result = {'kdj': kdj.__dict__}
        elif indicator == 'atr':
            atr = ti.calculate_atr(highs, lows, closes, period)
            result = {'atr': atr.__dict__, 'current': atr.current}
        elif indicator == 'obv':
            obv = ti.calculate_obv(closes, volumes)
            result = {'obv': obv.__dict__, 'current': obv.current}
        
        # Format output
        if output_format == 'json':
            click.echo(json.dumps(result, indent=2, default=str))
        else:
            click.echo(f"Technical Indicators for {symbol}")
            click.echo("-" * 40)
            if indicator == 'all':
                for k, v in result.items():
                    click.echo(f"{k}: {v}")
            else:
                click.echo(json.dumps(result, indent=2, default=str))
        
        return 0
        
    except Exception as e:
        click.echo(f"Error: {e}")
        return 1


@analyze_group.command()
@click.option('--symbol', required=True, help='Stock symbol')
@click.option('--strategy', type=click.Choice(['ma_crossover', 'rsi', 'macd', 'bollinger', 'all']), 
              default='all', help='Trading strategy to run')
@click.option('--days', type=int, default=100, help='Trading days for calculation')
@click.option('--output', 'output_format', type=click.Choice(['json', 'table']), default='json')
@click.pass_context
def strategy(ctx, symbol, strategy, days, output_format):
    """Run trading strategies."""
    try:
        from kronos_fincept.financial import QuantitativeStrategies
        from kronos_fincept.akshare_adapter import fetch_a_stock_ohlcv
        
        # Get price data
        price_data = fetch_a_stock_ohlcv(
            symbol=symbol,
            start_date="20250101",
            end_date="20260430"
        )
        
        if not price_data or len(price_data) == 0:
            click.echo(f"Error: Could not get price data for {symbol}")
            return 1
        
        closes = [row['close'] for row in price_data]
        
        # Run strategies
        qs = QuantitativeStrategies()
        
        if strategy == 'all':
            result = qs.run_all_strategies(closes)
            result = {k: {'signal': v.signal.value, 'strength': v.strength, 'reason': v.reason} for k, v in result.items()}
        elif strategy == 'ma_crossover':
            sr = qs.ma_crossover_strategy(closes)
            result = {'signal': sr.signal.value, 'strength': sr.strength, 'reason': sr.reason}
        elif strategy == 'rsi':
            sr = qs.rsi_strategy(closes)
            result = {'signal': sr.signal.value, 'strength': sr.strength, 'reason': sr.reason}
        elif strategy == 'macd':
            sr = qs.macd_strategy(closes)
            result = {'signal': sr.signal.value, 'strength': sr.strength, 'reason': sr.reason}
        elif strategy == 'bollinger':
            sr = qs.bollinger_breakout_strategy(closes)
            result = {'signal': sr.signal.value, 'strength': sr.strength, 'reason': sr.reason}
        
        # Format output
        if output_format == 'json':
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo(f"Trading Strategies for {symbol}")
            click.echo("-" * 40)
            if strategy == 'all':
                for k, v in result.items():
                    click.echo(f"{k}: {v['signal'].upper()} (strength: {v['strength']:.2f})")
                    click.echo(f"  Reason: {v['reason']}")
            else:
                click.echo(f"Signal: {result['signal'].upper()}")
            click.echo(f"Strength: {result['strength']:.2f}")
            click.echo(f"Reason: {result['reason']}")
        
        return 0
        
    except Exception as e:
        click.echo(f"Error: {e}")
        return 1


@analyze_group.command()
@click.option('--symbol', required=True, help='Stock symbol (e.g., AAPL, 0700.HK, BTC)')
@click.option('--market', type=click.Choice(['us', 'hk', 'crypto', 'auto']), default='auto', help='Market type')
@click.option('--period', type=click.Choice(['1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', 'max']), default='1y', help='Data period')
@click.option('--output', 'output_format', type=click.Choice(['json', 'table']), default='json')
@click.pass_context
def global_data(ctx, symbol, market, period, output_format):
    """Get global market data (US, HK, Crypto)."""
    try:
        from kronos_fincept.financial import GlobalMarketSource
        
        gms = GlobalMarketSource()
        df = gms.get_stock_data(symbol, market, period)
        
        if df is None or df.empty:
            click.echo(f"Error: Could not get data for {symbol}")
            return 1
        
        # Convert to list of dicts
        data = df.to_dict('records')
        
        # Format output
        if output_format == 'json':
            output = {
                'symbol': symbol,
                'market': market,
                'period': period,
                'data_points': len(data),
                'latest': data[-1] if data else None,
                'data': data[-10:]  # Last 10 records
            }
            click.echo(json.dumps(output, indent=2, default=str))
        else:
            click.echo(f"Global Market Data: {symbol}")
            click.echo("-" * 40)
            click.echo(f"Data points: {len(data)}")
            if data:
                latest = data[-1]
                click.echo(f"Latest: {latest['timestamp']}")
                click.echo(f"  Open: {latest['open']:.2f}")
                click.echo(f"  High: {latest['high']:.2f}")
                click.echo(f"  Low: {latest['low']:.2f}")
                click.echo(f"  Close: {latest['close']:.2f}")
                click.echo(f"  Volume: {latest['volume']:.0f}")
        
        return 0
        
    except Exception as e:
        click.echo(f"Error: {e}")
        return 1


@analyze_group.command()
@click.option('--output', 'output_format', type=click.Choice(['json', 'table']), default='json')
@click.pass_context
def market_summary(ctx, output_format):
    """Get major market indices summary."""
    try:
        from kronos_fincept.financial import GlobalMarketSource
        
        gms = GlobalMarketSource()
        summary = gms.get_market_summary()
        
        # Format output
        if output_format == 'json':
            click.echo(json.dumps(summary, indent=2))
        else:
            click.echo("Global Market Summary")
            click.echo("-" * 40)
            for name, data in summary.items():
                if 'error' in data:
                    click.echo(f"{name}: {data['error']}")
                else:
                    click.echo(f"{name}: {data.get('price', 'N/A')}")
        
        return 0
        
    except Exception as e:
        click.echo(f"Error: {e}")
        return 1


@analyze_group.command("agent")
@click.option("--question", required=True, help="Natural-language investment or project question")
@click.option("--symbol", default=None, help="Optional explicit stock symbol")
@click.option("--market", type=click.Choice(["cn", "hk", "us", "commodity"]), default=None, help="Optional market override")
@click.option("--dry-run", is_flag=True, default=False, help="Use deterministic Kronos dry-run predictor")
@click.option("--output", "output_format", type=click.Choice(["json", "text"]), default="text")
@click.pass_context
def agent(ctx, question, symbol, market, dry_run, output_format):
    """Stateless natural-language AI analysis agent shared with Web/API."""
    try:
        from kronos_fincept.agent import analyze_investment_question

        result = analyze_investment_question(
            question,
            symbol=symbol,
            market=market,
            dry_run=dry_run,
        )
        payload = result.to_dict()

        if output_format == "json":
            click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            click.echo("KronosFinceptLab Agent")
            click.echo("=" * 50)
            if result.rejected:
                click.echo(f"Rejected: {result.security_reason}")
            elif result.clarification_required:
                click.echo(result.clarifying_question)
            else:
                click.echo(result.final_report)
                _echo_macro_coverage(payload)
                click.echo("\nTool Calls:")
                for call in result.tool_calls:
                    click.echo(f"- [{call.status}] {call.name}: {call.summary}")

        return 0

    except Exception as e:
        click.echo(f"Error: {e}")
        return 1


@analyze_group.command("macro")
@click.option("--question", required=True, help="Macro or cross-market analysis question")
@click.option("--symbols", default="", help="Optional comma-separated related symbols")
@click.option("--market", type=click.Choice(["cn", "hk", "us", "commodity", "crypto"]), default=None, help="Optional market hint")
@click.option("--providers", default="", help="Optional comma-separated macro provider ids")
@click.option("--output", "output_format", type=click.Choice(["json", "text"]), default="text")
@click.pass_context
def macro(ctx, question, symbols, market, providers, output_format):
    """Macro signal analysis using Digital Oracle style providers."""
    try:
        from kronos_fincept.agent import analyze_macro_question

        symbol_list = [item.strip() for item in symbols.split(",") if item.strip()]
        provider_ids = [item.strip() for item in providers.split(",") if item.strip()] or None
        result = analyze_macro_question(
            question,
            symbols=symbol_list,
            market=market,
            provider_ids=provider_ids,
        )
        payload = result.to_dict()

        if output_format == "json":
            click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            click.echo("KronosFinceptLab Macro Agent")
            click.echo("=" * 50)
            if result.rejected:
                click.echo(f"Rejected: {result.security_reason}")
            elif result.clarification_required:
                click.echo(result.clarifying_question)
            else:
                click.echo(result.final_report)
                _echo_macro_coverage(payload)
                click.echo("\nTool Calls:")
                for call in result.tool_calls:
                    click.echo(f"- [{call.status}] {call.name}: {call.summary}")

        return 0

    except Exception as e:
        click.echo(f"Error: {e}")
        return 1


@analyze_group.command()
@click.option('--symbol', required=True, help='Stock symbol')
@click.option('--market', type=click.Choice(['cn', 'hk', 'us', 'commodity']), default='cn', help='Market: cn=A股, hk=港股, us=美股, commodity=大宗商品')
@click.option('--output', 'output_format', type=click.Choice(['json', 'text']), default='text')
@click.pass_context
def ai_analyze(ctx, symbol, market, output_format):
    """AI-powered stock analysis using DeepSeek + Kronos (支持A股/港股/美股/大宗商品)."""
    try:
        from kronos_fincept.financial import AIInvestmentAdvisor
        from kronos_fincept.financial import RiskCalculator, TechnicalIndicators
        from kronos_fincept.schemas import ForecastRequest, ForecastRow
        from kronos_fincept.service import forecast_from_request
        
        # ── 根据 market 选择数据源 ──
        price_data = None
        click.echo(f"Fetching data for {symbol} (market={market})...", err=True)
        
        # 检查是否有预获取的全球市场数据文件（使用 Windows 路径）
        import os
        global_data_file = None
        
        # 尝试常见的 Windows 临时文件位置
        possible_paths = [
            f"C:\\Users\\39795\\AppData\\Local\\Temp\\kronos_{symbol.replace('.', '_')}.json",
            f"C:\\Users\\39795\\AppData\\Local\\Temp\\kronos_{symbol.replace('/', '_')}.json",
            f"E:\\tmp\\kronos_{symbol.replace('.', '_')}.json"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                global_data_file = path
                click.echo(f"Found pre-fetched data at: {path}", err=True)
                break
        
        if market == 'cn' or not global_data_file:
            # A股 或 无预获取数据：使用现有数据源
            from kronos_fincept.akshare_adapter import fetch_a_stock_ohlcv
            price_data = fetch_a_stock_ohlcv(
                symbol=symbol,
                start_date="20250101",
                end_date="20260430"
            )
        else:
            # 港股/美股/大宗商品：使用预获取的 Yahoo Finance 数据
            from datetime import datetime
            
            try:
                with open(global_data_file, 'r') as f:
                    data = json.load(f)
                
                chart_data = data.get('chart', {}).get('result', [{}])[0]
                timestamps = chart_data.get('timestamp', [])
                quotes = chart_data.get('indicators', {}).get('quote', [{}])[0]
                
                if timestamps and quotes:
                    price_data = []
                    for i, ts in enumerate(timestamps):
                        dt = datetime.utcfromtimestamp(ts)
                        price_data.append({
                            'timestamp': dt.strftime('%Y-%m-%d'),
                            'open': float(quotes['open'][i]) if quotes['open'][i] else 0,
                            'high': float(quotes['high'][i]) if quotes['high'][i] else 0,
                            'low': float(quotes['low'][i]) if quotes['low'][i] else 0,
                            'close': float(quotes['close'][i]) if quotes['close'][i] else 0,
                            'volume': float(quotes['volume'][i]) if quotes['volume'][i] else 0,
                            'amount': float(quotes['volume'][i] * quotes['close'][i]) if quotes['volume'][i] and quotes['close'][i] else 0
                        })
                    
                    company_name = chart_data.get('meta', {}).get('longName', symbol)
                    click.echo(f"Got data from Yahoo Finance: {company_name}, {len(price_data)} days", err=True)
                    
                    # 清理临时文件
                    os.remove(global_data_file)
            except Exception as e:
                click.echo(f"Failed to read pre-fetched data: {e}", err=True)
                price_data = None
        
        if not price_data or len(price_data) == 0:
            click.echo(f"Error: Could not get price data for {symbol}")
            return 1
        
        # Prepare market data
        closes = [row['close'] for row in price_data]
        latest = price_data[-1]
        
        market_data = {
            'current_price': latest['close'],
            'data_points': len(price_data),
            'price_change_1d': (latest['close'] - price_data[-2]['close']) / price_data[-2]['close'] * 100 if len(price_data) > 1 else 0,
            'price_change_1w': (latest['close'] - price_data[-5]['close']) / price_data[-5]['close'] * 100 if len(price_data) > 5 else 0,
            'volume': latest.get('volume', 0)
        }
        
        # ── 获取最新财务数据（用于 AI 分析）──
        financial_data = None
        try:
            click.echo("Fetching financial data...", err=True)
            from kronos_fincept.financial import FinancialDataManager
            fin_manager = FinancialDataManager()
            financial_data = fin_manager.get_financial_data(symbol)
            if financial_data:
                click.echo(f"Got financial data: {financial_data.symbol}", err=True)
                # 将财务数据添加到 market_data
                market_data['financial'] = {
                    'revenue': financial_data.income_statements[0].revenue if financial_data.income_statements else None,
                    'net_income': financial_data.income_statements[0].net_income if financial_data.income_statements else None,
                    'gross_profit': financial_data.income_statements[0].gross_profit if financial_data.income_statements else None,
                    'ebitda': financial_data.income_statements[0].ebitda if financial_data.income_statements else None,
                }
        except Exception as e:
            click.echo(f"Failed to get financial data: {e}", err=True)
        
        # Calculate risk metrics
        risk_calc = RiskCalculator()
        risk_metrics = risk_calc.calculate_risk_metrics(symbol, closes)
        risk_data = {
            'var_95': risk_metrics.var_95,
            'sharpe_ratio': risk_metrics.sharpe_ratio,
            'max_drawdown': risk_metrics.max_drawdown,
            'volatility': risk_metrics.volatility
        }
        
        # Kronos Prediction
        prediction_data = None
        try:
            click.echo("Running Kronos prediction...", err=True)
            forecast_rows = []
            for row in price_data[-100:]:
                forecast_row = ForecastRow(
                    timestamp=row['timestamp'],
                    open=float(row['open']),
                    high=float(row['high']),
                    low=float(row['low']),
                    close=float(row['close']),
                    volume=float(row.get('volume', 0)),
                    amount=float(row.get('amount', 0))
                )
                forecast_rows.append(forecast_row)
            
            request = ForecastRequest(
                symbol=symbol,
                timeframe="1d",
                rows=forecast_rows,
                pred_len=5,
                sample_count=100
            )
            
            result = forecast_from_request(request)
            
            if result['ok']:
                prediction_data = {
                    'model': 'Kronos-base',
                    'prediction_days': 5,
                    'forecast': result['forecast'],
                    'probabilistic': result.get('probabilistic', {})
                }
                click.echo("Kronos prediction completed.", err=True)
        except Exception as e:
            click.echo(f"Kronos prediction failed: {e}", err=True)
        
        # AI Analysis (with Kronos data)
        advisor = AIInvestmentAdvisor()
        ai_result = advisor.analyze_stock(symbol, market_data, risk_data, prediction_data)
        
        # Format output
        if output_format == 'json':
            output = {
                'symbol': ai_result.symbol,
                'market': market,
                'summary': ai_result.summary,
                'detailed_analysis': ai_result.detailed_analysis,
                'recommendation': ai_result.recommendation,
                'confidence': ai_result.confidence,
                'risk_level': ai_result.risk_level,
                'kronos_prediction': prediction_data,
                'timestamp': ai_result.timestamp
            }
            click.echo(json.dumps(output, indent=2, ensure_ascii=False))
        else:
            click.echo(f"AI Analysis for {symbol} ({market})")
            click.echo("=" * 50)
            
            if prediction_data:
                click.echo("\nKronos Prediction:")
                click.echo("-" * 30)
                for day in prediction_data['forecast']:
                    click.echo(f"  {day['timestamp']}: {day['close']:.2f}")
            
            click.echo(f"\nSummary: {ai_result.summary}")
            click.echo(f"\nRecommendation: {ai_result.recommendation}")
            click.echo(f"Confidence: {ai_result.confidence:.0%}")
            click.echo(f"Risk Level: {ai_result.risk_level}")
            click.echo(f"\nDetailed Analysis:")
            click.echo("-" * 50)
            click.echo(ai_result.detailed_analysis)
        
        return 0
        
    except Exception as e:
        click.echo(f"Error: {e}")
        return 1


@analyze_group.command()
@click.option('--symbol', required=True, help='Stock symbol')
@click.option('--output', 'output_format', type=click.Choice(['json', 'text']), default='text')
@click.pass_context
def ai_report(ctx, symbol, output_format):
    """Generate AI-powered investment report."""
    try:
        from kronos_fincept.financial import AIInvestmentAdvisor
        from kronos_fincept.akshare_adapter import fetch_a_stock_ohlcv
        from kronos_fincept.financial import TechnicalIndicators
        
        # Get market data
        price_data = fetch_a_stock_ohlcv(
            symbol=symbol,
            start_date="20250101",
            end_date="20260430"
        )
        
        if not price_data or len(price_data) == 0:
            click.echo(f"Error: Could not get price data for {symbol}")
            return 1
        
        # Prepare data
        closes = [row['close'] for row in price_data]
        latest = price_data[-1]
        
        market_data = {
            'current_price': latest['close'],
            'data_points': len(price_data),
            'price_history': price_data[-10:]
        }
        
        # Calculate technical indicators
        ti = TechnicalIndicators()
        indicators = ti.calculate_all_indicators(closes)
        indicators_dict = {k: v.__dict__ if hasattr(v, '__dict__') else v for k, v in indicators.items()}
        
        # AI Report
        advisor = AIInvestmentAdvisor()
        report = advisor.generate_report(symbol, market_data, indicators_dict)
        
        # Format output
        if output_format == 'json':
            output = {
                'symbol': symbol,
                'report': report,
                'timestamp': datetime.now().isoformat()
            }
            click.echo(json.dumps(output, indent=2, ensure_ascii=False))
        else:
            click.echo(f"Investment Report for {symbol}")
            click.echo("=" * 50)
            click.echo(report)
        
        return 0
        
    except Exception as e:
        click.echo(f"Error: {e}")
        return 1


@analyze_group.command()
@click.option('--question', required=True, help='Investment question')
@click.option('--symbol', default=None, help='Related stock symbol (optional)')
@click.option('--output', 'output_format', type=click.Choice(['json', 'text']), default='text')
@click.pass_context
def ai_question(ctx, question, symbol, output_format):
    """Ask AI investment questions."""
    try:
        from kronos_fincept.agent import analyze_investment_question

        result = analyze_investment_question(question, symbol=symbol)

        if output_format == 'json':
            output = {
                'question': question,
                'symbol': result.symbol or symbol,
                'answer': result.final_report,
                'agent_result': result.to_dict(),
                'timestamp': result.timestamp,
            }
            click.echo(json.dumps(output, indent=2, ensure_ascii=False))
        else:
            click.echo(f"Question: {question}")
            if result.symbol or symbol:
                click.echo(f"Related Symbol: {result.symbol or symbol}")
            click.echo("-" * 50)
            if result.rejected:
                click.echo(f"Rejected: {result.security_reason}")
            elif result.clarification_required:
                click.echo(result.clarifying_question)
            else:
                click.echo(result.final_report)
        
        return 0
        
    except Exception as e:
        click.echo(f"Error: {e}")
        return 1
