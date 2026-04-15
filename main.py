import logging
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import yfinance as yf
from typing import Dict, Any

# Módulos Internos
from data_ingestion.yfinance_extractor import get_full_company_data
from data_ingestion.fred_extractor import get_risk_free_rate, get_terminal_growth_rate
from math_engine.cost_of_capital import DynamicWACC
from math_engine.montecarlo_cholesky import MonteCarloCholeskySimulator
from math_engine.treasury_stock import calculate_diluted_shares
from valuation_models.dcf_core import DynamicTerminalValue

# Configuración de Logging y Visualización
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

sns.set_theme(style="darkgrid")


def run_valuation_engine(ticker: str, n_simulations: int = 10000, scenario: dict = None):
    """
    Orquestador Maestro del Modelo de Valoración DCF Estocástico.
    Ejecuta el pipeline completo desde la ingesta de datos hasta la renderización de la curva de densidad KDE.
    """
    logger.info(f"=== INICIANDO VALORACIÓN ESTOCÁSTICA 10-YEAR U-FCF PARA {ticker.upper()} ===")

    # =========================================================================
    # FASE 1: INGESTIÓN DE DATOS EN CRUDO
    # =========================================================================
    logger.info("--- Fase 1: Ingestión de Datos ---")
    data = get_full_company_data(ticker)
    financials: pd.DataFrame = data['financials']
    current_price = data['current_price']
    base_shares = data['shares_outstanding'] # Acciones base (ya blindadas implícitamente en el módulo extractor)
    sbc_history = data['sbc_history']
    buyback_yield = data.get('historical_buyback_yield', 0.0)
    forward_consensus = data.get('forward_consensus', {})
    sector = data.get('sector', 'Unknown')
    
    if ticker.upper() == 'AMZN':
        sector = 'Technology'
        logger.info("[TRAMPA AMZN] Forzando sector a 'Technology' (en Yahoo Finance aparece como Consumer Cyclical).")
    
    def get_fin_val(metric_name, default=0.0):
        if metric_name in financials.index and pd.notna(financials.loc[metric_name].iloc[0]):
            return float(financials.loc[metric_name].iloc[0])
        return default

    # Extraer métricas clave puntuales del dataframe más reciente (Year 0)
    market_cap = current_price * base_shares
    current_total_debt = get_fin_val('Total Debt', 0.0)
    cash_equiv = get_fin_val('Cash And Cash Equivalents', 0.0)
    current_net_debt = max(0.0, current_total_debt - cash_equiv)
    
    minority_interest = get_fin_val('Minority Interests') or get_fin_val('Minority Interest', 0.0)
    current_net_debt_and_minority = current_net_debt + minority_interest
    
    interest_expense = abs(get_fin_val('Interest Expense', 0.0))
    
    # Extraemos Beta del diccionario de datos cacheados
    raw_beta = data.get('beta', 1.0)
        
    # [NUEVO] Tasa Máginal Dinámica (Effective Tax Rate)
    try:
        tax_prov = abs(get_fin_val('Tax Provision', 0.0))
        pretax = get_fin_val('Pretax Income', 0.0)
        tax_rate = max(0.0, min(tax_prov / pretax, 0.40)) if pretax > 0 else 0.21
        logger.info(f"[NUEVO] Tasa de impuestos efectiva dinámica: {tax_rate:.2%}")
    except:
        tax_rate = 0.21
    
    # [NUEVO] Proxy de Apalancamiento D/E Histórico Dinámico
    try:
        hist_total_debt = financials.loc['Total Debt'] if 'Total Debt' in financials.index else pd.Series(0, index=financials.columns)
        hist_total_assets = financials.loc['Total Assets'] if 'Total Assets' in financials.index else pd.Series(1, index=financials.columns)
        hist_total_liab = financials.loc['Total Liabilities Net Minority Interest'] if 'Total Liabilities Net Minority Interest' in financials.index else pd.Series(0, index=financials.columns)
        hist_equity = hist_total_assets - hist_total_liab
        
        hist_equity = hist_equity.mask(hist_equity <= 0) # Evita división por 0 o negativos
        hist_d_e_array = (hist_total_debt / hist_equity).dropna()
        hist_debt_to_equity = max(0.0, float(hist_d_e_array.mean())) if not hist_d_e_array.empty else 0.20
        logger.info(f"[NUEVO] D/E Histórico Promedio Dinámico: {hist_debt_to_equity:.2f}x")
    except:
        hist_debt_to_equity = 0.20

    # =========================================================================
    # FASE 2: GRAVEDAD (WACC Dinámico)
    # =========================================================================
    logger.info("--- Fase 2: Motor de Gravedad (Cost of Capital) ---")
    
    current_rf_rate = get_risk_free_rate()
    wacc_engine = DynamicWACC(risk_free_rate=current_rf_rate)
    
    ke = wacc_engine.calculate_ke(raw_beta, tax_rate, current_total_debt, market_cap, hist_debt_to_equity)
    kd = wacc_engine.calculate_kd(interest_expense, current_total_debt)
    wacc = wacc_engine.calculate_wacc(ke, kd, tax_rate, current_total_debt, market_cap)

    if wacc > 0.20:
        logger.warning(f"¡ALERTA DE RIESGO EXTERMO! El WACC del activo ({wacc:.2%}) cruza el umbral del 20%. Destrucción de valor altamente probable en descuento temporal.")

    # =========================================================================
    # FASE 2.5: ESCENARIO CONSENSO WALL STREET (Determinista)
    # =========================================================================
    if forward_consensus and forward_consensus.get('forward_eps', 0) > 0 and forward_consensus.get('forward_pe', 0) > 0:
        fwd_eps = forward_consensus['forward_eps']
        fwd_pe = forward_consensus['forward_pe']
        future_target_price = fwd_eps * fwd_pe
        present_fair_value_consensus = future_target_price / (1 + ke)
    else:
        logger.warning("No hay suficientes estimaciones prospectivas en Wall Street para generar un Escenario Consenso válido.")

    # =========================================================================
    # FASE 3: SIMULACIÓN DE CHOLESKY (Derivación de Tasas)
    # =========================================================================
    logger.info("--- Fase 3: Simulador de Correlación Matemática (Cholesky Multidimensional) ---")
    
    revenues = financials.loc['Total Revenue']
    rev_chronological = revenues.iloc[::-1]
    rev_growth_series = rev_chronological.pct_change().dropna()
    rev_growth_hist = rev_growth_series.values
    
    ebit_hist = financials.loc['EBIT'].iloc[::-1].values
    margin_hist = ebit_hist / rev_chronological.values
    margin_hist = np.nan_to_num(margin_hist, nan=0.0)
    
    def get_hist_ratio(metric_names_list, revenues_array, absolute=True):
        for metric_name in metric_names_list:
            if metric_name in financials.index:
                vals = financials.loc[metric_name].iloc[::-1].values
                if absolute:
                    vals = np.abs(vals)
                return np.nan_to_num(vals / revenues_array, nan=0.0)
        return np.zeros_like(revenues_array)

    # Nombres posibles de las métricas en YF
    capex_names = ['Capital Expenditure', 'Capital Expenditures']
    da_names = ['Depreciation And Amortization', 'Reconciled Depreciation', 'Depreciation']
    nwc_names = ['Change In Working Capital', 'Changes In Account Receivables'] # YF reporta 'Change In Working Capital' o no lo reporta

    capex_hist = get_hist_ratio(capex_names, rev_chronological.values, absolute=True)
    da_hist = get_hist_ratio(da_names, rev_chronological.values, absolute=True)
    nwc_hist = get_hist_ratio(nwc_names, rev_chronological.values, absolute=False)

    margin_hist_aligned = margin_hist[-len(rev_growth_hist):]
    capex_aligned = capex_hist[-len(rev_growth_hist):]
    da_aligned = da_hist[-len(rev_growth_hist):]
    nwc_aligned = nwc_hist[-len(rev_growth_hist):]
    
    if ticker.upper() == 'AMZN':
        logger.info("[TRAMPA AMZN] Purgando anomalías (2021-2022) del historial de Amazon.")
        fechas_validas = rev_growth_series.index
        mask_amzn = ~fechas_validas.year.isin([2021, 2022])
        rev_growth_hist = rev_growth_hist[mask_amzn]
        margin_hist_aligned = margin_hist_aligned[mask_amzn]
        capex_aligned = capex_aligned[mask_amzn]
        da_aligned = da_aligned[mask_amzn]
        nwc_aligned = nwc_aligned[mask_amzn]

    try:
        df_sim_input = pd.DataFrame({
            'Revenue_Growth': rev_growth_hist,
            'EBIT_Margin': margin_hist_aligned,
            'CapEx_Margin': capex_aligned,
            'DA_Margin': da_aligned,
            'NWC_Margin': nwc_aligned
        })
        simulator = MonteCarloCholeskySimulator(df_sim_input)
        simulations = simulator.simulate(n_simulations=n_simulations)
    except Exception as e:
        logger.error(f"Fallo en la simulación Cholesky: {e}. Abortando modelo.")
        return

    sim_rev_growth = simulations['Revenue_Growth'] 
    sim_ebit_margin = simulations['EBIT_Margin']   
    sim_capex_margin = simulations['CapEx_Margin']
    sim_da_margin = simulations['DA_Margin']
    sim_nwc_margin = simulations['NWC_Margin']
    
    base_revenue = revenues.iloc[0]

    # =========================================================================
    # FASE 4: PROYECCIÓN DEL UFCF (10 AÑOS + FADE FACTOR)
    # =========================================================================
    logger.info("--- Fase 4: Proyección Operativa UFCF (10 Años, Mean Reversion) ---")
    
    projected_fcf_n = np.zeros(n_simulations)
    projected_ebitda_n = np.zeros(n_simulations)
    present_value_of_fcfs = np.zeros(n_simulations)
    
    projected_net_income_y10 = np.zeros(n_simulations) # Para valorar por P/E
    
    current_sbc = sbc_history.iloc[0] if not sbc_history.empty else 0.0
    macro_g = get_terminal_growth_rate()

    for i in range(n_simulations):
        path_g = sim_rev_growth[i]
        path_margin = sim_ebit_margin[i]
        path_capex_m = sim_capex_margin[i]
        path_da_m = sim_da_margin[i]
        path_nwc_m = sim_nwc_margin[i]
        
        path_pv_fcfs = 0.0
        current_rev = base_revenue
        
        # Iniciar variables temporales para el ciclo de caída suave (Fade Factor)
        current_g = path_g
        current_capex_m = path_capex_m

        for year in range(1, 11):
            if year <= 5:
                # Disminución agresiva de hipercrecimientos para los primeros 5 años
                current_g = path_g * (0.80 ** (year - 1)) if path_g > 0.15 else path_g
            else:
                # Decaimiento macro-estructural hacia la madurez (Años 6-10)
                fade_steps = year - 5
                current_g = current_g - (current_g - macro_g) * (fade_steps / 5.0)
                current_capex_m = current_capex_m - (current_capex_m - path_da_m) * (fade_steps / 5.0)
                
            # =========================================================
            # [NUEVO] INTERCEPTOR DE ESCENARIOS
            # =========================================================
            if scenario and scenario.get("active"):
                ops = scenario.get("overrides", {})
                
                # 1. Shock de Crecimiento
                if "revenue_growth" in ops and year in ops["revenue_growth"].get("years", []):
                    current_g = ops["revenue_growth"]["value"] 
                
                # 2. Shock de Márgenes
                if "ebit_margin" in ops and year in ops["ebit_margin"].get("years", []):
                    path_margin += ops["ebit_margin"]["value_modifier"] 
                    
                # 3. Shock de CapEx
                if "capex_margin" in ops and year in ops["capex_margin"].get("years", []):
                    current_capex_m += ops["capex_margin"]["value_modifier"]
            # =========================================================

            current_rev = current_rev * (1 + current_g)
            current_ebit = current_rev * path_margin
            current_da = current_rev * path_da_m
            current_capex = current_rev * current_capex_m
            current_nwc = current_rev * path_nwc_m
            
            current_ebitda = current_ebit + current_da
            
            sbc_cushion_factor = 0.50 if current_g > 0.15 else 1.0
            
            # [NUEVO] Unlevered FCF Realístico: NOPAT + D&A - CapEx + NWC (Cashflow raw sign) - SBC
            current_nopat = current_ebit * (1 - tax_rate)
            current_fcf = current_nopat + current_da - current_capex + current_nwc - (current_sbc * sbc_cushion_factor)
            
            # Descuento
            path_pv_fcfs += current_fcf / ((1 + wacc) ** year)
            
            if year == 10:
                projected_fcf_n[i] = current_fcf
                projected_ebitda_n[i] = current_ebitda
                
                # Para la valoración relativa P/E (Net Income del año 10)
                current_net_income = max(0.0, (current_ebit - interest_expense) * (1 - tax_rate))
                projected_net_income_y10[i] = current_net_income

        present_value_of_fcfs[i] = path_pv_fcfs

    # =========================================================================
    # FASE 5: TERMINAL VALUE ESTOCÁSTICO (Router Dinámico + Multiplos Simulados)
    # =========================================================================
    logger.info("--- Fase 5: Enrutamiento del Terminal Value (Año 10) ---")
    dcf_core = DynamicTerminalValue()
    
    if sector in ['Technology', 'Communication Services']:
        base_macro_multiple = 18.0
        logger.info(f"-> Múltiplo de Salida asignado por Sector ({sector}): {base_macro_multiple}x (Premium Tech/Intangibles)")
    elif sector == 'Healthcare':
        base_macro_multiple = 15.0
        logger.info(f"-> Múltiplo de Salida asignado por Sector ({sector}): {base_macro_multiple}x")
    elif sector in ['Financial Services', 'Energy', 'Basic Materials', 'Industrials']:
        base_macro_multiple = 10.0
        logger.info(f"-> Múltiplo de Salida asignado por Sector ({sector}): {base_macro_multiple}x (Maduro/Cíclico)")
    else:
        base_macro_multiple = 12.0
        logger.info(f"-> Múltiplo de Salida asignado por Sector/Defecto ({sector}): {base_macro_multiple}x")
    
    # [NUEVO] Agregamos un comportamiento normal multivariado al múltiplo de salida para capturar sentimiento
    sim_exit_multiples = np.random.normal(loc=base_macro_multiple, scale=2.0, size=n_simulations)
    sim_exit_multiples = np.clip(sim_exit_multiples, 5.0, 35.0) # Evita aberraciones
    
    enterprise_values = np.zeros(n_simulations)
    safe_g = min(macro_g, wacc - 0.01)

    for i in range(n_simulations):
        tv_dict = dcf_core.calculate_blended_tv(
            fcf_n=projected_fcf_n[i],
            ebitda_n=projected_ebitda_n[i],
            wacc=wacc,
            g=safe_g,
            exit_multiple=sim_exit_multiples[i],
            historical_revenue_growth_array=rev_growth_hist,
            historical_margin_array=margin_hist,
            mute_logs=True
        )
        
        blended_tv = tv_dict['blended_tv']
        pv_tv = blended_tv / ((1 + wacc) ** 10)  # [ACTUALIZADO] Descuento a 10 años
        
        enterprise_values[i] = present_value_of_fcfs[i] + pv_tv

    # =========================================================================
    # FASE 5.5: AJUSTE DE ACCIONES BASE POR RECOMPRAS HISTÓRICAS
    # =========================================================================
    logger.info("--- Fase 5.5: Ajuste de Acciones Base por Recompras ---")
    
    if buyback_yield > 0:
        future_base_shares = base_shares * ((1 - buyback_yield) ** 10)
        logger.info(f"[RECOMPRAS] Reduciendo acciones base de {base_shares:,.0f} a {future_base_shares:,.0f} asumiendo un Buyback Yield anual del {buyback_yield:.2%} en 10 años.")
    else:
        future_base_shares = base_shares
        logger.info(f"[RECOMPRAS] Sin recompras detectadas o empresa diluyendo. Acciones base se mantienen en {base_shares:,.0f}.")


    # =========================================================================
    # FASE 6: DILUCIÓN (Treasury Stock Method Solver)
    # =========================================================================
    logger.info("--- Fase 6: Cálculo TSM para Precios de Acción Intrínsecos ---")
    
    assumed_options = base_shares * 0.05
    assumed_strike = current_price * 0.50
    simulated_prices = np.zeros(n_simulations)
    simulated_pe_prices = np.zeros(n_simulations) # Precios de la valoración por P/E
    
    for i in range(n_simulations):
        ev = enterprise_values[i]
        
        # El balance de reclamaciones es EV - Deuda - Minority Interest
        if (ev - current_net_debt_and_minority) <= 0:
            simulated_prices[i] = 0.0
            simulated_pe_prices[i] = 0.0
            continue
            
        try:
            exact_diluted_shares = calculate_diluted_shares(
                base_shares=future_base_shares,
                options_in_the_money=assumed_options,
                average_strike_price=assumed_strike,
                enterprise_value=ev,
                net_debt=current_net_debt_and_minority,
                max_iterations=50 
            )
        except RuntimeError:
            exact_diluted_shares = future_base_shares 
            
        simulated_prices[i] = max(0.0, (ev - current_net_debt_and_minority) / exact_diluted_shares)
        
        # MODELO P/E: Valor Futuro = EPS Año 10 * Múltiplo Simulado
        eps_y10 = max(0.001, projected_net_income_y10[i] / exact_diluted_shares)
        future_price_pe = eps_y10 * sim_exit_multiples[i]
        # Descontar a valor presente usando Costo de Capital (ke)
        simulated_pe_prices[i] = future_price_pe / ((1 + ke) ** 10)

    valid_prices = simulated_prices[(~np.isnan(simulated_prices)) & (~np.isinf(simulated_prices))]
    valid_pe_prices = simulated_pe_prices[(~np.isnan(simulated_pe_prices)) & (~np.isinf(simulated_pe_prices))]

    if len(valid_prices) == 0:
         logger.error("Todas las simulaciones colapsaron a valores no válidos. Verifica parámetros de entrada.")
         return

    p10 = np.percentile(valid_prices, 10)
    p50 = np.percentile(valid_prices, 50)
    p90 = np.percentile(valid_prices, 90)

    pe_p10 = np.percentile(valid_pe_prices, 10) if len(valid_pe_prices) > 0 else 0.0
    pe_p50 = np.percentile(valid_pe_prices, 50) if len(valid_pe_prices) > 0 else 0.0
    pe_p90 = np.percentile(valid_pe_prices, 90) if len(valid_pe_prices) > 0 else 0.0

    # [NUEVO] TARGETS TEMPORALES Y RENDIMIENTO BAJO KE (Costo de Oportunidad)
    target_1y = p50 * ((1 + ke) ** 1)
    target_5y = p50 * ((1 + ke) ** 5)
    target_10y = p50 * ((1 + ke) ** 10)
    
    implied_return_1y = (target_1y / current_price) - 1.0
    implied_return_5y = (target_5y / current_price) - 1.0
    implied_return_10y = (target_10y / current_price) - 1.0

    logger.info(f"\n===== REPORTE FINAL DE VALORACIÓN: {ticker.upper()} =====")
    logger.info(f"Precio Mercado Actual: ${current_price:.2f}")
    logger.info(f"Peor Escenario (P10):  ${p10:.2f}")
    logger.info(f"Valor Justo (P50):     ${p50:.2f}")
    logger.info(f"Mejor Escenario (P90): ${p90:.2f}")

    logger.info(f"\n===== PROYECCIONES TEMPORALES (Basadas en Costo de Capital: {ke:.2%}) =====")
    logger.info(f"Valor Esperado 1 Año:   ${target_1y:.2f} (Retorno: {implied_return_1y:+.2%})")
    logger.info(f"Valor Esperado 5 Años:  ${target_5y:.2f} (Retorno: {implied_return_5y:+.2%})")
    logger.info(f"Valor Esperado 10 Años: ${target_10y:.2f} (Retorno: {implied_return_10y:+.2%})")


    # Calculamos el potencial de retorno respecto al Precio Justo (P50)
    implied_return_spot = (p50 / current_price) - 1.0
    implied_return_pe = (pe_p50 / current_price) - 1.0
    
    # =========================================================================
    # FASE 6.5: DATOS CRUDOS EV/EBITDA (para modelo de valoración relativa)
    # =========================================================================
    # EBITDA TTM: extraemos del financiero más reciente Year 0
    ebitda_ttm = get_fin_val('EBITDA', 0.0)
    if ebitda_ttm == 0.0:
        # Fallback: EBIT + D&A del año más reciente
        ebit_y0 = get_fin_val('EBIT', 0.0)
        da_y0   = get_fin_val('Depreciation And Amortization', 0.0) or get_fin_val('Reconciled Depreciation', 0.0)
        ebitda_ttm = ebit_y0 + da_y0

    # EV actual = Market Cap + Total Debt - Cash
    ev_current = market_cap + current_total_debt - cash_equiv
    ev_ebitda_current = (ev_current / ebitda_ttm) if ebitda_ttm > 0 else 0.0

    logger.info(f"[EV/EBITDA] EBITDA TTM: ${ebitda_ttm/1e9:.2f}B | EV actual: ${ev_current/1e9:.2f}B | Múltiplo actual: {ev_ebitda_current:.1f}x")

    return {
        "ticker": ticker.upper(),
        "valid_prices": valid_prices,
        "valid_pe_prices": valid_pe_prices,
        "current_price": current_price,
        "p10": p10,
        "p50": p50,
        "p90": p90,
        "pe_p10": pe_p10,
        "pe_p50": pe_p50,
        "pe_p90": pe_p90,
        "target_1y": target_1y,
        "target_5y": target_5y,
        "target_10y": target_10y,
        "implied_return_1y": implied_return_1y,
        "implied_return_5y": implied_return_5y,
        "implied_return_10y": implied_return_10y,
        "implied_return_spot": implied_return_spot,
        "implied_return_pe": implied_return_pe,
        "ke": ke,
        "wacc": wacc,
        "macro_multiple": base_macro_multiple,
        # Datos crudos para el modelo P/E simple
        "forward_eps": forward_consensus.get("forward_eps", 0.0),
        "trailing_eps": forward_consensus.get("trailing_eps", 0.0),
        "trailing_pe": forward_consensus.get("trailing_pe", 0.0),
        "forward_pe": forward_consensus.get("forward_pe", 0.0),
        # Datos crudos para el modelo EV/EBITDA
        "ebitda_ttm": ebitda_ttm,
        "ev_current": ev_current,
        "ev_ebitda_current": ev_ebitda_current,
        "total_debt": current_total_debt,
        "cash_and_equiv": cash_equiv,
        "shares_outstanding": base_shares,
        "net_debt": current_net_debt,
        "sector": sector,
    }

if __name__ == "__main__":
    import sys
    
    t = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    logger.info("Activando Orquestador en el Ticker: " + t)
    
    logging.getLogger("math_engine.treasury_stock").setLevel(logging.WARNING)
    logging.getLogger("math_engine.montecarlo_cholesky").setLevel(logging.WARNING)
    logging.getLogger("valuation_models.dcf_core").setLevel(logging.WARNING)
    
    run_valuation_engine(t, n_simulations=10000)
    
