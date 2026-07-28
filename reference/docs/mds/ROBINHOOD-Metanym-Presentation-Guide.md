# Notebook Build Audit & Execution System — Guía de Presentación

> **Propósito:** Guía de acompañamiento para la presentación Beamer.
> Expande cada slide con contexto, fundamentos, implicaciones, y preguntas para discusión.
> Basado exclusivamente en los temas cubiertos en `NotebookBuildAudit-Presentation.tex`.

---

## Índice

1. [El Problema: Notebooks en Producción](#1-el-problema-notebooks-en-producción)
2. [Dos Frameworks Complementarios](#2-dos-frameworks-complementarios)
3. [Construction Framework — Tres Fases](#3-construction-framework--tres-fases)
4. [LLM-as-a-Judge — Dos Capas de Evaluación](#4-llm-as-a-judge--dos-capas-de-evaluación)
5. [ROBIN-HOOD — El Algoritmo](#5-robin-hood--el-algoritmo)
6. [ROBIN-HOOD — Aplicación al Six-Pass Audit](#6-robin-hood--aplicación-al-six-pass-audit)
7. [The Metanym Game — SVD y el Descubrimiento](#7-the-metanym-game--svd-y-el-descubrimiento)
8. [Multi-Judge Budget Allocation](#8-multi-judge-budget-allocation)
9. [Panel Architecture — Unificando los Hallazgos](#9-panel-architecture--unificando-los-hallazgos)
10. [Prompt Crafting — Estructura de Tres Niveles](#10-prompt-crafting--estructura-de-tres-niveles)
11. [Six-Pass Audit Protocol](#11-six-pass-audit-protocol)
12. [Arquitectura del Sistema](#12-arquitectura-del-sistema)
13. [Cost Analysis & ROI](#13-cost-analysis--roi)
14. [LLMOps Pipeline](#14-llmops-pipeline)
15. [Papers Comparison](#15-papers-comparison)
16. [Resource Costs](#16-resource-costs)
17. [Timeline & Roadmap](#17-timeline--roadmap)
18. [Discussion Points](#18-discussion-points)
19. [Referencias](#19-referencias)

---

## 1. El Problema: Notebooks en Producción

### El contexto

Los Jupyter Notebooks son el medio dominante en DS/ML por una razón: permiten exploración interactiva, visualización inmediata, y narrativa entre celdas de código. Pero esa misma flexibilidad los hace peligrosos fuera de un entorno controlado.

### Los tres riesgos sistémicos

**1. Ejecución no confiable (Untrusted Execution)**
- Notebooks de colaboradores, open-source, o generados por IA assistants
- Sin garantías deterministas de seguridad
- ¿Qué pasa si una celda descarga un modelo de una fuente no verificada?
- ¿Qué pasa si una celda ejecuta un comando shell sin sanitización?

**2. Falta de builds deterministas**
- Pinned dependencies inconsistentes o ausentes
- Seeds no controlados → resultados diferentes en cada máquina
- Entorno implícito (lo que está instalado en el kernel) vs explícito (requirements.txt)
- El clásico "works on my machine" pero versión notebook

**3. Ausencia de protocolo de auditoría estructurado**
- Code review tradicional asume archivos lineales, funciones puras
- Notebooks tienen estado oculto, orden de ejecución no lineal, y outputs inline
- No hay metodología sistemática para revisar notebooks antes de producción/publicación

### La cita clave

> "Existing code review practices are insufficient for the unique failure modes of notebook-based ML pipelines."

Esto no es una opinión — es la tesis central del sistema. El code review tradicional busca bugs lógicos. Un notebook necesita auditoría de *reproducibilidad, integridad de datos, correctness metodológica, y deployment readiness*.

---

## 2. Dos Frameworks Complementarios

### La dinámica

```
Construction → produce → Notebook → analiza → Audit → Weakness Diagnosis
     ↑                                                   |
     └───────────────── feedback ────────────────────────┘
```

No son dos sistemas separados — son dos caras del mismo ciclo de vida.

### Construction Framework (Forward-looking)

**Rol:** Prescriptivo. Guía al autor para construir un notebook bien estructurado desde cero.

**Preguntas que responde:**
- ¿Cómo organizo las secciones?
- ¿Cómo aseguro reproducibilidad desde el inicio?
- ¿Cómo documento decisiones a medida que codifico?
- ¿Cómo gestiono artifacts de salida?

**Cuándo se usa:** Cuando el notebook todavía no existe. El autor sigue la guía de construcción.

### Audit Framework (Backward-looking)

**Rol:** Diagnóstico. Evalúa sistemáticamente calidad, corrección, y riesgo de un notebook existente.

**Preguntas que responde:**
- ¿Este notebook es reproducible?
- ¿Los datos están correctamente separados (train/test/validation)?
- ¿La metodología ML es sólida?
- ¿Está listo para deploy?

**Cuándo se usa:** Antes de merge, publicación, o producción. El revisor ejecuta el protocolo.

### Feedback loop

Los hallazgos del Audit retroalimentan al Construction Framework — si un patrón de error aparece recurrentemente, la guía de construcción se actualiza para prevenirlo.

---

## 3. Construction Framework — Tres Fases

### Fase 1: Scaffold (Andamio)

El 80% de la calidad de un notebook se define antes de escribir la primera línea de código.

**Single Responsibility:** Cada notebook debe hacer UNA cosa. Si estás haciendo EDA + feature engineering + model training + deployment analysis, necesitás cuatro notebooks.

**8 Secciones Canónicas:**
1. Título y propósito
2. Setup del entorno
3. Carga de datos
4. Exploración y preprocesamiento
5. Feature engineering
6. Modelado
7. Evaluación
8. Conclusiones y artifacts

**Pin environment upfront:** Antes de cualquier `import`, fijar:
- Versión de Python
- Dependencias con hash (pip freeze o conda export)
- Seeds globales (`random.seed`, `np.random.seed`, `tf.random.set_seed`)

**Controles globales de reproducibilidad:**
- `os.environ['PYTHONHASHSEED']`
- `torch.backends.cudnn.deterministic = True`
- Deterministic algorithms flag

### Fase 2: Write (Escritura)

Una vez que el scaffold está armado, se escribe una sección a la vez.

**Markdown intent per code cell:** Cada celda de código debe tener una celda markdown antes explicando QUÉ va a hacer y POR QUÉ. No es comentario — es narrativa.

```markdown
## Limpieza de outliers en temperatura
Usamos IQR porque la distribución es asimétrica.
Descarte: valores fuera de Q1 - 1.5*IQR o Q3 + 1.5*IQR.
```

**Explicit variable passing:** No usar variables globales implícitas entre secciones. Cada sección recibe inputs explícitos y produce outputs explícitos. Si una sección necesita `df` de la sección anterior, que sea un parámetro, no una variable en el namespace global.

**Three-block refactor threshold:** Si una sección tiene más de 3 bloques de código seguidos sin markdown intermedio, es señal de que necesita refactorizarse en funciones o dividirse.

### Fase 3: Validate (Validación)

**Restart kernel per section:** Cada sección debería poder ejecutarse independiente si recibe los inputs correctos. Esto detecta dependencias ocultas.

**Cell idempotency check:** Ejecutar la misma celda dos veces debe dar el mismo resultado. Si no es así (acumulación, appends), hay un problema.

**Linear execution order:** El notebook debe ejecutarse en orden lineal, de arriba a abajo, sin saltos. Si el autor desarrolló en desorden (como suele pasar), el validate lo detecta.

**Versioned artifact routing:** Los modelos, gráficos, y tablas generados deben tener versiones y rutas predecibles, no archivos sueltos con nombres como `model_final_v3_real_final.pkl`.

---

## 4. LLM-as-a-Judge — Dos Capas de Evaluación

### ¿Por qué usar LLMs para evaluar?

Porque la auditoría de notebooks combina dos tipos de tareas:

| Tipo | Característica | Qué evaluar |
|------|---------------|-------------|
| **Determinista** | Binaria, reproducible | Dependencias, split, seeds, artifacts |
| **Semántica** | Requiere razonamiento | Documentación, coherencia, metodología |

Ningún chequeo programático puede evaluar si la *narrativa* del notebook es coherente. Y ningún LLM puede verificar *determinísticamente* si los seeds están bien puestos.

### Layer 1: Deterministic

Chequeos programáticos, 100% reproducibles, sin LLM.

- **Dependency validation:** ¿Están todas las dependencias declaradas? ¿Hay imports sin el package en requirements?
- **Execution reproducibility:** ¿El notebook corre de principio a fin sin errores? ¿Los seeds producen los mismos resultados?
- **Train/test split verification:** ¿Hay leakage? ¿El split es anterior a cualquier transformación?
- **Artifact existence:** Los archivos que el notebook dice generar, ¿existen realmente?

### Layer 2: LLM Judge

Evaluación semántica mediante prompts estructurados.

- **Documentation quality:** ¿Cada decisión tiene justificación? ¿El markdown explica el qué y el por qué?
- **Conceptual coherence:** ¿La narrativa del notebook es lógica? ¿Las conclusiones se siguen de los resultados?
- **Methodological soundness:** ¿La técnica estadística/ML es apropiada para el problema?
- **Deployment readiness:** ¿Faltan archivos de configuración? ¿Hay paths hardcodeados?

### G-Eval

El insight clave es descomponer la evaluación en criterios explícitos, como hace G-Eval (Liu et al., 2023). En lugar de preguntar "¿este notebook es bueno?", se pregunta por cada criterio específico y se agrega.

### Bias conocidos

- **Position bias:** El LLM tiende a favorecer lo que ve primero
- **Verbosity bias:** Texto más largo obtiene mejores puntuaciones aunque no sea mejor
- **Self-enhancement bias:** El LLM prefiere texto que se alinea con su propio estilo de escritura

---

## 5. ROBIN-HOOD — El Algoritmo

### Paper de referencia

Saha, Wagde & Kveton (2026). *LLM-as-Judge on a Budget.* arXiv:2602.15481.

### El problema matemático

Tenés $K$ items para evaluar y un presupuesto de $B$ queries de LLM. Si evaluás cada item el mismo número de veces, gastás $B$ queries pero podés estar desperdiciando presupuesto en items que ya son estables y quedándote corto en items controversiales.

**Formalmente:** Querés minimizar el error de estimación del score promedio de cada item, dado un presupuesto fijo de queries.

### La intuición

Algunos items son *fáciles* — todos los jueces coinciden. Otros son *difíciles* — hay desacuerdo. En vez de gastar el mismo presupuesto en todos, ROBIN-HOOD mide la varianza y concentra queries donde la incertidumbre es mayor.

Como Robin Hood: le saca queries a los items estables (los "ricos" en información) y se las da a los items inestables (los "pobres").

### El algoritmo paso a paso

```
1. Evaluar cada item UNA vez (seed inicial)
2. Para cada item i, computar:
   - μ_i = score promedio
   - σ²_i = varianza de los scores
   - n_i  = número de evaluaciones hasta ahora
3. Calcular priority score: p_i = σ²_i / n_i
4. Asignar la próxima query al item con mayor p_i
5. Recomputar μ_i, σ²_i, n_i
6. Repetir hasta agotar presupuesto B
```

### La garantía teórica

$$ \tilde{O}\!\left(\sqrt{\frac{\sum_{i=1}^K \sigma_i^2}{B}}\right) $$

Esto significa que el error decrece con la raíz cuadrada de la *varianza total* sobre el *presupuesto*. Comparado con allocation uniforme, ROBIN-HOOD alcanza la misma precisión con aproximadamente la mitad de queries.

### Resultados empíricos

- **Summarize-From-Feedback (SFF):** Benchmark de evaluación de summaries
- **HelpSteer2:** Benchmark de helpfulness
- En ambos: misma precisión que uniforme con ~50% menos queries

### Por qué funciona

ROBIN-HOOD es esencialmente un algoritmo de *multi-armed bandit* pero al revés: en lugar de explotar el brazo con mayor recompensa, explora el brazo con mayor incertidumbre. Es *exploration-driven* en vez de *exploitation-driven*.

---

## 6. ROBIN-HOOD — Aplicación al Six-Pass Audit

### Diferentes passes, diferentes varianzas

No todos los passes de auditoría son igual de difíciles:

| Pass | Tipo | Varianza esperada | Prioridad ROBIN-HOOD |
|------|------|-------------------|---------------------|
| 1 — Structural Overview | Fácil | Baja | Low |
| 2 — Reproducibility Check | Fácil | Baja | Low |
| 3 — Data Integrity Review | Medio | Media | Medium |
| 4 — ML Correctness Audit | Difícil | Alta | High |
| 5 — Code Quality Review | Medio | Media | Medium |
| 6 — Deployment Readiness | Difícil | Alta | High |

### Implicación

Con allocation uniforme, cada pass recibiría el mismo número de queries de LLM. Pero Pass 1 (structural overview) es rutinario — mirar secciones, verificar estructura. Pass 4 (ML correctness) es donde está el riesgo real: leakage, data contamination, métricas incorrectas.

ROBIN-HOOD asigna dinámicamente más presupuesto a Passes 4 y 6, y menos a 1 y 2. El resultado: misma precisión general con ~50% menos queries totales.

### El principio

> "Unevaluated variance wastes budget. Measure it — then allocate."

Si no medís la varianza, estás asignando a ciegas. ROBIN-HOOD hace que el presupuesto refleje la dificultad real de cada evaluación.

---

## 7. The Metanym Game — SVD y el Descubrimiento

### Paper de referencia

Nordfors, D. (2026). *The Metanym Game: A Self-Contained, Self-Consistent LLM Peer-Community Benchmark for Structural Intelligence.* arXiv:2606.21008.

### ¿Qué es Metanym Game?

Es un juego de palabras competitivo donde LLMs generan y evalúan analogías. Un jugador propone una analogía (ej: "árbol es a bosque como molécula es a ___") y otros jugadores la evalúan.

**Propiedad clave:** No hay test set fijo. Las analogías se generan en el momento. Esto lo hace inherentemente resistente a *contamination* (data leakage de benchmarks).

### SVD sobre la matriz de ratings

Con $K$ modelos (cada uno actúa como generador y como juez):

1. Cada modelo genera $N$ analogías
2. Cada modelo evalúa las analogías de los demás
3. Se construye una matriz $K \times K$ de ratings
4. Singular Value Decomposition (SVD) revela componentes latentes

### Los dos hallazgos fundamentales

**Hallazgo 1 — Correlación factual r = 0.92 con GPQA Diamond**
GPQA Diamond es un benchmark de razonamiento científico con ground truth. Metanym Game correlaciona con él en 0.92 *sin usar ningún dato etiquetado*. Esto sugiere que el juego captura una señal genuina de inteligencia estructural.

**Hallazgo 2 — Dissociation Gen ≠ Eval (CRÍTICO)**
El SVD revela que generar analogías y evaluar analogías son habilidades *disociadas*. El mejor generador es un evaluador mediocre. El juez más agudo es un generador de medio pelo.

### Implicación arquitectónica

> **Never assume the same model excels at both tasks.**

Esto tiene impacto directo en diseño de sistemas multi-judge: no podés asumir que un modelo que es bueno generando respuestas (como GPT-5 en chat) va a ser bueno evaluando respuestas. Necesitás modelos especializados para cada rol, y necesitás medir ambas habilidades por separado.

---

## 8. Multi-Judge Budget Allocation

### Paper de referencia

No identificado por nombre, referido como "Paper 2" — *Instance-Optimal Estimation with Multiple LLM Judges on a Budget*.

### Extensión de ROBIN-HOOD

ROBIN-HOOD original asume un solo juez (o todos los jueces iguales). Multi-Judge extiende al caso realista donde hay múltiples modelos disponibles, cada uno con **costo y precisión diferentes**.

### El espacio de decisión se duplica

Ya no es solo **cuántas queries** por item (ROBIN-HOOD original), sino también **qué juez** usar para cada query:

| Decisión | ROBIN-HOOD | Multi-Judge |
|----------|-----------|-------------|
| Qué items evaluar | ✓ | ✓ |
| Cuántas veces | ✓ | ✓ |
| Qué juez usar | — | ✓ |

### Regla de oro

- **Jueces baratos** (Gemini-2.5 Flash, Llama-3 8B): para items fáciles con baja varianza
- **Jueces caros** (GPT-5, Claude Opus): reservados para items difíciles con alta varianza
- **Repetir solo cuando la incertidumbre es alta:** si un item ya converge, no seguir preguntando

### Resultado teórico

El paper demuestra *instance-optimality*: ninguna otra estrategia puede lograr menor error con el mismo presupuesto. En muchos casos, asignar **un solo juez bien elegido** por item rinde mejor que combinar múltiples jueces en todos los items.

### Ejemplo práctico

| Tipo de pass | Juez recomendado | Costo relativo |
|-------------|-----------------|----------------|
| Pass 1-2 (fáciles) | Modelo local pequeño (Llama-3 8B) | $0.001/query |
| Pass 3-5 (medios) | Gemini-2.5 Pro | $0.01/query |
| Pass 4-6 (difíciles) | GPT-5 / Claude Opus | $0.05/query |

---

## 9. Panel Architecture — Unificando los Hallazgos

### La conclusión compartida

Ambos papers apuntan a la misma conclusión arquitectónica: **necesitamos un panel de jueces diversos, no un solo LLM.**

### Lo que cada paper aporta

| ROBIN-HOOD dice | Metanym Game dice |
|----------------|-------------------|
| Asignar budget por varianza | Usar modelos diversos |
| Concentrar en items difíciles | Gen ≠ Evaluators |
| Misma precisión, mitad de costo | Paneles superan a individuos |

### La arquitectura resultante

**Scheduler (ROBIN-HOOD)**
- Tracking de varianza por pass de auditoría
- Decide **cuántas** queries asignar a cada pass
- Algoritmo: priority = σ²_i / n_i

**Panel (Metanym-inspired)**
- Modelos: GPT-5, Claude, Gemini, Llama, Mistral
- Decide **qué modelo** usar para cada query
- SVD periódico para trackear competencia a lo largo del tiempo

### La división del trabajo

> ROBIN-HOOD decides quantity; the Panel decides quality.

Son dos problemas separados con dos algoritmos separados, pero se comunican: ROBIN-HOOD dice "necesito 3 evaluaciones más para Pass 4", el Panel dice "usá GPT-5 para la primera, Gemini para la segunda, Llama para la tercera".

---

## 10. Prompt Crafting — Estructura de Tres Niveles

### Niveles de profundidad

Los prompts de evaluación siguen la misma estructura que el audit protocol:

```
Level 1: Conceptual  ← Passes 1-2
    ↓
Level 2: Methodological  ← Passes 3-4
    ↓
Level 3: Implementation  ← Passes 5-6
```

### Gate 1 → 2: Decisión de continuar

**Input:** Resultados de Pass 1 (Structural Overview) y Pass 2 (Reproducibility)

**Pregunta:** El notebook corre end-to-end? Tiene un propósito coherente?

**Decisión:**
- ✓ Proceed → Nivel 2
- ⚠ Flag with caveats → Pasar con advertencias
- ✗ Block → Devolver al autor, no pasar a nivel metodológico

### Gate 2 → 3: Decisión metodológica

**Input:** Resultados de Pass 3 (Data Integrity) y Pass 4 (ML Correctness)

**Pregunta:** Hay methodological flaws? Data leakage? Invalid cross-validation?

**Decisión:**
- ✓ Proceed → Nivel 3
- ⚠ Halt with caveats → Pasar pero con riesgos documentados
- ✗ Block → No evaluar código ni deployment si la metodología está rota

### After Level 3

**Input:** Resultados de Pass 5 (Code Quality) y Pass 6 (Deployment Readiness)

**Output:** Reporte final con:
- Risk scores por cada uno de los 6 passes
- Resumen ejecutivo
- Recomendaciones accionables
- Score de deployment readiness

---

## 11. Six-Pass Audit Protocol

### La estrategia

```
Notebook Audit Strategy
├── Multi-Pass Incremental Analysis
├── Hierarchical Review Depth
├── Pattern Summarization with Thresholds
└── User-Guided Focus Areas (AI-assisted context)
```

### Level 1: Conceptual (Passes 1-2)

**Pass 1 — Structural Overview**
- ¿El notebook tiene secciones claras?
- ¿Cada sección tiene un propósito único?
- ¿Hay celdas huérfanas (sin markdown)?
- **Deliverable:** Mapa de secciones, red flags estructurales

**Pass 2 — Reproducibility Check**
- ¿Los seeds están fijados al inicio?
- ¿Las dependencias están pinneadas?
- ¿El kernel se puede reiniciar y ejecutar todo en orden?
- **Deliverable:** Reporte de reproducibilidad

### Level 2: Methodological (Passes 3-4)

**Pass 3 — Data Integrity Review**
- ¿Hay separación correcta train/test/validation?
- ¿Hay data leakage (información del futuro en el pasado)?
- ¿Los datos descriptos coinciden con los datos cargados?
- **Deliverable:** Pipeline data report, checklist de integridad

**Pass 4 — ML Correctness Audit**
- ¿La métrica de evaluación es apropiada para el problema?
- ¿El cross-validation está bien configurado?
- ¿Hay comparación justa entre modelos?
- ¿Hay overfitting evidente?
- **Deliverable:** Auditoría ML con findings

### Level 3: Implementation (Passes 5-6)

**Pass 5 — Code Quality Review**
- ¿Hay código duplicado o muerto?
- ¿Las funciones tienen responsabilidades claras?
- ¿Los nombres de variables son descriptivos?
- **Deliverable:** Code smell report

**Pass 6 — Deployment Readiness**
- ¿Hay paths hardcodeados?
- ¿Faltan archivos de configuración?
- ¿El modelo está serializado correctamente?
- ¿Hay instrucciones claras para deploy?
- **Deliverable:** Readiness score (0-100)

---

## 12. Arquitectura del Sistema

### Capa Conceptual

- **Construction ↔ Audit lifecycle:** El sistema no es solo auditoría — es un ciclo completo donde los hallazgos de audit retroalimentan la construcción
- **Three-level audit con HITL gates:** En cada gate hay decisión humana (Human-in-the-Loop): ¿seguimos, paramos, o continuamos con advertencias?
- **Provider-agnostic LLM layer:** El panel de jueces acepta cualquier proveedor (OpenAI, Anthropic, Google, Ollama local)

### Capa Lógica

| Componente | Rol |
|-----------|-----|
| **React + TypeScript Dashboard** | UI de usuario: ver notebooks, lanzar auditorías, ver resultados |
| **FastAPI REST + SSE Gateway** | Backend API con Server-Sent Events para progreso en vivo |
| **ROBIN-HOOD Scheduler** | Algoritmo de allocation de budget |
| **LLM Panel Proxy (Strategy Pattern)** | Proxy que selecciona qué modelo usar para cada query |
| **Audit State Machine** | Máquina de estados que trackea el progreso de cada auditoría |
| **@jupyter-kit Execution Engine** | Motor que ejecuta notebooks en sandbox |
| **PostgreSQL + SQLAlchemy** | Persistencia de sesiones, resultados, configuraciones |

### Capa Física

- **Docker Compose (5 servicios):** Dashboard, API, Scheduler, Execution Engine, Database
- **Sandbox efímero:** Cada auditoría de notebook se ejecuta en un contenedor temporal que se destruye al terminar
- **LLM local o cloud:** Ollama para local, OpenAI/Anthropic para cloud — intercambiables por configuración

---

## 13. Cost Analysis & ROI

### Costo mensual de inferencia

Para una carga de trabajo de **10,000 evaluaciones** (items) por mes:

| Estrategia | Queries/mes | Costo/mes | Precisión |
|-----------|------------|-----------|-----------|
| Uniforme (5 cada uno) | 50,000 | $1,500 | Alta |
| Uniforme (1 cada uno) | 10,000 | $300 | Baja |
| **ROBIN-HOOD** | ~15,000 | ~$450 | Alta |
| **ROBIN-HOOD + Panel** | ~12,000 | ~$350 | Alta |

### ROI anual

| Período | Sin ROBIN | Con ROBIN | Savings |
|---------|-----------|-----------|---------|
| Mes 1 | $1,500 | $1,000 + $500 dev | $0 |
| Mes 2 | $1,500 | $450 | **$1,050** |
| Anual | $18,000 | $11,400 | $6,600 |

- **ROI Año 1:** 37% (recuperás más de un tercio de la inversión en el primer año)
- **ROI Año 2+:** ~70%
- **A 100K items/mes:** ~$10K/mes en savings

### Nota sobre costos

Estos números asumen precios de API de LLM a mediados de 2026. Los costos reales dependen de:
- Proveedor y modelo elegido
- Cantidad de tokens por evaluación
- Descuentos por volumen
- Costo de infraestructura local si se usa Ollama

---

## 14. LLMOps Pipeline

### Monitoring & Observability

Trackeo continuo de:

- **Costo por pass y por modelo:** Saber exactamente cuánto gasta cada parte del sistema
- **Variance tracking por audit item:** Detectar qué items tienen varianza creciente
- **Judge competence drift:** Los modelos cambian con el tiempo (fine-tunes, nuevas versiones, concept drift). El SVD periódico detecta si un juez se está volviendo menos confiable.

### Feedback Loops

- **ROBIN-HOOD reasigna budget ante drift:** Si la varianza de un pass aumenta, recibe más queries automáticamente
- **El panel se rebalancea:** Si un modelo muestra competence drop, se le asignan menos queries
- **HITL triggers:** Cuando la varianza excede un umbral, se notifica a un humano
- **SVD recalibration periódico:** Re-evaluación periódica de la matriz de competencia

### CI/CD Integration

- **Nuevo modelo entra** → el panel lo evalúa automáticamente
- **Competence score** → decisión de deploy o reject
- **Score cae** → rollback automático + alerta

### Dashboard de métricas clave

- Query budget gastado por pass
- Reducción de varianza a lo largo del tiempo
- Matriz de precisión del panel de jueces
- Comparación de costos: ROBIN vs uniforme

---

## 15. Papers Comparison

### Tabla comparativa

| Aspecto | ROBIN-HOOD | Multi-Judge | Metanym Game |
|---------|-----------|-------------|-------------|
| Adaptive budget | ✓ | ✓ | — |
| Single judge | ✓ | ✓ | — |
| Multiple judges | — | ✓ | ✓ |
| Different judge costs | — | ✓ | — |
| Gen ≠ Eval dissociation | — | — | ✓ |
| Optimality guarantee | Partial | ✓ | — |
| Panel architecture | — | Implied | ✓ |

### Unified takeaway

> **ROBIN-HOOD** → decide quantity (cuántas queries por item).
> **Multi-Judge** → decide qué modelo usar para cada query.
> **Metanym Game** → prueba por qué necesitamos un panel diverso.
>
> Together: maximum precision at minimum cost.

Cada paper resuelve una parte del problema. ROBIN-HOOD sin Multi-Judge no aprovecha diferentes costos de modelos. Multi-Judge sin Metanym asume que un buen generador es un buen evaluador. Metanym sin ROBIN-HOOD no tiene mecanismo de asignación de presupuesto.

---

## 16. Resource Costs

### Costos computacionales (Q1)

| Item | USD |
|------|-----|
| Server PC | $1,000 |
| Hosting (3 meses) | $300 |
| **Total Q1** | **$1,300** |

**Development:** 8 semanas, 2 developers
**Total dev:** ~$5,000 USD (depende de tarifas locales)

### Energetic — Tercer Pilar Propuesto

**El problema:**
- LLM inference consume 0.01–0.1 kWh por pass
- Notebook execution suele ser ineficiente (celdas re-ejecutadas, loops sin vectorizar)
- ESG reporting es cada vez más requerido en organizaciones

**Compromiso propuesto — Pass 7 (optional):**
- Energy Impact Assessment como pass opcional
- Backends: RAPL (Intel), NVML (NVIDIA), powermetrics (Apple Silicon)
- Graceful degradation: si el backend no está disponible, se saltea con una nota
- No blocking: no bloquea el merge, pero queda registrado

---

## 17. Timeline & Roadmap

### Fases de desarrollo (8 semanas, 2 developers)

| Fase | Resumen | Duración |
|------|---------|----------|
| **1** | Dockerización, monorepo, sandbox, pinning de dependencias | 2 semanas |
| **2** | FastAPI REST + SSE, ROBIN-HOOD Scheduler, LLM Panel Proxy, Audit State Machine | 3 semanas |
| **3** | React dashboard, session management, live progress, risk visualization | 2 semanas |
| **4** | E2E testing, panel competence tracking, security review, documentation | 1 semana |

### Dependencias entre fases

- Fase 1 es requisito para todo lo demás (sin sandbox no hay ejecución segura)
- Fase 2 es el core del sistema (scheduler + panel + state machine)
- Fase 3 requiere Fase 2 (el dashboard necesita APIs)
- Fase 4 es hardening y puede empezar en paralelo con Fase 3 tardía

### Hitos clave

- **Semana 2:** Sandbox funcional, un notebook se ejecuta aislado
- **Semana 5:** Auditoría completa funcional via API (sin UI)
- **Semana 7:** Dashboard con visualización de resultados
- **Semana 8:** Release candidate, tests E2E, documentación

---

## 18. Discussion Points

Estas son las preguntas abiertas para discutir con el equipo/stackeholders:

### Provider Strategy

- **Local (Ollama) vs cloud (OpenAI/Anthropic) como default?**
  - Local: menor latencia, sin costo recurrente, privacidad total
  - Cloud: mejores modelos, menos mantenimiento, escalabilidad inmediata
  - Tradeoff: un sistema local-only no puede usar GPT-5 para los passes difíciles

- **Offline-first o híbrido?**
  - Offline-first: todos los modelos locales, cloud es opcional
  - Híbrido: automáticamente elige según disponibilidad y costo

### Pass 7 — Energy

- **Incluir desde Fase 2 como experimental?**
  - Ventaja: datos desde el día 1
  - Riesgo: complexity overhead en fases tempranas

- **Deferir a Fase 4?**
  - Ventaja: no distrae del core functionality
  - Riesgo: si ESG es requisito del cliente, hay que tenerlo antes

### Scope

- **Full 6-pass desde el día uno?**
  - Ventaja: evaluación completa desde el inicio
  - Riesgo: más features = más bugs = más tiempo

- **Start with Level 1 only?**
  - Ventaja: MVP rápido, validación temprana
  - Riesgo: el valor real está en Level 2-3

### Audience

- **Internal team only, or client-ready?**
  - Internal: menos pulido, más features, menos UI
  - Client-ready: UX pulida, documentación, onboarding

- **Academic publication use case?**
  - Requisitos adicionales: reproducibilidad certificada, citación de métodos

---

## 19. Referencias

1. Saha, A., Wagde, A., & Kveton, B. (2026). *LLM-as-Judge on a Budget.* arXiv:2602.15481.
   - Algoritmo ROBIN-HOOD para allocation adaptativa de presupuesto de evaluación
   - Garantía teórica: ~O(√(Σσ²/B))
   - Resultados empíricos en SFF y HelpSteer2

2. Nordfors, D. (2026). *The Metanym Game: A Self-Contained, Self-Consistent LLM Peer-Community Benchmark for Structural Intelligence.* arXiv:2606.21008.
   - Juego competitivo de analogías
   - SVD sobre matriz de ratings revela skills latentes
   - Correlación r=0.92 con GPQA Diamond
   - Hallazgo crítico: Gen ≠ Eval disociation

3. Liu, Y., et al. (2023). *G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment.*
   - Descomposición de evaluación en criterios explícitos
   - Base metodológica para los prompts estructurados de Layer 2

4. *Instance-Optimal Estimation with Multiple LLM Judges on a Budget.* (Paper 2, 2026).
   - Extensión multi-judge de ROBIN-HOOD
   - Instance-optimality guarantee
   - Estrategia: cheap judges para items fáciles, expensive para difíciles
