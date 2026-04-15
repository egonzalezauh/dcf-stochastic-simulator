import streamlit as st
import matplotlib.pyplot as plt
from main import run_valuation_engine
import os
import pandas as pd

st.set_page_config(page_title="Valuation Scenarios", page_icon="📈", layout="wide")

# CSS INJECTION GLASSMORPHISM & PREMIUM UI
st.markdown("""
<style>
[data-testid="stSidebar"] {
    background: rgba(20, 20, 20, 0.4);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border-right: 1px solid rgba(255,255,255,0.05);
}
[data-testid="stMetricValue"] {
    font-size: 2.2rem !important;
    font-weight: 800 !important;
}
[data-testid="stMetricDelta"] {
    font-size: 1.1rem !important;
    font-weight: 600 !important;
}
h1, h2, h3 {
    font-family: 'Inter', 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    font-weight: 700;
}
div.stButton > button {
    border-radius: 8px;
    font-weight: 600;
    transition: all 0.3s ease;
}
div.stButton > button:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(255,0,0,0.4);
}
</style>
""", unsafe_allow_html=True)

st.title("⚡ Simulaciones de valoracion con DCF Estocástico y P/E")
st.markdown("Inyecta escenarios específicos para ver su impacto en la distribución intrínseca y realizar pruebas de estrés de los fundamentales.")

tab_simulador = st.container()

# Inicializar estado de sesión para persistir resultados
if 'results' not in st.session_state:
    st.session_state.results = None
if 'base_results' not in st.session_state:
    st.session_state.base_results = None
if 'sim_meta' not in st.session_state:
    st.session_state.sim_meta = {}

# ========================================================
# PANEL IZQUIERDO: CONTROLES
# ========================================================
col1, col2 = tab_simulador.columns([1, 3])

with col1:
    ticker = st.text_input("Ticker", value="ADBE").upper()
    n_sims = st.number_input("Número de Simulaciones", min_value=1000, max_value=50000, value=10000, step=1000)

    st.header("🛠️ Inyección de Escenarios")
    activar_escenario = st.checkbox("Activar Escenario Personalizado")

    scenario_dict = None
    shock_capex = 0.0
    growth_forzado = 0.0
    castigo_margen = 0.0
    rango_años = (1, 3)

    if activar_escenario:
        st.subheader(f"Parámetros de Shock para {ticker}")
        rango_años = st.slider("Años involucrados en el shock", 1, 10, (1, 3))
        growth_forzado = st.slider("Crecimiento Forzado (%)", min_value=-0.20, max_value=0.30, value=0.05, step=0.01)
        castigo_margen = st.slider("Ajuste Margen EBIT (%)", min_value=-0.15, max_value=0.15, value=-0.02, step=0.01)
        shock_capex = st.slider("Shock CapEx / Ventas (%)", min_value=-0.10, max_value=0.20, value=0.02, step=0.01)

        st.info("""
        **Guía para Principiantes:**
        - **Crecimiento Forzado:** Fuerza el % de crecimiento en ventas. En negativo (-), simula recesión o pérdida de clientes.
        - **Ajuste Margen EBIT:** Impacto directo en la rentabilidad operativa. -5% significa que la empresa gana 5% menos por cada $ vendido.
        - **Shock CapEx:** Aumento o disminución de las inversiones obligatorias. Un valor positivo (+) asume que requieren más gasto en infraestructura.
        """)

        scenario_dict = {
            "active": True,
            "overrides": {
                "revenue_growth": {
                    "years": list(range(rango_años[0], rango_años[1] + 1)),
                    "value": growth_forzado
                },
                "ebit_margin": {
                    "years": list(range(rango_años[0], rango_años[1] + 1)),
                    "value_modifier": castigo_margen
                },
                "capex_margin": {
                    "years": list(range(rango_años[0], rango_años[1] + 1)),
                    "value_modifier": shock_capex
                }
            }
        }

    run_btn = st.button("Ejecutar Simulación", use_container_width=True, type="primary")

    st.divider()
    st.subheader("📊 Contexto de Mercado (Opcional)")
    pe_actual = st.number_input("P/E Actual del Mercado (Trailing)", min_value=0.0, max_value=200.0, value=0.0, step=0.5,
        help="El P/E al que cotiza HOY la acción. Si lo dejas en 0, el modelo lo omite.")
    pe_historico = st.number_input("P/E Histórico Promedio (5Y)", min_value=0.0, max_value=300.0, value=0.0, step=0.5,
        help="El múltiplo P/E promedio de los últimos 5 años. Sirve para detectar compresión de múaltiplos.")

