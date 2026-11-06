CREATE OR REPLACE FUNCTION raw_vault.sha256_key(
    VARIADIC p_values TEXT[]
)
RETURNS CHAR(64)
LANGUAGE SQL
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT encode(
        digest(
            convert_to(
                jsonb_build_array(VARIADIC p_values)::TEXT,
                'UTF8'
            ),
            'sha256'
        ),
        'hex'
    )::CHAR(64);
$$;