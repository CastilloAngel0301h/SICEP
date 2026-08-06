from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import gspread
from google.oauth2.service_account import Credentials
import os
import random
import string
import io
import json
import openpyxl  # Para leer archivos Excel (.xlsx) de Google Drive
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from datetime import datetime

# --- LIBRERÍAS PARA PDF E IMÁGENES ---
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'angel_admin_2026_secure')

CARPETA_RAIZ_DRIVE = "1PbH8767Q86O-TntoxDxozaGiBl3WJqE0"

# Scope para Google Cloud Services
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# --- INICIALIZACIÓN SEGURA DE GOOGLE SERVICES ---
client = None
sheet = None
drive_service = None

def inicializar_servicios_google():
    global client, sheet, drive_service
    try:
        creds_dict = None
        # 1. Intentar cargar desde archivo físico o Secret File en Render
        if os.path.exists('credenciales.json'):
            with open('credenciales.json', 'r', encoding='utf-8') as f:
                creds_dict = json.load(f)
        # 2. Si no existe archivo físico, buscar en la variable de entorno
        elif os.environ.get('GOOGLE_CREDENTIALS_JSON'):
            creds_raw = os.environ.get('GOOGLE_CREDENTIALS_JSON')
            creds_dict = json.loads(creds_raw)

        if creds_dict:
            # FIX CRÍTICO: Formatear saltos de línea en la private key para evitar 'Invalid JWT Signature'
            if 'private_key' in creds_dict:
                pk = creds_dict['private_key']
                if pk.startswith('"') and pk.endswith('"'):
                    pk = pk[1:-1]
                pk = pk.replace('\\\\n', '\n').replace('\\n', '\n')
                creds_dict['private_key'] = pk
            
            creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
            client = gspread.authorize(creds)
            sheet = client.open("Base_Datos_Calculadora").sheet1
            drive_service = build('drive', 'v3', credentials=creds)
            print("Conexión con Google APIs establecida correctamente.")
        else:
            print("Advertencia: No se encontraron credenciales válidas de Google.")
    except Exception as e:
        print(f"Error de conexión a Google: {e}")

# Ejecutar inicialización al arrancar
inicializar_servicios_google()

# --- RUTAS DE SINCRONIZACIÓN Y CONSULTA DE METAS ---

@app.route('/api/metas/sincronizar', methods=['GET', 'POST'])
@app.route('/api/metas/datos', methods=['GET', 'POST'])
def api_gestion_metas():
    global sheet_metas, sheet, pdf_metas_cache

    # 1. Intentar reconectar a Google Services si las variables globales están caídas
    if not sheet and not sheet_metas:
        inicializar_servicios_google()

    try:
        registros_metas = []

        # 2. Intentar leer de la hoja dedicada de Metas o de la pestaña 'Metas'
        if sheet_metas:
            registros_metas = sheet_metas.get_all_records()
        elif sheet:
            try:
                hoja_p = client.open("Base_Datos_Calculadora").worksheet("Metas")
                registros_metas = hoja_p.get_all_records()
            except Exception as err_ws:
                print(f"Pestaña 'Metas' no encontrada en el libro principal: {err_ws}")
                registros_metas = pdf_metas_cache.get("datos", [])

        # Actualizar la caché de metas si hay registros leídos
        if registros_metas:
            pdf_metas_cache["datos"] = registros_metas

        # 3. Retornar siempre un JSON estructurado con estado HTTP 200
        return jsonify({
            "status": "success",
            "message": "Datos de metas cargados correctamente",
            "estilos": pdf_metas_cache.get("estilos", []),
            "tallas": pdf_metas_cache.get("tallas", []),
            "procesos": pdf_metas_cache.get("procesos", []),
            "datos": pdf_metas_cache.get("datos", [])
        }), 200

    except Exception as e:
        print(f"Error al procesar la ruta de metas: {e}")
        # Respuesta de respaldo en formato JSON válido para evitar la falla del frontend
        return jsonify({
            "status": "error",
            "message": f"Error interno en la base de datos de metas: {str(e)}",
            "datos": pdf_metas_cache.get("datos", [])
        }), 200
        
