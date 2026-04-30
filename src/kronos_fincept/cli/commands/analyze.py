"""
CLI commands for financial analysis (v4.0).
"""
import click
import json
from typing import Optional


@click.group()
def analyze_group():
    """Financial analysis commands."""
    pass


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
