# credit-history-assessment-service

Microservicio FastAPI que determina si el prospecto de una oferta tiene otras ofertas en etapa `S2CREDIT`. Sólo consulta `oferta`; no consulta proveedores crediticios, no procesa reportes y no escribe datos.

## Flujo

1. Recibe `idOferta`.
2. Obtiene su `fk_persona`.
3. Si la oferta recibida ya está en `S2CREDIT`, responde que la operación no es válida.
4. En otro caso, excluye la oferta recibida y revisa las demás ofertas de esa persona.
5. Responde si existe una oferta previa en `S2CREDIT`, si existen otras sin esa etapa o si no hay otras ofertas.

`fk_persona` debe ser un entero mayor que cero. Una oferta inexistente o sin prospecto válido devuelve `404` RFC 9457.

## Configuración

Copie `.env.example` a `.env` y configure una base de originación existente. El usuario MySQL necesita únicamente permiso `SELECT` sobre `oferta`.

| Variable | Descripción |
| --- | --- |
| `MYSQL_HOST` | Host o IP de MySQL. |
| `MYSQL_PORT` | Puerto MySQL, normalmente `3306`. |
| `MYSQL_DATABASE` | Base que contiene `oferta`. |
| `MYSQL_USER` | Usuario de sólo lectura sobre `oferta`. |
| `MYSQL_PASSWORD` | Contraseña del usuario MySQL. |
| `DATABASE_URL` | Opcional; reemplaza las variables `MYSQL_*`. |
| `BEARER_TOKEN` | Secreto Bearer estático de la API. |

## Ejecución

```powershell
docker compose up --build
```

El contenedor usa un entorno virtual propio, se ejecuta sin privilegios y escucha en `0.0.0.0`. Cloud Run inyecta `PORT`; localmente usa `8000`.

## Endpoints

| Método | Ruta | Autenticación | Propósito |
| --- | --- | --- | --- |
| `GET` | `/health/live` | No | Disponibilidad del proceso. |
| `GET` | `/health/ready` | Bearer | Conectividad de lectura con MySQL. |
| `POST` | `/v1/s2-credit-assessments` | Bearer | Consulta el historial S2Credit del prospecto. |

```powershell
$headers = @{ Authorization = "Bearer $env:BEARER_TOKEN" }
$body = @{ idOferta = 12345 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/v1/s2-credit-assessments -Headers $headers -ContentType application/json -Body $body
```

La respuesta exitosa tiene `idOferta`, `etapa`, `mensaje` y `estatus`. `etapa` refleja sin transformación el valor de la oferta consultada. `estatus` es `SegundoCredito` si existe otra oferta en `S2CREDIT`, `PrimerCredito` en los demás casos exitosos o `null` si la oferta recibida ya está en `S2CREDIT`. Los errores usan `application/problem+json` conforme a RFC 9457 e incluyen `estatus: null`. Swagger y OpenAPI se publican en `/docs` y `/openapi.json`.

## Migración del contrato 3.0.0

Esta versión reemplaza el contrato anterior de la misma ruta: el cuerpo sólo admite `idOferta` y ya no devuelve una decisión. Los consumidores deben actualizarse de forma coordinada.

## Cloud Run

El workflow `.github/workflows/deploy-cloud-run.yml` sólo se ejecuta con `workflow_dispatch`; un push no despliega nada. Use un `MYSQL_USER` de sólo lectura y mantenga `CLOUD_RUN_ALLOW_UNAUTHENTICATED=false` salvo aprobación explícita.
