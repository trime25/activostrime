import streamlit as st
import sqlite3
import pandas as pd
import os
import plotly.express as px 
from datetime import datetime

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="SISTEMA DE GESTIÓN INDUSTRIAL", layout="wide")

for carpeta in ['imagenes_activos', 'codigos_qr']:
    if not os.path.exists(carpeta): os.makedirs(carpeta)

# --- BASE DE DATOS ---
def conectar_db():
    return sqlite3.connect('inventario.db', check_same_thread=False)

def inicializar_db():
    with conectar_db() as conn:
        c = conn.cursor()
        # Definición de 11 columnas
        c.execute('''CREATE TABLE IF NOT EXISTS activos (
                        id TEXT PRIMARY KEY, nombre TEXT, descripcion TEXT, 
                        ubicacion TEXT, ultima_revision DATE, imagen_path TEXT, 
                        qr_path TEXT, estado TEXT, modelo TEXT, marca TEXT, motivo_estado TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS historial (
                        id_activo TEXT, origen TEXT, destino TEXT, 
                        fecha TIMESTAMP, motivo TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS ubicaciones (nombre TEXT PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS activos_eliminados (
                        id TEXT, nombre TEXT, ubicacion TEXT, 
                        fecha_eliminacion TIMESTAMP, motivo TEXT)''')
        conn.commit()

inicializar_db()

# --- FUNCIONES ---
def generar_qr(id_activo):
    qr = qrcode.make(id_activo)
    path = f"codigos_qr/qr_{id_activo}.png"
    qr.save(path)
    return path

# --- DIÁLOGOS ---
@st.dialog("AMPLIACIÓN DE IMAGEN")
def mostrar_zoom(img_path, nombre):
    st.write(f"### {nombre}")
    st.image(img_path, use_container_width=True)

@st.dialog("ELIMINAR ACTIVO")
def confirmar_eliminacion(activo_row):
    st.error(f"⚠️ ATENCIÓN: VA A ELIMINAR EL ACTIVO {activo_row['id']}")
    motivo = st.text_input("INDIQUE EL MOTIVO DE ELIMINACIÓN:").upper()
    if st.button("CONFIRMAR Y REGISTRAR"):
        if motivo:
            with conectar_db() as conn:
                conn.execute("INSERT INTO activos_eliminados VALUES (?,?,?,?,?)",
                         (activo_row['id'], activo_row['nombre'], activo_row['ubicacion'], datetime.now(), motivo))
                conn.execute("DELETE FROM activos WHERE id=?", (activo_row['id'],))
                conn.commit()
            st.success("ACTIVO ELIMINADO")
            st.rerun()

# --- NAVEGACIÓN ---
menu = st.sidebar.radio("MENÚ PRINCIPAL", 
    ["DASHBOARD", "REGISTRAR ACTIVO", "TRASLADOS", "GESTIONAR UBICACIONES", "HISTORIAL ELIMINADOS", "ESTADÍSTICAS"])

