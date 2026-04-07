import streamlit as st
import matplotlib.pyplot as plt
from main import run_valuation_engine
import os

st.set_page_config(page_title="Valuation Scenarios", page_icon="📈", layout="wide")

# CSS INJECTION GLASSMORPHISM & PREMIUM UI
st.markdown("""
<style>
/* Glassmorphism sidebar */
[data-testid="stSidebar"] {
    background: rgba(20, 20, 20, 0.4);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border-right: 1px solid rgba(255,255,255,0.05);
}
/* Style metrics */
[data-testid="stMetricValue"] {
    font-size: 2.2rem !important;
    font-weight: 800 !important;
}
[data-testid="stMetricDelta"] {
    font-size: 1.1rem !important;
    font-weight: 600 !important;
}
/* Center align headers */
h1, h2, h3 {
    font-family: 'Inter', 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    font-weight: 700;
}
/* Rounded components */
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

st.title("⚡ DCF Estocástico - Simulador de Escenarios")
st.markdown("Inyecta escenarios específicos para ver su impacto en la distribución intrínseca y realizar pruebas de estrés de los fundamentales.")

# Layout
col1, col2 = st.columns([1, 3])

with col1:
    ticker = st.text_input("Ticker", value="ADBE").upper()
    n_sims = st.number_input("Número de Simulaciones", min_value=1000, max_value=50000, value=10000, step=1000)

    st.header("🛠️ Inyección de Escenarios")
    activar_escenario = st.checkbox("Activar Escenario Personalizado")

    scenario_dict = None

    if activar_escenario:
        st.subheader(f"Parámetros de Shock para {ticker}")
        
        # Sliders interactivos
        rango_años = st.slider("Años involucrados en el shock", 1, 10, (1, 3))
        growth_forzado = st.slider("Crecimiento Forzado (%)", min_value=0.0, max_value=0.30, value=0.05, step=0.01)
        castigo_margen = st.slider("Castigo Margen EBIT (%)", min_value=-0.20, max_value=0.05, value=-0.02, step=0.01)
        
        # Construimos el diccionario al vuelo basándonos en los sliders del usuario
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
                }
            }
        }

    run_btn = st.button("Ejecutar Simulación", use_container_width=True, type="primary")

with col2:
    if run_btn:
        with st.spinner(f"Ingestando datos y simulando trayectorias para {ticker} (Puede tomar unos segundos)..."):
            try:
                # Ejecutamos el motor de valoración base (si hay escenario) y principal
                base_results = None
                if activar_escenario:
                    base_results = run_valuation_engine(ticker, n_simulations=n_sims, scenario=None)
                
                results = run_valuation_engine(ticker, n_simulations=n_sims, scenario=scenario_dict)
                
                if results is None:
                    st.error("No se generaron resultados. Esto suele pasar si Yahoo Finance rechaza la conexión temporalmente.")
                else:
                    st.success(f"Simulación Monte Carlo completada con éxito.")
                    
                    if activar_escenario:
                        st.warning(f"**Escenario Inyectado:** Crecimiento ajustado a {growth_forzado:.1%} y márgenes EBIT impactados en {castigo_margen:.1%} durante los años {rango_años[0]} a {rango_años[1]}.")
                    
                    # Extraer variables para KPIs
                    p10, p50, p90 = results['p10'], results['p50'], results['p90']
                    current_price = results['current_price']
                    implied_spot = results['implied_return_spot']

                    # ==========================================
                    # BIG NUMBER CARDS (KPIs)
                    # ==========================================
                    col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
                    with col_kpi1:
                        st.metric("📍 Precio Spot", f"${current_price:.2f}")
                    with col_kpi2:
                        st.metric("⚖️ Valor Justo (P50)", f"${p50:.2f}", f"{implied_spot:+.2%}", delta_color="normal")
                    with col_kpi3:
                        st.metric("📉 Suelo Fundamental (P10)", f"${p10:.2f}", f"{(p10/current_price - 1):+.2%}", delta_color="normal")
                    
                    st.divider()
                    
                    # ==========================================
                    # RENDERING NATIVO Y PREMIUM: PLOTLY
                    # ==========================================
                    import numpy as np
                    import pandas as pd
                    import plotly.graph_objects as go
                    from scipy.stats import gaussian_kde
                    
                    prices = results['valid_prices']
                    p10, p50, p90 = results['p10'], results['p50'], results['p90']
                    current_price = results['current_price']
                    
                    # Acotar la data para el gráfico
                    min_val = max(0, p10 * 0.5)
                    max_val = np.percentile(prices, 99) * 1.2
                    filtered_prices = prices[(prices >= min_val) & (prices <= max_val)]
                    
                    kde = gaussian_kde(filtered_prices)
                    x_range = np.linspace(min_val, max_val, 500)
                    y_kde = kde(x_range)
                    
                    fig = go.Figure()
                    
                    # Añadir curva KDE
                    fig.add_trace(go.Scatter(
                        x=x_range, y=y_kde,
                        mode='lines',
                        fill='tozeroy',
                        fillcolor='rgba(72, 129, 233, 0.3)',
                        line=dict(color='#4881E9', width=2),
                        name="Densidad"
                    ))
                    
                    # Vertical lines func
                    def add_vline_annotation(fig, x, name, color, dash):
                        fig.add_vline(x=x, line_dash=dash, line_color=color, line_width=2)
                        fig.add_annotation(
                            x=x, y=max(y_kde)*0.95,
                            text=f" <b>{name}</b> ", showarrow=False,
                            textangle=0, font=dict(color=color),
                            bgcolor="rgba(0,0,0,0.6)",
                            xanchor="left", xshift=5
                        )

                    add_vline_annotation(fig, p10, f'P10: ${p10:.2f}', '#F44336', 'dash')
                    add_vline_annotation(fig, p50, f'P50: ${p50:.2f}', '#00E676', 'solid')
                    add_vline_annotation(fig, p90, f'P90: ${p90:.2f}', '#F44336', 'dash')
                    add_vline_annotation(fig, current_price, f'Spot: ${current_price:.2f}', '#FFFFFF', 'dot')
                    
                    implied_spot = results['implied_return_spot']
                    ret_color = '#00E676' if implied_spot > 0 else '#F44336'
                    
                    fig.add_annotation(
                        text=f"<b>Potencial Inmediato (Spot -> P50): {implied_spot:+.2%}</b>",
                        xref="paper", yref="paper",
                        x=0.99, y=0.98,
                        xanchor="right", yanchor="top",
                        showarrow=False,
                        font=dict(color=ret_color, size=14),
                        bgcolor="rgba(0, 0, 0, 0.7)",
                        bordercolor=ret_color,
                        borderwidth=1, borderpad=6
                    )

                    fig.update_layout(
                        title=f"<b>Distribución Estocástica UFCF 10 Años - {ticker}</b>",
                        xaxis_title="Precio Intrínseco por Acción ($)",
                        yaxis_title="Densidad Estocástica",
                        plot_bgcolor='rgba(0,0,0,0)',
                        paper_bgcolor='rgba(0,0,0,0)',
                        showlegend=False,
                        margin=dict(l=20, r=20, t=50, b=20)
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # ==========================================
                    # GRÁFICO PUENTE (WATERFALL CHART)
                    # ==========================================
                    if activar_escenario and base_results is not None:
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
                            connector={"line":{"color":"rgba(255,255,255,0.2)"}},
                            decreasing={"marker":{"color":"#F44336"}},
                            increasing={"marker":{"color":"#00E676"}},
                            totals={"marker":{"color":"#4881E9"}}
                        ))
                        
                        fig_waterfall.update_layout(
                            title=f"Impacto del Shock Estructural en el Valor Justo ({rango_años[0]}-{rango_años[1]})",
                            showlegend=False,
                            plot_bgcolor='rgba(0,0,0,0)',
                            paper_bgcolor='rgba(0,0,0,0)',
                            yaxis_title="Dólares por Acción"
                        )
                        st.plotly_chart(fig_waterfall, use_container_width=True)
                        
                        st.info(f"💡 El escenario personalizado extinguió estructuralmente **${abs(delta_value):.2f}** por acción en valor intrínseco, destruyendo un **{abs(delta_value/base_p50):.2%}** del valor estimado original.")
                        
                    # ==========================================
                    # RENDERING NATIVO: TABLA DE MÉTRICAS
                    # ==========================================
                    st.divider()
                    
                    def style_returns(val):
                        if val == "0.00%" or val == "-":
                            return ""
                        if val.startswith("+"):
                            return "color: #00E676; font-weight: bold;"
                        elif val.startswith("-"):
                            return "color: #F44336; font-weight: bold;"
                        return ""
                        
                    col_t1, col_t2 = st.columns(2)
                    
                    with col_t1:
                        st.subheader("Resumen de Valoración")
                        summary_data = {
                            "Escenario / Horizonte": [
                                "📍 Precio Spot (Actual)",
                                "📉 Peor Escenario (P10)",
                                "⚖️ Valor Justo (P50)",
                                "🚀 Mejor Escenario (P90)"
                            ],
                            "Cotización": [
                                f"${current_price:.2f}",
                                f"${p10:.2f}",
                                f"${p50:.2f}",
                                f"${p90:.2f}"
                            ],
                            "Retorno Implícito": [
                                "0.00%",
                                f"{(p10/current_price - 1):+.2%}",
                                f"{(implied_spot):+.2%}",
                                f"{(p90/current_price - 1):+.2%}"
                            ]
                        }
                        df_summary = pd.DataFrame(summary_data)
                        st.dataframe(df_summary.style.map(style_returns, subset=["Retorno Implícito"]), use_container_width=True, hide_index=True)
                        
                    with col_t2:
                        st.subheader("Proyecciones (Valor Esperado)")
                        proj_data = {
                            "Horizonte Temporal": [
                                "🗓️ Proyección a 1 Año",
                                "🗓️ Proyección a 5 Años",
                                "🗓️ Proyección a 10 Años"
                            ],
                            "Cotización": [
                                f"${results['target_1y']:.2f}",
                                f"${results['target_5y']:.2f}",
                                f"${results['target_10y']:.2f}"
                            ],
                            "Retorno Implícito": [
                                f"{results['implied_return_1y']:+.2%}",
                                f"{results['implied_return_5y']:+.2%}",
                                f"{results['implied_return_10y']:+.2%}"
                            ]
                        }
                        df_proj = pd.DataFrame(proj_data)
                        st.dataframe(df_proj.style.map(style_returns, subset=["Retorno Implícito"]), use_container_width=True, hide_index=True)

                    # ==========================================
                    # RENDERING NATIVO: RESUMEN DE JUSTIFICACIÓN
                    # ==========================================
                    st.divider()
                    st.subheader("📝 Justificación Matemática y Paramétrica")
                    
                    estado_val = "infravalorada" if implied_spot > 0 else "sobrevalorada"
                    color_val = "#00E676" if implied_spot > 0 else "#F44336"
                    
                    scenario_text = ""
                    if activar_escenario:
                        scenario_text = f"**⚠️ Impacto del Escenario Personalizado**: Al forzar el crecimiento a **{growth_forzado:.1%}** y reducir los márgenes operativos un **{castigo_margen:.1%}** (durante los años {rango_años[0]} a {rango_años[1]}), el modelo asume que la empresa perdió su 'ventaja competitiva' temporalmente (ej. por pérdida de retención o problemas legales). Esta caída inicial no se recupera mágicamente, sino que arrastra una menor generación de dinero en efectivo durante toda la década, castigando drásticamente su valor a largo plazo."
                    
                    st.markdown(f"""
Para generar estos **{n_sims:,} caminos posibles**, el sistema no lanza números al azar, sino que toma en cuenta factores comerciales del mundo real con mucha precaución:

*   **Efectivo Real vs Ganancias de Papel**: El modelo repudia las "ganancias netas" contables clásicas, que suelen ser engañosas. Nosotros proyectamos estrictamente el dinero libre en las cuentas. Restamos agresivamente lo que la empresa gasta en pagar a sus empleados con acciones propias (*Stock-Based Comp.*) y calculamos de forma realista cuánto tendrán que invertir obligatoriamente en infraestructura (CapEx) a medida que alcanzan su madurez de 10 años.
*   **El Riesgo Evoluciona Año a Año (Tasa de Descuento)**: Para penalizar el futuro, no usamos una tasa de riesgo estática convencional. Analizamos dinámicamente si la empresa empieza a asfixiarse en deuda frente a su patrimonio, calculamos el peso real de sus impuestos y los conectamos a las tasas de interés presentes de la FED. Si los niveles cruzan límites peligrosos, el modelo desploma el valor de la empresa automáticamente.
*   **Protección del Inversionista Final (Dilución y Recompras)**: El "Valor Justo" devuelto (${p50:.2f}) ya incluye un escudo preventivo. Matemáticamente asume la dilución de cuántas nuevas acciones podría emitir la empresa en el futuro, pero también te otorga un "beneficio compuesto" si la empresa tiene el hábito histórico comprobado de recomprar sus propias acciones en el mercado. Por último, para proyectar a qué precio te comprarían esta empresa en 10 años, el algoritmo ignora excesos de optimismo y usa métricas razonables estrictamente atadas al sector económico de **{ticker}**.

{scenario_text}

**Veredicto Práctico**: Tomando en cuenta todos los filtros de seguridad anteriores, la diferencia entre su precio actual en la bolsa (\${current_price:.2f}) y el precio de equilibrio más probable que defiende el modelo (Valor Justo P50: **\${p50:.2f}**), sugiere de forma concluyente que la acción está <span style='color:{color_val}; font-weight:bold;'>{estado_val} en un {abs(implied_spot):.2%}</span>. En caso de una recesión severa o colapso del negocio durante varios años (Percentil 10 pesimista), su valor intrínseco fundamental caería pero debería frenarse orgánicamente cerca de los **\${p10:.2f}**.
                    """, unsafe_allow_html=True)

            except Exception as e:
                error_msg = str(e)
                if "curl: (56) Recv failure" in error_msg or "Connection was reset" in error_msg:
                    st.error("⚠️ Error de red con Yahoo Finance (Connection Reset). Es un bloqueo temporal del servidor. Por favor, presiona 'Ejecutar' nuevamente.")
                else:
                    st.error(f"Error en la simulación: {error_msg}")
