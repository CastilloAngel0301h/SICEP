from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import random
import string
import io
import openpyxl  # Para leer archivos Excel (.xlsx) de Google Drive
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload 
from datetime import datetime  # <--- IMPORTACIÓN AGREGADA

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'angel_admin_2026_secure')

# --- CONFIGURACIÓN DE GOOGLE SHEETS ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
try:
    creds = ServiceAccountCredentials.from_json_keyfile_name('credenciales.json', scope)
    client = gspread.authorize(creds)
    sheet = client.open("Base_Datos_Calculadora").sheet1
except Exception as e:
    print(f"Error de conexión a Google: {e}")

def cargar_usuarios_drive():
    try:
        # Usamos get_all_values() para leer columnas exactas por índice
        records = sheet.get_all_values()
        usuarios = {}
        for row in records[1:]:  # Saltar encabezados
            if len(row) > 0 and str(row[0]).strip():
                tkn = str(row[0]).strip()
                usuarios[tkn] = {
                    "token": tkn,
                    "nombre": str(row[1]).strip() if len(row) > 1 else "",
                    "contacto": str(row[2]).strip() if len(row) > 2 else "",
                    "pin": str(row[3]).strip() if len(row) > 3 else "",
                    "rol": str(row[4]).strip() if len(row) > 4 else "operador",
                    "device_id": str(row[5]).strip() if len(row) > 5 else "",
                    "ultima_conexion": str(row[11]).strip() if len(row) > 11 else "Desconocida", # <--- DATO NUEVO
                    "permisos": {
                        "biohorario": str(row[6]).lower() == 'true' if len(row) > 6 and row[6] != "" else True,
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

# --- CONFIGURACIÓN DE BASE DE DATOS METAS (EXCEL .XLSX EN DRIVE) ---
pdf_metas_cache = {
    "estilos": [],
    "tallas": ['XXS', 'XS', 'S', 'M', 'L', 'XL', '2X', '3X', '4X'],
    "procesos": ['CONTEO','SORTEO','VOLTEO','DOBLADO','VOLTEO-SORTING','VOLTEO-PFD','SORTEO-REPROCESO'],
    "datos": []
}

def normalizar_talla(t):
    t = str(t).lower().strip()
    if '2x' in t: return '2X'
    if '3x' in t: return '3X'
    if '4x' in t: return '4X'
    if 'xxs' in t or 'bxx' in t: return 'XXS'
    if 'xs' in t or 'axs' in t or 'bxs' in t: return 'XS'
    if 'xl' in t or 'axl' in t or 'lxl' in t: return 'XL'
    if 'sm' in t or 'asm' in t or 'lsm' in t or 'bsm' in t: return 'S'
    if 'md' in t or 'amd' in t or 'lmd' in t or 'bmd' in t: return 'M'
    if 'lg' in t or 'alg' in t or 'llg' in t or 'blg' in t: return 'L'
    return t.upper()

def procesar_metas_drive():
    try:
        drive_service = build('drive', 'v3', credentials=creds)
        file_id = '1U9rvF4Uj55N9kV-sVuwP0y6OutkP___H' 
        request = drive_service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            
        fh.seek(0)
        wb = openpyxl.load_workbook(fh, data_only=True)
        hoja_metas = wb.active
        
        data = []
        estilos = set()
        procesos = set()
        
        for row in hoja_metas.iter_rows(min_row=2, values_only=True):
            if len(row) >= 6:
                estilo = str(row[0]).strip() if row[0] is not None else ""
                talla_raw = str(row[1]).strip() if row[1] is not None else ""
                proceso = str(row[3]).strip() if row[3] is not None else ""
                meta = str(row[5]).strip() if row[5] is not None else ""
                
                if estilo and talla_raw and proceso and meta:
                    if meta.replace('.', '', 1).isdigit():
                        talla_norm = normalizar_talla(talla_raw)
                        combinacion = {
                            'estilo': estilo,
                            'talla': talla_norm,
                            'proceso': proceso.upper(),
                            'meta': meta
                        }
                        if combinacion not in data:
                            data.append(combinacion)
                        estilos.add(estilo)
                        procesos.add(proceso.upper())

        pdf_metas_cache["estilos"] = list(estilos)
        pdf_metas_cache["procesos"] = list(procesos)
        pdf_metas_cache["datos"] = data
        return True, "Sincronización exitosa"
    except Exception as e:
        return False, str(e)

@app.route('/api/metas/sincronizar', methods=['POST'])
def sync_metas():
    exito, msj = procesar_metas_drive()
    if exito:
        return jsonify({"status": "success", "datos": pdf_metas_cache["datos"], "estilos": pdf_metas_cache["estilos"], "procesos": pdf_metas_cache["procesos"]})
    return jsonify({"status": "error", "message": msj}), 500

@app.route('/api/metas/datos', methods=['GET'])
def get_metas():
    return jsonify({"status": "success", "datos": pdf_metas_cache["datos"], "estilos": pdf_metas_cache["estilos"], "procesos": pdf_metas_cache["procesos"]})

# --- RUTAS DE ACCESO, SEGURIDAD Y PERMISOS ---

@app.route('/')
def index():
    token = request.args.get('token')
    usuarios_actuales = cargar_usuarios_drive()
    if not token or token not in usuarios_actuales:
        return "<h1 style='color:white;background:#0b132b;text-align:center;padding:50px;font-family:sans-serif;'>ACCESO DENEGADO: TOKEN INVÁLIDO</h1>", 403

    user_data = usuarios_actuales[token]
    return render_template('index.html', user=user_data, token=token)

@app.route('/api/login', methods=['POST'])
def login_verificar():
    data = request.json
    token = data.get('token')
    pin_ingresado = str(data.get('pin')).strip()
    device_id_cliente = str(data.get('device_id')).strip()
    
    # EXCEPCIÓN DEL ADMINISTRADOR
    if token == 'angel0301':
        usuarios_actuales = cargar_usuarios_drive()
        if token in usuarios_actuales and str(usuarios_actuales[token]['pin']).strip() == pin_ingresado:
            session['user_token'] = token
            session['user_name'] = 'Angel Castillo'
            permisos_admin = {"biohorario":True, "eficiencia":True, "tiempo":True, "metas":True, "historial":True}
            return jsonify({"status": "success", "permisos": permisos_admin})
        return jsonify({"status": "error", "message": "PIN Incorrecto"}), 401

    try:
        # Validación de usuario y dispositivo en Sheets
        celda = sheet.find(token)
        fila = celda.row
        valores_fila = sheet.row_values(fila)
        
        pin_correcto = str(valores_fila[3]).strip()
        if pin_ingresado != pin_correcto:
            return jsonify({"status": "error", "message": "PIN Incorrecto"}), 401

        # Protocolo Device ID (Columna F -> Índice 5)
        device_id_db = str(valores_fila[5]).strip() if len(valores_fila) >= 6 else ""

        if not device_id_db:
            # Vinculación del primer dispositivo
            sheet.update_cell(fila, 6, device_id_cliente)
        elif device_id_db != device_id_cliente:
            # Destrucción del perfil por violación de seguridad
            sheet.delete_row(fila)
            return jsonify({"status": "deleted"}), 403

        # Login Exitoso: Actualizar última conexión (Columna 12)
        fecha_actual = datetime.now().strftime("%d/%m/%Y %H:%M")
        sheet.update_cell(fila, 12, fecha_actual)

        # Login Exitoso: Construir permisos (Columnas G a K -> Índices 6 a 10)
        permisos = {
            "biohorario": str(valores_fila[6]).lower() == 'true' if len(valores_fila) > 6 and valores_fila[6] != "" else True,
            "eficiencia": str(valores_fila[7]).lower() == 'true' if len(valores_fila) > 7 and valores_fila[7] != "" else True,
            "tiempo": str(valores_fila[8]).lower() == 'true' if len(valores_fila) > 8 and valores_fila[8] != "" else True,
            "metas": str(valores_fila[9]).lower() == 'true' if len(valores_fila) > 9 and valores_fila[9] != "" else True,
            "historial": str(valores_fila[10]).lower() == 'true' if len(valores_fila) > 10 and valores_fila[10] != "" else True
        }

        session['user_token'] = token
        session['user_name'] = valores_fila[1]
        return jsonify({"status": "success", "permisos": permisos})

    except Exception as e:
        return jsonify({"status": "error", "message": "Usuario no encontrado"}), 404

# --- API DE ADMINISTRADOR (ANGEL) ---

@app.route('/api/admin/usuarios', methods=['GET', 'POST', 'PUT'])
def admin_drive():
    if session.get('user_token') != 'angel0301': 
        return jsonify({"error": "No autorizado"}), 403
    
    if request.method == 'GET':
        return jsonify(cargar_usuarios_drive())

    data = request.json
    
    if request.method == 'POST':
        nuevo_tkn = generar_token(data['nombre'])
        nuevo_pin = data.get('pin') if data.get('pin') else "".join(random.choices(string.digits, k=4))
        # Se añaden las nuevas columnas activadas ("true") por defecto al crear usuario
        sheet.append_row([nuevo_tkn, data['nombre'], data['contacto'], nuevo_pin, "operador", "", "true", "true", "true", "true", "true"])
        return jsonify({"token": nuevo_tkn, "pin": nuevo_pin})

    if request.method == 'PUT':
        try:
            celda = sheet.find(data['token'])
            fila = celda.row
            sheet.update_cell(fila, 2, data['nombre'])
            sheet.update_cell(fila, 3, data['contacto'])
            if data.get('nuevo_pin'):
                sheet.update_cell(fila, 4, data['nuevo_pin'])
            return jsonify({"status": "updated"})
        except:
            return jsonify({"error": "No encontrado"}), 404

# NUEVA RUTA: Guardar permisos directamente a Google Sheets
@app.route('/api/admin/permisos', methods=['POST'])
def update_permisos():
    if session.get('user_token') != 'angel0301': 
        return jsonify({"error": "No autorizado"}), 403
    data = request.json
    token = data.get('token')
    permisos = data.get('permisos')
    try:
        celda = sheet.find(token)
        fila = celda.row
        # Escribimos los booleanos en las columnas G, H, I, J, K
        sheet.update_cell(fila, 7, str(permisos.get('biohorario', True)).lower())
        sheet.update_cell(fila, 8, str(permisos.get('eficiencia', True)).lower())
        sheet.update_cell(fila, 9, str(permisos.get('tiempo', True)).lower())
        sheet.update_cell(fila, 10, str(permisos.get('metas', True)).lower())
        sheet.update_cell(fila, 11, str(permisos.get('historial', True)).lower())
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def generar_token(nombre):
    prefijo = nombre.split()[0].lower()
    return f"{prefijo}{''.join(random.choices(string.digits, k=3))}"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
