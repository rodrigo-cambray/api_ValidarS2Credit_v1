# credit-history-assessment-service

```sh
cp .env.example .env
uvicorn app.main:app --reload
```

The service does not run migrations or create tables. Its account needs access
to `oferta`, `persona_buro`, `persona_circulo` and `persona_quash`.

`docker compose up --build` connects to the existing database from
`MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_DATABASE`, `MYSQL_USER` and
`MYSQL_PASSWORD` in `.env`; it does not start a database container.
`DATABASE_URL` is an optional complete-URL override.

Send `calificadorDetalle.decision` as `APROBADO` or `RECHAZADO` until the
legacy decision rules are characterized; otherwise the API returns `PENDIENTE`.

The request identity is `idOferta`. For first credit, the service deactivates
the person's active legacy reports and inserts the reports received from
Calificador. Second credit does not write reports.
