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

## Despliegue manual a Cloud Run

El workflow [.github/workflows/deploy-cloud-run.yml](.github/workflows/deploy-cloud-run.yml) se ejecuta **sólo** desde GitHub Actions mediante `workflow_dispatch`. Un push nunca despliega el servicio.

### Secrets del Environment `cloud-run-production`

Configure estos GitHub Environment Secrets, sin valores en archivos versionados:

| Secret | Uso |
|---|---|
| `GCP_PROJECT_ID` | Proyecto de Google Cloud. |
| `GCP_REGION` | Región de Cloud Run y Artifact Registry. |
| `CLOUD_RUN_SERVICE` | Nombre del servicio Cloud Run. |
| `ARTIFACT_REPOSITORY` | Repositorio Docker existente en Artifact Registry. |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | Nombre completo del provider WIF. |
| `GCP_SERVICE_ACCOUNT` | Cuenta de servicio que GitHub Actions impersona mediante WIF. |
| `CLOUD_RUN_ALLOW_UNAUTHENTICATED` | `false` para mantener el servicio privado; `true` habilita acceso público explícitamente. |
| `CLOUD_RUN_ENV_FILE_B64` | Archivo de ejecución privado codificado en Base64. |

### Preparar `CLOUD_RUN_ENV_FILE_B64`

1. Copie la plantilla sin secretos:

   ```powershell
   Copy-Item deploy/cloud-run.env.example deploy/cloud-run.env
   ```

2. Complete únicamente `deploy/cloud-run.env` con los valores reales de producción. No agregue `PORT`; Cloud Run lo inyecta.
3. Codifique el archivo sin imprimir su contenido:

   ```powershell
   [Convert]::ToBase64String([IO.File]::ReadAllBytes('deploy/cloud-run.env'))
   ```

4. Guarde la salida como el secret `CLOUD_RUN_ENV_FILE_B64` del Environment `cloud-run-production` y elimine o conserve de forma segura el archivo local. `deploy/cloud-run.env` está ignorado por Git y Docker.

### Ejecutar el workflow

En GitHub, abra **Actions**, seleccione **Deploy Cloud Run**, pulse **Run workflow** y confirme el Environment `cloud-run-production`. Las reglas de protección de ese Environment, si existen, se aplican antes del despliegue.

### Configuración pendiente del administrador de Cloud Run

- Crear el repositorio Docker de Artifact Registry en `GCP_REGION`.
- Configurar Workload Identity Federation para este repositorio de GitHub y restringirlo al repositorio, rama o Environment permitidos.
- Otorgar a la identidad federada `roles/iam.workloadIdentityUser` sobre `GCP_SERVICE_ACCOUNT`.
- Otorgar a `GCP_SERVICE_ACCOUNT` los permisos mínimos para publicar en Artifact Registry y desplegar Cloud Run, normalmente `roles/artifactregistry.writer`, `roles/run.admin` y `roles/iam.serviceAccountUser` sobre la cuenta de ejecución de Cloud Run.
- Verificar que la cuenta de ejecución de Cloud Run puede leer la imagen de Artifact Registry y tiene conectividad autorizada hacia la base de datos existente.
- Mantener `CLOUD_RUN_ALLOW_UNAUTHENTICATED=false` salvo que se apruebe explícitamente acceso público.
