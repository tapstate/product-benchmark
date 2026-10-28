-- Confluent Oracle connector prerequisites that need a SYSDBA session on a self-managed or
-- partner-hosted Oracle 19c (multitenant, users created as common users in CDB$ROOT).
-- A DBA-role user without SYS cannot run these: granting EXECUTE on SYS packages and calling
-- DBMS_XSTREAM_AUTH both failed with ORA-01031 / PLS-00201 in this benchmark. Run as SYS:
--
--   sqlplus / as sysdba   (or: sqlplus sys/<password>@<host>:1521/<service> as sysdba)
--
-- The two users already exist (created by the DBA user); this script only adds what SYS must grant.

-- LogMiner route (Oracle CDC Source Premium) and snapshot reads
GRANT SELECT_CATALOG_ROLE  TO C##CFLTUSER CONTAINER=ALL;
GRANT EXECUTE_CATALOG_ROLE TO C##CFLTUSER CONTAINER=ALL;
GRANT EXECUTE ON SYS.DBMS_LOGMNR   TO C##CFLTUSER CONTAINER=ALL;
GRANT EXECUTE ON SYS.DBMS_LOGMNR_D TO C##CFLTUSER CONTAINER=ALL;

-- XStream route (Oracle XStream CDC Source Premium): capture administrator
BEGIN
  DBMS_XSTREAM_AUTH.GRANT_ADMIN_PRIVILEGE(grantee => 'C##CFLTADMIN', privilege_type => 'CAPTURE',
                                          grant_select_privileges => TRUE, container => 'ALL');
END;
/
-- XStream needs the GoldenGate switch and a streams pool; both are instance-wide settings.
ALTER SYSTEM SET enable_goldengate_replication = TRUE SCOPE=BOTH;
ALTER SYSTEM SET streams_pool_size = 1G SCOPE=BOTH;

-- Outbound server over the benchmark tables (run after `python -m bench seed`), as C##CFLTADMIN
-- or as SYS:
DECLARE
  tables  DBMS_UTILITY.UNCL_ARRAY;
  schemas DBMS_UTILITY.UNCL_ARRAY;
BEGIN
  tables(1) := 'C##TAPDATA.BENCH_CUSTOMERS';
  tables(2) := 'C##TAPDATA.BENCH_ORDERS';
  tables(3) := 'C##TAPDATA.BENCH_LINES';
  schemas(1) := NULL;
  DBMS_XSTREAM_ADM.CREATE_OUTBOUND(server_name => 'xout', capture_name => 'xcap',
                                   table_names => tables, schema_names => schemas);
  DBMS_XSTREAM_ADM.ALTER_OUTBOUND(server_name => 'xout', connect_user => 'C##CFLTUSER');
END;
/
