-- 仅空 PG 卷初始化运行；密码值不进入 SQL 文本或仓库。
DO $body$
BEGIN
    EXECUTE format('CREATE ROLE gol_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L',
        trim(pg_read_file('/run/secrets/app_password')));
END $body$;
ALTER DATABASE game_of_life OWNER TO gol_app;
ALTER SCHEMA public OWNER TO gol_app;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