# --- HELPER FUNCTIONS FOR DRIVE & FILES ---

def obtener_o_crear_carpeta_usuario(nombre_usuario):
    """Busca la subcarpeta del usuario en la raíz; si no existe, la crea."""
    if not drive_service:
        return None
    try:
        query = f"'{CARPETA_RAIZ_DRIVE}' in parents and name = '{nombre_usuario}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        results = drive_service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])
        
        if files:
            return files[0]['id']
        
        file_metadata = {
            'name': nombre_usuario,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [CARPETA_RAIZ_DRIVE]
        }
        folder = drive_service.files().create(body=file_metadata, fields='id').execute()
        return folder.get('id')
    except Exception as e:
        print(f"Error al gestionar carpeta de usuario {nombre_usuario}: {e}")
        return None

def generar_nombre_correlativo(folder_id):
    """Cuenta los archivos existentes de la carpeta para generar el nombre correlativo exacto."""
    if not drive_service:
        fecha_actual = datetime.now().strftime("%d-%m-2026")
        return f"calculo000001-{fecha_actual}"
    try:
        query = f"'{folder_id}' in parents and trashed = false"
        results = drive_service.files().list(q=query, fields="files(name)").execute()
        files = results.get('files', [])
        
        numero_calculo = len(files) + 1
        str_numero = f"{numero_calculo:06d}" # Formato 000001
        fecha_actual = datetime.now().strftime("%d-%m-2026")
        
        return f"calculo{str_numero}-{fecha_actual}"
    except Exception as e:
        print(f"Error al generar correlativo: {e}")
        fecha_actual = datetime.now().strftime("%d-%m-2026")
        return f"calculo000001-{fecha_actual}"

def crear_pdf_en_memoria(datos_extensos):
    """Genera un archivo PDF estructurado a partir de texto extenso."""
    pdf_buffer = io.BytesIO()
    c = canvas.Canvas(pdf_buffer, pagesize=letter)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, 750, "REPORTE DETALLADO DE CÁLCULO DE PRODUCCIÓN")
    c.setFont("Helvetica", 10)
    c.drawString(50, 730, f"Fecha de registro: {datetime.now().strftime('%d/%m/2026 %H:%M')}")
    c.line(50, 720, 550, 720)
    
    y = 690
    c.setFont("Helvetica", 12)
    for linea in datos_extensos:
        if y < 50:
            c.showPage()
            c.setFont("Helvetica", 12)
            y = 750
        c.drawString(50, y, str(linea))
        y -= 20
        
    c.save()
    pdf_buffer.seek(0)
    return pdf_buffer

def crear_imagen_en_memoria(datos_cortos):
    """Genera una imagen PNG nítida a partir de datos cortos."""
    img = Image.new('RGB', (600, 300), color='#0b132b')
    d = ImageDraw.Draw(img)
    
    d.text((30, 30), "CÁLCULO DE PRODUCCIÓN (RESUMEN)", fill='#ffffff')
    d.line([(30, 55), (570, 55)], fill='#48cae4', width=2)
    
    y = 80
    for linea in datos_cortos:
        d.text((30, y), str(linea), fill='#edf2f4')
        y += 30
        
    img_buffer = io.BytesIO()
    img.save(img_buffer, format='PNG')
    img_buffer.seek(0)
    return img_buffer

# --- CONFIGURACIÓN DE BASE DE DATOS USUARIOS (SHEETS) ---

