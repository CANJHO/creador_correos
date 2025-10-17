import streamlit as st
import pandas as pd
import hashlib
import unicodedata
import re
from io import BytesIO

st.set_page_config(page_title="Generador de Correos - Autonoma de Ica", page_icon="📧", layout="wide")

# ------------------ Utilidades ------------------
DOMAIN_DEFAULT = "autonomadeica.edu.pe"

def remove_accents(s: str) -> str:
    if s is None:
        return ""
    s = str(s)
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))

def normalize_text(s: str) -> str:
    s = remove_accents(s).lower()
    s = s.replace("’", "").replace("'", "")
    s = re.sub(r"[^a-z0-9.]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def slug_inicial_apellido(nombres: str, ap_paterno: str, max_len: int = 15) -> str:
    n = normalize_text(nombres)
    a = normalize_text(ap_paterno)
    first_token = n.split(" ")[0] if n else "alumno"
    first_char = first_token[0] if first_token else "a"
    apellido = a.replace(" ", "") if a else "sinapellido"
    slug = (first_char + apellido)[:max_len]
    return slug

def slug_nombre_apellido(nombres: str, ap_paterno: str, max_len: int = 30) -> str:
    n = normalize_text(nombres)
    a = normalize_text(ap_paterno)
    first_token = n.split(" ")[0] if n else "alumno"
    apellido = a.split(" ")[0] if a else "sinapellido"
    base = f"{first_token}.{apellido}"
    base = base[:max_len]
    return base

def sha1_hex(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest().lower()

def base36_encode(num: int) -> str:
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    if num == 0:
        return "0"
    sign = ""
    if num < 0:
        sign = "-"
        num = -num
    out = []
    while num:
        num, r = divmod(num, 36)
        out.append(chars[r])
    return sign + "".join(reversed(out))

# --- Selección del ID estable según ROL ---
def elegir_id_estable(rol: str, codigo_alumno: str = "", dni: str = "") -> str:
    # Estudiante: prioriza código; Admin/Docente: prioriza DNI
    rol = (rol or "").strip()
    codigo_alumno = (codigo_alumno or "").strip()
    dni = (dni or "").strip()

    if rol == "Estudiante (E)":
        if codigo_alumno:
            return f"ALU:{codigo_alumno}"
        elif dni:
            return f"DNI:{dni}"
    else:  # Administrativo (AD) o Docente (D)
        if dni:
            return f"DNI:{dni}"
        elif codigo_alumno:
            return f"ALU:{codigo_alumno}"

    return "NOID"

def sufijo_sha1_hex_last(stable_id: str, last_n: int = 5) -> str:
    h = sha1_hex(stable_id if stable_id else "NOID")
    return h[-last_n:]

def sufijo_sha1_base36_last(stable_id: str, last_n: int = 5) -> str:
    h = sha1_hex(stable_id if stable_id else "NOID")
    val = int(h, 16)
    b36 = base36_encode(val)
    return b36[-last_n:]

def construir_email_localpart(formato: str, rol: str, nombres: str, ap_paterno: str, codigo_alumno: str, dni: str) -> str:
    # formatos: 'legible_hex', 'legible_b36', 'nombre_apellido_b36'
    stable_id = elegir_id_estable(rol, codigo_alumno, dni)

    if formato == "legible_hex":
        slug = slug_inicial_apellido(nombres, ap_paterno, max_len=15)
        suf = sufijo_sha1_hex_last(stable_id, last_n=5)
        return f"{slug}.{suf}"
    elif formato == "legible_b36":
        slug = slug_inicial_apellido(nombres, ap_paterno, max_len=15)
        suf = sufijo_sha1_base36_last(stable_id, last_n=5)
        return f"{slug}.{suf}"
    elif formato == "nombre_apellido_b36":
        slug = slug_nombre_apellido(nombres, ap_paterno, max_len=30)
        suf = sufijo_sha1_base36_last(stable_id, last_n=5)
        return f"{slug}.{suf}"
    else:
        return "invalid"

def aplicar_rol_suffix(localpart: str, rol: str) -> str:
    suf = {"Estudiante (E)": "E", "Administrativo (AD)": "AD", "Docente (D)": "D"}.get(rol, "")
    return f"{localpart}{suf}"

# ------------------ UI ------------------
st.title("📧 Generador de Correos Institucionales")
st.caption("Universidad Autónoma de Ica — sufijo determinístico + marca de rol (E, AD, D).")

with st.expander("ℹ️ Instrucciones rápidas", expanded=True):
    st.markdown("""
    1) Descarga la **plantilla** y llénala con los datos requeridos.  
    2) Sube el archivo.  
    3) Elige el **tipo de usuario** para este lote (E, AD o D).  
    4) Elige el **modo**: mostrar los **tres formatos (demo)** o **uno específico**.  
    5) Descarga el resultado en CSV o Excel.
    """)

domain = st.text_input("Dominio", value=DOMAIN_DEFAULT, help="Dominio para el correo institucional")
rol = st.selectbox("Tipo de usuario para este lote", ["Estudiante (E)", "Administrativo (AD)", "Docente (D)"])
if rol == "Estudiante (E)":
    st.info("Para **Estudiante (E)**, se usa **Código de Alumno** (si falta, se usa DNI).")
else:
    st.info("Para **Administrativo (AD)** o **Docente (D)**, se usa **DNI** (si falta, se usa Código de Alumno).")

modo = st.radio("Modo de salida", ["Mostrar los 3 formatos (presentación)", "Solo 1 formato"])

formato_unico = None
if modo == "Solo 1 formato":
    formato_unico = st.selectbox(
        "Elige el formato único",
        [
            "Formato legible + sufijo (SHA1 hex last 5)",
            "Formato legible + sufijo base36 (last 5)",
            "Nombre.apellido + sufijo base36 (last 5)",
        ],
    )

st.divider()

st.subheader("📥 Subida de archivo")
st.write("Sube un **Excel (.xlsx)** o **CSV** con columnas: `Nombres`, `ApellidoPaterno`, `ApellidoMaterno` (opcional), `CodigoAlumno`, `DNI`.")

# Plantilla descargable
template_df = pd.DataFrame([
    {"Nombres":"Jhony Freddy", "ApellidoPaterno":"Canchari", "ApellidoMaterno":"Barrios", "CodigoAlumno":"A191000173", "DNI":"44823948"}
])
bio_template = BytesIO()
with pd.ExcelWriter(bio_template, engine="openpyxl") as writer:
    template_df.to_excel(writer, index=False, sheet_name="Plantilla")
bio_template.seek(0)
st.download_button("⬇️ Descargar plantilla (Excel)", data=bio_template, file_name="plantilla_correos.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

uploaded = st.file_uploader("Arrastra o selecciona tu archivo (.xlsx o .csv)", type=["xlsx", "csv"])

def leer_archivo(uploaded_file) -> pd.DataFrame | None:
    if uploaded_file is None:
        return None
    name = uploaded_file.name.lower()
    try:
        if name.endswith(".xlsx"):
            return pd.read_excel(uploaded_file)
        elif name.endswith(".csv"):
            return pd.read_csv(uploaded_file)
        else:
            st.error("Formato no soportado. Sube .xlsx o .csv")
            return None
    except Exception as e:
        st.error(f"Error leyendo archivo: {e}")
        return None

df = leer_archivo(uploaded)

def validar_fila_por_rol(row, rol: str) -> str | None:
    codigo = str(row.get("CodigoAlumno", "") or "").strip()
    dni = str(row.get("DNI", "") or "").strip()
    if rol == "Estudiante (E)":
        if not codigo and not dni:
            return "Falta Código de Alumno y DNI."
    else:
        if not dni and not codigo:
            return "Falta DNI y Código de Alumno."
    return None

if df is not None:
    expected_cols = {"Nombres", "ApellidoPaterno", "CodigoAlumno", "DNI"}
    missing = expected_cols - set(df.columns)
    if missing:
        st.error(f"Faltan columnas: {', '.join(sorted(missing))}")
    else:
        # Validación por rol
        errores = []
        for idx, row in df.iterrows():
            msg = validar_fila_por_rol(row, rol)
            if msg:
                errores.append(f"Fila {idx+1}: {msg}")

        if errores:
            st.error("No se puede continuar. Corrige estas filas:\n- " + "\n- ".join(errores))
        else:
            st.success(f"Archivo cargado. Filas: {len(df)}")
            out = df.copy()

            def gen_legible_hex(row):
                local = construir_email_localpart("legible_hex", rol, row.get("Nombres",""), row.get("ApellidoPaterno",""), str(row.get("CodigoAlumno","")), str(row.get("DNI","")))
                return aplicar_rol_suffix(local, rol) + "@" + domain

            def gen_legible_b36(row):
                local = construir_email_localpart("legible_b36", rol, row.get("Nombres",""), row.get("ApellidoPaterno",""), str(row.get("CodigoAlumno","")), str(row.get("DNI","")))
                return aplicar_rol_suffix(local, rol) + "@" + domain

            def gen_nombre_apellido_b36(row):
                local = construir_email_localpart("nombre_apellido_b36", rol, row.get("Nombres",""), row.get("ApellidoPaterno",""), str(row.get("CodigoAlumno","")), str(row.get("DNI","")))
                return aplicar_rol_suffix(local, rol) + "@" + domain

            if modo == "Mostrar los 3 formatos (presentación)":
                out["Correo_legible_hex"] = df.apply(gen_legible_hex, axis=1)
                out["Correo_legible_base36"] = df.apply(gen_legible_b36, axis=1)
                out["Correo_nombre_apellido_base36"] = df.apply(gen_nombre_apellido_b36, axis=1)
                vista_cols = ["Nombres","ApellidoPaterno","ApellidoMaterno","CodigoAlumno","DNI","Correo_legible_hex","Correo_legible_base36","Correo_nombre_apellido_base36"]
            else:
                if formato_unico == "Formato legible + sufijo (SHA1 hex last 5)":
                    out["Correo"] = df.apply(gen_legible_hex, axis=1)
                elif formato_unico == "Formato legible + sufijo base36 (last 5)":
                    out["Correo"] = df.apply(gen_legible_b36, axis=1)
                else:
                    out["Correo"] = df.apply(gen_nombre_apellido_b36, axis=1)
                vista_cols = ["Nombres","ApellidoPaterno","ApellidoMaterno","CodigoAlumno","DNI","Correo"]

            st.subheader("👀 Vista previa")
            st.dataframe(out[vista_cols].head(50), use_container_width=True)

            csv_data = out[vista_cols].to_csv(index=False).encode("utf-8")
            st.download_button("💾 Descargar CSV", data=csv_data, file_name="correos_generados.csv", mime="text/csv")

            xls_buf = BytesIO()
            with pd.ExcelWriter(xls_buf, engine="openpyxl") as writer:
                out[vista_cols].to_excel(writer, index=False, sheet_name="Correos")
            xls_buf.seek(0)
            st.download_button("💾 Descargar Excel (.xlsx)", data=xls_buf, file_name="correos_generados.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

st.sidebar.markdown("### Acerca de")
st.sidebar.write("Genera correos únicos con sufijo determinístico según rol.")
st.sidebar.write("Prioridad de ID: Estudiante → Código; AD/Docente → DNI.")
st.sidebar.write("Formatos:")
st.sidebar.write("- Inicial+Apellido + sufijo (SHA1 hex last 5)")
st.sidebar.write("- Inicial+Apellido + sufijo (SHA1 base36 last 5)")
st.sidebar.write("- Nombre.Apellido + sufijo (SHA1 base36 last 5)")
st.sidebar.caption("© 2025 — Chat Gpt ++ NW")
