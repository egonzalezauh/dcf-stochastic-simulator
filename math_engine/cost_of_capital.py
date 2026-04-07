import logging
from typing import Dict, Any

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DynamicWACC:
    """
    Calculador avanzado del Costo Promedio Ponderado de Capital (WACC).
    Utiliza el modelo CAPM (Capital Asset Pricing Model) integrando las 
    ecuaciones de Hamada para desapalancar y reapalancar la Beta histórica.
    """
    def __init__(self, erp: float = 0.055, risk_free_rate: float = 0.042):
        """
        Args:
            erp (float): Equity Risk Premium (Prima de Riesgo del Mercado). 
                         Por defecto, 5.5% (Típico para EE.UU.).
            risk_free_rate (float): Tasa Libre de Riesgo inyectada. 
                                    Por defecto, asume 4.2%.
        """
        self.erp = erp
        self.risk_free_rate = risk_free_rate



    def calculate_ke(
        self, 
        beta_raw: float, 
        tax_rate: float, 
        current_total_debt: float, 
        market_cap: float, 
        historical_debt_to_equity: float
    ) -> float:
        """
        Calcula el Costo del Capital Accionario (Ke) puro utilizando CAPM y las
        ecuaciones de Hamada para reapalancamiento estructural.
        
        Args:
            beta_raw (float): La Beta histórica leída de yfinance.
            tax_rate (float): Tasa impositiva marginal efectiva.
            current_total_debt (float): Deuda Total en el Balance actual.
            market_cap (float): Market Capitalization actual (Equity).
            historical_debt_to_equity (float): Proxy D/E bajo la cual la `beta_raw` fue promediada.
            
        Returns:
            float: Costo del Capital (Ke).
        """
        if market_cap <= 0:
            raise ValueError("La capitalización de mercado (Market Cap) debe ser > 0 para calcular Ke.")
            
        # 1. Hamada - Desapalancar la Beta (Extraer el riesgo puro del negocio subyacente)
        unlevered_beta = beta_raw / (1 + (1 - tax_rate) * historical_debt_to_equity)
        
        # 2. Hamada - Reapalancar la Beta (Inyectar el riesgo financiero real de HOY)
        current_debt_to_equity = current_total_debt / market_cap
        relevered_beta = unlevered_beta * (1 + (1 - tax_rate) * current_debt_to_equity)
        
        # 3. Calcular Ke (CAPM)
        # Ke = Rf + Beta_Relevered * ERP
        ke = self.risk_free_rate + (relevered_beta * self.erp)
        
        logger.info("Cálculo Ke Finalizado:")
        logger.info(f" - Unlevered Beta (Riesgo Puro Empresa): {unlevered_beta:.3f}")
        logger.info(f" - Relevered Beta (Riesgo + Estructura): {relevered_beta:.3f}")
        logger.info(f" - Costo de Capital (Ke): {ke:.2%}")
        
        return ke

    def calculate_kd(self, interest_expense: float, current_total_debt: float) -> float:
        """
        Calcula el Costo Pre-Tax de la Deuda Sintéico.
        
        Args:
            interest_expense (float): Gasto Absoluto por Intereses (Income Statement).
            current_total_debt (float): Deuda Total (Balance Sheet).
            
        Returns:
            float: Costo de Deuda (Kd) antes de impuestos.
        """
        # Si la empresa no tiene deuda, su costo de deuda es 0
        if current_total_debt <= 0:
             logger.info("Deuda Total es 0. Costo de Deuda (Kd) asignado como 0.00%.")
             return 0.0
             
        # Calculamos una tasa implícita 
        # (usamos abs() en interest_expense dado que las APIs a veces los reportan negativos por convención contable)
        synthetic_kd = abs(interest_expense) / current_total_debt
        
        logger.info(f"Costo de Deuda (Kd Sintético Pre-Tax): {synthetic_kd:.2%}")
        return synthetic_kd

    def calculate_wacc(
        self, 
        ke: float, 
        kd: float, 
        tax_rate: float, 
        current_total_debt: float, 
        market_cap: float
    ) -> float:
        """
        Calcula el Costo Promedio Ponderado del Capital (WACC), ensamblando 
        el costo de la deuda y capital proporcionalmente.
        """
        total_value = market_cap + current_total_debt
        
        if total_value <= 0:
            raise ValueError("Enterprise Value pre-cash (Market Cap + Debt) es <= 0. WACC incalculable.")
            
        # Ponderaciones exactas
        w_equity = market_cap / total_value
        w_debt = current_total_debt / total_value
        
        # WACC Formula = (We * Ke) + (Wd * Kd * (1 - t))
        wacc = (w_equity * ke) + (w_debt * kd * (1 - tax_rate))
        
        logger.info("Cálculo WACC Ensamblado:")
        logger.info(f" - Peso Capital (We): {w_equity:.2%} | Peso Deuda (Wd): {w_debt:.2%}")
        logger.info(f" - Cost of Debt (After-Tax): {kd * (1 - tax_rate):.2%}")
        logger.info(f" - WACC Final: {wacc:.2%}")
        
        # --- PRUEBAS ESTRICTAS DE CORDURA ACADÉMICA ---
        if wacc < self.risk_free_rate:
             raise ValueError(f"CRÍTICA (WACC < Rf): WACC calculado ({wacc:.2%}) es inferior "
                              f"a la tasa libre de riesgo garantizada ({self.risk_free_rate:.2%}). "
                              f"Es estadísticamente imposible y denota errores de estructura de datos.")
                              
        if wacc > 0.25:
             raise ValueError(f"CRÍTICA (WACC Extremadamente Alto): WACC calculado es {wacc:.2%}. "
                              f"Valores por encima del 25% generalmente destruyen algebraícamente cualquier "
                              f"valoración y denotan quiebra estructural o sobreestimación de riesgo.")
                              
        return wacc


