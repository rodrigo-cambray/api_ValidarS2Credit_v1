# Contrato de API S2Credit v1

| Campo | Valor |
| --- | --- |
| Nombre | `credit-history-assessment-service` |
| Versión | `3.0.0` |
| Consumidor | Orquestador de originación |
| Estado | Borrador |

## Propósito

Determina si el prospecto asociado a una oferta tiene otras ofertas en etapa `S2CREDIT`. La API sólo consulta `oferta`; no persiste información ni consulta sistemas de reportes.

Si la oferta solicitada ya está en `S2CREDIT`, la operación termina exitosamente sin consultar el historial. En otro caso, una oferta anterior es cualquier fila con el mismo `fk_persona` y un `id_oferta` distinto de la solicitud. No se aplican filtros de fecha, estatus u orden de creación.

## Seguridad y errores

`/health/live` es público. Los demás endpoints requieren `Authorization: Bearer <BEARER_TOKEN>`. Los errores usan `application/problem+json` conforme a RFC 9457.

## Endpoints

| Método | Ruta | Seguridad | Resultado |
| --- | --- | --- | --- |
| `GET` | `/health/live` | No | Estado del proceso. |
| `GET` | `/health/ready` | Bearer | Conectividad de lectura con MySQL. |
| `POST` | `/v1/s2-credit-assessments` | Bearer | Historial S2Credit del prospecto. |

### `POST /v1/s2-credit-assessments`

Solicitud:

```json
{"idOferta": 12345}
```

`idOferta` es obligatorio, entero y mayor que cero. No se permiten campos adicionales.

Respuesta exitosa (`200`):

```json
{
  "idOferta": 12345,
  "etapa": "PRECALIFICADA",
  "mensaje": "El prospecto ya tiene un crédito pagado anteriormente.",
  "estatus": "SegundoCredito"
}
```

| Condición | Mensaje | Estatus |
| --- | --- | --- |
| La oferta solicitada está en `S2CREDIT` | `La oferta ya está en etapa S2Credit. Operación no válida.` | `null` |
| Otra oferta con `etapa = S2CREDIT` | `El prospecto ya tiene un crédito pagado anteriormente.` | `SegundoCredito` |
| Otras ofertas, ninguna en `S2CREDIT` | `El prospecto no tiene una oferta en S2Credit.` | `PrimerCredito` |
| No hay otra oferta | `El prospecto no tiene solicitudes de crédito anteriores a esta.` | `PrimerCredito` |

El campo `etapa` aparece en toda respuesta exitosa y reproduce sin transformación el valor de `oferta.etapa` de la oferta solicitada.

| HTTP | Código | Cuándo ocurre |
| --- | --- | --- |
| `401` | `UNAUTHORIZED` | Falta o falla el token Bearer. |
| `404` | `NOT_FOUND` | La oferta no ha sido originada o no tiene prospecto válido. |
| `422` | `VALIDATION_ERROR` | `idOferta` es inválido o se envían campos adicionales. |
| `503` | `AUTH_NOT_CONFIGURED` | Falta `BEARER_TOKEN`. |

Los dos casos `404` se distinguen por `detail`: `La oferta no ha sido originada.` o `La oferta no tiene un prospecto asignado aún.` Toda respuesta de error incluye la extensión RFC 9457 `estatus` con valor `null`.

## Dependencia de datos

La cuenta MySQL necesita sólo `SELECT` sobre `oferta`. `fk_persona` debe ser un entero mayor que cero para consultar el historial.
