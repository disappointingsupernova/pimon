# SD Card Longevity

This application is designed to run 24/7 on a Raspberry Pi with an SD card. Several optimisations protect the card from excessive write wear:

- **Batched I/O**: All sensor readings from a poll cycle are written in a single file open (CSV) and a single database commit, rather than per-sensor
- **SQLite WAL mode**: Write-Ahead Logging uses sequential appends instead of rewriting the database file, dramatically reducing write amplification
- **Dashboard serves cached data**: API endpoints never trigger fresh sensor reads or disk I/O on HTTP requests
- **Log rotation**: Application logs are bounded at a configurable maximum size
- **CSV retention pruning**: Old CSV files are automatically deleted after the retention period

## Low-Write Mode

For maximum SD card longevity on always-on deployments, enable low-write mode:

```
LOW_WRITE_MODE=true
```

This automatically:

- Disables CSV logging (the database stores all readings instead, avoiding duplicate writes)
- Enforces a minimum 60-second poll interval (halves write operations vs the 30s default)
- Reduces log verbosity to WARNING level (eliminates routine INFO log writes)

## Write Budget

| Mode     | Writes/day | Data/day | SD card lifespan (32 GB) |
|----------|-----------|----------|-------------------------|
| Default  | ~5,900    | ~1.9 MB  | 14-43 years             |
| Low-write| ~2,900    | ~0.9 MB  | 30-85 years             |

## Manual Tuning

If you prefer fine-grained control without low-write mode:

- Set `CSV_LOGGING_ENABLED=false` if the database is sufficient for your history needs
- Increase `POLL_INTERVAL` to 60 or 120 seconds if real-time granularity is not needed
- Set `LOG_LEVEL=WARNING` to suppress routine informational log writes
- Use an external MySQL/PostgreSQL database (`DATABASE_URL`) to move all write I/O off the SD card entirely
