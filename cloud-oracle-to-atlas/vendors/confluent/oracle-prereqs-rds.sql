-- Oracle-side prerequisites for the Confluent Oracle XStream CDC Source connector on
-- Amazon RDS for Oracle 19c (non-CDB). Follow Confluent's prerequisites page for the
-- current version of these steps; this file records what this benchmark ran.
--
-- Instance settings (console or CLI, not SQL):
--   backup retention > 0 days            (keeps the database in ARCHIVELOG mode)
--   parameter group: enable_goldengate_replication = true
--   security group: Confluent Cloud egress IPs, the benchmark host, the other products' egress IPs

-- 1. As the RDS master user --------------------------------------------------------
EXEC rdsadmin.rdsadmin_util.set_configuration('archivelog retention hours', '24');
COMMIT;
EXEC rdsadmin.rdsadmin_util.alter_supplemental_logging(p_action => 'ADD');

CREATE TABLESPACE xstream_adm_tbs DATAFILE SIZE 25M AUTOEXTEND ON MAXSIZE UNLIMITED;
CREATE TABLESPACE xstream_tbs     DATAFILE SIZE 25M AUTOEXTEND ON MAXSIZE UNLIMITED;

-- the benchmark schema owner (seeded by `python -m bench seed`)
CREATE USER bench IDENTIFIED BY "<redacted>" DEFAULT TABLESPACE users QUOTA UNLIMITED ON users;
GRANT CREATE SESSION, CREATE TABLE TO bench;

-- XStream administrator
CREATE USER cfltadmin IDENTIFIED BY "<redacted>" DEFAULT TABLESPACE xstream_adm_tbs QUOTA UNLIMITED ON xstream_adm_tbs;
GRANT CREATE SESSION TO cfltadmin;
BEGIN
  DBMS_XSTREAM_AUTH.GRANT_ADMIN_PRIVILEGE(grantee => 'cfltadmin', privilege_type => 'CAPTURE',
                                          grant_select_privileges => TRUE);
END;
/

-- connector connect user
CREATE USER cfltuser IDENTIFIED BY "<redacted>" DEFAULT TABLESPACE xstream_tbs QUOTA UNLIMITED ON xstream_tbs;
GRANT CREATE SESSION, SELECT_CATALOG_ROLE, SELECT ANY TABLE, LOCK ANY TABLE, FLASHBACK ANY TABLE TO cfltuser;

-- 2. After `python -m bench seed --supplemental-logging` has created BENCH_* with ALL COLUMNS
--    supplemental logging, as cfltadmin: create the outbound server --------------------
DECLARE
  tables DBMS_UTILITY.UNCL_ARRAY;
  schemas DBMS_UTILITY.UNCL_ARRAY;
BEGIN
  tables(1) := 'BENCH.BENCH_CUSTOMERS';
  tables(2) := 'BENCH.BENCH_ORDERS';
  tables(3) := 'BENCH.BENCH_LINES';
  schemas(1) := NULL;
  DBMS_XSTREAM_ADM.CREATE_OUTBOUND(server_name => 'xout', capture_name => 'xcap',
                                   table_names => tables, schema_names => schemas);
END;
/
-- as the master user: let the connect user attach to the outbound server
BEGIN
  DBMS_XSTREAM_ADM.ALTER_OUTBOUND(server_name => 'xout', connect_user => 'cfltuser');
END;
/
