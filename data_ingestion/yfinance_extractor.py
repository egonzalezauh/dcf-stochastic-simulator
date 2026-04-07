import yfinance as yf
import pandas as pd
import numpy as np
import logging
from typing import Optional, Dict

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Definimos métricas que consideramos cruciales y que no deben rellenarse con 0 sin más.
CRUCIAL_METRICS = [
    'Operating Cash Flow',
    'Net Income',
    'Total Revenue',
    'Total Assets',
    'Total Liabilities Net Minority Interest',
    'Free Cash Flow',
    'EBIT',
    'EBITDA'
]

def _interpolate_missing_data(df: pd.DataFrame, crucial_columns: list) -> pd.DataFrame:
    """
    Interpola valores faltantes (NaN) en años intermedios de manera lineal.
    Lanza un ValueError si hay más de 2 años consecutivos faltantes para métricas cruciales.
    
    Args:
        df (pd.DataFrame): DataFrame con fechas como columnas y métricas como índice.
        crucial_columns (list): Lista de nombres de métricas cruciales.
        
    Returns:
        pd.DataFrame: DataFrame limpio e interpolado.
    """
    if df.empty:
        return df
        
    df_cleaned = df.copy()
    
    # yfinance devuelve las fechas como columnas.
    # Transponemos para que las fechas sean el índice (orden cronológico) y sea más fácil interpolar.
    df_cleaned = df_cleaned.T
    
    # Aseguramos que el índice sea de tipo datetime y esté ordenado cronológicamente (de más antiguo a más reciente)
    df_cleaned.index = pd.to_datetime(df_cleaned.index)
    df_cleaned = df_cleaned.sort_index(ascending=True)

    for col in df_cleaned.columns:
        if col in crucial_columns:
            # Identificamos si hay NaNs consecutivos
            is_nan = df_cleaned[col].isna()
            # Agrupamos por bloques de valores no-NaN para contar los NaNs consecutivos
            consecutive_nans = is_nan.groupby((~is_nan).cumsum()).sum()
            
            if (consecutive_nans > 2).any():
                raise ValueError(f"Faltan más de 2 años consecutivos de datos para la métrica crucial: {col}")
            
            # Interpolación lineal solo para valores intermedios (limit_direction='inside')
            # Limitamos la interpolación a un máximo de 2 valores consecutivos
            df_cleaned[col] = df_cleaned[col].interpolate(method='linear', limit=2, limit_area='inside')
            
    # Volvemos a transponer para que las fechas sean columnas y las métricas el índice, ordenando de más reciente a más antiguo
    df_cleaned = df_cleaned.sort_index(ascending=False)
    return df_cleaned.T


def get_financials(ticker_symbol: str) -> pd.DataFrame:
    """
    Extrae el Income Statement, Balance Sheet y Cash Flow de los últimos 5 años.
    
    Args:
        ticker_symbol (str): Ticker de la empresa (ej: 'AAPL').
        
    Returns:
        pd.DataFrame: DataFrame combinado y tipado estrictamente con las finanzas.
    """
    try:
        logger.info(f"Extrayendo estados financieros para {ticker_symbol}...")
        ticker = yf.Ticker(ticker_symbol)
        
        # Obtener los estados financieros anuales
        inc_stmt = ticker.financials
        bal_sheet = ticker.balance_sheet
        cash_flow = ticker.cashflow
        
        if inc_stmt.empty and bal_sheet.empty and cash_flow.empty:
            raise ValueError(f"No se encontraron datos financieros históricos para el ticker {ticker_symbol}.")
            
        # Combinar los DataFrames
        combined_df = pd.concat([inc_stmt, bal_sheet, cash_flow])
        
        # Eliminar índices duplicados (ej: 'Net Income' aparece en Income Statement y en Cash Flow)
        combined_df = combined_df[~combined_df.index.duplicated(keep='first')]
        
        # yfinance usualmente devuelve 4 años. Tomamos hasta los últimos 5 disponibles.
        # Ordenamos las columnas (fechas) de forma descendente y tomamos las primeras 5
        combined_df.columns = pd.to_datetime(combined_df.columns)
        combined_df = combined_df[sorted(combined_df.columns, reverse=True)[:5]]
        
        # Aseguramos que los valores sean floats
        combined_df = combined_df.astype(float)
        
        # Proceder a interpolar y validar
        combined_df = _interpolate_missing_data(combined_df, CRUCIAL_METRICS)
        
        logger.info(f"Estados financieros extraídos y limpiados correctamente para {ticker_symbol}.")
        return combined_df
        
    except Exception as e:
        logger.error(f"Error crítico al extraer estados financieros de {ticker_symbol}: {e}")
        raise