if __name__ == "__main__":
    # --- PRUEBA MATEMÁTICA CON UNA EMPRESA DE TECNOLOGÍA FICTICIA ---
    
    # 1. Supuestos (Extraídos típicamente de YFinance)
    empresa_beta_raw = 1.25                        # Algo más volátil que el S&P 500
    empresa_tax_rate = 0.21                        # 21% US Corporate Tax
    empresa_market_cap = 1_000_000_000             # $1 Billón de Capitalización de Mercado
    
    # Supuestos de Deuda (Cambio dinámico)
    # Imaginemos que la API midió el beta los últimos 5 años promediando 20% D/E...
    hist_d_e_proxy = 0.20
    # ...Pero hoy la empresa adquirió una deuda brutal (500M contra 1000M Equity) -> D/E real = 50%
    curr_debt = 500_000_000
    curr_interest = 35_000_000                     # $35 Millones pagados 
    
    print("--- Probando Módulo Avanzado de WACC ---")
    
    try:
        wacc_engine = DynamicWACC(risk_free_rate=0.042)
        
        # 1. Ke (Capital)
        ke_final = wacc_engine.calculate_ke(
            beta_raw=empresa_beta_raw,
            tax_rate=empresa_tax_rate,
            current_total_debt=curr_debt,
            market_cap=empresa_market_cap,
            historical_debt_to_equity=hist_d_e_proxy
        )
        
        # 2. Kd (Deuda)
        kd_final = wacc_engine.calculate_kd(
            interest_expense=curr_interest,
            current_total_debt=curr_debt
        )
        
        # 3. WACC
        wacc_definitivo = wacc_engine.calculate_wacc(
            ke=ke_final,
            kd=kd_final,
            tax_rate=empresa_tax_rate,
            current_total_debt=curr_debt,
            market_cap=empresa_market_cap
        )
        
        print("\n[ÉXITO] Cálculo estricto finalizado.")
        print(f"Resultado Final WACC: {wacc_definitivo:.2%}")

    except Exception as e:
        print(f"\n[FALLO INTERCEPTADO] {e}")