def cargar_usuarios_drive():
    """Carga los usuarios desde Google Sheets sin riesgo de NameError."""
    if not sheet:
        print("Atención: La hoja de cálculo no está inicializada.")
        return {}
    try:
        records = sheet.get_all_values()
        usuarios = {}
        for row in records[1:]:
            if len(row) > 0 and str(row[0]).strip():
                tkn = str(row[0]).strip()
                is_hibernated = str(row[6]).lower() == 'false' if len(row) > 6 and row[6] != "" else False
                
                usuarios[tkn] = {
                    "token": tkn,
                    "nombre": str(row[1]).strip() if len(row) > 1 else "",
                    "contacto": str(row[2]).strip() if len(row) > 2 else "",
                    "pin": str(row[3]).strip() if len(row) > 3 else "",
                    "rol": str(row[4]).strip() if len(row) > 4 else "operador",
                    "device_id": str(row[5]).strip() if len(row) > 5 else "",
                    "ultima_conexion": str(row[11]).strip() if len(row) > 11 else "Desconocida",
                    "permisos": {
                        "biohorario": not is_hibernated, 
                        "eficiencia": str(row[7]).lower() == 'true' if len(row) > 7 and row[7] != "" else True,
                        "tiempo": str(row[8]).lower() == 'true' if len(row) > 8 and row[8] != "" else True,
                        "metas": str(row[9]).lower() == 'true' if len(row) > 9 and row[9] != "" else True,
                        "historial": str(row[10]).lower() == 'true' if len(row) > 10 and row[10] != "" else True
                    }
                }
        return usuarios
    except Exception as e:
        print("Error al cargar usuarios de Drive:", e)
        return {}

# --- PROCESAMIENTO DE METAS ---
pdf_metas_cache = {
    "estilos": [], 
    "tallas": ['XXS', 'XS', 'S', 'M', 'L', 'XL', '2X', '3X', '4X'], 
    "procesos": ['CONTEO','SORTEO','VOLTEO','DOBLADO','VOLTEO-SORTING','VOLTEO-PFD','SORTEO-REPROCESO'], 
    "datos": []
}

# --- RUTAS DE NAVEGACIÓN Y AUTENTICACIÓN ---

@app.route('/')
def index():
    token = request.args.get('token')
    
    # 1. Si no hay token en la URL, permitir ver la vista de inicio
    if not token:
        return render_template('index.html', user=None, token=None)

    # 2. Bypass maestro para administrador
    if token == 'angel0301':
        admin_user = {
            "token": "angel0301",
            "nombre": "Angel Castillo",
            "rol": "admin",
            "permisos": {"biohorario": True, "eficiencia": True, "tiempo": True, "metas": True, "historial": True}
        }
        return render_template('index.html', user=admin_user, token=token)

    # 3. Validar token contra Google Sheets
    usuarios_actuales = cargar_usuarios_drive()
    if token in usuarios_actuales:
        return render_template('index.html', user=usuarios_actuales[token], token=token)

    return "<h1 style='color:white;background:#0b132b;text-align:center;padding:50px;font-family:sans-serif;'>ACCESO DENEGADO: TOKEN INVÁLIDO</h1>", 403

@app.route('/api/login', methods=['POST'])
def login_verificar():
    data = request.json or {}
    token = data.get('token')
    pin_ingresado = str(data.get('pin', '')).strip()
    device_id_cliente = str(data.get('device_id', '')).strip()

    if token == 'angel0301':
        session['user_token'] = token
        session['user_name'] = 'Angel Castillo'
        return jsonify({"status": "success", "permisos": {"biohorario":True, "eficiencia":True, "tiempo":True, "metas":True, "historial":True}})

    if not sheet:
        return jsonify({"status": "error", "message": "Servicio de base de datos no disponible"}), 500

    try:
        celda = sheet.find(token)
        fila = celda.row
        valores_fila = sheet.row_values(fila)

        if pin_ingresado != str(valores_fila[3]).strip():
            return jsonify({"status": "error", "message": "PIN Incorrecto"}), 401

        if len(valores_fila) > 6 and str(valores_fila[6]).strip().lower() == "false":
            return jsonify({"status": "hibernacion", "message": "SISTEMA Y SERVER EN MODO HIBERNACION HASTA FUTURO AVISO"}), 200

        device_id_db = str(valores_fila[5]).strip() if len(valores_fila) >= 6 else ""
        if not device_id_db:
            sheet.update_cell(fila, 6, device_id_cliente)
        elif device_id_db != device_id_cliente:
            sheet.delete_row(fila)
            return jsonify({"status": "deleted"}), 403

        sheet.update_cell(fila, 12, datetime.now().strftime("%d/%m/%Y %H:%M"))
        session['user_token'] = token
        session['user_name'] = valores_fila[1]
        
        return jsonify({"status": "success", "permisos": {
            "biohorario": True, 
            "eficiencia": str(valores_fila[7]).lower() == 'true' if len(valores_fila) > 7 else True, 
            "tiempo": str(valores_fila[8]).lower() == 'true' if len(valores_fila) > 8 else True, 
            "metas": str(valores_fila[9]).lower() == 'true' if len(valores_fila) > 9 else True, 
            "historial": str(valores_fila[10]).lower() == 'true' if len(valores_fila) > 10 else True
        }})
    except Exception as e:
        print(f"Error en login: {e}")
        return jsonify({"status": "error", "message": "Usuario no encontrado"}), 404