def get_current_price(ticker_symbol: str) -> float:
    """
    Obtiene el precio actual de la acción de manera robusta.
    """
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        
        # Intento 1: A través del diccionario principal
        if 'currentPrice' in info and info['currentPrice'] is not None:
             return float(info['currentPrice'])
        if 'regularMarketPrice' in info and info['regularMarketPrice'] is not None:
             return float(info['regularMarketPrice'])
             
        # Intento 2: A través de fast_info
        if hasattr(ticker, 'fast_info') and 'last_price' in ticker.fast_info:
            return float(ticker.fast_info['last_price'])
            
        # Intento 3: A través del historial de 1 día
        hist = ticker.history(period="1d")
        if not hist.empty:
            return float(hist['Close'].iloc[-1])
            
        raise ValueError("No se pudo extraer el precio actual de la acción (no se encuentra en info, fast_info ni history).")
        
    except Exception as e:
        logger.error(f"Error al extraer el precio actual para {ticker_symbol}: {e}")
        raise

def get_shares_outstanding(ticker_symbol: str, current_price: float) -> int:
    """
    Obtiene las acciones en circulación (Shares Outstanding) blindadas contra
    anomalías de apis o Stock Splits defectuosamente reportados comparando 
    la capitalización de mercado con el precio spot actual.
    """
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        
        reported_shares = None
        
        # 1. Extraer los datos reportados explícitos de yf
        if 'sharesOutstanding' in info and info['sharesOutstanding'] is not None:
            reported_shares = int(info['sharesOutstanding'])
        elif 'impliedSharesOutstanding' in info and info['impliedSharesOutstanding'] is not None:
            reported_shares = int(info['impliedSharesOutstanding'])
        elif hasattr(ticker, 'fast_info') and 'shares' in ticker.fast_info:
            reported_shares = int(ticker.fast_info['shares'])
            
        # 2. Extraer Market Cap actual para forzar la matemática 
        market_cap = info.get('marketCap', None)
        
        if market_cap is not None and current_price > 0:
            implied_shares = int(market_cap / current_price)
            
            # 3. Blindaje Crucial Anti-Splits (Tolerancia 10%)
            if reported_shares is not None:
                diff_percentage = abs(implied_shares - reported_shares) / reported_shares
                if diff_percentage > 0.10:
                    logger.warning(f"[{ticker_symbol}] ALARMA DE STOCK SPLIT / CORRUPCIÓN YFINANCE:")
                    logger.warning(f"-> Acciones reportadas crudas:   {reported_shares:,.0f}")
                    logger.warning(f"-> Acciones implícitas (MC/Spot): {implied_shares:,.0f}")
                    logger.warning(f"-> Diferencia detectada: {diff_percentage:.2%}. Forzando uso de acciones IMPLÍCITAS como defensa estructural.")
                    return implied_shares
                else:
                    return reported_shares
            else:
                return implied_shares
                
        if reported_shares is not None:
            return reported_shares
            
        raise ValueError("No se pudo extraer la cantidad de acciones en circulación (Shares Outstanding ni por vía directa ni implícita).")
        
    except Exception as e:
        logger.error(f"Error al extraer Shares Outstanding para {ticker_symbol}: {e}")
        raise

