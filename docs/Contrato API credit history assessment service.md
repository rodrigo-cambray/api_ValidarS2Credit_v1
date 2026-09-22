# Contrato de API validar\_S2Creadit\_v1

Este contrato define la API que clasifica una oferta como primer o segundo crédito y, para primer crédito, persiste los reportes recibidos de BC Calificador en las tablas heredadas. No consulta proveedores externos ni crea tablas.

## 1\. Control del documento

| Campo | Valor |
| --- | --- |
| Nombre de la API | `credit-history-assessment-service` |
| Identificador del producto | `ms_verificarS2Credit_v1` |
| Versión del contrato | `1.0.0` |
| Versión de la API | `v1` |
| Estado | `Borrador` |
| Propietario técnico | `Pendiente de asignar` |
| Propietario funcional | `Pendiente de asignar` |
| Equipo consumidor | `Orquestador de originación` |
| Fecha de creación | `2026-09-22` |
| Última actualización | `2026-09-22` |
| Aprobadores | `Pendiente de asignar` |

## 2\. Propósito y alcance

**Problema que resuelve:** centraliza la clasificación de una oferta y la escritura de reportes de crédito en las tablas heredadas asociadas a la persona.

**Resultado esperado:** el consumidor recibe una decisión de Calificador y los reportes disponibles quedan activos para la persona cuando la oferta corresponde a primer crédito.

**Incluye:**

-   Consultar `oferta` por `idOferta` para obtener la persona y su etapa.
-   Clasificar `S2CREADIT` como `SEGUNDO_CREDITO`; cualquier otra etapa como `PRIMER_CREDITO`.
-   Para primer crédito, desactivar los reportes activos anteriores e insertar Buró, Círculo y Quash disponibles.
-   Para segundo crédito, no escribir reportes.

**No incluye:**

-   Consultas directas a Buró, Círculo o Quash.
-   Creación o migración de tablas.
-   Persistencia de la decisión, motivo o versión de regla por oferta.
-   Idempotencia transaccional estricta, porque las tablas heredadas no almacenan `idOferta`.

**Actores y consumidores:**

| Actor o sistema | Responsabilidad | Ambiente | Contacto |
| --- | --- | --- | --- |
| Orquestador de originación | Envía el detalle producido por Calificador y consume la respuesta | Todos | Pendiente de asignar |
| BC Calificador | Produce el detalle de reportes y decisión | Todos | Pendiente de asignar |
| Base de originación | Provee `oferta`, `persona_buro`, `persona_circulo` y `persona_quash` | Todos | Pendiente de asignar |

## 3\. Artefactos y fuente de verdad

| Artefacto | Ruta o vínculo | Carácter |
| --- | --- | --- |
| Contrato descriptivo | `docs/Contrato API credit history assessment service.md` | Normativo mientras no exista OpenAPI versionado |
| Swagger | `/docs` | Representación generada |
| Esquema generado | `/openapi.json` | Normativo en modo code-first |
| Diagrama de flujo | `No aplica` | No aplica |
| Decisiones técnicas | `docs/adr/` | No aplica actualmente |

**Modo elegido:** `code-first`.

## 4\. Ambientes y direccionamiento

| Ambiente | URL base | Exposición | Swagger |
| --- | --- | --- | --- |
| Local | `http://localhost:8000` | Equipo local | Habilitado |
| Desarrollo | `Pendiente de asignar` | Interna | Restringido |
| QA | `Pendiente de asignar` | Interna | Restringido |
| Producción | `Pendiente de asignar` | Interna | Deshabilitado o restringido |

-   Formato principal: `application/json`.
-   Errores actuales: `application/json`; `application/problem+json` está pendiente de implementación.
-   Fechas recibidas o persistidas por el servicio: fecha local de ejecución; no forman parte de las respuestas actuales.
-   Codificación: UTF-8.
-   Ruta principal: `/v1`.

## 5\. Seguridad obligatoria

### 5.1 Estado actual

La API no implementa autenticación todavía. Sólo debe exponerse en redes internas controladas. Antes de producción se debe implementar `X-API-Key` o el mecanismo corporativo equivalente y deshabilitar o restringir Swagger.

### 5.2 API key

