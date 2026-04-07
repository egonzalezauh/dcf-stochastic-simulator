import numpy as np
import pandas as pd
import scipy.stats as stats
import logging
from typing import Dict, Tuple

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def is_positive_definite(matrix: np.ndarray) -> bool:
    """
    Verifica si una matriz es definida positiva intentando calcular
    su descomposición de Cholesky.

    Args:
        matrix (np.ndarray): Matriz cuadrada bidimensional.

    Returns:
        bool: True si es definida positiva, False en caso contrario.
    """
    try:
        np.linalg.cholesky(matrix)
        return True
    except np.linalg.LinAlgError:
        return False


def nearest_positive_definite(matrix: np.ndarray, eps: float = 1e-8) -> np.ndarray:
    """
    Encuentra la matriz definida positiva más cercana a la matriz dada.
    Útil cuando las matrices empíricas de covarianza resultan ser solo
    semi-definidas positivas debido a ruido computacional o datos incompletos.
    
    Basado en Higham (1988), usa la descomposición espectral (autovalores).
    
    Args:
        matrix (np.ndarray): Matriz bidimensional simétrica.
        eps (float): Tolerancia mínima para asegurar que los autovalores son estrictamente positivos.

    Returns:
        np.ndarray: Matriz simétrica y definida positiva.
    """
    # 1) Asegurar simetría estricta
    sim_matrix = (matrix + matrix.T) / 2.0
    
    # 2) Descomposición espectral
    eigenvalues, eigenvectors = np.linalg.eigh(sim_matrix)
    
    # 3) Forzar autovalores a ser estrictamente positivos
    # Si todos son positivos y mayores a eps, la matriz ya era PD.
    if np.all(eigenvalues > 0):
        # Aún así reconstruimos para eliminar ruido minúsculo asimétrico
        # o devolvemos sim_matrix, pero es más seguro reconstruirla.
        eigenvalues = np.maximum(eigenvalues, eps)
        pd_matrix = eigenvectors @ np.diag(eigenvalues) @ eigenvectors.T
        return (pd_matrix + pd_matrix.T) / 2.0
        
    logger.warning("La matriz original no es definida positiva. Aplicando corrección nearest-positive-definite.")
    
    # Reemplazar autovalores negativos o muy pequeños por eps
    # En matrices de covarianza, un autovalor negativo representa varianza negativa, 
    # lo cual es físicamente imposible (es ruido puramente matemático).
    positive_eigenvalues = np.maximum(eigenvalues, eps)
    
    # 4) Reconstruir la matriz
    pd_matrix = eigenvectors @ np.diag(positive_eigenvalues) @ eigenvectors.T
    
    # 5) Forzar simetría de nuevo por problemas de precisión de coma flotante
    pd_matrix = (pd_matrix + pd_matrix.T) / 2.0
    return pd_matrix


