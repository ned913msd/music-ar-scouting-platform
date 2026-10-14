"""
🧠 Capa de consultas SQL avanzadas del dashboard (DuckDB).

Idea central (la lección del decano): mover la carga de trabajo de la
memoria de Python al motor de datos. El DataFrame del runtime se registra
como vista temporal UNA vez y los filtros/agregaciones viajan como query.

Conceptos aplicados aquí:
  * WHERE parametrizado con `?` — los widgets del sidebar se bindean como
    parámetros (sin concatenar strings: sin SQL injection).
  * list_contains(?, col) — equivalente a pandas .isin([...]) para listas.
  * GROUP BY + HAVING — resumen por género solo donde hay suficiente data.
  * CASE + SUM/AVG/MEDIAN — lógica condicional y agregaciones en el motor.
"""


def _registrar(con, df, nombre):
    """Publica un DataFrame como vista temporal en la conexión del proceso."""
    con.register(nombre, df)
    return nombre


def filtrar_artistas(
    df,
    con,
    *,
    recomendaciones,
    score_min,
    fans_min,
    fans_max,
    prob_min,
    generos=None,
    paises=None,
    solo_ventana=False,
    favoritos=None,
):
    """Filtros de Scouting ejecutados por DuckDB (reemplazan el .isin() pandas).

    Devuelve las mismas filas que el filtrado booleano clásico:
      * recomendaciones: lista (puede estar vacía -> 0 filas, como en pandas)
      * generos/paises: solo aplican si la lista no está vacía
      * prob_min: COALESCE para que los NaN cuenten como 0 (igual que pandas)
      * favoritos: lista solo si el checkbox está activo (None = sin filtrar)
    """
    vista = _registrar(con, df, "df_scouting")

    conds = [
        "list_contains(?, ar_recommendation)",
        "scouting_score >= ?",
        "deezer_fans BETWEEN ? AND ?",
        "COALESCE(prob_breakout_6m, 0) >= ?",
    ]
    params = [
        list(recomendaciones),
        float(score_min),
        int(fans_min),
        int(fans_max),
        float(prob_min),
    ]

    if generos:
        conds.append("list_contains(?, CAST(genero AS VARCHAR))")
        params.append(list(generos))
    if paises:
        conds.append("list_contains(?, CAST(pais_origen AS VARCHAR))")
        params.append(list(paises))
    if solo_ventana:
        conds.append("mes_optimo_firma IS NOT NULL")
    if favoritos is not None:
        conds.append("list_contains(?, artist_name)")
        params.append(list(favoritos))

    sql = (
        f"SELECT * FROM {vista}\n"
        "WHERE " + "\n  AND ".join(conds) + "\n"
        "ORDER BY scouting_score DESC"
    )
    return con.execute(sql, params).df()


def resumen_por_genero(con, df, min_artistas=None):
    """Resumen ejecutivo por género: GROUP BY + HAVING + CASE.

    min_artistas: si se pasa, activa `HAVING COUNT(artist_name) > ?` (solo
    géneros con suficiente data — la cláusula HAVING filtra DESPUÉS de
    agrupar, a diferencia de WHERE que filtra ANTES).
    """
    vista = _registrar(con, df, "df_genero")

    having = ""
    params = []
    if min_artistas is not None:
        having = "HAVING COUNT(artist_name) > ?"
        params.append(int(min_artistas))

    sql = f"""
        WITH filtrado AS (
            SELECT artist_name, genero, scouting_score, deezer_fans,
                   prob_breakout_6m
            FROM {vista}
            WHERE genero IS NOT NULL
        ),
        resumen AS (
            SELECT
                genero,
                COUNT(artist_name)                         AS total_artistas,
                ROUND(AVG(scouting_score), 1)              AS score_promedio,
                CAST(ROUND(MEDIAN(deezer_fans)) AS BIGINT) AS fans_mediana,
                SUM(CASE WHEN prob_breakout_6m >= 50
                         THEN 1 ELSE 0 END)                AS firma_inmediata
            FROM filtrado
            GROUP BY genero
            {having}
        )
        SELECT * FROM resumen
        ORDER BY fans_mediana DESC NULLS LAST, total_artistas DESC
    """
    return con.execute(sql, params).df()