No aplica en la implementación actual. Pendiente antes de producción: llave por consumidor y ambiente, secreto fuera de código e imagen, almacenamiento de huella no reversible y auditoría mediante `key_id`.

### 5.3 Rotación trimestral de API key

No aplica hasta implementar autenticación. La política prevista es rotación trimestral, preparación siete días antes y gracia de 72 horas.

### 5.4 Excepciones

| Ruta exceptuada | Motivo | Control compensatorio | Expira |
| --- | --- | --- | --- |
| `/health/live` | Sonda de proceso | Respuesta mínima | No aplica |
| `/health/ready` | Sonda de conectividad | Restringir a infraestructura | No aplica |

## 6\. Inventario de endpoints

| Método | Ruta | operationId | Objetivo | Seguridad | Estado |
| --- | --- | --- | --- | --- | --- |
| `GET` | `/health/live` | `live` | Verifica que el proceso responde | Pública interna | Implementado |
| `GET` | `/health/ready` | `ready` | Verifica conectividad con la base | Pública interna | Implementado |
| `POST` | `/v1/credit-assessments` | `assess` | Clasifica la oferta y persiste reportes de primer crédito | Red interna, sin API key actual | Implementado |
| `GET` | `/v1/credit-assessments/by-oferta/{idOferta}` | `by_offer` | Consulta los reportes activos de la persona de la oferta | Red interna, sin API key actual | Implementado |

## 7\. Ficha por endpoint

### 7.1 `GET /health/live`

**operationId:** `live`

**Objetivo:** confirmar que el proceso HTTP está activo.

**Reglas de autorización:** pública sólo para infraestructura interna.

**Idempotencia:** No aplica.

**Respuesta exitosa de ejemplo:**

```json
{"status":"ok"}
```

| HTTP | Cuándo ocurre | Esquema |
| --- | --- | --- |
| `200` | El proceso está disponible | Objeto con `status` |

### 7.2 `GET /health/ready`

**operationId:** `ready`

**Objetivo:** confirmar que la API puede ejecutar una consulta contra la base configurada.

**Reglas de autorización:** pública sólo para infraestructura interna.

**Idempotencia:** No aplica.

| HTTP | Cuándo ocurre | Esquema |
| --- | --- | --- |
| `200` | La consulta de disponibilidad fue exitosa | Objeto con `status` |
| `500` | No se puede consultar la base | Error JSON de FastAPI |

### 7.3 `POST /v1/credit-assessments`

**operationId:** `assess`

**Objetivo:** clasificar la oferta y guardar los reportes disponibles cuando corresponde a primer crédito.

**Reglas de autorización:** red interna; autenticación pendiente.

**Idempotencia:** No. Un reintento de primer crédito desactiva los registros activos de la persona e inserta nuevos registros.

**Parámetros:** no tiene parámetros de ruta, consulta ni encabezados obligatorios.

**Solicitud de ejemplo:**

```json
{
  "idOferta": 12345,
  "calificadorDetalle": {
    "idCalificador": 5566,
    "decision": "APROBADO",
    "motivo": null,
    "reporteBuro": {
      "score": 720,
      "ingresoMensual": 10000,
      "codigoRespuesta": "00"
    },
    "reporteCirculo": {
      "idUnykoo": "unykoo-ejemplo-001"
    },
    "quash": {
      "applicantId": "applicant-ejemplo-001",
      "approvalScore": "800"
    }
  }
}
```

**Respuesta exitosa de ejemplo:**

```json
{
  "assessmentId": "oferta_12345",
  "idOferta": 12345,
  "tipoCredito": "PRIMER_CREDITO",
  "estado": "APROBADO",
  "motivo": null,
  "idUnykoo": "unykoo-ejemplo-001",
  "reportesPersistidos": ["BURO", "CIRCULO", "QUASH"]
}
```

| HTTP | Cuándo ocurre | Esquema |
| --- | --- | --- |
| `201` | Oferta encontrada y operación completada | `AssessmentResponse` |
| `404` | No existe la oferta | Error JSON de FastAPI |
| `422` | Falta `idOferta`, es menor que uno o el cuerpo no es válido | Error JSON de FastAPI |
| `500` | Error de base o escritura | Error JSON de FastAPI |

### 7.4 `GET /v1/credit-assessments/by-oferta/{idOferta}`

**operationId:** `by_offer`

