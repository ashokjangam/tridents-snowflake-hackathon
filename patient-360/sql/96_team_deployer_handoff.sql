-- Teammate deployer grants. Run as ACCOUNTADMIN after 90_roles_grants.sql.
-- Safe to re-run; it does not drop or replace the app.
--
-- Assigns PATIENT_360_ADMIN to the named teammates. Does not grant ACCOUNTADMIN.
-- Warehouse and schema privileges are in 90_roles_grants.sql.

USE ROLE ACCOUNTADMIN;

GRANT ROLE PATIENT_360_ADMIN TO USER ASHOK;
GRANT ROLE PATIENT_360_ADMIN TO USER SAINATH;
GRANT ROLE PATIENT_360_ADMIN TO USER SIDHARTH;

-- Repeat the deploy privileges from 90_roles_grants.sql so this handoff still
-- applies them when 90 was run before CREATE STAGE and CREATE STREAMLIT were added.
GRANT CREATE STAGE, CREATE STREAMLIT
    ON SCHEMA PATIENT_360.CORE TO ROLE PATIENT_360_ADMIN;

SHOW GRANTS TO ROLE PATIENT_360_ADMIN;
SHOW GRANTS TO USER ASHOK;
SHOW GRANTS TO USER SAINATH;
SHOW GRANTS TO USER SIDHARTH;
