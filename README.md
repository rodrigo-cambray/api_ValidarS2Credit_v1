# credit-history-assessment-service

Microservicio FastAPI que evalúa una oferta de crédito usando el resultado ya generado por BC Calificador. Clasifica la oferta como primer o segundo crédito y conserva los reportes recibidos en las tablas existentes de originación.

No consulta Buró, Círculo ni Quash directamente, no crea tablas y no ejecuta migraciones.

## Flujo funcional

1. El orquestador envía `idOferta` y `calificadorDetalle`.
2. El servicio consulta `oferta` para obtener `fk_persona` y `etapa`.
3. Si la etapa es `S2CREDIT`, se trata como `SEGUNDO_CREDITO`; cualquier otra etapa es `PRIMER_CREDITO`.
4. Para primer crédito, desactiva los reportes activos de la persona e inserta únicamente los reportes recibidos.
5. Para segundo crédito no escribe reportes; devuelve la decisión recibida de Calificador.

La decisión se toma de `calificadorDetalle.decision`: `APROBADO` o `RECHAZADO`. Si no se recibe una decisión explícita, la respuesta es `PENDIENTE` con el motivo `DECISION_CALIFICADOR_AUSENTE`.

## Persistencia

La base de datos es externa al contenedor. El usuario de conexión necesita acceso a estas tablas existentes:

| Tabla | Uso |
|---|---|
| `oferta` | Identifica la persona y determina el tipo de crédito. |
| `persona_buro` | Guarda el reporte Buró y sus valores derivados. |
| `persona_circulo` | Guarda el JSON e `id_unykoo` de Círculo. |
| `persona_quash` | Guarda los campos disponibles de Quash. |

Los nuevos reportes de primer crédito se marcan con `estatus = 1`. Los registros activos anteriores de la misma persona se cambian a `estatus = 0`.

> Las tablas heredadas no guardan `idOferta`, decisión ni versión de regla. Por ello el servicio no ofrece idempotencia transaccional estricta y la consulta posterior devuelve `PENDIENTE` con `DECISION_NO_PERSISTIDA`.

## Seguridad

Configura `BEARER_TOKEN` como secreto compartido. Todo endpoint que consulta la base requiere:

```http
Authorization: Bearer <BEARER_TOKEN>
```

`/health/live` es público. Una credencial faltante, incorrecta o con un esquema distinto devuelve `401` con `WWW-Authenticate: Bearer`. Si `BEARER_TOKEN` no está configurado, los endpoints protegidos devuelven `503`.

Los errores usan `application/problem+json` conforme a RFC 9457 e incluyen un `traceId` y el encabezado `X-Request-ID` para correlación.

## Configuración

Copie el archivo de ejemplo y complete los datos de la base existente:

```powershell
Copy-Item .env.example .env
```

| Variable | Descripción |
|---|---|
| `MYSQL_HOST` | Host o dirección IP de MySQL. |
| `MYSQL_PORT` | Puerto MySQL; normalmente `3306`. |
| `MYSQL_DATABASE` | Base de datos de originación existente. |
| `MYSQL_USER` | Usuario con permisos sobre las tablas requeridas. |
| `MYSQL_PASSWORD` | Contraseña del usuario MySQL. |
| `BEARER_TOKEN` | Secreto estático usado por los clientes de la API. |
| `DATABASE_URL` | Opcional. Reemplaza todas las variables `MYSQL_*`. |

No registre `.env`, credenciales, tokens ni los JSON completos de reportes en control de versiones o logs.

## Ejecutar con Docker

```powershell
docker compose up --build
```

El contenedor instala sus dependencias en `/opt/venv`, se ejecuta como usuario no privilegiado y se conecta a la base configurada. Compose no inicia MySQL.

## Ejecutar localmente

Requiere Python 3.12 o superior y acceso a la misma base configurada en `.env`.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --env-file .env
```

## Endpoints

| Método | Ruta | Autenticación | Propósito |
|---|---|---|---|
| `GET` | `/health/live` | No | Confirma que el proceso está activo. |
| `GET` | `/health/ready` | Bearer | Comprueba conectividad con MySQL. |
| `POST` | `/v1/credit-assessments` | Bearer | Evalúa una oferta y persiste reportes de primer crédito. |
| `GET` | `/v1/credit-assessments/by-oferta/{idOferta}` | Bearer | Consulta reportes activos de la persona de una oferta. |

Ejemplo de evaluación:

```powershell
$headers = @{ Authorization = "Bearer $env:BEARER_TOKEN" }
$body = @{
  idOferta = 12345
  calificadorDetalle = @{
    decision = "APROBADO"
    reporteBuro = @{ score = 720; ingresoMensual = 10000 }
    reporteCirculo = @{ idUnykoo = "unykoo-ejemplo-001" }
  }
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method Post -Uri http://localhost:8000/v1/credit-assessments `
  -Headers $headers -ContentType application/json -Body $body
```

## Documentación del contrato

- Swagger: `http://localhost:8000/docs`
- OpenAPI: `http://localhost:8000/openapi.json`
- Contrato funcional: [docs/Contrato API_s2cRESDIT_v1.md](docs/Contrato%20API_s2cRESDIT_v1.md)
