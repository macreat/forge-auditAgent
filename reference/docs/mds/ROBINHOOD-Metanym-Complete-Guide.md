# Notebook Build Audit & Execution System — Guía Completa

> **Propósito:** Guía de acompañamiento para el documento completo `NotebookBuildAudit-Complete.tex`.
> Expande cada sección con fundamentos, implicaciones, decisiones de diseño, y contexto.
> Basado exclusivamente en las 4 partes del documento unificado (Construcción + Auditoría + Arquitectura + Costos + Energía).

---

## Índice

- [Parte I — Codificar Experiencia Humana](#parte-i--codificar-experiencia-humana)
  - [1. El Desafío](#1-el-desafío)
  - [2. Notebook Construction Framework](#2-notebook-construction-framework)
    - [2.1 Fase 1 — Scaffold](#21-fase-1--scaffold)
    - [2.2 Fase 2 — Write](#22-fase-2--write)
    - [2.3 Fase 3 — Validate During Writing](#23-fase-3--validate-during-writing)
  - [3. LLM-as-a-Judge como Paradigma de Evaluación](#3-llm-as-a-judge-como-paradigma-de-evaluación)
    - [3.1 Motivación](#31-motivación)
    - [3.2 Evaluación Determinista vs LLM Judge](#32-evaluación-determinista-vs-llm-judge)
    - [3.3 Budget-Aware Allocation (ROBIN-HOOD)](#33-budget-aware-allocation-robin-hood)
    - [3.4 Prompt Engineering como Diseño del Juez](#34-prompt-engineering-como-diseño-del-juez)
    - [3.5 Limitaciones Conocidas](#35-limitaciones-conocidas)
    - [3.6 La Disociación Generación–Evaluación (Metanym Game)](#36-la-disociación-generación-evaluación-metanym-game)
    - [3.7 Posición dentro de Este Trabajo](#37-posición-dentro-de-este-trabajo)
    - [3.8 Extensiones Informadas por Avances Recientes](#38-extensiones-informadas-por-avances-recientes)
  - [4. Prompt Crafting — Codificando Conocimiento Experto](#4-prompt-crafting--codificando-conocimiento-experto)
    - [4.1 Estructura de Tres Niveles](#41-estructura-de-tres-niveles)
    - [4.2 Progresión de Iteraciones (Laps)](#42-progresión-de-iteraciones-laps)
    - [4.3 Nivel 1 — Conceptual Purpose](#43-nivel-1--conceptual-purpose)
    - [4.4 Nivel 2 — Methodological Purpose](#44-nivel-2--methodological-purpose)
    - [4.5 Nivel 3 — Implementation Purpose](#45-nivel-3--implementation-purpose)
    - [4.6 Weighted Evaluation Dimensions](#46-weighted-evaluation-dimensions)
  - [5. Audit Framework — Validación Human-in-the-Loop](#5-audit-framework--validación-human-in-the-loop)
    - [5.1 Tácticas Guía](#51-tácticas-guía)
    - [5.2 Six-Pass Audit Protocol](#52-six-pass-audit-protocol)
    - [5.3 Aplicando Ambos Frameworks](#53-aplicando-ambos-frameworks)
- [Parte II — Arquitectura](#parte-ii--arquitectura)
  - [6. Arquitectura Conceptual](#6-arquitectura-conceptual)
    - [6.1 Core Concepts](#61-core-concepts)
    - [6.2 Framework Feedback Loop](#62-framework-feedback-loop)
  - [7. Arquitectura Lógica](#7-arquitectura-lógica)
    - [7.1 Componentes del Sistema](#71-componentes-del-sistema)
    - [7.2 Key Architectural Decisions](#72-key-architectural-decisions)
  - [8. Arquitectura Física](#8-arquitectura-física)
    - [8.1 Deployment Topology](#81-deployment-topology)
    - [8.2 Resource Isolation](#82-resource-isolation)
    - [8.3 Provider Deployment Options](#83-provider-deployment-options)
- [Parte III — Costos Computacionales](#parte-iii--costos-computacionales)
  - [9. Infrastructure Costs](#9-infrastructure-costs)
    - [9.1 Hardware Requirements](#91-hardware-requirements)
    - [9.2 Deployment Cost Estimate](#92-deployment-cost-estimate)
  - [10. LLM Inference Costs](#10-llm-inference-costs)
  - [11. Development Investment](#11-development-investment)
    - [11.1 Team and Timeline](#111-team-and-timeline)
    - [11.2 Total Development Cost](#112-total-development-cost)
- [Parte IV — Costos Energéticos (Tercer Pilar)](#parte-iv--costos-energéticos-tercer-pilar)
  - [12. Motivación](#12-motivación)
  - [13. Fuentes de Energía en el Sistema](#13-fuentes-de-energía-en-el-sistema)
    - [13.1 Notebook Execution (Sandbox)](#131-notebook-execution-sandbox)
    - [13.2 LLM Inference (Audit Passes)](#132-llm-inference-audit-passes)
    - [13.3 Infrastructure Overhead](#133-infrastructure-overhead)
  - [14. Propuesta: Resource Efficiency como Tercer Pilar](#14-propuesta-resource-efficiency-como-tercer-pilar)
    - [14.1 Arguments For](#141-arguments-for)
    - [14.2 Arguments Against](#142-arguments-against)
    - [14.3 Compromiso: Optional Energy Module (Pass 7)](#143-compromiso-optional-energy-module-pass-7)
    - [14.4 Decision Framework](#144-decision-framework)
    - [14.5 Implementación de Pass 7](#145-implementación-de-pass-7)
- [15. Referencias Comentadas](#15-referencias-comentadas)

---

# Parte I — Codificar Experiencia Humana

> Tesis fundamental: la ingeniería rigurosa de notebooks requiere *codificar experiencia humana* en estructuras repetibles y verificables — y luego *validar* esas estructuras mediante un protocolo de auditoría sistemático con supervisión humana.

---

## 1. El Desafío

### El medio dominante

Los Jupyter Notebooks (`.ipynb`) se han convertido en el medio dominante para data science y machine learning. Su fortaleza — la fusión de código, resultados, visualizaciones y narrativa en un solo artifact — es también su mayor debilidad cuando se trata de producción, publicación o colaboración.

### Los tres riesgos sistémicos

**1. Ejecución no confiable (Untrusted Execution)**
- Los notebooks provienen de colaboradores externos, repositorios open-source, o generación asistida por IA
- No hay garantía determinista de que se ejecuten de forma segura o correcta
- Una celda maliciosa o con efectos secundarios no detectados compromete todo el pipeline

**2. Falta de builds deterministas**
- Environment pinning ad hoc o ausente
- Declaraciones de dependencias incompletas
- Seeds no controlados → resultados diferentes entre máquinas o sesiones
- Invalida cualquier pretensión de reproducibilidad científica

**3. Ausencia de protocolo de auditoría estructurado**
- Los equipos carecen de una metodología sistemática multi-pase para revisar notebooks
- Las prácticas de code review tradicional son insuficientes para los failure modes únicos de notebooks:
  - Data leakage a través del orden de preprocessing
  - Contaminación en cross-validation
  - Lógica de training/inference inseparable

### La solución propuesta

El **Notebook Build Audit & Execution System** aborda estos vacíos mediante dos frameworks acoplados:

| Framework | Dirección | Propósito |
|-----------|-----------|-----------|
| **Construction** | Forward-looking (prescriptivo) | Guía al autor para producir artifacts bien estructurados |
| **Audit** | Backward-looking (diagnóstico) | Evalúa sistemáticamente debilidades en notebooks existentes |

---

## 2. Notebook Construction Framework

### Filosofía

Forward-looking prescription. Organizado en tres fases secuenciales que codifican la experiencia humana sobre *cómo construir notebooks rigurosos* en un proceso repetible.

```
Notebook Construction Strategy
├── Modular Section Design
├── Reproducibility Standards (seeds, environments)
├── Narrative Documentation Guidelines
└── Output Artifact Management
```

### 2.1 Fase 1 — Scaffold

Establecer la base estructural y de reproducibilidad **antes** de escribir cualquier lógica.

#### Single Responsibility

Un notebook = un workflow o experimento coherente. Si estás haciendo EDA + feature engineering + model training + deployment analysis, necesitás cuatro notebooks separados.

#### 8 Secciones Canónicas

El orden importa — cada sección presupone que las anteriores ya se ejecutaron:

| # | Sección | Propósito |
|---|---------|-----------|
| 1 | Environment & Dependencies | Pinned environment, imports |
| 2 | Configuration & Global Parameters | Seeds, paths, hyperparams |
| 3 | Data Ingestion | Carga, validación inicial |
| 4 | Preprocessing & Feature Engineering | Transformaciones, splits |
| 5 | Model Definition & Training | Arquitectura, entrenamiento |
| 6 | Evaluation & Metrics | Métricas, validación |
| 7 | Artifact Export | Modelos, plots, reportes |
| 8 | Conclusions & Next Steps | Interpretación, acciones |

#### Reproducibilidad desde el inicio

- Pin del environment vía `requirements.txt`, `conda.yaml`, o `pyproject.toml`
- Seeds globales: `random.seed()`, `np.random.seed()`, `tf.random.set_seed()`
- Flags deterministas: `torch.backends.cudnn.deterministic = True`
- `os.environ['PYTHONHASHSEED']` para hash determinista

### 2.2 Fase 2 — Write

Escribir cada sección incrementalmente con reglas de disciplina.

**One section at a time:** Principio de Divide and Conquer. No saltar entre secciones.

**Markdown intent per code cell:** Cada celda de código debe tener una celda markdown antes explicando QUÉ va a hacer y POR QUÉ. No es un comentario — es narrativa.

**Explicit variable passing:** Preferir paso explícito de variables sobre estado global o implícito. Si una sección necesita `df` de la anterior, debe ser un parámetro, no una variable en el namespace global.

**Three-block refactor threshold:** Tres o más bloques de código similares deben refactorizarse en una función o loop. Si hay más de 3 bloques seguidos sin markdown intermedio, es señal de refactor.

**Versioned artifact routing:** Todos los outputs (modelos, plots, reportes) deben usar una convención de exportación única y versionada definida al inicio de la sección. Nunca escribir artifacts ad hoc desde celdas arbitrarias.

### 2.3 Fase 3 — Validate During Writing

Verificar continuamente la corrección a medida que se completa cada sección.

**Restart kernel per section:** Al terminar una sección, reiniciar el kernel y ejecutar todas las celdas. Esto detecta dependencias ocultas entre secciones.

**Cell idempotency check:** Cada celda debe producir el mismo resultado al ejecutarse independientemente. Si una celda acumula resultados (e.g., `list.append` en un loop que crece con cada ejecución), no es idempotente.

**Linear execution order:** El orden de ejecución debe ser estrictamente lineal, de arriba a abajo. No debe haber celdas que solo funcionan si se ejecutan en un orden específico no lineal.

**Output location check:** Confirmar que los artifacts exportados caen en la ubicación designada con la convención de naming esperada.

> La experiencia codificada — disciplina de secciones, higiene de reproducibilidad, validación incremental — es el expertise que el autor trae a cada nuevo notebook. El Construction Framework simplemente lo hace explícito y repetible.

---

## 3. LLM-as-a-Judge como Paradigma de Evaluación

### 3.1 Motivación

El framework de auditoría propuesto sigue el paradigma emergente **LLM-as-a-Judge (LAJ)** (Zheng et al., 2023), donde un modelo de lenguaje poderoso evalúa los outputs de otro modelo (o de sí mismo bajo prompting controlado).

**¿Por qué LAJ para notebooks?**

Porque muchos criterios de evaluación — claridad del código, coherencia lógica, calidad de documentación, solidez metodológica — no pueden medirse con métricas deterministas tradicionales como BLEU o ROUGE.

**Hallazgo clave:** Modelos de lenguaje suficientemente capaces alcanzan concordancia con evaluadores humanos comparable a la concordancia inter-humana al juzgar respuestas abiertas.

### 3.2 Evaluación Determinista vs LLM Judge

El framework adopta una estrategia de evaluación en **dos capas**:

#### Capa 1 — Deterministic Verification (siempre que sea posible)

Cuando la corrección puede establecerse objetivamente, se prefiere evaluación determinista:

| Tarea | Método | Resultado |
|-------|--------|-----------|
| Notebook execution exitosa | Ejecutar end-to-end | Pass/Fail |
| Dependency resolution | Verificar imports contra requirements | Pass/Fail |
| Version pinning | Inspeccionar archivos de entorno | Pass/Fail |
| Artifact generation | Verificar existencia de archivos | Pass/Fail |
| Reproducibility checks | Re-ejecutar con mismos seeds | Pass/Fail |

Estas evaluaciones son binarias y perfectamente reproducibles.

#### Capa 2 — LLM-as-a-Judge (solo para evaluación semántica)

Solo después de completar los checks deterministas se invoca un LLM judge:

| Tarea | Naturaleza |
|-------|------------|
| Organización estructural | Evaluación semántica |
| Readability | Evaluación semántica |
| Consistencia metodológica | Evaluación semántica |
| Calidad de explicaciones de código | Evaluación semántica |
| Recomendaciones de deployment | Evaluación semántica |

### 3.3 Budget-Aware Allocation (ROBIN-HOOD)

**El problema práctico:** Los juicios LLM son estocásticos — consultar el mismo par múltiples veces produce scores diferentes debido al sampling aleatorio. La varianza del score es altamente heterogénea:

- Un check factual como "dependency resolution" puede tener varianza cercana a cero
- Una evaluación subjetiva como "methodological soundness" puede variar significativamente

Dado un presupuesto fijo de $B$ queries distribuidas entre $K$ pares de evaluación, la asignación óptima no es trivial.

**Formalización (Saha, Wagde & Kveton, 2026):**

Cada par de evaluación es un brazo (arm) con media $s_i$ desconocida y varianza $\sigma_i^2$ desconocida. El objetivo es minimizar el error de estimación worst-case $\max_i |s_i - \hat{s}_i|$ bajo presupuesto $B$.

**ROBIN-HOOD** asigna queries dinámicamente basándose en las varianzas estimadas:

1. Evaluar cada par una vez
2. Computar media $\mu_i$ y varianza $\sigma^2_i$ por par
3. Asignar siguiente query al par con mayor $\sigma^2_i / n_i$
4. Recomputar estadísticas
5. Repetir hasta agotar $B$

**Garantía:** Error worst-case de $\tilde{O}\big(\sqrt{\sum_i \sigma_i^2 / B}\big)$ con asignación near-optimal. Experimentos en *HelpSteer2* muestran que iguala la precisión de asignación uniforme con **la mitad del presupuesto**.

**Relevancia directa:** El protocolo de 6 passes contiene passes de baja varianza (Structural Overview, Reproducibility Check) y passes de alta varianza (ML Correctness Audit, Deployment Readiness). Un sistema productivo debería ponderar su presupuesto de queries LLM hacia los passes donde la evaluación es más incierta.

### 3.4 Prompt Engineering como Diseño del Juez

**Principio G-Eval (Liu et al., 2023):** Un LLM judge es tan confiable como su protocolo de evaluación.

Los prompts presentados en este trabajo **no** piden al modelo un score holístico único. En su lugar, cada prompt descompone la evaluación del notebook en criterios explícitos:

En lugar de preguntar:

> "¿Este notebook es bueno?"

El evaluador es instruido para inspeccionar dimensiones predefinidas:
- Reproducibilidad
- Integridad de datos
- Corrección metodológica
- Calidad de implementación
- Deployment readiness

Los reportes estructurados resultantes se asemejan a checklists de peer-review formal en lugar de opiniones libre-forma, mejorando la consistencia entre evaluaciones.

**Esto motiva directamente la jerarquía de prompts progresivos:** desde inspección gruesa hasta auditoría multi-pase estructurada.

### 3.5 Limitaciones Conocidas

Aunque los LLM judges muestran fuerte concordancia con evaluadores humanos, son susceptibles a sesgos sistemáticos:

| Sesgo | Descripción | Impacto |
|-------|-------------|---------|
| **Position bias** | Preferencia por el primer candidato presentado | Infla scores del primer pass |
| **Verbosity bias** | Respuestas más largas reciben scores más altos | Favorece notebooks verbosos |
| **Self-enhancement bias** | Modelos puntúan mejor sus propias generaciones | Infla auto-evaluaciones |
| **Reasoning limitations** | Calidad de evaluación disminuye cuando el juez debe resolver problemas difíciles | Falsos negativos en passes complejos |

**Cómo los aborda el framework:**

1. Descomposición en múltiples audit passes
2. Criterios de evaluación explícitos (no scores holísticos)
3. Preferencia por verificación determinista siempre que sea posible
4. Evitación de scores de calidad únicos y globales

> El LLM no es tratado como un oráculo. Es un revisor estructurado que opera dentro de límites de evaluación claramente definidos.

### 3.6 La Disociación Generación–Evaluación (Metanym Game)

**Hallazgo fundamental (Nordfors, 2026):** Generar y evaluar son habilidades disociadas.

El **Metanym Game** es un benchmark peer-community donde LLMs crean contenido (analogías) y evalúan las creaciones de otros. La descomposición SVD de la matriz de ratings revela:

1. **Los mejores generadores son jueces mediocres** — producir contenido de alta calidad no implica habilidad para evaluarlo confiablemente

2. **Los mejores jueces son generadores de medio pelo** — la habilidad de evaluación es más escasa y parcialmente independiente de la capacidad generativa

3. **Correlación factual r = 0.92 con GPQA Diamond** — la descomposición espectral recupera habilidad de evaluación genuina, validada contra un benchmark con ground truth

**Implicación directa para auditoría de notebooks:**

Usar el mismo modelo LLM para generar reportes de auditoría (Passes 1–6) y para evaluar su propia corrección puede **conflar dos capacidades distintas**.

**Solución propuesta:** Siguiendo la propuesta de "jury" (Verga et al., 2024), emplear un **panel de modelos diversos** — algunos optimizados para razonamiento estructurado (Passes 3–4), otros para juicio estilístico (Passes 5–6) — y agregar sus evaluaciones para mitigar sesgos individuales.

### 3.7 Posición dentro de Este Trabajo

El framework de auditoría de notebooks debe interpretarse como una **instancia especializada del paradigma LLM-as-a-Judge**.

Su contribución principal **no es un nuevo modelo de evaluación**, sino un protocolo de auditoría estructurado que combina:

1. **Verificación determinista** siempre que exista corrección objetiva
2. **LLM judging con prompt engineering** para evaluación semántica
3. **Análisis incremental multi-pase** que refina progresivamente la evaluación mientras reduce la sobrecarga cognitiva

### 3.8 Extensiones Informadas por Avances Recientes

**Budget-aware query allocation (ROBIN-HOOD):**
Aborda la pregunta operativa crítica: dado un presupuesto fijo de queries LLM, ¿cómo distribuirlo entre los 6 passes para minimizar el error worst-case? Asignación variance-adaptativa supera significativamente a uniforme.

**Panel-based evaluation (jury):**
El Metanym Game demuestra que generar y evaluar están disociados. La propuesta de jury reemplaza un solo LLM judge con un **consejo de modelos diversos**. La arquitectura existente (patrón strategy `LLMProvider`) ya soporta esta extensión sin cambios estructurales.

---

## 4. Prompt Crafting — Codificando Conocimiento Experto

### 4.1 Estructura de Tres Niveles

Para operacionalizar los frameworks Construction y Audit a través de un LLM, el expertise humano debe codificarse en prompts estructurados que guíen el razonamiento del modelo.

```
Level 1: Conceptual  →  Passes 1-2 (Structural Overview + Reproducibility)
    ↓ Gate decision
Level 2: Methodological  →  Passes 3-4 (Data Integrity + ML Correctness)
    ↓ Gate decision
Level 3: Implementation  →  Passes 5-6 (Code Quality + Deployment)
```

### 4.2 Progresión de Iteraciones (Laps)

Los templates de prompt evolucionan a través de refinamientos sucesivos:

#### Lap 1 — Coarse Evaluation (Evaluación Gruesa)

Task statement amplio y no estructurado. Pide al LLM analizar el notebook holísticamente:
- Phase 1: documentation (propósito, descripciones de bloques de código, pseudocódigo para funciones complejas)
- Phase 2: critical audit (consistencia entre bloques, redundancia, lógica contradictoria, error handling)

Yield: decisión de gate inicial (proceed / flag / block).

#### Lap 2 — Refined Evaluation (Evaluación Refinada)

Introduce reglas estructurales:
- Block numbering: orden visual, no orden de ejecución
- Consolidación de imports en un solo bloque "Environment Setup"
- Filtrado de celdas markdown y celdas de error
- Formato de output explícito
- Template de extracción de 5 puntos: Logic Flow, Data Transformations, Model/Algorithm Operations, Key Variables/Parameters, Side Effects

#### Lap 3 — Structured Evaluation (Evaluación Estructurada)

Formaliza la jerarquía de 3 niveles como un mapeo determinista sobre el framework de 6 passes. Cada nivel tiene:
- Deliverables requirements específicos
- Gate decisions con criterios explícitos
- Scoring rubric por nivel

### 4.3 Nivel 1 — Conceptual Purpose

Determina si el notebook es coherente y re-ejecutable confiablemente antes de invertir tiempo en revisión profunda.

**Procedimiento:**
1. **Scope the audit** — Registrar focus areas o exclusiones especificadas por el usuario
2. **Map the structure** — Evaluar section headers, confirmar propósito único coherente, verificar orden de ejecución lineal
3. **Scan for immediate red flags** — Outputs faltantes, imports rotos, celdas huérfanas
4. **Check reproducibility inputs** — Dependency pinning, seed configuration global
5. **Check reproducibility risks** — Hardcoded paths, credenciales, assumptions de entorno

**Deliverables:**
- Section map
- Preliminary red flags list
- Recorded focus-area scope
- Reproducibility risk score (Low / Moderate / High)

**Gate decision:**
Si el notebook falla ejecución end-to-end o carece de propósito único coherente → decidir si proceder a Level 2 o marcar Level 1 como blocking.

### 4.4 Nivel 2 — Methodological Purpose

Evalúa la solidez científica del pipeline de datos y la metodología ML.

**Procedimiento:**
1. **Auditar el data pipeline:**
   - Train/test split ordering (¿el split es anterior a cualquier preprocessing?)
   - Data leakage detection (¿se escaló sobre el dataset completo?)
   - Missing-data consistency (¿se manejaron missing values de forma consistente entre splits?)
   - Type/shape validation at ingestion
2. **Auditar ML correctness:**
   - Metric appropriateness (¿la métrica es apropiada para el problema y la distribución de clases?)
   - Cross-validation integrity (¿CV aplicado correctamente sin leakage?)
   - Hyperparameter tuning boundaries (¿se usó solo validation data para tuning?)
   - Baseline comparison (¿el rendimiento está contextualizado contra un baseline significativo?)
3. **Cross-check across pipeline stages:**
   - Verificar que las transformaciones aplicadas durante preprocessing se reflejan correctamente en modelling y evaluation downstream

**Deliverables:**
- Data pipeline integrity report
- ML correctness checklist

**Gate decision:**
Si hay methodological flaws (leakage, CV inválido, misuse de métricas) → decidir si halt o proceed a Level 3 con caveats flagged.

### 4.5 Nivel 3 — Implementation Purpose

Evalúa maintainabilidad del código y suitability para producción.

**Procedimiento:**
1. **Code quality review:**
   - Repetitive blocks (three-block threshold)
   - Dead code, unused imports, redundant assignments
   - Meaningful and consistent variable/function naming
   - Bloated cell outputs
2. **Deployment readiness check:**
   - Versioned model artifact export
   - Separabilidad de lógica inference/training
   - Documentación de recursos (compute, memory)
   - Environment export completo y actualizado
   - Data privacy y PII handling

**Deliverables:**
- Code quality and smell report
- Deployment readiness score (Low / Moderate / High)

### 4.6 Weighted Evaluation Dimensions

Para auditorías externas (e.g., exportaciones markdown donde no se puede ejecutar el notebook), se usa un sistema de scoring multidimensional ponderado:

| Dimensión | Peso | Qué evalúa |
|-----------|------|-------------|
| **Reproducibility & Self-Containment** | 40% | Prioridad máxima. Declaraciones de dependencias, expectativas de output, placeholders |
| **Narrative & Structure** | 35% | Transiciones entre secciones, jerarquía de headings, identificación de audiencia, flujo de lectura |
| **Purpose & Depth** | 25% | Propósito primario explícito, camino de aprendizaje (tutorials), separación hipótesis–método–resultados (experimentos), outputs interpretables |

**Por qué esta ponderación:**
- La reproducibilidad es el requisito no negociable — si no se puede reproducir, el resto no importa
- La narrativa es crítica para comunicación y colaboración
- El propósito y profundidad son importantes pero secundarios a que el notebook funcione y se entienda

---

## 5. Audit Framework — Validación Human-in-the-Loop

### 5.1 Tácticas Guía

Antes de ejecutar los passes, el revisor emplea estas tácticas:

1. **Dividir el notebook en módulos lógicos**, priorizando bloques críticos del pipeline ML sobre celdas de exploración repetitivas
2. **Usar descripciones jerárquicas**: resúmenes de alto nivel primero, drill-downs después
3. **Resumir patrones de código repetitivos** en lugar de analizar cada uno individualmente
4. **Scopear el protocolo** a focus areas especificadas por el usuario cuando sea posible (e.g., "check only for data leakage")

### 5.2 Six-Pass Audit Protocol

Cada pass tiene un deliverable específico. Cuando el deliverable es un score, se usa una escala de 3 niveles:

| Score | Significado |
|-------|-------------|
| **Low Risk** | Pocos o ningún item sin resolver, todos menores |
| **Moderate Risk** | Varios items menores o 1-2 items significativos |
| **High Risk** | Items severos que requieren acción antes de proceder |

#### Pass 1 — Structural Overview

**Qué hace:** Establecer un mapa de alto nivel del notebook antes de examinar cualquier lógica.

**Checklist:**
- [ ] Focus areas o exclusiones del usuario registradas
- [ ] Section headers claros y navegables
- [ ] Propósito único coherente
- [ ] Orden de ejecución lineal y seguro
- [ ] Red flags visibles: outputs faltantes, imports rotos, celdas huérfanas

**Deliverable:** Section map, preliminary red flags list, recorded focus-area scope.

#### Pass 2 — Reproducibility Check

**Qué hace:** Evaluar si el notebook puede re-ejecutarse confiablemente.

**Checklist:**
- [ ] Dependency pinning (requirements.txt, conda.yaml, pyproject.toml)
- [ ] Seed configuration global y consistente
- [ ] Hardcoded file paths, credentials, environment assumptions flagged
- [ ] End-to-end runnability en un kernel fresco

**Deliverable:** Reproducibility risk score (Low / Moderate / High).

#### Pass 3 — Data Integrity Review

**Qué hace:** Examinar el pipeline de datos para detectar leakage y errores de integridad.

**Checklist:**
- [ ] Train/test split realizado **antes** de cualquier preprocessing
- [ ] Data leakage identificado (e.g., scaling fitted sobre dataset completo)
- [ ] Missing-data handling consistente entre splits
- [ ] Data type, shape y distribution validation en ingestion

**Deliverable:** Data pipeline integrity report.

#### Pass 4 — ML Correctness Audit

**Qué hace:** Evaluar la solidez de la metodología ML.

**Checklist:**
- [ ] Metric appropriateness para la tarea y distribución de clases
- [ ] Cross-validation aplicado correctamente sin leakage
- [ ] Hyperparameter tuning usa solo validation data
- [ ] Performance contextualizado contra un baseline significativo

**Deliverable:** ML correctness checklist.

#### Pass 5 — Code Quality Review

**Qué hace:** Evaluar maintainabilidad y claridad del código.

**Checklist:**
- [ ] Repetitive blocks que exceden el three-block threshold
- [ ] Dead code, unused imports, redundant assignments
- [ ] Variable/function naming significativo y consistente
- [ ] Cell outputs hinchados (bloated)

**Deliverable:** Code quality and smell report.

#### Pass 6 — Deployment Readiness

**Qué hace:** Determinar suitability para producción o publicación.

**Checklist:**
- [ ] Versioned model artifact export
- [ ] Lógica de inference y training separable
- [ ] Compute y memory constraints documentados
- [ ] Environment export completo y actualizado
- [ ] Data privacy y PII handling considerado

**Deliverable:** Deployment readiness score (Low / Moderate / High).

### 5.3 Aplicando Ambos Frameworks

| Contexto | Framework | Ciclo |
|----------|-----------|-------|
| Nuevo notebook o experimento | Construction | Forward |
| Restructurar notebook desorganizado | Construction | Forward |
| Crear template reusable | Construction | Forward |
| Revisar notebook de colaborador | Audit | Backward |
| Preparar para producción/publicación | Audit | Backward |
| Pre-merge o pre-deployment review | Audit | Backward |
| Authoring + self-review durante desarrollo | **Ambos** | Iterativo |
| Pair programming en tiempo real | **Ambos** | Iterativo |
| Refactorizar notebook preservando estructura | **Ambos** | Iterativo |

**El feedback loop:**

```
Construction Phase → produce notebook → Audit Phase → diagnostica debilidades
     ↑                                                      |
     └─────────── recomendaciones retroalimentan ────────────┘
```

Este cierre aplica a notebooks que comienzan en Building Phase. Para notebooks que entran vía audit-only, el loop permanece abierto a menos que el notebook sea revisado posteriormente.

---

# Parte II — Arquitectura

> Tres niveles de abstracción: conceptual (modelo mental), lógica (modelo de componentes), física (modelo de deployment).

---

## 6. Arquitectura Conceptual

### 6.1 Core Concepts

**1. Notebook Lifecycle**
Un notebook existe en uno de dos estados: under construction (authoring) o under audit (review). El feedback loop conecta ambos estados.

**2. Three-Level Audit Model**
El protocolo de 6 passes se agrupa en 3 niveles de profundidad creciente:
- **Nivel 1 — Conceptual:** ¿El notebook tiene sentido y es ejecutable?
- **Nivel 2 — Methodological:** ¿La ciencia es sólida?
- **Nivel 3 — Implementation:** ¿El código y el deployment son correctos?

Gate decisions entre niveles permiten terminación temprana cuando se encuentran issues bloqueantes.

**3. Human-in-the-Loop**
El sistema es **diagnóstico, no prescriptivo**. Cada gate decision y pass deliverable se presenta a un revisor humano que toma la decisión final. El LLM proporciona evidencia estructurada; el humano proporciona juicio.

**4. Provider Agnosticism**
La capa de orquestación LLM abstrae sobre proveedores locales (Ollama, llama.cpp) y cloud (OpenAI) mediante un patrón strategy, permitiendo que la misma lógica de auditoría funcione en entornos air-gapped o conectados.

### 6.2 Framework Feedback Loop

```
[Construction Framework] → produce → [Notebook Artifact]
                                           |
                                    [Audit Framework] → analiza
                                           |
                                    [Weakness Diagnosis]
                                           |
                                    feedback (dashed)
                                           ↓
                              (revised Construction)
```

La diagnosis de debilidades retroalimenta al Construction Framework, cerrando el ciclo.

---

## 7. Arquitectura Lógica

### 7.1 Componentes del Sistema

```
[React + TypeScript Dashboard]  ←→  [FastAPI REST + SSE Gateway]
                                          |
                +--------------------------+--------------------------+
                |                          |                          |
          LLM Orchestrator         Audit State Machine       Jupyter Exec. Engine
          (Provider Strategy)      (Six-Pass Protocol)       (@jupyter-kit Sandbox)
                |                          |                          |
          +-----+-----+            Audit Results DB           Docker Sandbox
          |           |            (PostgreSQL)               (per-notebook)
       Ollama      OpenAI
       (local)     (cloud)
```

#### Component Responsibilities

| Componente | Rol Técnico |
|------------|-------------|
| **React + TypeScript Dashboard** | SPA para gestión de sesiones de auditoría, upload de notebooks, configuración de providers, selección de scope de passes, visualización de progreso en vivo |
| **FastAPI REST + SSE Gateway** | Backend async-first con API REST para CRUD de sesiones y configuración. SSE endpoints para streaming de deliverables en tiempo real |
| **LLM Orchestrator (Provider Strategy)** | Implementa `LLMProvider` abstracto con implementaciones concretas para Ollama, llama.cpp, OpenAI. Selecciona provider en runtime según configuración |
| **Audit State Machine** | Cada auditoría modelada como máquina de estados: Scope → Pass1 → Pass2 → ... → Pass6. Gate decisions configurables como checkpoints |
| **Jupyter Execution Engine (@jupyter-kit)** | Gestión programática de kernels Jupyter, ejecución a nivel de celda, captura de output, inspección de metadatos en sandbox Docker |
| **PostgreSQL + SQLAlchemy 2.0 (async)** | Almacenamiento relacional para sesiones, metadatos, resultados y configuración. Migraciones con Alembic |

### 7.2 Key Architectural Decisions

**1. Strategy Pattern para LLM Providers**
`LLMProvider` define `generate(prompt, **kwargs)`. Implementaciones concretas manejan formato específico de cada API. Selección en runtime basada en configuración:
- Local para auditorías offline o privacy-sensitive
- Cloud para máxima capacidad de inferencia

**2. Audit State Machine**
Transiciones de estado con checkpoints de gate. Cada gate configurable:
- **Halt on failure:** Detener la auditoría en el primer blocking issue
- **Continue with caveats:** Seguir pero documentar los riesgos

**3. Server-Sent Events (SSE) para Logs en Tiempo Real**
Streaming de deliverables por pass al frontend sin polling overhead. El dashboard se actualiza en vivo a medida que cada pass completa.

---

## 8. Arquitectura Física

### 8.1 Deployment Topology

El sistema se despliega vía Docker Compose con 5 servicios:

| Servicio | Base | Rol |
|----------|------|-----|
| **Frontend** | Node 20 + Vite build | Sirve el React SPA |
| **Backend** | Python 3.11+ / FastAPI | API REST + SSE |
| **Database** | PostgreSQL 15 | Almacenamiento persistente |
| **Sandbox** | Python 3.11+ (per-notebook) | Ejecución aislada @jupyter-kit |
| **LLM Local** | Ollama / llama.cpp | Inferencia on-device |

### 8.2 Resource Isolation

Cada auditoría de notebook:
1. Spawnea un contenedor Docker de corta duración
2. Pre-instala las dependencias declaradas del notebook
3. Ejecuta un kernel Jupyter headless manejado por @jupyter-kit
4. Se destruye al completar la auditoría

Esto proporciona **aislamiento completo** entre sesiones de auditoría — no hay estado compartido, dependencias cruzadas, ni contaminación entre notebooks.

### 8.3 Provider Deployment Options

| Opción | Uso | Ventajas | Desventajas |
|--------|-----|----------|-------------|
| **Local (air-gapped)** | Ollama o llama.cpp en mismo host | Zero llamadas externas, privacidad total, sin costo por query | Modelos más pequeños, requiere HW dedicado |
| **Cloud (high-capability)** | OpenAI API (y potencialmente Anthropic) | Modelos más capaces, escalabilidad inmediata | Costo por query, requiere internet, datos viajan a terceros |

Ambos modos usan la misma interfaz `LLMProvider` — cambiar entre ellos es configuración, no código.

---

# Parte III — Costos Computacionales

---

## 9. Infrastructure Costs

### 9.1 Hardware Requirements

| Componente | Especificación Mínima |
|------------|----------------------|
| CPU | 8+ cores (x86_64 o ARM64) |
| RAM | 32 GB mínimo; 64 GB recomendado para inferencia LLM local |
| GPU | Opcional; NVIDIA con 8+ GB VRAM para inferencia GPU local |
| Storage | 100 GB SSD (sistema + modelos + bases de datos) |
| Network | 100 Mbps (modo cloud requiere internet) |

### 9.2 Deployment Cost Estimate

| Item | USD | COP (approx.) |
|------|-----|---------------|
| Server PC / Workstation | $1,000 | ~3,900,000 |
| Cloud hosting inicial (3 meses) | $300 | ~1,170,000 |
| **Total Q1** | **$1,300** | **~5,070,000** |

---

## 10. LLM Inference Costs

| Provider | Costo | Notas |
|----------|-------|-------|
| **Ollama (local)** | $0 (solo hardware) | Sin costo por token. Requiere RAM/VRAM local suficiente |
| **llama.cpp (local)** | $0 (solo hardware) | Inferencia optimizada para CPU; no requiere GPU |
| **OpenAI API** | Por token | Variable según modelo (GPT-4o, GPT-4o-mini) y longitud de prompt |

**Recomendación:** Inferencia local (llama.cpp o Ollama) para entornos privacy-sensitive o de alto volumen. Cloud API para passes que demandan alta capacidad donde hay conectividad.

---

## 11. Development Investment

### 11.1 Team and Timeline

**8 semanas (2 meses) con 2 developers.**

| Fase | Descripción | Duración |
|------|-------------|----------|
| **1** | Environment & Dockerization. Monorepo, Docker Compose, sandbox por notebook, dependency pinning, environment export | 2 semanas |
| **2** | FastAPI Backend & LLM Integration. REST API, LLMProvider strategy, AuditStateMachine, @jupyter-kit, SSE streaming | 3 semanas |
| **3** | Frontend Interface. React dashboard, session management, live progress, risk score visualization, provider config | 2 semanas |
| **4** | Integration & QA. E2E testing, prompt template validation, security review, documentation | 1 semana |

### 11.2 Total Development Cost

| Cost Item | USD | COP (approx.) |
|-----------|-----|---------------|
| Developer Costs (2 devs × 2 meses × $1,000/mo) | $4,000 | ~15,600,000 |
| Hardware / Server PC | $1,000 | ~3,900,000 |
| **Total Project Cost** | **$5,000** | **~19,500,000** |

> Nota: Los costos de developer varían significativamente según ubicación y seniority. Esta estimación asume tarifas de mercado en Latinoamérica.

---

# Parte IV — Costos Energéticos (Tercer Pilar)

---

## 12. Motivación

Tres tendencias convergentes motivan la inclusión del costo energético como preocupación de primera clase:

**1. LLM inference es energy-intensive**
Una sola query LLM grande consume 0.01–0.1 kWh (Paterson et al., 2024). Sobre cientos o miles de audit passes, esto se acumula significativamente.

**2. Notebook execution es a menudo wasteful**
- Pipelines de datos no optimizados re-ejecutan transformaciones costosas
- GPU memory queda asignada entre celdas
- Exploratory dead ends no se limpian
- El Construction Framework aborda algo de esto indirectamente (cell independence, explicit variable passing), pero la energía no es un target de optimización explícito

**3. Accountability ambiental es cada vez más un requisito**
- Instituciones académicas y funding bodies requieren energy reporting
- Corporate ESG frameworks exigen transparencia energética
- Un sistema de auditoría que no puede medir o reportar impacto energético es incompleto para estos stakeholders

---

## 13. Fuentes de Energía en el Sistema

### 13.1 Notebook Execution (Sandbox)

Cada sesión de auditoría ejecuta el notebook desde cero en un contenedor Docker:

- CPU cycles para data loading, preprocessing, modelling
- GPU cycles (si está disponible) para training e inference dentro del notebook
- Memory e I/O operations durante la ejecución
- Container orchestration overhead

### 13.2 LLM Inference (Audit Passes)

Cada audit pass involucra una o más llamadas LLM:

| Factor | Impacto en energía |
|--------|-------------------|
| **Model size** | Modelos grandes (70B+) consumen significativamente más energía por token que modelos pequeños (7B–13B) |
| **Context length** | Notebooks más largos → prompts más largos → mayor latencia y energía por pass |
| **Provider efficiency** | Inferencia local en hardware dedicado puede ser más o menos eficiente que cloud, según utilización, generación de hardware, y energy mix del datacenter |

### 13.3 Infrastructure Overhead

- Server idle power draw entre sesiones de auditoría
- Network transfer para llamadas cloud API y descargas de modelos
- Storage I/O para persistencia de resultados y caching de modelos

---

## 14. Propuesta: Resource Efficiency como Tercer Pilar

La pregunta central: **¿deberían los costos computacionales y energéticos elevarse a un tercer pilar, co-igual con Construction y Audit?**

### 14.1 Arguments For

| Argumento | Explicación |
|-----------|-------------|
| **Completeness** | Un framework que prescribe cómo construir y auditar notebooks pero ignora el costo de recursos de ambas actividades está incompleto. Los tres pilares serían: Construction, Audit, Resource Efficiency |
| **Feedback integration** | Construction podría extenderse con guías energy-aware ("preferir lazy loading", "limpiar GPU memory entre celdas", "profile energía de transformaciones pesadas"). Audit podría incluir un Energy Pass opcional |
| **Stakeholder alignment** | ESG reporting, grant compliance, y políticas institucionales demandan transparencia energética. Un sistema que reporte "este notebook consumió X kWh" provee valor inmediato |
| **Market differentiation** | Ninguna herramienta de auditoría de notebooks existente mide u optimiza explícitamente consumo energético |

### 14.2 Arguments Against

| Argumento | Explicación |
|-----------|-------------|
| **Scope creep** | El sistema es primariamente una herramienta de auditoría y construcción para corrección y reproducibilidad. Agregar energía como pilar co-igual cambia el scope de "quality assurance" a "QA + environmental impact" |
| **Measurement complexity** | Medición precisa por notebook requiere tooling especializado (Intel RAPL, NVIDIA NVML, kernel-level profiling) que puede no estar disponible en todos los entornos |
| **Pillar asymmetry** | Construction y Audit son *metodológicos* — prescriben cómo humanos y LLMs deberían trabajar. Resource Efficiency es *cuantitativo* — mide y optimiza uso de recursos. Mezclar pilares metodológicos y cuantitativos puede crear fricción conceptual |
| **User burden** | Requerir energy reporting y optimización puede disuadir adopción, especialmente para equipos que solo quieren verificar corrección sin contabilidad ambiental |

### 14.3 Compromiso: Optional Energy Module (Pass 7)

En lugar de elevar Resource Efficiency a pilar co-igual, se propone su inclusión como **módulo opcional** dentro del Audit Framework:

**Pass 7 — Energy Impact Assessment (opcional)**
- Pass adicional que mide la huella energética del notebook
- Deliverable: energy impact report con rating Low / Moderate / High
- No blocking — si el backend de medición no está disponible, se salta con "energy data unavailable"

**Energy-aware construction guidelines**
- El Construction Framework (Phases 2 y 3) podría incluir best practices opcionales de energy-awareness
- Gated detrás de un toggle "green mode"

**Measurement layer pluggable**
- RAPL para Intel CPUs
- NVML para NVIDIA GPUs
- powermetrics para Apple Silicon
- Software estimation model como fallback cross-platform

### 14.4 Decision Framework

| Criterio | Full Third Pillar | Optional Module (Pass 7) |
|----------|-------------------|-------------------------|
| Scope | Co-igual con Construction y Audit | Subordinado al Audit Framework |
| Measurement | Requerido para todas las auditorías | Opcional, graceful degradation |
| User impact | Energy reporting obligatorio | Opt-in, sin burden por defecto |
| Implementation | Nuevo framework, procesos, docs | Single additional pass + config |
| Market signal | Diferenciación fuerte | Mejora incremental |

**Recomendación:** Proceder con **Optional Module (Pass 7)** en la implementación inicial. Revisitar la decisión del Tercer Pilar después de 6–12 meses de uso productivo, basado en adopción del energy pass y demanda de stakeholders.

### 14.5 Implementación de Pass 7

#### Measurement Backends

| Platform | Tool | Scope |
|----------|------|-------|
| Linux (Intel) | `perf` / RAPL | CPU package + DRAM energy |
| Linux (AMD) | `rapl-read` / Zenpower | CPU package energy |
| Linux (NVIDIA GPU) | NVML (`pynvml`) | GPU energy + memory |
| macOS (Apple Silicon) | `powermetrics` | CPU + GPU + ANE |
| Cloud / fallback | Software estimation model | Cross-platform estimate |

#### Pass Deliverables

1. **Notebook Execution Energy:** Energía total durante kernel-restart-and-run-all, desglosada por sección cuando sea posible
2. **LLM Inference Energy:** Energía estimada por audit pass, basada en model size, context length, y duración de inferencia
3. **Energy Rating:** Low / Moderate / High, contextualizado contra un baseline ("2× la energía de un notebook típico de esta longitud")
4. **Optimisation Suggestions:** Cuando el rating es Moderate o High, sugerir acciones específicas ("considerar un modelo LLM más pequeño para Pass 5", "esta transformación podría cachearse en lugar de recomputarse")

---

## 15. Referencias Comentadas

### LLM-as-a-Judge y Evaluación

1. **Zheng et al. (2023).** *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena.* NeurIPS 2023.
   → El paper fundacional del paradigma LAJ. Establece que LLMs suficientemente capaces alcanzan concordancia inter-humana en evaluación de respuestas abiertas.

2. **Liu et al. (2023).** *G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment.* EMNLP 2023, pp. 2511–2522.
   → Base metodológica para los prompts estructurados. Descomposición de evaluación en criterios explícitos en lugar de scores holísticos.

### Sesgos y Limitaciones

3. **Wang et al. (2024).** *A Systematic Study of Bias in LLM-as-a-Judge.* arXiv:2405.07632.
   → Estudio sistemático de position bias, verbosity bias, self-enhancement bias en LLM judges.

4. **Zhang et al. (2024).** *Evaluating and Mitigating Positional Bias in LLM-as-a-Judge.* arXiv:2404.01234.
   → Técnicas para mitigar position bias específicamente.

### Asignación de Presupuesto

5. **Saha, Wagde & Kveton (2026).** *LLM-as-Judge on a Budget.* arXiv:2602.15481.
   → Algoritmo ROBIN-HOOD para asignación adaptativa de presupuesto de queries LLM. Garantía teórica de error $\tilde{O}(\sqrt{\sum \sigma^2 / B})$. Misma precisión con mitad de queries.

### Disociación Generación-Evaluación

6. **Nordfors (2026).** *The Metanym Game: A Self-Contained, Self-Consistent LLM Peer-Community Benchmark for Structural Intelligence.* arXiv:2606.21008.
   → Juego competitivo de analogías. SVD revela que generación y evaluación son habilidades disociadas. Correlación r=0.92 con GPQA Diamond.

### Panel de Jueces

7. **Verga et al. (2024).** *Replacing Judges with Juries: Evaluating LLM Generations with a Panel of Diverse Models.* arXiv:2404.18796.
   → Propuesta de "jury" — panel de modelos diversos en lugar de un solo LLM judge. Base para la Panel Architecture.

### Eficiencia Energética

8. **Paterson et al. (2024).** *EcoAssistant: Using LLM Assistant More Affordably and Environmentally Friendly.* arXiv:2402.02156.
   → Estimación de costo energético de inferencia LLM: 0.01–0.1 kWh por query.

9. **Henderson et al. (2020).** *Towards the Systematic Reporting of the Energy and Carbon Footprints of Machine Learning.* JMLR 21, pp. 1–43.
   → Marco para reporte sistemático de huella energética y de carbono en ML.

10. **Strubell, Ganesh & McCallum (2019).** *Energy and Policy Considerations for Deep Learning in NLP.* ACL 2019, pp. 3645–3650.
    → Estudio seminal sobre costo energético del entrenamiento de modelos NLP.

11. **Lacoste et al. (2019).** *Quantifying the Carbon Emissions of Machine Learning.* NeurIPS Workshop on Tackling Climate Change with ML, 2019.
    → Métricas y herramientas para cuantificar emisiones de carbono de cómputo ML.

12. **Dodge et al. (2020).** *Fine-Tuning Pretrained Language Models: Weight Initializations, Data Orders, and Early Stopping.* arXiv:2002.06305.
    → Impacto de decisiones de fine-tuning en reproducibilidad y eficiencia.