def get_sbc_history(ticker_symbol: str) -> pd.Series:
    """
    Extrae explícitamente la línea de Share-Based Compensation del Cash Flow Statement.
    Si no existe, asume 0 y lanza un logging.warning.
    
    Returns:
        pd.Series: Serie de tiempo con los valores de SBC, tipada como float.
    """
    try:
        ticker = yf.Ticker(ticker_symbol)
        cash_flow = ticker.cashflow
        
        if cash_flow.empty:
            logger.warning(f"[{ticker_symbol}] El Cash flow statement está vacío. Asumiendo que SBC es 0.")
            return pd.Series(dtype=float)

        # Posibles nombres bajo los que yfinance puede reportar el SBC
        sbc_possible_names = [
            'Share Based Compensation',
            'Stock Based Compensation',
            'Stock-Based Compensation',
            'Share-Based Compensation',
            'Issuance Of Stock', # A veces yfinance lo agrupa o reporta diferente, pero priorizamos los de arriba
        ]

        for name in sbc_possible_names:
            if name in cash_flow.index:
                sbc_series = cash_flow.loc[name]
                # Llenamos los NaNs con 0 explícitamente y aseguramos tipado
                sbc_series = sbc_series.fillna(0.0).astype(float)
                logger.info(f"[{ticker_symbol}] Se encontró Share-Based Compensation bajo el nombre '{name}'.")
                return sbc_series
                
        # Si llegamos aquí, no se encontró el SBC
        logger.warning(f"[{ticker_symbol}] No se encontró la línea de Share-Based Compensation. Asumiendo 0 para todos los periodos históricos.")
        # Devolvemos una serie de 0s con las mismas fechas que el cash flow statement
        return pd.Series(0.0, index=pd.to_datetime(cash_flow.columns), dtype=float)
        
    except Exception as e:
        logger.error(f"Error al extraer el historial de SBC para {ticker_symbol}: {e}. Asumiendo 0.")
        return pd.Series(dtype=float)

def get_historical_share_reduction_yield(ticker_symbol: str) -> float:
    """
    Extrae el historial de 'Diluted Average Shares' o 'Basic Average Shares' del
    Income Statement de los últimos 5 años, calcula la Tasa de Crecimiento Anual
    Compuesta (CAGR) de las acciones, y devuelve un 'buyback_yield'.
    
    Reglas estandarizadas:
    - CAGR Negativo: La empresa está recomprando acciones (y destruyéndolas).
      Se devuelve este valor en positivo (max 5%).
    - CAGR Positivo: La empresa emite acciones y diluye. Devuelve 0.
    
    Returns:
         float: El yield de recompra de acciones estructurado como decimal (ej. 0.03 para 3%).
    """
    try:
        ticker = yf.Ticker(ticker_symbol)
        
        # Acciones históricas promedio se encuentran en el Income Statement histórico de YF
        inc_stmt = ticker.financials
        
        if inc_stmt.empty:
            logger.warning(f"[{ticker_symbol}] No se encontraron financieros históricos para extraer Share Reduction Yield. Asumiendo 0%.")
            return 0.0
            
        # Posibles nombres bajo los que yfinance asienta las acciones circulantes año a año.
        share_possible_names = ['Diluted Average Shares', 'Basic Average Shares', 'Diluted NI Availto Com Stockholders']
        
        shares_series = None
        for name in share_possible_names:
            if name in inc_stmt.index:
                shares_series = inc_stmt.loc[name]
                break
                
        if shares_series is None or shares_series.empty:
            logger.warning(f"[{ticker_symbol}] No se halló el historial de acciones. Asumiendo Buyback Yield 0%.")
            return 0.0
            
        # Convertir a datetime y ordenar cronológicamente (más antiguo al inicio)
        shares_series.index = pd.to_datetime(shares_series.index)
        shares_series = shares_series.sort_index(ascending=True)
        # Limpiar NaNs
        shares_series = shares_series.dropna()
        
        clean_years = len(shares_series)
        if clean_years < 2:
            return 0.0
            
        oldest_shares = float(shares_series.iloc[0])
        newest_shares = float(shares_series.iloc[-1])
        
        if oldest_shares <= 0 or newest_shares <= 0:
            return 0.0
            
        # Fórmula CAGR: (Valor_Final / Valor_Inicial)^(1 / Número_de_Años) - 1
        cagr = (newest_shares / oldest_shares) ** (1.0 / (clean_years - 1)) - 1
        
        if cagr < 0:
            # Están recomprando
            buyback_yield = abs(cagr)
            if buyback_yield > 0.05:
                logger.warning(f"[{ticker_symbol}] Crecimiento negativo extremo de acciones ({buyback_yield:.2%}). Limitando Buyback Yield al techo del 5.00%.")
                buyback_yield = 0.05
            else:
                 logger.info(f"[{ticker_symbol}] Tasa de Reducción Histórica de Acciones (Recompras): {buyback_yield:.2%}.")
                 
            return float(buyback_yield)
        else:
            # Están emitiendo (o neutro)
             logger.info(f"[{ticker_symbol}] La empresa está diluyendo históricamente a los accionistas (CAGR de Acciones: {cagr:.2%}). Asignando Buyback Yield a 0.00%.")
             return 0.0

    except Exception as e:
         logger.error(f"Error fatal calculando la reducción de acciones para {ticker_symbol}: {e}. Retornando Buyback Yield de 0.")
         return 0.0
         
