from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import random
import string
import io
import openpyxl  # <-- NUEVO: Para leer archivos Excel (.xlsx)
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

app = Flask(__name__)
# Cambia esto por una palabra secreta muy difícil de adivinar
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
        records = sheet.get_all_records()
        # Limpiamos espacios en blanco de los tokens y pines por seguridad
        return {str(r['token']).strip(): r for r in records}
    except:
        return {}

# --- NUEVO: CONFIGURACIÓN DE BASE DE DATOS METAS (EXCEL .XLSX EN DRIVE) ---

# Caché en memoria para no descargar los datos cada vez que alguien hace clic
pdf_metas_cache = {
    "estilos": ['1466', '1467','1468', '1469','1545','1566','1567','1580','1717','1745','4017','4410','6014','6030','6045','9018','9360','1301GD','1302GD','1467Y','1566L','15BT','1745Y','207GD','3023CL','307GD' ],
    "tallas": ['XXS', 'XS', 'S', 'M', 'L', 'XL', '2X', '3X', '4X'],
    "procesos": ['CONTEO','SORTEO','VOLTEO','DOBLADO','VOLTEO-SORTING','VOLTEO-PFD','SORTEO-REPROCESO'],
    "datos": []
}

def normalizar_talla(t):
    """Convierte nomenclaturas a tallas universales"""
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
    """Descarga el Excel (.xlsx) desde Google Drive y extrae las columnas requeridas"""
    try:
        drive_service = build('drive', 'v3', credentials=creds)
        file_id = '1U9rvF4Uj55N9kV-sVuwP0y6OutkP___H' 
        
        # Descargamos el archivo Excel (.xlsx) en memoria
        request = drive_service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            
        fh.seek(0)
        
        # Leemos el archivo con openpyxl (data_only=True obtiene los valores, no las fórmulas)
        wb = openpyxl.load_workbook(fh, data_only=True)
        hoja_metas = wb.active
        
        data = []
        estilos = set()
        procesos = set()
        
        # Recorremos las filas omitiendo la primera (encabezados)
        for row in hoja_metas.iter_rows(min_row=2, values_only=True):
            # Nos aseguramos de que la fila tenga al menos 6 columnas
            if len(row) >= 6:
                # Columnas según tu requerimiento (índice base 0)
                estilo = str(row[0]).strip() if row[0] is not None else ""      # Columna 1
                talla_raw = str(row[1]).strip() if row[1] is not None else ""   # Columna 2
                proceso = str(row[3]).strip() if row[3] is not None else ""     # Columna 4
                meta = str(row[5]).strip() if row[5] is not None else ""        # Columna 6
                
                # Validamos que los datos requeridos existan y que la meta sea numérica
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
    else:
        return jsonify({"status": "error", "message": msj}), 500

@app.route('/api/metas/datos', methods=['GET'])
def get_metas():
    return jsonify({
        "status": "success",
        "datos": pdf_metas_cache["datos"],
        "estilos": pdf_metas_cache["estilos"],
        "procesos": pdf_metas_cache["procesos"]
    })

# --- RUTAS DE ACCESO Y SEGURIDAD ---

@app.route('/')
def index():
    token = request.args.get('token')
    
    # 1. Verificar si el token existe en la URL
    usuarios_actuales = cargar_usuarios_drive()
    if not token or token not in usuarios_actuales:
        return "<h1 style='color:white;background:#0b132b;text-align:center;padding:50px;font-family:sans-serif;'>ACCESO DENEGADO: TOKEN INVÁLIDO</h1>", 403

    # 2. Verificar si ya tiene la sesión iniciada para este token
    if session.get('user_token') == token and session.get('auth_logged'):
        user_data = usuarios_actuales[token]
        return render_template('index.html', user=user_data, token=token)
    
    # 3. Si el token es válido pero no ha puesto el PIN, mostrar pantalla de login
    user_name = usuarios_actuales[token]['nombre']
    return render_template('login.html', token=token, nombre=user_name)

@app.route('/api/login', methods=['POST'])
def login_verificar():
    data = request.json
    token = data.get('token')
    pin_ingresado = str(data.get('pin')).strip()
    device_id_cliente = str(data.get('device_id')).strip()
    
    # EXCEPCIÓN DE ADMINISTRADOR: Angel Castillo tiene acceso irrestricto multidispositivo
    if token == 'angel0301':
        usuarios_actuales = cargar_usuarios_drive()
        if token in usuarios_actuales and str(usuarios_actuales[token]['pin']).strip() == pin_ingresado:
            session['user_token'] = token
            session['user_name'] = 'Angel Castillo'
            session['auth_logged'] = True
            return jsonify({"status": "success"})
        return jsonify({"status": "error", "message": "PIN Incorrecto"}), 401

    try:
        # Buscamos la fila exacta del usuario en Google Sheets
        celda = sheet.find(token)
        fila = celda.row
        valores_fila = sheet.row_values(fila)
        
        # Validación de PIN (El PIN está en la columna 4 -> índice 3)
        pin_correcto = str(valores_fila[3]).strip()
        if pin_ingresado != pin_correcto:
            return jsonify({"status": "error", "message": "PIN Incorrecto"}), 401

        # 🛡️ PROTOCOLO DE SEGURIDAD: DEVICE ID (Se guardará en la columna 6)
        device_id_db = str(valores_fila[5]).strip() if len(valores_fila) >= 6 else ""

        if not device_id_db:
            # Es su primer inicio de sesión: Vinculamos este dispositivo permanentemente a su perfil
            sheet.update_cell(fila, 6, device_id_cliente)
        elif device_id_db != device_id_cliente:
            # 🚨 INFRACCIÓN DETECTADA: Intento desde un dispositivo no autorizado
            sheet.delete_row(fila) # Elimina el perfil automáticamente
            return jsonify({"status": "deleted"}), 403

        # Login Exitoso
        session['user_token'] = token
        session['user_name'] = valores_fila[1]
        session['auth_logged'] = True
        return jsonify({"status": "success"})

    except Exception as e:
        return jsonify({"status": "error", "message": "Usuario no encontrado o error de red"}), 404
@app.route('/logout')
def logout():
    session.clear()
    return "Sesión cerrada. Cierre esta ventana."

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
        sheet.append_row([nuevo_tkn, data['nombre'], data['contacto'], nuevo_pin, "operador"])
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

def generar_token(nombre):
    prefijo = nombre.split()[0].lower()
    return f"{prefijo}{''.join(random.choices(string.digits, k=3))}"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
