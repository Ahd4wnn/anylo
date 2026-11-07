-- Run as a Postgres superuser. Passwords come from psql variables, never from git:
--   psql -U postgres -v owner_pw='...' -v app_pw='...' -f scripts/setup_roles.sql
CREATE ROLE anylo_owner LOGIN PASSWORD :'owner_pw';
CREATE ROLE anylo_app LOGIN PASSWORD :'app_pw' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
CREATE DATABASE anylo OWNER anylo_owner;
CREATE DATABASE anylo_test OWNER anylo_owner;

\c anylo
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
GRANT CONNECT ON DATABASE anylo TO anylo_app;

\c anylo_test
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
GRANT CONNECT ON DATABASE anylo_test TO anylo_app;