**Objetivo:** obtener los tipos de reporte activos asociados a la persona de una oferta.

**Reglas de autorización:** red interna; autenticación pendiente.

**Idempotencia:** Sí.

**Parámetros:**

| Nombre | Ubicación | Tipo/formato | Obligatorio | Restricciones | Ejemplo |
| --- | --- | --- | --- | --- | --- |
| `idOferta` | path | entero | Sí | Debe identificar una fila existente de `oferta` | `12345` |

**Respuesta exitosa de ejemplo:**

```json
{
  "assessmentId": "oferta_12345",
  "idOferta": 12345,
  "tipoCredito": "PRIMER_CREDITO",
  "estado": "PENDIENTE",
  "motivo": "DECISION_NO_PERSISTIDA",
  "idUnykoo": "unykoo-ejemplo-001",
  "reportesPersistidos": ["BURO", "CIRCULO"]
}
```

| HTTP | Cuándo ocurre | Esquema |
| --- | --- | --- |
| `200` | Oferta encontrada | `AssessmentResponse` |
| `404` | No existe la oferta | Error JSON de FastAPI |
| `500` | Error de base | Error JSON de FastAPI |

## 8\. Modelos de información

| Modelo | Campo | Tipo | Requerido | Restricciones | Clasificación |
| --- | --- | --- | --- | --- | --- |
| `AssessmentRequest` | `idOferta` | entero | Sí | Mayor que cero | Interno |
| `AssessmentRequest` | `calificadorDetalle` | objeto | Sí | Debe ser un objeto JSON | Confidencial |
| `CalificadorDetalle` | `idCalificador` | entero | No | Identificador recibido de Calificador | Interno |
| `CalificadorDetalle` | `decision` | cadena | No | `APROBADO`, `RECHAZADO`, `PENDIENTE` o `ERROR`; sólo se conservan explícitamente APROBADO y RECHAZADO en la respuesta | Interno |
| `CalificadorDetalle` | `motivo` | cadena o nulo | No | Texto de negocio | Interno |
| `CalificadorDetalle` | `reporteBuro` | objeto o arreglo | No | Se persiste como JSON en `persona_buro` | Confidencial |
| `CalificadorDetalle` | `reporteCirculo` | objeto o arreglo | No | Se persiste como JSON en `persona_circulo` | Confidencial |
| `CalificadorDetalle` | `quash` | objeto o arreglo | No | Se mapea a columnas de `persona_quash` | Confidencial |
| `AssessmentResponse` | `assessmentId` | cadena | Sí | Formato `oferta_<idOferta>`; no es una fila persistida | Interno |
| `AssessmentResponse` | `idOferta` | entero | Sí | Identificador de oferta | Interno |
| `AssessmentResponse` | `tipoCredito` | cadena | Sí | `PRIMER_CREDITO` o `SEGUNDO_CREDITO` | Interno |
| `AssessmentResponse` | `estado` | cadena | Sí | `APROBADO`, `RECHAZADO` o `PENDIENTE` | Interno |
| `AssessmentResponse` | `motivo` | cadena o nulo | Sí | Nulo si no aplica | Interno |
| `AssessmentResponse` | `idUnykoo` | cadena o nulo | Sí | Derivado de Círculo cuando está disponible | Confidencial |
| `AssessmentResponse` | `reportesPersistidos` | arreglo de cadenas | Sí | Valores `BURO`, `CIRCULO`, `QUASH` | Interno |

Los consumidores deben tolerar campos nuevos en objetos JSON. No deben registrar los objetos de reporte completos ni `idUnykoo` fuera de controles de datos confidenciales.

### 8.1 Formato uniforme de errores

La implementación actual devuelve errores JSON generados por FastAPI. La adopción de `application/problem+json` con `code`, `traceId` y `errors` queda pendiente; los consumidores no deben depender de detalles internos ni de trazas.

## 9\. Aprobación

| Rol | Nombre | Decisión | Fecha |
| --- | --- | --- | --- |
| Negocio | Pendiente de asignar | Pendiente | Pendiente |
| Desarrollo | Pendiente de asignar | Pendiente | Pendiente |
| Seguridad | Pendiente de asignar | Pendiente | Pendiente |
| Infraestructura | Pendiente de asignar | Pendiente | Pendiente |