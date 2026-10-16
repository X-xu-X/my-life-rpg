-- 仅空 PG 卷初始化运行；密码值不进入 SQL 文本或仓库。
DO $body$
DECLARE
    secret text;
BEGIN
    secret := btrim(pg_read_file('/run/secrets/app_password'), E' \t\r\n');
    IF length(secret) NOT BETWEEN 24 AND 256 OR secret ~ '[^!-~]' THEN
        RAISE EXCEPTION 'APP_PASSWORD_FORMAT_INVALID';
    END IF;
    BEGIN
        EXECUTE format('CREATE ROLE gol_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L', secret);
    EXCEPTION WHEN OTHERS THEN
        RAISE EXCEPTION 'APP_ROLE_INITIALIZATION_FAILED';
    END;
END $body$;
ALTER DATABASE game_of_life OWNER TO gol_app;
ALTER SCHEMA public OWNER TO gol_app;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
