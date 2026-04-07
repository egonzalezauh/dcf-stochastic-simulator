import logging
import numpy as np
from typing import Dict, Any

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DynamicTerminalValue:
    """
    Motor núcleo para calcular el Valor Terminal (TV) en un modelo DCF.
    Utiliza heurísticas dinámicas para ponderar entre el Método de Crecimiento a Perpetuidad
    (Gordon Growth) y el Método de Múltiplos de Salida (Exit Multiple) según la madurez de la empresa.
    """

    @staticmethod
    def calculate_gordon_tv(fcf_n: float, wacc: float, g: float, mute_logs: bool = False) -> float:
        """
        Calcula el TV usando el Modelo de Crecimiento a Perpetuidad (Gordon Growth).
        
        Args:
            fcf_n (float): Flujo de Caja Libre proyectado en el último año explícito (Año N).
            wacc (float): Costo Promedio Ponderado del Capital (Tasa de Descuento).
            g (float): Tasa de crecimiento a perpetuidad esperada.
            mute_logs (bool): Suprime logs para simulaciones masivas (Monte Carlo).
        
        Returns:
            float: Terminal Value calculado por Gordon (con Suelo de $0).
            
        Raises:
            ValueError: Si wacc <= g (Matemáticamente el TV sería infinito o negativo carente de sentido).
        """
        # Sanity Check 1: Evitar el colapso matemático al infinito o negativo
        if wacc <= g:
            raise ValueError(f"CRÍTICA: El WACC ({wacc:.2%}) debe ser estrictamente mayor que 'g' ({g:.2%}). "
                             f"Un modelo perpetuo asume que la empresa no crecerá más rápido que la economía para siempre.")
            
        # Sanity Check 2: Advertencia sobre crecimiento surrealista
        if g > 0.04 and not mute_logs:
            logger.warning(f"ADVERTENCIA PRUEBA DE CORDURA: Has configurado un 'g' a perpetuidad de {g:.2%}. "
                           f"Pocas o ninguna empresa puede crecer por encima del 4% (inflación + PIB global) para siempre.")
                           
        # Fórmula: TV = [FCF_n * (1 + g)] / (WACC - g)
        # Floor de 0.0 para empresas destruyendo caja perpetuamente
        tv = (fcf_n * (1 + g)) / (wacc - g)
        return max(0.0, tv)

    @staticmethod
    def calculate_exit_multiple_tv(ebitda_n: float, exit_multiple: float, mute_logs: bool = False) -> float:
        """
        Calcula el TV usando el Método de Múltiplos de Salida.
        
        Args:
            ebitda_n (float): EBITDA proyectado en el último año explícito (Año N).
            exit_multiple (float): Múltiplo EV/EBITDA de salida.
            mute_logs (bool): Suprime logs para simulaciones masivas (Monte Carlo).
            
        Returns:
            float: Terminal Value calculado por Múltiplos (con Suelo de $0).
        """
        if exit_multiple <= 0 and not mute_logs:
            logger.warning("El múltiplo de salida proyectado es <= 0. Normalmente es atípico a menos que la empresa decaiga severamente.")
        
        tv = ebitda_n * exit_multiple
        # Floor de 0.0 para evitar valuaciones negativas irreales en empresas quemando EBITDA
        return max(0.0, tv)

    @staticmethod
    def audit_implied_metrics(
        gordon_tv: float, 
        multiple_tv: float, 
        ebitda_n: float, 
        fcf_n: float, 
        wacc: float
    ) -> Dict[str, float]:
        """
        Realiza una prueba cruzada de qué asume cada modelo respecto al otro.
        """
        implied_metrics = {}
        
        # 1. Hallar qué Múltiplo de Salida (EV/EBITDA) implica el Gordon Growth Model
        # Si Gordon calcula un TV de 1,000 y el EBITDA es 100, implica un múltiplo de salida de 10x
        if ebitda_n != 0:
            implied_multiple = gordon_tv / ebitda_n
            implied_metrics['gordon_implied_exit_multiple'] = implied_multiple
        else:
             implied_metrics['gordon_implied_exit_multiple'] = None
             
        # 2. Hallar qué Tasa de Crecimiento Perpetua implica el Múltiplo de Salida
        # Partiendo de TV = [FCF_n * (1 + g)] / (wacc - g)
        # Despejando 'g' algebraicamente: g = (TV * wacc - FCF_n) / (TV + FCF_n)
        if (multiple_tv + fcf_n) != 0:
            implied_g = (multiple_tv * wacc - fcf_n) / (multiple_tv + fcf_n)
            implied_metrics['multiple_implied_g'] = implied_g
        else:
            implied_metrics['multiple_implied_g'] = None
            
        return implied_metrics

    def calculate_blended_tv(
        self, 
        fcf_n: float, 
        ebitda_n: float, 
        wacc: float, 
        g: float, 
        exit_multiple: float, 
        historical_revenue_growth_array: list, 
        historical_margin_array: list,
        mute_logs: bool = False
    ) -> Dict[str, Any]:
        """
        El Enrutador Dinámico (Lógica Central). 
        Calcula el Terminal Value ponderado, el escenario detectado y las métricas cruzadas.
        """
        
        # 1. Calcular TV base (ambos métodos)
        gordon_tv = self.calculate_gordon_tv(fcf_n, wacc, g, mute_logs)
        multiple_tv = self.calculate_exit_multiple_tv(ebitda_n, exit_multiple, mute_logs)
        
        # 2. Evaluar desempeño histórico
        if len(historical_revenue_growth_array) == 0 or len(historical_margin_array) == 0:
            raise ValueError("Debes proveer arrays de crecimiento histórico y márgenes históricos para la ponderación dinámica.")
            
        avg_rev_growth = np.mean(historical_revenue_growth_array)
        std_margins = np.std(historical_margin_array)
        
        if not mute_logs:
            logger.info(f"Evaluando Enrutador Dinámico: Avg Rev Growth = {avg_rev_growth:.2%}, Margin STD = {std_margins:.2%}")
        
        # 3. Lógica Clásica de Clasificación (El Enrutador)
        if avg_rev_growth < 0:
            classification = "DECLINE"
            g_weight = 0.0
            m_weight = 1.0
            if not mute_logs:
                logger.info("[ENRUTADOR] Empresa clasificada en DECLIVE. Aplicando penalización de Múltiplo (100% Exit Multiple).")
            
        elif avg_rev_growth > 0.15:
            classification = "HIGH GROWTH"
            g_weight = 0.20
            m_weight = 0.80
            if not mute_logs:
                logger.info("[ENRUTADOR] Empresa clasificada como ALTO CRECIMIENTO (Ventas Históricas > 15%). Ponderando 80% Múltiplo de Salida y 20% Modelo Gordon.")
            
        else:
            if std_margins <= 0.05:
                classification = "MATURE STABLE"
                g_weight = 0.80
                m_weight = 0.20
                if not mute_logs:
                    logger.info(f"[ENRUTADOR] Empresa clasificada como MADURA (Ventas estables). Ponderando 80% Modelo Gordon y 20% Múltiplo de Salida. Tasa 'g' a perpetuidad asumida: {g:.2%}.")
            else:
                classification = "MATURE VOLATILE"
                g_weight = 0.50  
                m_weight = 0.50
                if not mute_logs:
                    logger.info(f"[ENRUTADOR] Empresa clasificada como MADURA VOLÁTIL (Márgenes inestables). Ponderando 50/50. Tasa 'g' asumida: {g:.2%}.")
                
        # 4. Cálculo Ponderado Final
        blended_tv = (gordon_tv * g_weight) + (multiple_tv * m_weight)
        
        # 5. Auditoría de Métricas Implícitas (Sanity Check cruzado)
        audit_metrics = self.audit_implied_metrics(gordon_tv, multiple_tv, ebitda_n, fcf_n, wacc)
        
        # Log explícito de auditoría cruzada en consola
        if not mute_logs:
            if audit_metrics['multiple_implied_g'] is not None:
                logger.info(f"[AUDITORÍA IMPLÍCITA] El Múltiplo de Salida asignado ({exit_multiple}x) asume de facto que la empresa crecerá eternamente al: {audit_metrics['multiple_implied_g']:.2%}")
            if audit_metrics['gordon_implied_exit_multiple'] is not None:
                logger.info(f"[AUDITORÍA IMPLÍCITA] El Modelo de Gordon asume de facto un múltiplo EV/EBITDA de salida de: {audit_metrics['gordon_implied_exit_multiple']:.1f}x")

            if audit_metrics['multiple_implied_g'] and audit_metrics['multiple_implied_g'] > 0.06:
                logger.warning(f"ADVERTENCIA AUDITORÍA: El múltiplo de salida ({exit_multiple}x) asume matemáticamente un "
                               f"crecimiento a perpetuidad altísimo de {audit_metrics['multiple_implied_g']:.2%}. Considera bajar el múltiplo.")
                               
            if audit_metrics['gordon_implied_exit_multiple'] and audit_metrics['gordon_implied_exit_multiple'] > 30:
                logger.warning(f"ADVERTENCIA AUDITORÍA: El FCF de Gordon asume indirectamente un múltiplo EV/EBITDA de "
                               f"{audit_metrics['gordon_implied_exit_multiple']:.1f}x. Esto puede catalogarse de sobrevaloración explícita.")

        return {
            'blended_tv': blended_tv,
            'gordon_tv': gordon_tv,
            'multiple_tv': multiple_tv,
            'weights': {
                'gordon': g_weight,
                'multiple': m_weight
            },
            'classification': classification,
            'audit': audit_metrics
        }


