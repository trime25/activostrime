import streamlit as st
import sqlite3
import pandas as pd
import os
import base64
from datetime import datetime

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="SISTEMA GESTIÓN TRIMECA", layout="wide", initial_sidebar_state="collapsed")

# Crear carpetas si no existen
for carpeta in ['fotos_activos', 'docs_activos']:
    if not os.path.exists(carpeta): os.makedirs(carpeta)

# --- BASE DE DATOS ---
def conectar_db():
    return sqlite3.connect('inventario.db', check_same_thread=False, timeout=30)

def inicializar_db():
    with conectar_db() as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS activos (
                        id TEXT PRIMARY KEY, descripcion TEXT, ubicacion TEXT, 
                        ultima_revision DATE, estado TEXT, modelo TEXT, 
                        marca TEXT, motivo_estado TEXT, categoria TEXT, pais TEXT)''')
        
        for col in ["categoria", "pais"]:
            try:
                c.execute(f"ALTER TABLE activos ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass

        c.execute('''CREATE TABLE IF NOT EXISTS fotos (id_activo TEXT, path TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS documentos (id_activo TEXT, path TEXT, nombre_real TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS ubicaciones (nombre TEXT PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS historial (id_activo TEXT, origen TEXT, destino TEXT, fecha TIMESTAMP, motivo TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS activos_eliminados (id TEXT, ubicacion TEXT, fecha_eliminacion TIMESTAMP, motivo TEXT)''')
        conn.commit()

inicializar_db()

# --- LISTAS DE DATOS ---
CATEGORIAS_LISTA = ["Maquinaria Pesada", "maquinaria ligera", "vehículos (flota)", "equipos industriales/planta", "equipos de T.I."]
PAISES_LISTA = ["VENEZUELA", "COLOMBIA", "ESTADOS UNIDOS"]

# --- FUNCIONES DE APOYO ---
def display_pdf(file_path):
    with open(file_path, "rb") as f:
        base64_pdf = base64.b64encode(f.read()).decode('utf-8')
    pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" type="application/pdf"></iframe>'
    st.markdown(pdf_display, unsafe_allow_html=True)

def guardar_archivos(id_activo, archivos, tipo):
    carpeta = 'fotos_activos' if tipo == 'foto' else 'docs_activos'
    with conectar_db() as conn:
        for idx, arc in enumerate(archivos):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            ext = os.path.splitext(arc.name)[1]
            ruta = os.path.join(carpeta, f"{id_activo}_{idx}_{timestamp}{ext}")
            with open(ruta, "wb") as f: f.write(arc.getbuffer())
            if tipo == 'foto': 
                conn.execute("INSERT INTO fotos (id_activo, path) VALUES (?,?)", (id_activo, ruta))
            else: 
                conn.execute("INSERT INTO documentos (id_activo, path, nombre_real) VALUES (?,?,?)", (id_activo, ruta, arc.name))
        conn.commit()

# --- DIÁLOGOS ---
@st.dialog("VISOR")
def visor_documento(path, nombre):
    st.write(f"### {nombre}")
    if path.lower().endswith('.pdf'): display_pdf(path)
    else: st.info("Vista previa solo disponible para archivos PDF.")
    with open(path, "rb") as f: 
        st.download_button("📥 DESCARGAR", f, file_name=nombre)

@st.dialog("CONFIRMAR ELIMINACIÓN DE ACTIVO")
def confirmar_eliminar_activo(activo_id):
    st.error(f"⚠️ ¿Está seguro de que desea eliminar permanentemente el activo **{activo_id}**?")
    if st.button("SÍ, ELIMINAR AHORA", use_container_width=True):
        with conectar_db() as conn:
            res = conn.execute("SELECT ubicacion FROM activos WHERE id=?", (activo_id,)).fetchone()
            ubi_act = res[0] if res else "DESCONOCIDA"
            conn.execute("""
                INSERT INTO activos_eliminados (id, ubicacion, fecha_eliminacion, motivo) 
                VALUES (?, ?, ?, ?)
            """, (activo_id, ubi_act, datetime.now(), "ELIMINACIÓN MANUAL"))
            conn.execute("DELETE FROM activos WHERE id=?", (activo_id,))
            conn.execute("DELETE FROM fotos WHERE id_activo=?", (activo_id,))
            conn.execute("DELETE FROM documentos WHERE id_activo=?", (activo_id,))
            conn.commit()
        st.success("Activo eliminado.")
        st.rerun()

@st.dialog("CONFIRMAR ELIMINACIÓN DE UBICACIÓN")
def confirmar_eliminacion_ubi(nombre_ubi):
    st.warning(f"¿Está seguro de que desea eliminar la ubicación: **{nombre_ubi}**?")
    if st.button("SÍ, ELIMINAR UBICACIÓN"):
        with conectar_db() as conn:
            conn.execute("DELETE FROM ubicaciones WHERE nombre=?", (nombre_ubi,))
            conn.commit()
        st.success("Ubicación eliminada.")
        st.rerun()

# --- NAVEGACIÓN ---
menu = st.sidebar.radio("MENÚ PRINCIPAL", ["DASHBOARD", "REGISTRAR ACTIVO", "TRASLADOS", "GESTIONAR UBICACIONES", "HISTORIAL ELIMINADOS"])

# ==========================================
# DASHBOARD
# ==========================================
if menu == "DASHBOARD":
    st.title("📊 ACTIVOS")
    with conectar_db() as conn:
        df = pd.read_sql_query("SELECT * FROM activos", conn)
        ubis = pd.read_sql_query("SELECT nombre FROM ubicaciones", conn)['nombre'].tolist()

    st.sidebar.header("FILTROS GENERALES")
    f_cat = st.sidebar.selectbox("CATEGORÍA", ["TODAS"] + CATEGORIAS_LISTA)
    f_est = st.sidebar.selectbox("ESTADO", ["TODOS", "OPERATIVO", "DAÑADO", "REPARACION"])
    f_ubi = st.sidebar.selectbox("UBICACIÓN", ["TODAS"] + ubis)
    f_busq = st.sidebar.text_input("BUSCAR POR ID O MARCA").upper()
    
    df_f = df.copy()
    if f_cat != "TODAS": df_f = df_f[df_f['categoria'] == f_cat]
    if f_est != "TODOS": df_f = df_f[df_f['estado'] == f_est]
    if f_ubi != "TODAS": df_f = df_f[df_f['ubicacion'] == f_ubi]
    if f_busq: 
        df_f = df_f[df_f['id'].str.contains(f_busq, na=False) | df_f['marca'].str.contains(f_busq, na=False)]
    
    # --- RESUMEN DE ACTIVOS POR PAÍS ---
    st.subheader("🌐 RESUMEN GLOBAL")
    c_res1, c_res2, c_res3, c_res4 = st.columns(4)
    c_res1.metric("TOTAL GLOBAL", len(df_f))
    c_res2.metric("VENEZUELA 🇻🇪", len(df_f[df_f['pais'] == "VENEZUELA"]))
    c_res3.metric("COLOMBIA 🇨🇴", len(df_f[df_f['pais'] == "COLOMBIA"]))
    c_res4.metric("ESTADOS UNIDOS 🇺🇸", len(df_f[df_f['pais'] == "ESTADOS UNIDOS"]))
    st.divider()

    # --- SECCIONES POR PAÍS ---
    tabs_paises = st.tabs(PAISES_LISTA)

    for i, pais_nombre in enumerate(PAISES_LISTA):
        with tabs_paises[i]:
            df_pais = df_f[df_f['pais'] == pais_nombre]
            
            if df_pais.empty:
                st.info(f"No hay activos registrados en {pais_nombre}.")
            
            for _, row in df_pais.iterrows():
                color = "🟢" if row['estado'] == "OPERATIVO" else "🔴" if row['estado'] == "DAÑADO" else "🟡"
                with st.expander(f"{color} ID: {row['id']} | {row['categoria']} | {row['marca']}"):
                    
                    if f"edit_{row['id']}" in st.session_state:
                        with st.form(f"form_edit_{row['id']}"):
                            st.subheader("✏️ EDITAR DETALLES")
                            c1, c2 = st.columns(2)
                            emarc = c1.text_input("MARCA", str(row['marca'] or "")).upper()
                            emod = c2.text_input("MODELO", str(row['modelo'] or "")).upper()
                            ecat = st.selectbox("CATEGORÍA", CATEGORIAS_LISTA, index=CATEGORIAS_LISTA.index(row['categoria']) if row['categoria'] in CATEGORIAS_LISTA else 0)
                            epais = st.selectbox("PAÍS", PAISES_LISTA, index=PAISES_LISTA.index(row['pais']) if row['pais'] in PAISES_LISTA else 0)
                            est_list = ["OPERATIVO", "DAÑADO", "REPARACION"]
                            eest = st.selectbox("ESTADO", est_list, index=est_list.index(row['estado']) if row['estado'] in est_list else 0)
                            
                            try: f_rev = datetime.strptime(str(row['ultima_revision']), '%Y-%m-%d').date()
                            except: f_rev = datetime.now().date()
                            erev = st.date_input("FECHA ÚLTIMA REVISIÓN", f_rev)
                            
                            # --- CAMBIO: CAMPO MOTIVO EN EDICIÓN ---
                            emot = st.text_input("MOTIVO / ESTADO", str(row['motivo_estado'] or "")).upper()
                            
                            eubi = st.selectbox("UBICACIÓN", ubis, index=ubis.index(row['ubicacion']) if row['ubicacion'] in ubis else 0)
                            edesc = st.text_area("DESCRIPCIÓN", str(row['descripcion'] or "")).upper()

                            st.write("---")
                            st.write("📂 **GESTIONAR ARCHIVOS ACTUALES**")
                            with conectar_db() as conn:
                                f_actuales = conn.execute("SELECT path FROM fotos WHERE id_activo=?", (row['id'],)).fetchall()
                                d_actuales = conn.execute("SELECT path, nombre_real FROM documentos WHERE id_activo=?", (row['id'],)).fetchall()
                            
                            del_files = []
                            col_f, col_d = st.columns(2)
                            with col_f:
                                for path in f_actuales:
                                    if st.checkbox(f"Eliminar {os.path.basename(path[0])}", key=f"del_f_{path[0]}"): del_files.append(("foto", path[0]))
                            with col_d:
                                for path, nom in d_actuales:
                                    if st.checkbox(f"Eliminar {nom}", key=f"del_d_{path}"): del_files.append(("doc", path))

                            new_f = st.file_uploader("Subir fotos adicionales", accept_multiple_files=True, key=f"new_f_{row['id']}")
                            new_d = st.file_uploader("Subir documentos adicionales", accept_multiple_files=True, key=f"new_d_{row['id']}")

                            if st.form_submit_button("💾 GUARDAR CAMBIOS"):
                                with conectar_db() as conn:
                                    # --- CAMBIO: UPDATE INCLUYENDO MOTIVO_ESTADO ---
                                    conn.execute("""UPDATE activos SET marca=?, modelo=?, estado=?, ubicacion=?, descripcion=?, categoria=?, ultima_revision=?, pais=?, motivo_estado=? WHERE id=?""", 
                                                 (emarc, emod, eest, eubi, edesc, ecat, erev, epais, emot, row['id']))
                                    for tipo, path in del_files:
                                        tabla = "fotos" if tipo == "foto" else "documentos"
                                        conn.execute(f"DELETE FROM {tabla} WHERE path=?", (path,))
                                        if os.path.exists(path): os.remove(path)
                                if new_f: guardar_archivos(row['id'], new_f, 'foto')
                                if new_d: guardar_archivos(row['id'], new_d, 'doc')
                                del st.session_state[f"edit_{row['id']}"]
                                st.rerun()
                        
                        if st.button("CANCELAR EDICIÓN", key=f"canc_{row['id']}"):
                            del st.session_state[f"edit_{row['id']}"]; st.rerun()

                    else:
                        col_img, col_info = st.columns([1, 1.2])
                        with col_img:
                            with conectar_db() as conn:
                                fotos = [f[0] for f in conn.execute("SELECT path FROM fotos WHERE id_activo=?", (row['id'],)).fetchall()]
                            if fotos:
                                idx = st.session_state.get(f"idx_{row['id']}", 0)
                                st.image(fotos[idx % len(fotos)], use_container_width=True)
                                ca, cb = st.columns(2)
                                if ca.button("⬅️", key=f"p_{row['id']}"): st.session_state[f"idx_{row['id']}"] = idx - 1; st.rerun()
                                if cb.button("➡️", key=f"n_{row['id']}"): st.session_state[f"idx_{row['id']}"] = idx + 1; st.rerun()
                            else: st.info("Sin fotos registradas.")

                        with col_info:
                            st.write(f"**PAÍS:** {row['pais']}")
                            st.write(f"**CATEGORÍA:** {row['categoria']}")
                            st.write(f"**MARCA:** {row['marca']} | **MODELO:** {row['modelo']}")
                            st.write(f"**ESTADO:** {row['estado']} | **UBICACIÓN:** {row['ubicacion']}")
                            st.write(f"**REVISIÓN:** {row['ultima_revision']}")
                            st.write("📄 **DOCUMENTOS**")
                            with conectar_db() as conn:
                                docs = conn.execute("SELECT path, nombre_real FROM documentos WHERE id_activo=?", (row['id'],)).fetchall()
                            for i, (d_path, d_nom) in enumerate(docs):
                                if st.button(f"👁️ Ver {d_nom}", key=f"v_{d_path}_{i}"): visor_documento(d_path, d_nom)
                        
                        st.divider()
                        c_b1, c_b2 = st.columns(2)
                        if c_b1.button("✏️ EDITAR ACTIVO", key=f"btn_ed_{row['id']}", use_container_width=True): 
                            st.session_state[f"edit_{row['id']}"] = True
                            st.rerun()
                        if c_b2.button("🗑️ ELIMINAR ACTIVO", key=f"btn_del_{row['id']}", use_container_width=True):
                            confirmar_eliminar_activo(row['id'])

# (El resto del código: REGISTRO, TRASLADOS, UBICACIONES e HISTORIAL permanecen iguales)
elif menu == "REGISTRAR ACTIVO":
    st.title("📝 REGISTRO")
    with conectar_db() as conn:
        ubis = pd.read_sql_query("SELECT nombre FROM ubicaciones", conn)['nombre'].tolist()
    
    with st.container(border=True):
        if not ubis: st.warning("DEBE CREEAR UNA UBICACION PRIMERO.")
        rid = st.text_input("ID ACTIVO*").upper()
        c_p1, c_p2 = st.columns(2)
        rcat = c_p1.selectbox("CATEGORÍA*", CATEGORIAS_LISTA)
        rpais = c_p2.selectbox("PAÍS*", PAISES_LISTA)
        c1, c2 = st.columns(2)
        rmarc = c1.text_input("MARCA").upper()
        rmod = c2.text_input("MODELO").upper()
        rubi = c1.selectbox("UBICACIÓN", ubis) 
        rest = c2.selectbox("ESTADO", ["OPERATIVO", "DAÑADO", "REPARACION"])
        rmot = st.text_input("MOTIVO DE TRASLADO / DAÑO*").upper() if rest in ["DAÑADO", "REPARACION"] else ""
        rdesc = st.text_area("DESCRIPCIÓN").upper()
        col_f, col_d = st.columns(2)
        rfotos = col_f.file_uploader("🖼️ SUBIR FOTOS", accept_multiple_files=True, type=['png','jpg','jpeg'])
        rdocs = col_d.file_uploader("📄 SUBIR DOCUMENTOS", accept_multiple_files=True)
        if st.button("💾 REGISTRAR ACTIVO", use_container_width=True):
            if rid and rubi and rcat and rpais and (rest == "OPERATIVO" or rmot):
                with conectar_db() as conn:
                    conn.execute("""INSERT INTO activos (id, marca, modelo, ubicacion, estado, motivo_estado, descripcion, ultima_revision, categoria, pais) 
                                 VALUES (?,?,?,?,?,?,?,?,?,?)""", 
                                 (rid, rmarc, rmod, rubi, rest, rmot, rdesc, datetime.now().date(), rcat, rpais))
                if rfotos: guardar_archivos(rid, rfotos, 'foto')
                if rdocs: guardar_archivos(rid, rdocs, 'doc')
                st.success(f"Activo {rid} guardado correctamente."); st.rerun()
            else: st.error("Faltan campos obligatorios (*)")

elif menu == "TRASLADOS":
    st.title("🚚 TRASLADOS")
    with conectar_db() as conn:
        activos = pd.read_sql_query("SELECT id, ubicacion FROM activos", conn)
        ubis = pd.read_sql_query("SELECT nombre FROM ubicaciones", conn)['nombre'].tolist()
    if not activos.empty:
        sel = st.selectbox("SELECCIONE ACTIVO", activos['id'])
        u_orig = activos[activos['id'] == sel]['ubicacion'].values[0]
        st.info(f"📍 UBICACIÓN ACTUAL: **{u_orig}**")
        u_dest = st.selectbox("SELECCIONE DESTINO", ubis)
        mot = st.text_input("MOTIVO DEL TRASLADO").upper()
        if st.button("EJECUTAR TRASLADO", use_container_width=True):
            if u_orig != u_dest:
                with conectar_db() as conn:
                    conn.execute("UPDATE activos SET ubicacion=? WHERE id=?", (u_dest, sel))
                    conn.execute("INSERT INTO historial VALUES (?,?,?,?,?)", (sel, u_orig, u_dest, datetime.now(), mot))
                    conn.commit()
                st.success(f"Activo {sel} trasladado a {u_dest}"); st.rerun()
            else: st.error("El destino debe ser diferente al origen.")
    st.write("---")
    st.write("### HISTORIAL DE MOVIMIENTOS")
    with conectar_db() as conn:
        st.dataframe(pd.read_sql_query("SELECT * FROM historial ORDER BY fecha DESC", conn), use_container_width=True)

elif menu == "GESTIONAR UBICACIONES":
    st.title("📍 UBICACIONES")
    nubi = st.text_input("NOMBRE DE NUEVA UBICACIÓN").upper()
    if st.button("AÑADIR"):
        if nubi:
            with conectar_db() as conn:
                try: conn.execute("INSERT INTO ubicaciones VALUES (?)", (nubi,)); conn.commit(); st.success("Añadida")
                except: st.error("Esta ubicación ya existe.")
            st.rerun()
    with st.container(border=True):
        st.subheader("LISTADO REGISTRADO")
        with conectar_db() as conn:
            for r in conn.execute("SELECT * FROM ubicaciones").fetchall():
                c1, c2 = st.columns([4,1])
                c1.write(f"🏢 {r[0]}")
                if c2.button("🗑️", key=f"del_u_{r[0]}"):
                    cant = conn.execute("SELECT COUNT(*) FROM activos WHERE ubicacion=?", (r[0],)).fetchone()[0]
                    if cant > 0: st.error(f"No se puede eliminar: tiene {cant} activo(s) asociados.")
                    else: confirmar_eliminacion_ubi(r[0])

elif menu == "HISTORIAL ELIMINADOS":
    st.title("🗑️ ACTIVOS ELIMINADOS")
    with conectar_db() as conn:
        st.dataframe(pd.read_sql_query("SELECT * FROM activos_eliminados ORDER BY fecha_eliminacion DESC", conn), use_container_width=True)










