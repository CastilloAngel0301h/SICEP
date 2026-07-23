from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import random
import string
import io
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

# --- CONFIGURACIÓN DE GOOGLE SERVICES ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
try:
    creds = ServiceAccountCredentials.from_json_keyfile_name('credenciales.json', scope)
    client = gspread.authorize(creds)
    sheet = client.open("Base_Datos_Calculadora").sheet1
    drive_service = build('drive', 'v3', credentials=creds)
except Exception as e:
    print(f"Error de conexión a Google: {e}")

# --- ESTRUCTURA CACHÉ DE METAS ---
pdf_metas_cache = {
    "estilos": ["ESTILO-A", "ESTILO-B", "ESTILO-C"], 
    "tallas": ['XXS', 'XS', 'S', 'M', 'L', 'XL', '2X', '3X', '4X'], 
    "procesos": ['CONTEO','SORTEO','VOLTEO','DOBLADO','VOLTEO-SORTING','VOLTEO-PFD','SORTEO-REPROCESO'], 
    "datos": [
        {"estilo": "ESTILO-A", "talla": "M", "proceso": "DOBLADO", "meta": 50},
        {"estilo": "ESTILO-B", "talla": "L", "proceso": "SORTEO", "meta": 65}
    ]
}

# --- HELPER FUNCTIONS FOR DRIVE & FILES ---

def obtener_o_crear_carpeta_usuario(nombre_usuario):
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
    try:
        query = f"'{folder_id}' in parents and trashed = false"
        results = drive_service.files().list(q=query, fields="files(name)").execute()
        files = results.get('files', [])

        numero_calculo = len(files) + 1
        str_numero = f"{numero_calculo:06d}"
        fecha_actual = datetime.now().strftime("%d-%m-2026")

        return f"calculo{str_numero}-{fecha_actual}"
    except:
        fecha_actual = datetime.now().strftime("%d-%m-2026")
        return f"calculo000001-{fecha_actual}"

def crear_pdf_en_memoria(datos_extensos):
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

def cargar_usuarios_drive():
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

# --- RUTAS DE API ---

@app.route('/')
def index():
    token = request.args.get('token')
    usuarios_actuales = cargar_usuarios_drive()
    if not token or token not in usuarios_actuales:
        return "<h1 style='color:white;background:#050814;text-align:center;padding:50px;font-family:sans-serif;'>ACCESO DENEGADO: TOKEN INVÁLIDO</h1>", 403
    return render_template('index.html', user=usuarios_actuales[token], token=token)

@app.route('/api/login', methods=['POST'])
def login_verificar():
    data = request.json
    token = data.get('token')
    pin_ingresado = str(data.get('pin')).strip()
    device_id_cliente = str(data.get('device_id')).strip()

    usuarios_actuales = cargar_usuarios_drive()
    if token in usuarios_actuales and str(usuarios_actuales[token]['pin']).strip() == pin_ingresado:
        session['user_token'] = token
        session['user_name'] = usuarios_actuales[token]['nombre']
        return jsonify({"status": "success", "permisos": usuarios_actuales[token]['permisos']})
    return jsonify({"status": "error", "message": "PIN o Token Incorrecto"}), 401

@app.route('/api/metas/datos', methods=['GET'])
def obtener_metas_datos():
    return jsonify({
        "status": "success",
        "datos": pdf_metas_cache["datos"],
        "estilos": pdf_metas_cache["estilos"],
        "tallas": pdf_metas_cache["tallas"],
        "procesos": pdf_metas_cache["procesos"]
    })

@app.route('/api/metas/sincronizar', methods=['POST'])
def sincronizar_metas():
    return jsonify({
        "status": "success",
        "datos": pdf_metas_cache["datos"],
        "estilos": pdf_metas_cache["estilos"],
        "tallas": pdf_metas_cache["tallas"],
        "procesos": pdf_metas_cache["procesos"]
    })

@app.route('/api/save', methods=['POST'])
@app.route('/api/historial/guardar', methods=['POST'])
def guardar_calculo():
    data = request.json or {}
    token = data.get('token')
    tipo = data.get('tipo', 'Cálculo Generado')
    info = data.get('info', {})
    lineas_calculo = data.get('lineas', [f"{tipo}: {info.get('res', '')}"])

    if not token:
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
        uploaded_file = drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()

        return jsonify({
            "status": "success", 
            "file_name": nombre_archivo, 
            "file_id": uploaded_file.get('id'),
            "drive_url": uploaded_file.get('webViewLink')
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"Error al subir a Drive: {str(e)}"}), 500

@app.route('/api/load', methods=['GET'])
@app.route('/api/historial/archivos', methods=['GET'])
def listar_historial_usuario():
    token = request.args.get('token')
    if not token:
        return jsonify({"status": "error", "message": "Falta token"}), 400

    usuarios = cargar_usuarios_drive()
    if token not in usuarios:
        return jsonify({"status": "error", "message": "Usuario denegado"}), 403

    nombre_usuario = usuarios[token]['nombre']
    folder_id = obtener_o_crear_carpeta_usuario(nombre_usuario)

    if not folder_id:
        return jsonify([])

    try:
        query = f"'{folder_id}' in parents and trashed = false"
        results = drive_service.files().list(q=query, fields="files(id, name, webViewLink, mimeType, createdTime)").execute()
        files = results.get('files', [])

        formateados = []
        for f in files:
            formateados.append({
                "tipo": "Reporte Guardado",
                "fecha_hora": f.get('createdTime', datetime.now().strftime("%d/%m/%Y")),
                "drive_url": f.get('webViewLink'),
                "info": {"res": f.get('name'), "detalle": f.get('mimeType')}
            })
        return jsonify(formateados)
    except Exception as e:
        return jsonify([]), 500

@app.route('/api/admin/usuarios', methods=['GET', 'POST', 'PUT'])
def admin_drive():
    if request.method == 'GET':
        return jsonify(cargar_usuarios_drive())

    data = request.json or {}
    if request.method == 'POST':
        nuevo_token = "tkn_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
        nuevo_pin = "".join(random.choices(string.digits, k=4))
        try:
            sheet.append_row([nuevo_token, data.get('nombre'), data.get('contacto'), nuevo_pin, "operador", "", "true", "true", "true", "true", "true", ""])
            return jsonify({"status": "success", "token": nuevo_token, "pin": nuevo_pin})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    if request.method == 'PUT':
        token = data.get('token')
        try:
            celda = sheet.find(token)
            if data.get('nombre'): sheet.update_cell(celda.row, 2, data.get('nombre'))
            if data.get('contacto'): sheet.update_cell(celda.row, 3, data.get('contacto'))
            if data.get('nuevo_pin'): sheet.update_cell(celda.row, 4, data.get('nuevo_pin'))
            return jsonify({"status": "success"})
        except:
            return jsonify({"status": "error"}), 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