# ==========================================
# DASHBOARD
# ==========================================
if menu == "DASHBOARD":
    st.title("🏭 PANEL DE CONTROL")
    with conectar_db() as conn:
        df = pd.read_sql_query("SELECT * FROM activos", conn)
        list_ubis = pd.read_sql_query("SELECT nombre FROM ubicaciones", conn)['nombre'].tolist()

    # 3. Mostrar cantidad total de activos
    st.metric("TOTAL DE ACTIVOS EN INVENTARIO", len(df))

    st.sidebar.header("FILTROS")
    f_estado = st.sidebar.selectbox("POR ESTADO", ["TODOS", "OPERATIVO", "DAÑADO", "REPARACION"])
    f_ubi = st.sidebar.selectbox("POR UBICACIÓN", ["TODAS"] + list_ubis)
    f_busq = st.sidebar.text_input("BUSCAR (NOMBRE/ID/MARCA)").upper()

    df_f = df.copy()
    if f_estado != "TODOS": df_f = df_f[df_f['estado'] == f_estado]
    if f_ubi != "TODAS": df_f = df_f[df_f['ubicacion'] == f_ubi]
    if f_busq: 
        df_f = df_f[df_f['nombre'].str.contains(f_busq, na=False) | 
                    df_f['id'].str.contains(f_busq, na=False) | 
                    df_f['marca'].str.contains(f_busq, na=False)]

    for _, row in df_f.iterrows():
        tag = "🟢" if row['estado'] == "OPERATIVO" else "🟡" if row['estado'] == "REPARACION" else "🔴"
        color_t = "green" if row['estado'] == "OPERATIVO" else "orange" if row['estado'] == "REPARACION" else "red"
        
        with st.expander(f"{tag} {row['id']} - {row['nombre']} | {row['marca'] or ''} - {row['modelo'] or ''}"):
            
            if f"edit_mode_{row['id']}" in st.session_state:
                # FORMULARIO DE EDICIÓN REACTIVO (Sin st.form para permitir cambios dinámicos)
                with st.container(border=True):
                    st.write("### ✏️ MODIFICAR ACTIVO")
                    ce1, ce2 = st.columns(2)
                    # Corregido: str(val or "") evita error de AttributeError: 'NoneType'
                    enom = ce1.text_input("NOMBRE", str(row['nombre'] or "")).upper()
                    emarc = ce1.text_input("MARCA", str(row['marca'] or "")).upper()
                    emod = ce2.text_input("MODELO", str(row['modelo'] or "")).upper()
                    
                    # Corregido: Manejo de error si el estado antiguo no existe en la lista nueva
                    lista_estados = ["OPERATIVO", "DAÑADO", "REPARACION"]
                    estado_actual = row['estado'] if row['estado'] in lista_estados else "OPERATIVO"
                    eest = ce2.selectbox("ESTADO", lista_estados, index=lista_estados.index(estado_actual), key=f"st_{row['id']}")
                    
                    edesc = st.text_area("DESCRIPCIÓN", str(row['descripcion'] or "")).upper()
                    
                    # Reactivo: Solo muestra motivo si es Dañado o Reparación
                    emot = str(row['motivo_estado'] or "")
                    if eest in ["DAÑADO", "REPARACION"]:
                        emot = st.text_area("MOTIVO DEL ESTADO*", emot).upper()

                    c_b1, c_b2 = st.columns(2)
                    if c_b1.button("💾 GUARDAR", key=f"sv_{row['id']}"):
                        with conectar_db() as conn:
                            conn.execute("""UPDATE activos SET nombre=?, marca=?, modelo=?, estado=?, 
                                         descripcion=?, motivo_estado=? WHERE id=?""",
                                         (enom, emarc, emod, eest, edesc, emot, row['id']))
                            conn.commit()
                        del st.session_state[f"edit_mode_{row['id']}"]
                        st.rerun()
                    if c_b2.button("❌ CANCELAR", key=f"cn_{row['id']}"):
                        del st.session_state[f"edit_mode_{row['id']}"]
                        st.rerun()
            else:
                # VISTA NORMAL
                c_img, c_info, c_acts = st.columns([1, 2, 1])
                with c_img:
                    if row['imagen_path'] and os.path.exists(row['imagen_path']):
                        st.image(row['imagen_path'], width=150)
                        # 1. Restablecer botón ZOOM
                        if st.button("🔍 ZOOM", key=f"z_{row['id']}"): mostrar_zoom(row['imagen_path'], row['nombre'])
                
                with c_info:
                    st.write(f"**MARCA:** {row['marca'] or 'N/A'}  |  **MODELO:** {row['modelo'] or 'N/A'}")
                    st.write(f"**UBICACIÓN:** {row['ubicacion']}")
                    st.write(f"**DESCRIPCIÓN:** {row['descripcion'] or 'S/D'}")
                    if row['estado'] in ["DAÑADO", "REPARACION"]:
                        st.error(f"**MOTIVO:** {row['motivo_estado'] or 'NO ESPECIFICADO'}")
                    
                    st.write(f"**📅 ÚLTIMA REVISIÓN:** {row['ultima_revision']}")
                    
                    # Botón para Actualizar Revisión
                    if st.button("🔄 ACTUALIZAR FECHA", key=f"rev_{row['id']}"):
                        st.session_state[f"date_pick_{row['id']}"] = True
                    
                    if f"date_pick_{row['id']}" in st.session_state:
                        nueva_f = st.date_input("SELECCIONE FECHA", datetime.now(), key=f"cal_{row['id']}")
                        if st.button("CONFIRMAR", key=f"conf_{row['id']}"):
                            with conectar_db() as conn:
                                conn.execute("UPDATE activos SET ultima_revision=? WHERE id=?", (nueva_f, row['id']))
                                conn.commit()
                            del st.session_state[f"date_pick_{row['id']}"]
                            st.rerun()

                with c_acts:
                    if st.button("✏️ MODIFICAR", key=f"ed_btn_{row['id']}", use_container_width=True):
                        st.session_state[f"edit_mode_{row['id']}"] = True
                        st.rerun()
                    if st.button("🗑️ ELIMINAR", key=f"dl_btn_{row['id']}", use_container_width=True):
                        confirmar_eliminacion(row)