# --- OPERACIONES DE HISTORIAL Y DRIVE ---

@app.route('/api/historial/guardar', methods=['POST'])
def guardar_calculo():
    """Recibe los datos de un cálculo, clasifica la extensión y lo sube a Drive."""
    if not drive_service:
        return jsonify({"status": "error", "message": "Google Drive no disponible"}), 500

    data = request.json or {}
    token = data.get('token')
    lineas_calculo = data.get('lineas')

    if not token or not lineas_calculo:
        return jsonify({"status": "error", "message": "Datos incompletos"}), 400

    usuarios = cargar_usuarios_drive()
    if token not in usuarios:
        return jsonify({"status": "error", "message": "Usuario no válido"}), 403

    nombre_usuario = usuarios[token]['nombre']
    
    folder_id = obtener_o_crear_carpeta_usuario(nombre_usuario)
    if not folder_id:
        return jsonify({"status": "error", "message": "No se pudo gestionar la carpeta en Drive"}), 500

    nombre_base = generar_nombre_correlativo(folder_id)
    
    if len(lineas_calculo) > 5:
        archivo_binario = crear_pdf_en_memoria(lineas_calculo)
        nombre_archivo = f"{nombre_base}.pdf"
        mime_type = "application/pdf"
    else:
        archivo_binario = crear_imagen_en_memoria(lineas_calculo)
        nombre_archivo = f"{nombre_base}.png"
        mime_type = "image/png"

    try:
        file_metadata = {'name': nombre_archivo, 'parents': [folder_id]}
        media = MediaIoBaseUpload(archivo_binario, mimetype=mime_type, resumable=True)
        uploaded_file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        
        return jsonify({"status": "success", "file_name": nombre_archivo, "file_id": uploaded_file.get('id')})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Error al subir a Drive: {str(e)}"}), 500


@app.route('/api/historial/archivos', methods=['GET'])
def listar_historial_usuario():
    """Devuelve la lista de archivos con enlaces web dentro de la subcarpeta del usuario."""
    if not drive_service:
        return jsonify({"status": "error", "message": "Google Drive no disponible"}), 500

    token = request.args.get('token')
    if not token:
        return jsonify({"status": "error", "message": "Falta token"}), 400

    usuarios = cargar_usuarios_drive()
    if token not in usuarios:
        return jsonify({"status": "error", "message": "Usuario denegado"}), 403

    nombre_usuario = usuarios[token]['nombre']
    folder_id = obtener_o_crear_carpeta_usuario(nombre_usuario)
    
    if not folder_id:
        return jsonify({"status": "success", "archivos": []})

    try:
        query = f"'{folder_id}' in parents and trashed = false"
        results = drive_service.files().list(q=query, fields="files(id, name, webViewLink, mimeType)").execute()
        archivos = results.get('files', [])
        return jsonify({"status": "success", "archivos": archivos})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# --- RUTAS DE ADMINISTRACIÓN ---

@app.route('/api/admin/usuarios', methods=['GET', 'POST', 'PUT'])
def admin_drive():
    return jsonify({"status": "success", "message": "Ruta lista para gestión de usuarios"})

@app.route('/api/admin/permisos', methods=['POST'])
def update_permisos():
    return jsonify({"status": "success", "message": "Ruta lista para actualización de permisos"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