if __name__ == "__main__":
    # --- PRUEBAS DE ESTRÉS Y CORDURA ---
    validator = DynamicTerminalValue()

    # CONSTANTES COMPARTIDAS PROYECTADAS (Año N)
    test_wacc = 0.10             # 10%
    test_g = 0.02                # 2% Perpetuo
    test_fcf_n = 500_000_000     # 500 Millones
    test_ebitda_n = 800_000_000  # 800 Millones
    test_exit_mult = 12.0        # 12x EV/EBITDA
    
    print("--- Probando Valuation Models Core (Dynamic TV) ---")
    
    # --- CASO 1: Empresa Madura y Estable ---
    print("\n[CASO 1] Empresa 'Value' Madura")
    hist_growth_mature = [0.04, 0.05, 0.03, 0.04, 0.04] # Promedio ~ 4% (< 15%)
    hist_margin_mature = [0.20, 0.21, 0.20, 0.19, 0.20] # Margen muy estable
    
    mature_tv = validator.calculate_blended_tv(
        fcf_n=test_fcf_n, ebitda_n=test_ebitda_n, wacc=test_wacc, g=test_g,
        exit_multiple=test_exit_mult, 
        historical_revenue_growth_array=hist_growth_mature, 
        historical_margin_array=hist_margin_mature
    )
    
    print(f"Clasificación Automática: {mature_tv['classification']}")
    print(f"Pesos: Gordon {mature_tv['weights']['gordon']:.0%} | Múltiplos {mature_tv['weights']['multiple']:.0%}")
    print(f"Gordon TV: ${mature_tv['gordon_tv']:,.0f}")
    print(f"Exit multiple TV: ${mature_tv['multiple_tv']:,.0f}")
    print(f"TV Blend Final: ${mature_tv['blended_tv']:,.0f}")
    print(f"Auditoría Implícita: El múltiplo {test_exit_mult}x implica un crecimiento de {mature_tv['audit']['multiple_implied_g']:.2%}")

    # --- CASO 2: High Growth Tech ---
    print("\n[CASO 2] Startup Tecnológica de Alto Crecimiento")
    hist_growth_tech = [0.25, 0.30, 0.20, 0.28, 0.22] # Promedio ~ 25% (> 15%)
    
    tech_tv = validator.calculate_blended_tv(
        fcf_n=test_fcf_n, ebitda_n=test_ebitda_n, wacc=test_wacc, g=test_g,
        exit_multiple=18.0, # Mayor múltiplo de tech
        historical_revenue_growth_array=hist_growth_tech, 
        historical_margin_array=hist_margin_mature
    )
    print(f"Clasificación Automática: {tech_tv['classification']}")
    print(f"Pesos: Gordon {tech_tv['weights']['gordon']:.0%} | Múltiplos {tech_tv['weights']['multiple']:.0%}")
    print(f"TV Blend Final: ${tech_tv['blended_tv']:,.0f}")

    # --- CASO 3: Sanity Check Fail (WACC <= g) ---
    print("\n[CASO 3] Probando WACC Alert Firewall")
    try:
        validator.calculate_blended_tv(
            fcf_n=test_fcf_n, ebitda_n=test_ebitda_n, wacc=0.08, g=0.09, # 8% WACC < 9% Crecimiento Indefinido
            exit_multiple=test_exit_mult, 
            historical_revenue_growth_array=hist_growth_tech, 
            historical_margin_array=hist_margin_mature
        )
    except ValueError as e:
        print(f"[BLOQUEO MATEMÁTICO EXITOSO]: {e}")