class MonteCarloCholeskySimulator:
    """
    Simulador de Monte Carlo que preserva la correlación histórica utilizando
    Descomposición de Cholesky.
    """
    def __init__(self, historical_df: pd.DataFrame):
        """
        Inicializa el simulador con datos históricos reales.
        
        Args:
            historical_df (pd.DataFrame): DataFrame donde cada COLUMNA es una variable
                                          (ej. Crecimiento Ventas, Margen) y cada FILA es un periodo.
        """
        if historical_df.empty:
            raise ValueError("El DataFrame histórico proporcionado está vacío.")
            
        self.variables = historical_df.columns.tolist()
        self.n_vars = len(self.variables)
        
        logger.info(f"Inicializando simulador para {self.n_vars} variables: {self.variables}")
        
        # 1) Calcular el vector de medias empíricas (mu)
        self.mean_vector = historical_df.mean().values
        
        # 2) Calcular la matriz de covarianza empírica (Sigma)
        cov_matrix = historical_df.cov().values
        
        # Validación de NaNs en la covarianza (si los datos eran pocos o invariables)
        if np.isnan(cov_matrix).any():
            raise ValueError("La matriz de covarianza calculada contiene NaNs. Verifica que los datos históricos sean suficientes y variables.")

        # 3) Validar y asegurar que Sigma sea Definida Positiva
        if not is_positive_definite(cov_matrix):
            cov_matrix = nearest_positive_definite(cov_matrix)
            # Re-verificar (debería pasar siempre a menos que haya un edge-case drástico de coma flotante)
            if not is_positive_definite(cov_matrix):
                cov_matrix = nearest_positive_definite(cov_matrix, eps=1e-6) # Elevar la tolerancia
                if not is_positive_definite(cov_matrix):
                     raise RuntimeError("No se pudo forzar la matriz de covarianza a ser Definida Positiva.")
                
        self.cov_matrix = cov_matrix
        
        # 4) Calcular la matriz triangular inferior L (Descomposición de Cholesky)
        # Sigma = L * L.T
        self.L_matrix = np.linalg.cholesky(self.cov_matrix)
        logger.info("Descomposición de Cholesky (Matriz L) completada exitosamente.")

    def simulate(self, n_simulations: int = 10000) -> Dict[str, np.ndarray]:
        """
        Genera N simulaciones correlacionadas.
        
        Args:
            n_simulations (int): Número de trayectorias/escenarios a simular.
            
        Returns:
            Dict[str, np.ndarray]: Diccionario donde las keys son los nombres de las variables
                                   y los values son arrays numpy de tamaño (n_simulations,).
        """
        logger.info(f"Generando {n_simulations:,} simulaciones correlacionadas...")
        
        # Z = Distribución Normal Estándar Multivariada No Correlacionada
        # Matriz de dimensiones (n_vars, n_simulations)
        Z = stats.norm.rvs(size=(self.n_vars, n_simulations))
        
        # X = mu + L * Z
        # L es (n_vars, n_vars), Z es (n_vars, n_simulations)
        # L @ Z resulta en (n_vars, n_simulations) de shocks correlacionados
        # self.mean_vector[:, np.newaxis] asegura un broadcasting (n_vars, 1) + (n_vars, n_simulations)
        
        X = self.mean_vector[:, np.newaxis] + (self.L_matrix @ Z)
        
        # Convertir a un diccionario accesible y seguro tipado
        simulated_data = {}
        for idx, var_name in enumerate(self.variables):
            simulated_data[var_name] = X[idx, :]
            
        return simulated_data


if __name__ == "__main__":
    # Prueba conceptual y validación del modelo matemático
    
    # 1. Crear un DataFrame dummy estructurado como saldría de yfinance_extractor
    # Simulamos 5 años históricos de 3 variables financieras
    # (Los valores están estructurados para que haya una covarianza obvia)
    dummy_data = {
        'Revenue_Growth': [0.10, 0.12, 0.08, 0.15, 0.05],
        'EBIT_Margin': [0.20, 0.22, 0.18, 0.25, 0.15],
        'Tax_Rate': [0.21, 0.21, 0.21, 0.21, 0.21] # Variable constante -> covarianza 0 -> PROBLEMA de PD matriz
    }
    df_history = pd.DataFrame(dummy_data, index=[2020, 2021, 2022, 2023, 2024])
    
    # Hemos introducido intencionalmente una columna constante ('Tax_Rate')
    # Esto CAUSA que la matriz de covarianza NO sea definida positiva (es singular).
    # Este es el test perfecto para 'nearest_positive_definite'.
    
    print("--- Probando Simulador de Monte Carlo Cholesky engine ---")
    try:
        simulator = MonteCarloCholeskySimulator(df_history)
        
        n_sims = 5000
        resultados = simulator.simulate(n_simulations=n_sims)
        
        print("\n[ÉXITO] Simulaciones generadas.")
        print(f"Diccionario devuelto con {len(resultados.keys())} keys.")
        for name, array in resultados.items():
            print(f"- {name}: media={np.mean(array):.4f}, std={np.std(array):.4f}, tamaño={array.shape}")
            
    except Exception as e:
         logger.error(f"Fallo en la prueba: {e}")