def get_forward_consensus(ticker_symbol: str) -> Dict[str, any]:
    """
    Extrae la Inteligencia Colectiva paramétrica de Wall Street (Estimaciones de Analistas).
    Si los datos prospectivos no existen en la API gratuita para este modelo, los devuelve
    en cero sin romper el pipeline principal.
    """
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        
        forward_eps = info.get('forwardEps', 0.0)
        revenue_growth = info.get('revenueGrowth', 0.0)
        forward_pe = info.get('forwardPE', 0.0)
        
        # En caso de venir nulos de yfinance
        forward_eps = float(forward_eps) if forward_eps is not None else 0.0
        revenue_growth = float(revenue_growth) if revenue_growth is not None else 0.0
        forward_pe = float(forward_pe) if forward_pe is not None else 0.0
        
        if forward_eps > 0 and forward_pe > 0:
             logger.info(f"[{ticker_symbol}] Estimaciones Prospectivas de Consenso extraídas con éxito.")
             
        return {
            'forward_eps': forward_eps,
            'expected_revenue_growth': revenue_growth,
            'forward_pe': forward_pe
        }
    except Exception as e:
        logger.warning(f"[{ticker_symbol}] No se pudo extraer el consenso de analistas: {e}")
        return {
            'forward_eps': 0.0,
            'expected_revenue_growth': 0.0,
            'forward_pe': 0.0
        }

def get_full_company_data(ticker_symbol: str) -> Dict[str, any]:
    """
    Función envoltorio para obtener todos los datos principales de una empresa
    y devolverlos en un formato estructurado.
    """
    logger.info(f"--- Iniciando extracción de datos completos para {ticker_symbol} ---")
    
    financials_df = get_financials(ticker_symbol)
    price = get_current_price(ticker_symbol)
    
    # Extraemos el sector (lo necesitamos para métricas dinámicas de valoración)
    try:
        ticker_obj = yf.Ticker(ticker_symbol)
        sector = ticker_obj.info.get('sector', 'Unknown')
    except Exception as e:
        logger.warning(f"[{ticker_symbol}] No se pudo extraer el sector: {e}")
        sector = 'Unknown'
    
    financials_df = get_financials(ticker_symbol)
    price = get_current_price(ticker_symbol)
    
    # El price se pasa activamente a las shares para el firewall de Stock Splits
    shares = get_shares_outstanding(ticker_symbol, price)
    
    sbc_history = get_sbc_history(ticker_symbol)
    historical_buyback_yield = get_historical_share_reduction_yield(ticker_symbol)
    forward_consensus = get_forward_consensus(ticker_symbol)
    
    return {
        "financials": financials_df,
        "current_price": price,
        "shares_outstanding": shares,
        "sbc_history": sbc_history,
        "historical_buyback_yield": historical_buyback_yield,
        "forward_consensus": forward_consensus,
        "sector": sector
    }

if __name__ == "__main__":
    # Bloque de prueba
    ticker_prueba = "AAPL"
    try:
        datos = get_full_company_data(ticker_prueba)
        print(f"\n[ÉXITO] Datos extraídos para {ticker_prueba}:")
        print(f"- Precio Actual: ${datos['current_price']:.2f}")
        print(f"- Acciones en Circulación: {datos['shares_outstanding']:,}")
        print("\n- Historial de SBC (Share-Based Compensation):")
        print(datos['sbc_history'])
        print("\n- Muestra de Financials (Net Income):")
        if 'Net Income' in datos['financials'].index:
            print(datos['financials'].loc['Net Income'])
    except Exception as e:
        logger.error(f"Excepción durante la prueba: {e}")
