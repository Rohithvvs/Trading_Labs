# Runtime Database Read-Only Smoke Test Report

**Timestamp**: 2026-09-20T10:07:59.614768+00:00  
**Overall Status**: `ALL_READ_CHECKS_PASSED`

## Safety & Preconditions

- **Local PostgreSQL URL Empty**: `True`
- **Local PostgreSQL Disabled**: `True`
- **Candle History Backend**: `turso`
- **Neon Target (Masked)**: `postgresql+asyncpg://neondb_owner:***@ep-patient-bonus-aonma8xh-pooler.c-2.ap-southeast-1.aws.neon.tech/neondb`
- **Turso Target (Masked)**: `libsql://tradinghistory-rohithvvs.aws-ap-south-1.turso.io`
- **Read-Only Transaction Enforced on Neon**: `True`
- **Local PostgreSQL Contacted**: `False`
- **Writes Attempted**: `False`

## Neon Operational Read

- **Table**: `stocks_master`
- **Status**: `SUCCESS`
- **Row Count**: `755` (Expected: `755`)

## Turso Candle Reads

### Daily Equity Candles (`INFY-EQ`)
- **Status**: `SUCCESS`
- **Rows Returned**: `5`
- **First Trade Date**: `2008-07-22`
- **Sample Close**: `197.29`

### Index Candles (`NIFTY500`)
- **Status**: `SUCCESS`
- **Rows Returned**: `5`
- **First Trade Date**: `2008-07-22`
- **Sample Close**: `3355.9`
