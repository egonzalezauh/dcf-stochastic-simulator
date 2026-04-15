import os
import logging
from dotenv import load_dotenv
from fredapi import Fred
import streamlit as st

# Configuración de Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Cargar variables de entorno desde el archivo .env
load_dotenv()
FRED_API_KEY = os.getenv("FRED_API_KEY")

if not FRED_API_KEY:
    logger.warning("No se encontró FRED_API_KEY en el archivo .env. Asegúrate de configurarlo para la inyección de datos macroeconómicos.")
    fred = None
else:
    try:
        fred = Fred(api_key=FRED_API_KEY)
    except Exception as e:
        logger.error(f"Error inicializando el cliente de FRED API: {e}")
        fred = None

@st.cache_data(ttl=21600, show_spinner=False)
def get_risk_free_rate(fallback_rate: float = 0.042) -> float:
    """
    Extrae la Tasa Libre de Riesgo (Risk-Free Rate) actual desde la FRED 
    utilizando el bono del Tesoro de EE. UU. a 10 años (DGS10).
    """
    if not fred:
        logger.warning(f"FRED API no disponible. Usando fallback asumido del {fallback_rate:.2%} para Risk-Free Rate.")
        return fallback_rate
        
    logger.info("Intentando extraer Tasa Libre de Riesgo desde FRED (DGS10 - 10-Year Treasury)...")
    try:
        # Extraer la serie DGS10
        series = fred.get_series('DGS10')
        series = series.dropna()
        if not series.empty:
            current_yield = series.iloc[-1]
            rf_rate = current_yield / 100.0  # Convertir porcentaje a decimal
            logger.info(f"Éxito (FRED). Risk-Free Rate obtenido: {rf_rate:.2%}")
            return rf_rate
        else:
            raise ValueError("Serie DGS10 vacía.")
    except Exception as e:
        logger.warning(f"[CRÍTICO] Falló la extracción desde FRED (DGS10): {e}. "
                       f"Usando fallback asumido del {fallback_rate:.2%}.")
        return fallback_rate

@st.cache_data(ttl=21600, show_spinner=False)
def get_terminal_growth_rate(fallback_rate: float = 0.025) -> float:
    """
    Extrae la Tasa de Inflación Esperada a 10 años desde la FRED (T10YIE)
    para utilizarla como proxy de la Tasa de Crecimiento Terminal (macro_g).
    """
    if not fred:
        logger.warning(f"FRED API no disponible. Usando fallback asumido del {fallback_rate:.2%} para Terminal Growth.")
        return fallback_rate
        
    logger.info("Intentando extraer Tasa de Crecimiento Terminal desde FRED (T10YIE - 10-Year Breakeven Inflation Rate)...")
    try:
        # Extraer la serie T10YIE
        series = fred.get_series('T10YIE')
        series = series.dropna()
        if not series.empty:
            current_inflation_expectation = series.iloc[-1]
            growth_rate = current_inflation_expectation / 100.0  # Convertir porcentaje a decimal
            logger.info(f"Éxito (FRED). Terminal Growth Rate (Inflación Esperada) obtenido: {growth_rate:.2%}")
            # Limitamos el crecimiento macro entre 1.5% y 4% para evitar locuras temporales del mercado
            growth_rate = max(0.015, min(0.04, growth_rate))
            return growth_rate
        else:
            raise ValueError("Serie T10YIE vacía.")
    except Exception as e:
        logger.warning(f"[CRÍTICO] Falló la extracción desde FRED (T10YIE): {e}. "
                       f"Usando fallback asumido del {fallback_rate:.2%}.")
        return fallback_rate

if __name__ == "__main__":
    rf = get_risk_free_rate()
    print(f"Risk Free Rate: {rf:.4f}")
    
    tg = get_terminal_growth_rate()
    print(f"Terminal Growth Rate: {tg:.4f}")