# ==========================================
# REGISTRAR ACTIVO
# ==========================================
elif menu == "REGISTRAR ACTIVO":
    st.title("📝 REGISTRO DE ACTIVO")
    with conectar_db() as conn:
        ubis = pd.read_sql_query("SELECT nombre FROM ubicaciones", conn)['nombre'].tolist()

    with st.container(border=True):
        c1, c2 = st.columns(2)
        id_a = c1.text_input("CÓDIGO ÚNICO*").upper()
        nom = c1.text_input("NOMBRE DEL ACTIVO*").upper()
        marca_reg = c1.text_input("MARCA").upper()
        modelo_reg = c2.text_input("MODELO").upper()
        ubi_reg = c2.selectbox("UBICACIÓN", ubis) if ubis else c2.error("CREE UNA UBICACIÓN PRIMERO")
        
        est_reg = st.selectbox("ESTADO ACTUAL*", ["OPERATIVO", "DAÑADO", "REPARACION"])
        
        motivo_reg = ""
        if est_reg in ["DAÑADO", "REPARACION"]:
            motivo_reg = st.text_area("MOTIVO DEL ESTADO*").upper()
        
        desc_reg = st.text_area("DESCRIPCIÓN GENERAL").upper()
        foto_reg = st.file_uploader("FOTO DEL ACTIVO")
        
        # 4. Corrección de error de INSERT (Explicitando columnas)
        if st.button("💾 GUARDAR ACTIVO", use_container_width=True):
            if id_a and nom and ubi_reg:
                if est_reg in ["DAÑADO", "REPARACION"] and not motivo_reg:
                    st.error("DEBE INGRESAR EL MOTIVO")
                else:
                    with conectar_db() as conn:
                        check = conn.execute("SELECT id FROM activos WHERE id=?", (id_a,)).fetchone()
                        if check: st.error("CÓDIGO YA EXISTE")
                        else:
                            img_p = f"imagenes_activos/{id_a}.png" if foto_reg else ""
                            if foto_reg:
                                with open(img_p, "wb") as f: f.write(foto_reg.getbuffer())
                            qr_p = generar_qr(id_a)
                            # Se especifican las 11 columnas para evitar el error de OperationalError
                            conn.execute("""INSERT INTO activos (id, nombre, descripcion, ubicacion, ultima_revision, imagen_path, qr_path, estado, modelo, marca, motivo_estado) 
                                         VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                                (id_a, nom, desc_reg, ubi_reg, datetime.now().date(), img_p, qr_p, est_reg, modelo_reg, marca_reg, motivo_reg))
                            conn.commit()
                            st.success("ACTIVO REGISTRADO")
                            st.rerun()
            else: st.warning("ID, NOMBRE Y UBICACIÓN SON OBLIGATORIOS")

# ==========================================
# HISTORIAL ELIMINADOS
# ==========================================
elif menu == "HISTORIAL ELIMINADOS":
    st.title("🗑️ REGISTRO DE ELIMINADOS")
    with conectar_db() as conn:
        # 2. Ordenar de forma descendente (último eliminado arriba)
        query = "SELECT * FROM activos_eliminados ORDER BY fecha_eliminacion DESC"
        elims = pd.read_sql_query(query, conn)
    st.dataframe(elims, use_container_width=True)

# --- LAS SECCIONES TRASLADOS, UBICACIONES Y ESTADÍSTICAS SE MANTIENEN ---
elif menu == "TRASLADOS":
    st.title("🚚 MOVIMIENTOS")
    with conectar_db() as conn:
        activos = pd.read_sql_query("SELECT id, nombre, ubicacion FROM activos", conn)
        ubis = pd.read_sql_query("SELECT nombre FROM ubicaciones", conn)['nombre'].tolist()
    if not activos.empty:
        opcs = [f"{r['id']} | {r['nombre']}" for _, r in activos.iterrows()]
        sel = st.selectbox("ACTIVO", opcs)
        id_sel = sel.split(" | ")[0]
        u_orig = activos[activos['id'] == id_sel]['ubicacion'].values[0]
        c1, c2 = st.columns(2)
        u_dest = c1.selectbox("DESTINO", ubis, index=ubis.index(u_orig) if u_orig in ubis else 0)
        mot = c2.text_input("MOTIVO TRASLADO*").upper()
        if st.button("TRASLADAR"):
            if mot:
                with conectar_db() as conn:
                    conn.execute("UPDATE activos SET ubicacion=? WHERE id=?", (u_dest, id_sel))
                    conn.execute("INSERT INTO historial VALUES (?,?,?,?,?)", (id_sel, u_orig, u_dest, datetime.now(), mot))
                    conn.commit()
                st.rerun()
    st.subheader("📜 HISTORIAL")
    with conectar_db() as conn:
        st.dataframe(pd.read_sql_query("SELECT * FROM historial ORDER BY fecha DESC", conn), use_container_width=True)

elif menu == "GESTIONAR UBICACIONES":
    st.title("📍 UBICACIONES")
    nueva = st.text_input("NUEVA UBICACIÓN").upper()
    if st.button("AÑADIR"):
        if nueva:
            with conectar_db() as conn:
                try: conn.execute("INSERT INTO ubicaciones VALUES (?)", (nueva,)); conn.commit()
                except: st.error("EXISTE")
            st.rerun()
    with conectar_db() as conn:
        for _, u in pd.read_sql_query("SELECT * FROM ubicaciones", conn).iterrows():
            col1, col2 = st.columns([4,1])
            col1.write(f"• {u['nombre']}")
            if col2.button("BORRAR", key=u['nombre']):
                with conectar_db() as conn:
                    conn.execute("DELETE FROM ubicaciones WHERE nombre=?", (u['nombre'],))
                    conn.commit()
                st.rerun()

elif menu == "ESTADÍSTICAS":
    st.title("📊 ESTADÍSTICAS")
    with conectar_db() as conn:
        df = pd.read_sql_query("SELECT * FROM activos", conn)
    if not df.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("OPERATIVOS", len(df[df['estado'] == 'OPERATIVO']))
        c2.metric("DAÑADOS", len(df[df['estado'] == 'DAÑADO']))
        c3.metric("REPARACIÓN", len(df[df['estado'] == 'REPARACION']))
        fig = px.pie(df, names='estado', color='estado', color_discrete_map={'OPERATIVO':'#28a745','DAÑADO':'#dc3545','REPARACION':'#ffc107'})

        st.plotly_chart(fig)
