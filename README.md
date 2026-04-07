# ⚡ DCF Estocástico y Simulador de Escenarios (Monte Carlo)

Una plataforma profesional de valoración financiera y pruebas de estrés. Desarrollado en Python, este motor proyecta el Flujo de Caja Libre No Apalancado (UFCF) a 10 años, ejecutando decenas de miles de simulaciones de Monte Carlo para encontrar el Valor Intrínseco real de empresas cotizadas en bolsa, castigando drásticamente el "ruido contable" optimista de Wall Street.

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)
![Plotly](https://img.shields.io/badge/Plotly-3F4F75?style=for-the-badge&logo=plotly&logoColor=white)
![Pandas](https://img.shields.io/badge/Pandas-150458?style=for-the-badge&logo=pandas&logoColor=white)

---

## 💡 ¿Por qué es especial? (Física Financiera Avanzada)

A diferencia de los anticuados modelos de Excel tradicionales (DCF Estáticos) que crecen con líneas rectas planas y sin fricción, este algoritmo implementa **heurísticas del mundo real** para defender al inversionista:

1. 💸 **Efectivo Real vs Ganancias de Papel (SBC & CapEx)**: El motor ignora las ganancias contables puras. Le resta automáticamente todo el dinero con el que la empresa diluye o paga a sus empleados (*Stock-Based Compensation*) antes del UFCF libre, y proyecta de forma madura la necesidad técnica de infraestructura (*CapEx*) sobre las Depreciaciones operativas.
2. 🛡️ **Protección al Inversionista (Dilución y Buybacks)**: Todo precio proyectado absorbe internamente el *Treasury Stock Method*. Es decir, el modelo pre-evalúa cuántas nuevas acciones va a emitir la empresa a futuro contra ti (arruinando tus retornos) y, por el otro lado, premia fuertemente a la empresa reduciendo el denominador si demuestra tener un hábito histórico constante de recomprar sus propias acciones en el mercado abierto.
3. 🌪️ **Gravedad Fractal (WACC Mutante)**: No asume un costo de capital pasivo. Extrae dinámicamente el apalancamiento real del balance histórico (Deuda/Capital) y ajusta la prima por riesgo absorbiendo directamente las tasas presentes desde la Reserva Federal (FRED API). Si hay presiones macroeconómicas, la valoración es masacrada matemáticamente de forma proporcional.
4. 🎲 **Matriz de Cholesky y Proyecciones Estocásticas**: Emplea el método algebraico de descomposición de Cholesky. Esto significa que correlaciona históricamente cómo reaccionan los Crecimientos de Ingresos a la vez que los Márgenes Operativos. Posteriormente expulsa iteraciones gaussianas simulando miles de escenarios probables para construir Densidad, aislando el "P10" (El pero escenario desastroso medible).
5. 🩸 **Inyectores de Escenarios y Gráficos de Cascada**: Cuenta con una interfaz intuitiva para pruebas de estrés. Si crees que una demanda legal puede mermar el crecimiento de la empresa del año 2 al 4, el *Dashboard* quiebra intencionalmente la proyección histórica y renderiza a través de Plotly Waterfall qué porcentaje de riqueza estructural quemó ese escenario exactamente.

---

## 🛠️ Stack Tecnológico
* **Core Engine**: Python (POO modular).
* **Gestión de Datos y Álgebra**: `pandas`, `numpy`, `scipy` (Gaussian KDE).
* **Fuentes y Data Pipelines**: `yfinance` (Estados Financieros dinámicos en vivo) y la API de `fredapi` (St. Louis Federal Reserve Data).
* **Frontend interactivo**: `streamlit`, `plotly` y componentes de Glassmorphism/CSS inyectado en el DOM.

---

## 🚀 Despliegue Local (Localhost)

Si prefieres explorar esta aplicación por tu cuenta o ver bajo el capó de la matriz y alterar su límite analítico temporal:

1. **Clona este repositorio**:
   ```bash
   git clone https://github.com/TU_USUARIO/dcf-stochastic-simulator.git
   cd dcf-stochastic-simulator
   ```

2. **Crea y Activa un Entorno Virtual (Opcional pero Recomendado)**:
   ```bash
   # En Windows
   python -m venv env
   .\env\Scripts\activate
   # En macOS / Linux
   python3 -m venv env
   source env/bin/activate
   ```

3. **Instala las dependencias estables**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Variables de Entorno (IMPORTANTE)**:
   El modelo extrae en vivo el US Treasury Risk-Free Rate usando FRED. Necesitarás ir [aquí y conseguir una API gratis](https://fred.stlouisfed.org/docs/api/api_key.html).
   Crea un archivo llamado `.env` en la misma raíz y pon dentro tu API:
   ```env
   FRED_API_KEY="pega_tu_api_aqui"
   ```

5. **Inicia el servidor local de interfaz web**:
   ```bash
   streamlit run app.py
   ```
