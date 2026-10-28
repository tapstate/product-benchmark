# Oracle prerequisites log (shared source, Oracle 19.17 EE, CDB$ROOT)

| Step | By | Started (UTC) | Result |
|---|---|---|---|
| Seed BENCH_* (Tier A) with ALL COLUMNS supplemental logging | DBA-role user | 2026-10-28T03:28:14Z | PASS, 1.5 s |
| Create C##CFLTADMIN, C##CFLTUSER and system grants | DBA-role user | 2026-10-28T03:28:56Z | partial: CREATE SESSION, SET CONTAINER, SELECT/LOCK/FLASHBACK ANY TABLE, LOGMINING, SELECT ANY TRANSACTION, SELECT ANY DICTIONARY, CREATE TABLE, CREATE SEQUENCE granted |
| SELECT_CATALOG_ROLE, EXECUTE_CATALOG_ROLE | DBA-role user | same | FAIL: ORA-01924 / ORA-01932 (no ADMIN OPTION) |
| EXECUTE ON SYS.DBMS_LOGMNR, DBMS_LOGMNR_D | DBA-role user | same | FAIL: ORA-01031 insufficient privileges |
| DBMS_XSTREAM_AUTH.GRANT_ADMIN_PRIVILEGE | DBA-role user | same | FAIL: PLS-00201 package not visible to a non-SYS user |
| Remaining steps (`oracle-prereqs-sys.sql`) | SYSDBA | 2026-10-28T03:45Z | BLOCKED: no SYS or SYSTEM password available (ORA-01017 with the application user's password) |
| LogMiner-route check with the existing DBA-role user (C##TAPDATA) | benchmark | 2026-10-28T03:50Z | PASS: all listed system privileges, EXECUTE on DBMS_LOGMNR and DBMS_LOGMNR_D, DBMS_LOGMNR_D.BUILD succeeded |

Decision: the Confluent leg runs the LogMiner-based Oracle CDC Source Premium connector with the same DBA-role user the other products use. The XStream connector is deferred until SYS access exists.

Finding: both Confluent Oracle CDC connectors' documented setup needs SYS-level steps on a multitenant 19c; a DBA-role
application user is not enough. The product under test from the same database vendor (Tapstate) ran
its connection test with the DBA-role user alone.