# ========================================================
# PANEL DERECHO: EJECUCIÓN Y RESULTADOS
# ========================================================
with col2:
    # --- EJECUTAR SIMULACIÓN ---
    if run_btn:
        with st.spinner(f"Ingestando datos y simulando trayectorias para {ticker}..."):
            try:
                base_results = None
                if activar_escenario:
                    base_results = run_valuation_engine(ticker, n_simulations=n_sims, scenario=None)

                results = run_valuation_engine(ticker, n_simulations=n_sims, scenario=scenario_dict)

                if results is None:
                    st.error("No se generaron resultados. Esto suele pasar si Yahoo Finance rechaza la conexión temporalmente.")
                else:
                    # Guardar en session_state para persistir entre re-renders de pestañas
                    st.session_state.results = results
                    st.session_state.base_results = base_results
                    st.session_state.sim_meta = {
                        "ticker": ticker,
                        "n_sims": n_sims,
                        "activar_escenario": activar_escenario,
                        "growth_forzado": growth_forzado,
                        "castigo_margen": castigo_margen,
                        "shock_capex": shock_capex,
                        "rango_años": rango_años,
                        "pe_actual": pe_actual,
                        "pe_historico": pe_historico,
                    }

                    st.success("Simulación Monte Carlo completada con éxito.")

            except Exception as e:
                error_msg = str(e)
                if "curl: (56) Recv failure" in error_msg or "Connection was reset" in error_msg:
                    st.error("⚠️ Error de red con Yahoo Finance. Es un bloqueo temporal. Presiona 'Ejecutar' nuevamente.")
                else:
                    st.error(f"Error en la simulación: {error_msg}")

    # --- RENDERIZAR RESULTADOS (desde session_state, persiste entre clicks de pestaña) ---
    if st.session_state.results is not None:
        import numpy as np
        import plotly.graph_objects as go
        from scipy.stats import gaussian_kde

        results = st.session_state.results
        base_results = st.session_state.base_results
        meta = st.session_state.sim_meta
        
        scenario_was_active = meta.get("activar_escenario", False)
        ticker_used = meta.get("ticker", ticker)
        growth_used = meta.get("growth_forzado", 0)
        margen_used = meta.get("castigo_margen", 0)
        years_used = meta.get("rango_años", (1, 3))
        n_sims_used = meta.get("n_sims", 10000)

        p10, p50, p90 = results['p10'], results['p50'], results['p90']
        current_price = results['current_price']
        implied_spot = results['implied_return_spot']
        pe_p10 = results.get('pe_p10', 0)
        pe_p50 = results.get('pe_p50', 0)
        pe_p90 = results.get('pe_p90', 0)
        implied_pe = results.get('implied_return_pe', 0)

        if scenario_was_active:
            st.warning(f"**Escenario Inyectado:** Crecimiento {growth_used:.1%}, Margen EBIT {margen_used:.1%}, años {years_used[0]}-{years_used[1]}.")

        # Función helper de anotaciones verticales (reutilizable en ambas gráficas)
        def add_vline_annotation(fig, x, name, color, dash, y_kde_max):
            fig.add_vline(x=x, line_dash=dash, line_color=color, line_width=2)
            fig.add_annotation(
                x=x, y=y_kde_max * 0.95,
                text=f" <b>{name}</b> ", showarrow=False,
                textangle=0, font=dict(color=color),
                bgcolor="rgba(0,0,0,0.6)",
                xanchor="left", xshift=5
            )

        pe_actual_used = meta.get("pe_actual", 0.0)
        pe_historico_used = meta.get("pe_historico", 0.0)

        tab_dcf, tab_pe, tab_evebitda, tab_integrado = st.tabs([
            "⚖️ Valoración DCF (Efectivo)",
            "📊 Valoración P/E (Contable)",
            "🏭 Valoración EV/EBITDA (Relativa)",
            "🔬 Análisis Integrado"
        ])

        # ===========================================
        # PESTAÑA 1: DCF
        # ===========================================
        with tab_dcf:
            col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
            with col_kpi1:
                st.metric("📍 Precio Spot", f"${current_price:.2f}")
            with col_kpi2:
                st.metric("⚖️ Valor Justo (P50)", f"${p50:.2f}", f"{implied_spot:+.2%}", delta_color="normal")
            with col_kpi3:
                st.metric("📉 Suelo Fundamental (P10)", f"${p10:.2f}", f"{(p10/current_price - 1):+.2%}", delta_color="normal")

            st.divider()

            # Gráfico KDE DCF
            prices = results['valid_prices']
            min_val = max(0, p10 * 0.5)
            max_val = np.percentile(prices, 99) * 1.2
            filtered_prices = prices[(prices >= min_val) & (prices <= max_val)]
            kde = gaussian_kde(filtered_prices)
            x_range = np.linspace(min_val, max_val, 500)
            y_kde = kde(x_range)

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=x_range, y=y_kde, mode='lines', fill='tozeroy',
                fillcolor='rgba(72, 129, 233, 0.3)',
                line=dict(color='#4881E9', width=2), name="Densidad"
            ))
            add_vline_annotation(fig, p10, f'P10: ${p10:.2f}', '#F44336', 'dash', max(y_kde))
            add_vline_annotation(fig, p50, f'P50: ${p50:.2f}', '#00E676', 'solid', max(y_kde))
            add_vline_annotation(fig, p90, f'P90: ${p90:.2f}', '#F44336', 'dash', max(y_kde))
            add_vline_annotation(fig, current_price, f'Spot: ${current_price:.2f}', '#FFFFFF', 'dot', max(y_kde))

            ret_color = '#00E676' if implied_spot > 0 else '#F44336'
            fig.add_annotation(
                text=f"<b>Potencial Inmediato (Spot -> P50): {implied_spot:+.2%}</b>",
                xref="paper", yref="paper", x=0.99, y=0.98,
                xanchor="right", yanchor="top", showarrow=False,
                font=dict(color=ret_color, size=14),
                bgcolor="rgba(0, 0, 0, 0.7)", bordercolor=ret_color,
                borderwidth=1, borderpad=6
            )
            fig.update_layout(
                title=f"<b>Distribución Estocástica UFCF 10 Años - {ticker_used}</b>",
                xaxis_title="Precio Intrínseco por Acción ($)",
                yaxis_title="Densidad Estocástica",
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                showlegend=False, margin=dict(l=20, r=20, t=50, b=20)
            )
            st.plotly_chart(fig, use_container_width=True)

            # Waterfall (solo en escenario activo)
            if scenario_was_active and base_results is not None:
                st.divider()
                st.subheader("🌉 Puente de Destrucción de Valor")
                base_p50 = base_results['p50']
                scenario_p50 = results['p50']
                delta_value = scenario_p50 - base_p50

                fig_waterfall = go.Figure(go.Waterfall(
                    name="Impacto", orientation="v",
                    measure=["absolute", "relative", "total"],
                    x=["Valor Base Inicial", "Impacto Daño Compuesto", "Valor Justo Final"],
                    textposition="outside",
                    text=[f"${base_p50:.2f}", f"${delta_value:+.2f}", f"${scenario_p50:.2f}"],
                    y=[base_p50, delta_value, scenario_p50],
                    connector={"line": {"color": "rgba(255,255,255,0.2)"}},
                    decreasing={"marker": {"color": "#F44336"}},
                    increasing={"marker": {"color": "#00E676"}},
                    totals={"marker": {"color": "#4881E9"}}
                ))
                fig_waterfall.update_layout(
                    title=f"Impacto del Shock Estructural en el Valor Justo ({years_used[0]}-{years_used[1]})",
                    showlegend=False, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                    yaxis_title="Dólares por Acción"
                )
                st.plotly_chart(fig_waterfall, use_container_width=True)
                st.info(f"💡 El escenario extinguió estructuralmente **${abs(delta_value):.2f}** por acción, destruyendo un **{abs(delta_value/base_p50):.2%}** del valor estimado original.")

            st.divider()

            # Tablas de métricas
            def style_returns(val):
                if val == "0.00%" or val == "-": return ""
                if val.startswith("+"): return "color: #00E676; font-weight: bold;"
                elif val.startswith("-"): return "color: #F44336; font-weight: bold;"
                return ""

            col_t1, col_t2 = st.columns(2)
            with col_t1:
                st.subheader("Resumen de Valoración")
                summary_data = {
                    "Escenario / Horizonte": ["📍 Precio Spot (Actual)", "📉 Peor Escenario (P10)", "⚖️ Valor Justo (P50)", "🚀 Mejor Escenario (P90)"],
                    "Cotización": [f"${current_price:.2f}", f"${p10:.2f}", f"${p50:.2f}", f"${p90:.2f}"],
                    "Retorno Implícito": ["0.00%", f"{(p10/current_price - 1):+.2%}", f"{implied_spot:+.2%}", f"{(p90/current_price - 1):+.2%}"]
                }
                st.dataframe(pd.DataFrame(summary_data).style.map(style_returns, subset=["Retorno Implícito"]), use_container_width=True, hide_index=True)

            with col_t2:
                st.subheader("Proyecciones (Valor Esperado)")
                proj_data = {
                    "Horizonte Temporal": ["🗓️ Proyección a 1 Año", "🗓️ Proyección a 5 Años", "🗓️ Proyección a 10 Años"],
                    "Cotización": [f"${results['target_1y']:.2f}", f"${results['target_5y']:.2f}", f"${results['target_10y']:.2f}"],
                    "Retorno Implícito": [f"{results['implied_return_1y']:+.2%}", f"{results['implied_return_5y']:+.2%}", f"{results['implied_return_10y']:+.2%}"]
                }
                st.dataframe(pd.DataFrame(proj_data).style.map(style_returns, subset=["Retorno Implícito"]), use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("📝 Justificación Matemática y Paramétrica")
            estado_val = "infravalorada" if implied_spot > 0 else "sobrevalorada"
            color_val = "#00E676" if implied_spot > 0 else "#F44336"
            scenario_text = ""
            if scenario_was_active:
                scenario_text = f"**⚠️ Impacto del Escenario Personalizado**: Al forzar el crecimiento a **{growth_used:.1%}** y reducir los márgenes operativos un **{margen_used:.1%}** (durante los años {years_used[0]} a {years_used[1]}), el modelo asume que la empresa perdió su ventaja competitiva temporalmente. Esta caída arrastra una menor generación de efectivo durante toda la década, castigando drásticamente su valor a largo plazo."

            st.markdown(f"Para generar estos **{n_sims_used:,} caminos posibles**, el sistema considera factores del mundo real:")
            st.markdown("""
- **Efectivo Real vs Ganancias de Papel:** El modelo proyecta estrictamente el dinero libre en cuentas, restando la Compensación en Acciones (SBC) y calculando el CapEx obligatorio a medida que la empresa madura.
- **El Riesgo Evoluciona Año a Año (Tasa de Descuento):** Analizamos dinámicamente si la empresa se asfixia en deuda, calculamos el peso real de sus impuestos y los conectamos a las tasas de la FED. Si los niveles cruzan límites peligrosos, el modelo desploma el valor automáticamente.
- **Protección del Inversionista Final (Dilución y Recompras):** El Valor Justo ya incluye un escudo preventivo contra dilución futura y premia las recompras históricas comprobadas.
            """)

            if scenario_was_active:
                st.warning(
                    f"⚠️ **Impacto del Escenario Personalizado:** Al forzar el crecimiento a "
                    f"{growth_used:.1%} y reducir los márgenes operativos {margen_used:.1%} "
                    f"(durante los años {years_used[0]} a {years_used[1]}), el modelo asume que la empresa "
                    f"perdió su ventaja competitiva temporalmente. Esta caída arrastra una menor generación "
                    f"de efectivo durante toda la década, castigando drásticamente su valor a largo plazo."
                )

            verdict_color = "#00E676" if implied_spot > 0 else "#F44336"
            estado_val = "infravalorada" if implied_spot > 0 else "sobrevalorada"
            verdict_line = (
                f"La diferencia entre el precio actual ({current_price:.2f} USD) "
                f"y el Valor Justo P50 ({p50:.2f} USD) sugiere que la acción está "
            )
            st.markdown(
                f"{verdict_line}<span style='color:{verdict_color}; font-weight:bold;'>"
                f"{estado_val} en un {abs(implied_spot):.2%}</span>. "
                f"En un colapso severo (P10 pesimista), el suelo intrínseco estaría en {p10:.2f} USD.",
                unsafe_allow_html=True
            )

        # ===========================================
        # PESTAÑA 2: P/E SIMPLE
        # ===========================================
        with tab_pe:
            forward_eps = results.get('forward_eps', 0.0)
            trailing_eps = results.get('trailing_eps', 0.0)
            trailing_pe_yf = results.get('trailing_pe', 0.0)
            forward_pe_yf = results.get('forward_pe', 0.0)
            macro_multiple = results.get('macro_multiple', 15.0)
            
            # El Forward P/E es el más relevante: dice a cuántas veces el mercado paga las ganancias FUTURAS
            pe_vigente = forward_pe_yf if forward_pe_yf > 0 else trailing_pe_yf
            pe_vigente_label = "Forward P/E" if forward_pe_yf > 0 else "Trailing P/E"

            st.subheader(f"Valoración por Múltiplo P/E — {ticker_used}")

            # === PASO 1: LO QUE GANA LA EMPRESA ===
            st.markdown("### 💰 Paso 1: ¿Cuánto gana la empresa?")
            st.markdown("El EPS (Earnings Per Share) es la ganancia neta por acción. El Forward EPS es lo que **los analistas esperan que gane en los próximos 12 meses**.", unsafe_allow_html=True)

            eps_c1, eps_c2, eps_c3 = st.columns(3)
            with eps_c1:
                st.metric("📍 Precio Spot", f"${current_price:.2f}")
            with eps_c2:
                st.metric("📅 EPS último año (TTM)", f"${trailing_eps:.2f}" if trailing_eps > 0 else "N/D")
            with eps_c3:
                st.metric("🔮 EPS esperado (Próx. 12M)", f"${forward_eps:.2f}" if forward_eps > 0 else "N/D")

            st.divider()

            # === PASO 2: A CUÁNTAS VECES COTIZA EL MERCADO ESAS GANANCIAS ===
            st.markdown("### 🧠 Paso 2: ¿A cuántas veces paga el mercado esas ganancias?")
            st.markdown("El múltiplo P/E dice: 'por cada $1 de ganancia, el mercado paga X dólares'. Si cae respecto a su historia, significa que el mercado tiene miedo — no que el negocio se deterioró.", unsafe_allow_html=True)

            pe_c1, pe_c2, pe_c3 = st.columns(3)
            with pe_c1:
                lbl = "Forward P/E (Actual)" if forward_pe_yf > 0 else "Trailing P/E (Actual)"
                val = forward_pe_yf if forward_pe_yf > 0 else trailing_pe_yf
                st.metric(f"⏱️ {lbl}", f"{val:.1f}x" if val > 0 else "N/D", help="El P/E calculado con las ganancias esperadas del próximo año. Es el que usa Wall Street para evaluar si la acción está cara o barata HOY.")
            with pe_c2:
                st.metric("📊 P/E Histórico 5Y", f"{pe_historico_used:.1f}x" if pe_historico_used > 0 else "Ingrésalo en el panel ←", help="El promedio de múltiplos que el mercado le ha pagado a esta empresa en los últimos 5 años.")
            with pe_c3:
                st.metric("🏭 Múltiplo del Sector", f"{macro_multiple:.1f}x", help="El múltiplo razonable que paga Wall Street por una empresa madura de este sector.")

            # Señal automática de compresión
            if pe_historico_used > 0 and pe_vigente > 0:
                compresion = (pe_vigente / pe_historico_used) - 1
                if compresion < -0.05:
                    st.success(f"✅ **Múltiplo Comprimido** — La acción cotiza a {pe_vigente:.1f}x, un {abs(compresion):.0%} por debajo de su media histórica de {pe_historico_used:.1f}x. El mercado aplica un descuento por sentimiento, no por deterioro del negocio.")
                elif compresion > 0.05:
                    st.warning(f"⚠️ **Múltiplo Expandido** — La acción cotiza a {pe_vigente:.1f}x, un {compresion:.0%} por encima de su media histórica de {pe_historico_used:.1f}x. El mercado paga una prima; mayor riesgo de contracción si los resultados decepcionan.")
                else:
                    st.info(f"🟡 **Múltiplo Neutro** — La acción cotiza en línea con su media histórica ({pe_historico_used:.1f}x). Sin señal clara de compresión ni expansión.")

            st.divider()

            # === PASO 3: PRECIO OBJETIVO A 1 AÑO ===
            st.markdown("### 🎯 Paso 3: ¿Cuánto podría valer en 12 meses?")
            st.markdown(
                "Fórmula: <b>Precio Objetivo = EPS Forward × Múltiplo P/E</b>. "
                "Se usa el <b>Trailing P/E</b> como base (múltiplo actual del mercado sobre ganancias reales), "
                "no el Forward P/E — ya que Forward P/E × EPS Forward = precio actual (circular, sin valor informativo).",
                unsafe_allow_html=True
            )

            targets = []

            if forward_eps > 0:
                # Columna 1: Trailing P/E × Forward EPS (base case — múltiplo actual sobre ganancias futuras)
                if trailing_pe_yf > 0:
                    targets.append((
                        f"Trailing P/E ({trailing_pe_yf:.1f}x) — Base",
                        forward_eps * trailing_pe_yf,
                        "Múltiplo actual del mercado sobre las ganancias esperadas del próximo año"
                    ))
                # Columna 2: P/E Histórico × Forward EPS (si el usuario lo ingresó)
                if pe_historico_used > 0:
                    targets.append((
                        f"P/E Histórico 5Y ({pe_historico_used:.1f}x)",
                        forward_eps * pe_historico_used,
                        "Si el múltiplo revierte a su media histórica"
                    ))
                # Columna 3: Múltiplo Sector × Forward EPS
                targets.append((
                    f"Múltiplo Sector ({macro_multiple:.1f}x)",
                    forward_eps * macro_multiple,
                    "Si el mercado valora la empresa como una compañía madura de su sector"
                ))

                target_cols = st.columns(len(targets))
                for i, (label, target_price, desc) in enumerate(targets):
                    ret = (target_price / current_price) - 1
                    with target_cols[i]:
                        st.metric(label, f"${target_price:.2f}", f"{ret:+.2%}", delta_color="normal")
                        st.caption(desc)
            else:
                st.info("No hay Forward EPS disponible en Yahoo Finance para este ticker.")


            st.divider()
            st.caption("💡 **Nota:** El EPS Forward es la estimación de consenso de analistas de Wall Street. No está garantizado — si la empresa decepciona, el precio objetivo cae. El modelo P/E es simple y poderoso, pero no considera la estructura de deuda ni los flujos de caja reales (para eso está la pestaña DCF).")

        # ===========================================
        # PESTAÑA 3: EV/EBITDA
        # ===========================================
        with tab_evebitda:
            ebitda_ttm   = results.get('ebitda_ttm', 0.0)
            ev_current   = results.get('ev_current', 0.0)
            ev_mult_now  = results.get('ev_ebitda_current', 0.0)
            total_debt   = results.get('total_debt', 0.0)
            cash_eq      = results.get('cash_and_equiv', 0.0)
            net_debt     = results.get('net_debt', 0.0)
            shares_out   = results.get('shares_outstanding', 1.0)
            sector_name  = results.get('sector', 'Unknown')
            wacc_used    = results.get('wacc', 0.10)

            # Benchmarks de múltiplo sectorial EV/EBITDA
            SECTOR_EV_BENCHMARKS = {
                'Technology': (18, 25, "premium de innovación + alta escalabilidad"),
                'Communication Services': (12, 18, "mezcla de contenido digital y telecomunicaciones"),
                'Healthcare': (13, 18, "primas de patentes + regulación defensiva"),
                'Consumer Defensive': (11, 15, "márgenes estables, bajo riesgo ciclico"),
                'Consumer Cyclical': (8, 13, "demanda elástica al ciclo económico"),
                'Industrials': (9, 14, "activos físicos pesados, EBITDA visible"),
                'Financial Services': (7, 12, "complejo: deuda = materia prima"),
                'Energy': (6, 10, "cíclico, altamente dependiente del commodity"),
                'Basic Materials': (6, 9,  "commodity puro, márgenes comprimidos"),
                'Real Estate': (14, 20, "activos tangibles + rentas recurrentes"),
                'Utilities': (8, 12, "regulado, flujos predecibles, alta deuda"),
            }
            bench_low, bench_high, bench_desc = SECTOR_EV_BENCHMARKS.get(
                sector_name, (10, 16, "promedio de mercado amplio")
            )
            bench_mid = (bench_low + bench_high) / 2

            st.subheader(f"Valoración por Múltiplo EV/EBITDA — {ticker_used}")

            # == PASO 1: ESTRUCTURA DE CAPITAL ==
            st.markdown("### 🏗️ Paso 1: Estructura de Capital")
            st.markdown(
                "El EV (Enterprise Value) representa el **valor total de la empresa** para todos sus acreedores e inversionistas. "
                "Es el precio que pagarías para comprar *el negocio completo*, incluyendo su deuda pero deduciendo el efectivo disponible.",
                unsafe_allow_html=True
            )

            ev_c1, ev_c2, ev_c3, ev_c4 = st.columns(4)
            with ev_c1:
                st.metric("🏢 Market Cap", f"${(current_price * shares_out)/1e9:.1f}B",
                          help="Capitalizáción burstil: precio spot × acciones en circulación.")
            with ev_c2:
                st.metric("💳 Deuda Total", f"${total_debt/1e9:.1f}B",
                          help="Obligaciones financieras con costo: bonos, préstamos bancarios, leasing.")
            with ev_c3:
                st.metric("💵 Efectivo & Equiv.", f"${cash_eq/1e9:.1f}B",
                          help="Activos líquidos que reducen la deuda neta efectiva.")
            with ev_c4:
                st.metric("🎯 EV Calculado", f"${ev_current/1e9:.1f}B",
                          help="EV = Market Cap + Deuda Total − Efectivo. Es el valor que el mercado le asigna hoy al negocio completo.")

            _mc = f"&#36;{(current_price * shares_out)/1e9:.1f}B"
            _td = f"&#36;{total_debt/1e9:.1f}B"
            _ce = f"&#36;{cash_eq/1e9:.1f}B"
            _ev = f"&#36;{ev_current/1e9:.1f}B"
            st.markdown(
                f"💡 <b>Fórmula:</b> EV = Market Cap + Deuda Total − Efectivo = "
                f"{_mc} + {_td} − {_ce} = <b>{_ev}</b>",
                unsafe_allow_html=True
            )
            st.divider()

            # == PASO 2: EL EBITDA Y EL MÚLTIPLO ACTUAL ==
            st.markdown("### 💰 Paso 2: EBITDA y el Múltiplo que paga el Mercado HOY")
            st.markdown(
                "El **EBITDA** *(Earnings Before Interest, Taxes, Depreciation & Amortization)* mide la rentabilidad operacional "
                "**antes de la estructura financiera**. Elimina sesgos contables y de apalancamiento, siendo ideal para comparar "
                "empresas con estructuras de capital muy diferentes.",
                unsafe_allow_html=True
            )

            ebit_c1, ebit_c2, ebit_c3 = st.columns(3)
            with ebit_c1:
                st.metric("📊 EBITDA TTM", f"${ebitda_ttm/1e9:.2f}B",
                          help="Ganancias antes de intereses, impuestos, depreciáción y amortización. Últimos 12 meses.")
            with ebit_c2:
                st.metric("⏱️ EV/EBITDA Actual", f"{ev_mult_now:.1f}x" if ev_mult_now > 0 else "N/D",
                          help="A cuántas veces el EBITDA anual cotiza el mercado la empresa completa HOY.")
            with ebit_c3:
                st.metric("🏥 Benchmark Sectorial", f"{bench_low}–{bench_high}x",
                          help=f"Rango histórico razonable para empresas de {sector_name}: {bench_desc}.")

            # Semaforo de múltiplo
            if ev_mult_now > 0:
                if ev_mult_now < bench_low:
                    st.success(f"✅ **Múltiplo Comprimido** — La empresa cotiza a **{ev_mult_now:.1f}x EBITDA**, "
                               f"por *debajo* del rango sectorial ({bench_low}–{bench_high}x). "
                               f"El mercado aplica un descuento estructural — últil si la posición operacional es sólida.")
                elif ev_mult_now > bench_high:
                    st.warning(f"⚠️ **Múltiplo Expandido** — La empresa cotiza a **{ev_mult_now:.1f}x EBITDA**, "
                               f"*por encima* del techo sectorial ({bench_low}–{bench_high}x). "
                               f"El mercado paga una prima — mayor riesgo de contracción si el crecimiento decepciona.")
                else:
                    st.info(f"🟡 **Múltiplo Neutro** — La empresa cotiza a **{ev_mult_now:.1f}x EBITDA**, "
                            f"dentro del rango sectorial ({bench_low}–{bench_high}x). Sin señal clara de descuento ni prima.")

            st.divider()

            # == PASO 3: PRECIO OBJETIVO ==
            st.markdown("### 🎯 Paso 3: ¿Cuánto podría valer la acción?")
            st.markdown(
                "**Fórmula:** `Precio Objetivo = (EBITDA × Múltiplo Objetivo − Deuda Neta) ÷ Acciones`\n\n"
                "Calculamos tres escenarios aplicando diferentes múltiplos al EBITDA TTM, luego deducimos la deuda neta "
                "y dividimos entre las acciones en circulación. Esto convierte el valor del negocio en un precio por acción.",
                unsafe_allow_html=True
            )

            scenarios_ev = []
            if ebitda_ttm > 0 and shares_out > 0:
                for label, múltiplo, desc in [
                    (f"Múltiplo Bajo ({bench_low}x) — Pesimista",  bench_low,  "Si el mercado castiga el múltiplo al piso del sector"),
                    (f"Múltiplo Medio ({bench_mid:.0f}x) — Base",   bench_mid,  "Si el múltiplo revierte a la mediana histórica del sector"),
                    (f"Múltiplo Alto ({bench_high}x) — Optimista", bench_high, "Si el mercado paga el techo sectorial por premios de crecimiento"),
                ]:
                    implied_ev  = ebitda_ttm * múltiplo
                    equity_val  = max(0.0, implied_ev - net_debt)
                    price_tgt   = equity_val / shares_out
                    ret_implied = (price_tgt / current_price) - 1
                    scenarios_ev.append((label, múltiplo, price_tgt, ret_implied, desc))

                tgt_cols = st.columns(3)
                ev_base_price = 0.0
                for i, (label, mult, price_tgt, ret, desc) in enumerate(scenarios_ev):
                    with tgt_cols[i]:
                        st.metric(label, f"${price_tgt:.2f}", f"{ret:+.2%}", delta_color="normal")
                        st.caption(desc)
                    if i == 1:  # guardar el base para el Blended
                        ev_base_price = price_tgt

                # Guardar en session state para usar en Integrado
                st.session_state['ev_base_price'] = ev_base_price

                st.divider()

                # Tabla resumen
                ev_table = {
                    "Escenario": [s[0] for s in scenarios_ev],
                    "Múltiplo Aplicado": [f"{s[1]:.0f}x" for s in scenarios_ev],
                    "EV Implicado": [f"${ebitda_ttm * s[1] / 1e9:.1f}B" for s in scenarios_ev],
                    "Precio Objetivo": [f"${s[2]:.2f}" for s in scenarios_ev],
                    "Retorno Implícito": [f"{s[3]:+.2%}" for s in scenarios_ev],
                }
                st.dataframe(
                    pd.DataFrame(ev_table).style.map(style_returns, subset=["Retorno Implícito"]),
                    use_container_width=True, hide_index=True
                )
            else:
                st.warning("⚠️ No hay datos de EBITDA disponibles en Yahoo Finance para este ticker. El modelo EV/EBITDA requiere este dato.")
                st.session_state['ev_base_price'] = p50  # fallback al DCF

            st.divider()
            st.caption(
                "💡 **¿Por qué usar EV/EBITDA?** A diferencia del P/E, este múltiplo "
                "*es agnóstico a la estructura de capital*: dos empresas con idéntico negocio pero diferente deuda "
                "tendrán el mismo EV/EBITDA si generan igual EBITDA. "
                "Es el múltiplo favorito de private equity y banqueros de M&A para valorar adquisiciones."
            )

        # ===========================================
        # PESTAÑA 4: ANÁLISIS INTEGRADO (3 MODELOS)
        # ===========================================
        with tab_integrado:
            _fwd_eps  = results.get('forward_eps', 0.0)
            _trail_pe = results.get('trailing_pe', 0.0)
            _fwd_pe   = results.get('forward_pe', 0.0)

            # --- Precio P/E (Trailing P/E x Forward EPS) ---
            pe_price_simple = _fwd_eps * _trail_pe if (_fwd_eps > 0 and _trail_pe > 0) else p50
            pe_return = (pe_price_simple / current_price) - 1

            # --- Precio EV/EBITDA (recuperado del session_state, calculado en tab_evebitda) ---
            ev_base_price = st.session_state.get('ev_base_price', None)
            ev_available  = ev_base_price is not None and ev_base_price > 0
            n_models      = 3 if ev_available else 2
            ev_return     = (ev_base_price / current_price) - 1 if ev_available else 0.0

            if ev_available:
                blended_p50 = (p50 + pe_price_simple + ev_base_price) / 3
            else:
                blended_p50 = (p50 + pe_price_simple) / 2
            blended_return = (blended_p50 / current_price) - 1

            # --- Veredicto (mayoría de votos entre modelos) ---
            dcf_up = implied_spot > 0
            pe_up  = pe_return  > 0
            ev_up  = ev_return  > 0 if ev_available else dcf_up
            ups    = sum([dcf_up, pe_up, ev_up])

            if ups == 3:
                verdict_emoji, verdict_label, verdict_color = "🟢", "INFRAVALORADA", "#00E676"
                verdict_bg, verdict_border = "rgba(0, 230, 118, 0.08)", "#00E676"
                consenso_txt = "Los tres modelos coinciden: la acción cotiza por debajo de su valor estimado. Señal de compra de alta convicción."
            elif ups == 0:
                verdict_emoji, verdict_label, verdict_color = "🔴", "SOBREVALORADA", "#F44336"
                verdict_bg, verdict_border = "rgba(244, 67, 54, 0.08)", "#F44336"
                consenso_txt = "Los tres modelos coinciden: el precio actual supera el valor estimado en todas las metodologías. Se recomienda cautela."
            elif ups >= 2:
                verdict_emoji, verdict_label, verdict_color = "🟡", "MAYORITARIAMENTE INFRAVALORADA", "#FFC107"
                verdict_bg, verdict_border = "rgba(255, 193, 7, 0.08)", "#FFC107"
                consenso_txt = "2 de 3 modelos detectan valor por encima del precio actual. Señal moderada de oportunidad con divergencia entre metodologías."
            else:
                verdict_emoji, verdict_label, verdict_color = "🟡", "MAYORITARIAMENTE SOBREVALORADA", "#FFC107"
                verdict_bg, verdict_border = "rgba(255, 193, 7, 0.08)", "#FFC107"
                consenso_txt = "La mayoría de los modelos apuntan a sobrevaloración. El mercado pagaría demasiado en relación a los fundamentales."

            st.markdown(f"""
<div style="
    background: {verdict_bg};
    border-left: 4px solid {verdict_border};
    border-radius: 8px;
    padding: 20px 24px;
    margin-bottom: 16px;
">
    <div style="font-size: 2rem; margin-bottom: 4px;">{verdict_emoji}</div>
    <div style="color: {verdict_color}; font-size: 1.4rem; font-weight: 800; letter-spacing: 1px;">{verdict_label}</div>
    <div style="color: #ccc; font-size: 0.95rem; margin-top: 6px;">{consenso_txt}</div>
</div>
            """, unsafe_allow_html=True)

            # KPIs: 3 modelos + Blended
            n_kpi_cols = 4 if ev_available else 3
            kpi_cols = st.columns(n_kpi_cols)
            with kpi_cols[0]:
                st.metric("💵 Precio Spot", f"${current_price:.2f}")
            with kpi_cols[1]:
                st.metric("⚖️ DCF (P50)", f"${p50:.2f}", f"{implied_spot:+.2%}", delta_color="normal")
            with kpi_cols[2]:
                pe_label_i = f"P/E {_trail_pe:.0f}x × EPS Fwd" if _trail_pe > 0 else "P/E Base"
                st.metric(f"📊 {pe_label_i}", f"${pe_price_simple:.2f}", f"{pe_return:+.2%}", delta_color="normal")
            # Tabla de benchmarks sectoriales (usada tanto en KPIs como en narrativa)
            _bmarks = {
                'Technology': (18, 25), 'Communication Services': (12, 18),
                'Healthcare': (13, 18), 'Consumer Defensive': (11, 15),
                'Consumer Cyclical': (8, 13), 'Industrials': (9, 14),
                'Financial Services': (7, 12), 'Energy': (6, 10),
                'Basic Materials': (6, 9), 'Real Estate': (14, 20), 'Utilities': (8, 12),
            }
            sector_i = results.get('sector', '')
            if ev_available:
                with kpi_cols[3]:
                    _bl, _bh = _bmarks.get(sector_i, (10, 16))
                    st.metric(f"🏭 EV/EBITDA {(_bl+_bh)//2}x", f"${ev_base_price:.2f}", f"{ev_return:+.2%}", delta_color="normal")

            st.divider()

            # Blended destacado
            blend_color = "#00E676" if blended_return > 0 else "#F44336"
            st.markdown(f"""
<div style="
    background: rgba(72, 129, 233, 0.08);
    border: 1px solid #4881E9;
    border-radius: 10px;
    padding: 20px 28px;
    text-align: center;
    margin: 12px 0;
">
    <div style="color: #aaa; font-size: 0.9rem; text-transform: uppercase; letter-spacing: 1px;">
        🎯 Blended Target ({n_models} modelos — {100//n_models}% cada uno)
    </div>
    <div style="font-size: 2.6rem; font-weight: 900; color: #fff; margin: 8px 0;">${blended_p50:.2f}</div>
    <div style="font-size: 1.3rem; font-weight: 700; color: {blend_color};">{blended_return:+.2%} vs. Spot ${current_price:.2f}</div>
</div>
            """, unsafe_allow_html=True)

            st.divider()

            # Gráfico comparativo horizontal
            models_labels = ["Precio Spot", "DCF (P50)", "P/E Base"]
            models_values = [current_price, p50, pe_price_simple]
            models_colors = ["#AAAAAA", "#4881E9", "#AB47BC"]
            if ev_available:
                models_labels.append("EV/EBITDA Base")
                models_values.append(ev_base_price)
                models_colors.append("#FF7043")
            models_labels.append("Blended Target")
            models_values.append(blended_p50)
            models_colors.append(blend_color)

            fig_bar = go.Figure(go.Bar(
                x=models_values, y=models_labels, orientation='h',
                marker_color=models_colors,
                text=[f"${v:.2f}" for v in models_values],
                textposition='outside',
            ))
            fig_bar.update_layout(
                title="📊 Comparativa de Precios Objetivo por Metodología",
                xaxis_title="Precio por Acción ($)",
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                showlegend=False,
                margin=dict(l=20, r=90, t=50, b=20),
                height=300 + (40 if ev_available else 0)
            )
            fig_bar.add_vline(
                x=current_price, line_dash="dot", line_color="white", line_width=1.5,
                annotation_text=f"Spot ${current_price:.2f}",
                annotation_position="top right",
                annotation_font_color="#AAAAAA"
            )
            st.plotly_chart(fig_bar, use_container_width=True)

            st.divider()

            # Narrativa
            st.markdown("**📦 Qué dice el Modelo DCF**")
            st.write(
                f"El negocio genera suficiente efectivo libre para justificar un precio de **{p50:.2f} USD** "
                f"bajo las tasas de descuento y riesgos actuales. Este modelo es *agnóstico al sentimiento*: "
                f"no le importa lo que el mercado piense ahora — solo evalúa el dinero real que generará la empresa en los próximos 10 años."
            )

            st.markdown("**📊 Qué dice el Modelo P/E (Simple)**")
            if _fwd_eps > 0 and _trail_pe > 0:
                pe_txt_i = (
                    f"Con un EPS Forward de **{_fwd_eps:.2f} USD** y el Trailing P/E de **{_trail_pe:.1f}x**, "
                    f"el precio objetivo a 1 año es **{pe_price_simple:.2f} USD**. "
                    f"Este modelo refleja lo que el mercado *pagaría hoy* por las ganancias futuras esperadas."
                )
            else:
                pe_txt_i = "No hay suficientes datos de EPS disponibles en Yahoo Finance para este ticker."
            st.write(pe_txt_i)

            if ev_available:
                ebitda_n_i = results.get('ebitda_ttm', 0)
                net_debt_i = results.get('net_debt', 0)
                sector_i2  = results.get('sector', 'el sector')
                bl_i, bh_i = _bmarks.get(sector_i2, (10, 16))
                bm_i = (bl_i + bh_i) / 2
                st.markdown("**🏭 Qué dice el Modelo EV/EBITDA (Relativo)**")
                _ebitda_str  = f"&#36;{ebitda_n_i/1e9:.2f}B"
                _bm_str      = f"{bm_i:.0f}x"
                _impl_ev_str = f"&#36;{ebitda_n_i * bm_i / 1e9:.1f}B"
                _nd_str      = f"&#36;{net_debt_i/1e9:.2f}B"
                _tgt_str     = f"&#36;{ev_base_price:.2f} USD"
                st.markdown(
                    f"Con un EBITDA TTM de <b>{_ebitda_str}</b> y aplicando el múltiplo medio sectorial "
                    f"(<b>{_bm_str}</b> para {sector_i2}), el EV implícito es <b>{_impl_ev_str}</b>. "
                    f"Deduciendo deuda neta de <b>{_nd_str}</b> y dividiendo entre las acciones, el precio objetivo es <b>{_tgt_str}</b>. "
                    f"Este modelo elimina el sesgo del apalancamiento — ideal para comparar empresas con estructuras de capital distintas.",
                    unsafe_allow_html=True
                )

            st.markdown(f"**🎯 Blended Target ({n_models} modelos)**")
            st.write(
                f"Promediando {n_models} metodologías en igual peso, el objetivo consolidado es **{blended_p50:.2f} USD**, "
                f"representando un potencial de **{blended_return:+.2%}** desde el precio actual ({current_price:.2f} USD). "
                f"Este número toma lo mejor de cada disciplina: el rigor del DCF, la señal de sentimiento del P/E "
                f"{'y la neutralidad estructural del EV/EBITDA' if ev_available else ''}."
            )
