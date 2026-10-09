# JupyterLab con los drivers de PostgreSQL y Redis ya instalados.
# La imagen base incluye pandas, numpy, scipy, matplotlib, seaborn y SQLAlchemy.
FROM quay.io/jupyter/scipy-notebook:2026-07-28

COPY requirements.txt /tmp/requirements.txt

# Se instalan solo los drivers, con las mismas versiones que requirements.txt
RUN grep -E '^(psycopg2-binary|redis)==' /tmp/requirements.txt > /tmp/jupyter-extra.txt \
    && pip install --no-cache-dir -r /tmp/jupyter-extra.txt \
    && fix-permissions "${CONDA_DIR}" \
    && fix-permissions "/home/${NB_USER}"
