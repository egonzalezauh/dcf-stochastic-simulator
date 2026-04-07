import logging

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def calculate_diluted_shares(
    base_shares: float,
    options_in_the_money: float,
    average_strike_price: float,
    enterprise_value: float,
    net_debt: float,
    tolerance: float = 0.001,
    max_iterations: int = 100
) -> float:
    """
    Resuelve la circularidad matemática entre el precio por acción y las acciones
    diluidas debidas a opciones compensatorias y RSUs usando el Treasury Stock Method.

    Args:
        base_shares (float): Acciones ordinarias en circulación inicialmente (del Extractor).
        options_in_the_money (float): Cantidad total de opciones no ejercidas (otorgadas pero no ejercidas).
        average_strike_price (float): Precio de ejercicio promedio ponderado de las opciones.
        enterprise_value (float): Valor de la Empresa (NPV del Free Cash Flow + Terminal Value).
        net_debt (float): Deuda neta total (Deuda Total - Efectivo y Equivalentes).
        tolerance (float): Criterio de convergencia para el precio de la acción (default = $0.001).
        max_iterations (int): Número máximo de iteraciones para evitar bucles infinitos (default = 100).

    Returns:
        float: Cantidad exacta de acciones diluidas finales tras convergencia.
        
    Raises:
        RuntimeError: Si el algoritmo no converge de la tolerancia en `max_iterations`.
    """
    # 1. El Valor del Capital (Equity Value) es constante asumiendo el EV dado
    equity_value = enterprise_value - net_debt
    
    if equity_value <= 0:
         logger.warning("El Equity Value inicial es <= 0. La circularidad asume precio de acción $0.0 y no hay dilución por opciones.")
         return base_shares

    # 2. Iniciar el Precio de la Acción base (sin dilución aún)
    current_share_price = equity_value / base_shares
    current_diluted_shares = base_shares
    
    logger.info(f"Iniciando TSM. Precio base inicial: ${current_share_price:.4f}, Equity Value: ${equity_value:,.0f}")

    iteration = 0
    diff = float('inf')

    # 3. Bucle while para la Circularidad
    while diff >= tolerance and iteration < max_iterations:
        iteration += 1
        previous_share_price = current_share_price

        # Comprobar si las opciones están "in the money"
        if current_share_price > average_strike_price:
            # a) Proceeds (Ingresos a la empresa al ejercer las opciones)
            proceeds = options_in_the_money * average_strike_price
            
            # b) Las acciones que la empresa puede "recomprar" al precio de mercado actual con esos ingresos
            shares_bought_back = proceeds / current_share_price
            
            # c) Las nuevas acciones netas emitidas que causan dilución
            net_new_shares = max(0, options_in_the_money - shares_bought_back)
        else:
            # Las opciones están "out of the money", no se ejercen, no hay dilución
            net_new_shares = 0

        # Calcular nuevas acciones diluidas
        current_diluted_shares = base_shares + net_new_shares
        
        # Recalcular el nuevo precio de la acción
        current_share_price = equity_value / current_diluted_shares

        # Calcular la diferencia para el criterio de parada
        diff = abs(current_share_price - previous_share_price)

    # 4. Chequear el motivo de salida del bucle
    if iteration >= max_iterations and diff >= tolerance:
        error_msg = f"Fallo al converger en TSM después de {max_iterations} iteraciones. Diferencia final: {diff:.6f}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    logger.info(f"Convergencia TSM alcanzada en la iteración {iteration}.")
    logger.info(f"Precio Final de la Acción: ${current_share_price:.4f} | Acciones Diluidas Finales: {current_diluted_shares:,.2f} (Dilución: {current_diluted_shares - base_shares:,.2f})")
    
    return current_diluted_shares


if __name__ == "__main__":
    # Prueba conceptual interactiva del TSM Calculator
    
    # Supuestos realistas para una Tech Corp mid-cap
    test_base_shares = 100_000_000   # 100M acciones base
    test_options = 10_000_000        # 10M opciones otorgadas a directivos/empleados
    test_strike = 50.00              # Strike price promedio ponderado
    test_ev = 11_000_000_000         # 11 Billones Enterprise Value
    test_net_debt = 1_000_000_000    # 1 Billón Deuda Neta
    # Equity Value = 10_000_000_000
    # Initial Base Price = 10_000_000_000 / 100_000_000 = $100
    # $100 > $50 (In the money by $50)
    
    print("--- Probando Calculadora de Circularidad Treasury Stock Method ---")
    try:
        final_diluted = calculate_diluted_shares(
            base_shares=test_base_shares,
            options_in_the_money=test_options,
            average_strike_price=test_strike,
            enterprise_value=test_ev,
            net_debt=test_net_debt
        )
        print(f"\n[ÉXITO] El método finalizó correctamente.")
        print(f"Resultado de acciones diluidas tras convergencia: {final_diluted:,.2f}")
    except RuntimeError as e:
        print(f"\n[FALLO] Runtime Error lanzado: {e}")
