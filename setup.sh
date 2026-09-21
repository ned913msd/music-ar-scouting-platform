#!/bin/bash
# ============================================================================
# setup.sh — Music A&R Data Product | Configuración del entorno de desarrollo
# Crea el entorno virtual 'venv' e instala las dependencias de requirements.txt
# (dbt-core, dbt-duckdb, duckdb, pandas, numpy, streamlit).
#
# NOTA de compatibilidad: dbt aún no soporta Python >= 3.13, por lo que el
# script elige automáticamente la mejor versión disponible (3.12 → 3.11 → 3.10).
#
# Uso:  bash setup.sh    (desde la raíz del repositorio)
# ============================================================================

set -e
echo "🚀 Configurando entorno de desarrollo (Music A&R Data Product)..."

# Elegir un intérprete compatible con dbt (3.10–3.12), con fallback a python3/python.
# Se usa un array porque el comando puede tener argumentos ("py -V:3.10").
# La sintaxis 'py -V:3.x' cubre el launcher moderno de Windows; '-3.x' el clásico.
PY=()
for cand in "py -V:3.12" "py -3.12" "py -V:3.11" "py -3.11" "py -V:3.10" "py -3.10" "python3" "python"; do
    read -r -a words <<< "$cand"
    if command -v "${words[0]}" >/dev/null 2>&1 && "${words[@]}" --version >/dev/null 2>&1; then
        PY=("${words[@]}")
        break
    fi
done
if [ ${#PY[@]} -eq 0 ]; then
    echo "❌ No se encontró un intérprete de Python. Instala Python 3.10–3.12."
    exit 1
fi

PYVER=$("${PY[@]}" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
echo "   Usando Python $PYVER (comando: ${PY[*]})"
case "$PYVER" in
    3.13|3.14)
        echo "⚠️  Python $PYVER: dbt aún no lo soporta. Si falla el import de dbt,"
        echo "   instala Python 3.10–3.12 y vuelve a ejecutar este script."
        ;;
esac

rm -rf venv
"${PY[@]}" -m venv venv

# Ruta de activación según plataforma: venv/Scripts (Windows) o venv/bin (unix)
if [ -f venv/Scripts/activate ]; then
    ACTIVATE=venv/Scripts/activate
else
    ACTIVATE=venv/bin/activate
fi
# shellcheck disable=SC1091
source "$ACTIVATE"

python -m pip install --upgrade pip --quiet
pip install -r requirements.txt

echo "✅ ¡Listo! Ejecuta 'source $ACTIVATE' para comenzar."
