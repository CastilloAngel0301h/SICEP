"""
============================================================
SISTEMA DE GESTIÓN DE PRODUCCIÓN - BACKEND (FLASK)
Desarrollado para: Angel Castillo (UTH)
Descripción: Servidor con integración a Google Sheets API
             y control de acceso por tokens dinámicos.
============================================================
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import random
import string
import datetime
import logging

# --- CONFIGURACIÓN DE LOGS ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# LLAVE SECRETA: Se recomienda usar una variable de entorno en producción
app.secret_key = os.environ.get('SECRET_KEY', 'angel_admin_2026_secure_key_prod')

# --- CONFIGURACIÓN DE GOOGLE SHEETS ---
def conectar_google_sheets():
    """
    Establece la conexión con la API de Google Drive y Sheets.
    Requiere el archivo 'credenciales.json' en el directorio raíz.
    """
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    try:
        # Buscamos las credenciales locales o configuradas
        creds_path = os.path.join(os.getcwd(), 'credenciales.json')
        creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
        client = gspread.authorize(creds)
        
        # Abrimos la base de datos (Asegúrate de que este nombre sea exacto en tu Drive)
        db = client.open("Base_Datos_Calculadora")
        logger.info("✅ Conexión exitosa con Google Sheets")
        return db.sheet1
    except Exception as e:
        logger.error(f"❌ Error crítico de conexión: {e}")
        return None

# Inicializamos la hoja de cálculo
sheet = conectar_google_sheets()

# --- FUNCIONES DE UTILIDAD (HELPERS) ---

def cargar_usuarios_drive():
    """ Lee todos los registros de la base de datos y los convierte en diccionario """
    if not sheet: return {}
    try:
        records = sheet.get_all_records()
        # Mapeo por TOKEN para búsqueda instantánea
        return {str(r['token']).strip(): r for r in records}
    except Exception as e:
        logger.error(f"Error al leer registros: {e}")
        return {}

def generar_token_unico(nombre):
    """ Crea un token basado en el nombre + 3 números aleatorios """
    nombre_limpio = nombre.split()[0].lower().replace(" ", "")
    random_part = "".join(random.choices(string.digits, k=3))
    return f"{nombre_limpio}{random_part}"

def generar_pin_aleatorio():
    """ Genera un PIN numérico de 4 dígitos """
    return "".join(random.choices(string.digits, k=4))

# --- RUTAS DE NAVEGACIÓN Y AUTENTICACIÓN ---

@app.route('/')
def index():
    """ 
    Punto de entrada principal. 
    Valida el token de la URL antes de permitir cargar el HTML. 
    """
    token_url = request.args.get('token')
    
    # 1. Carga de datos fresca desde el Drive
    db_usuarios = cargar_usuarios_drive()
    
    # 2. Validación de existencia del token
    if not token_url or token_url not in db_usuarios:
        logger.warning(f"Intento de acceso fallido con token: {token_url}")
        return render_template('errors/403.html'), 403

    # 3. Verificación de sesión activa
    # Si el usuario ya se logueó con este token, entra directo
    if session.get('user_token') == token_url and session.get('auth_logged'):
        user_data = db_usuarios[token_url]
        return render_template('index.html', user=user_data, token=token_url)
    
    # 4. Redirección silenciosa: Si el token existe pero no hay sesión, 
    # la propia lógica del front-end en index.html (pantalla de bloqueo) 
    # pedirá el PIN comparándolo con el del objeto 'user'.
    user_data = db_usuarios[token_url]
    return render_template('index.html', user=user_data, token=token_url)

@app.route('/api/login_check', methods=['POST'])
def login_check():
    """ Endpoint para validar el PIN desde el servidor (Seguridad extra) """
    data = request.json
    token = data.get('token')
    pin_intento = str(data.get('pin')).strip()
    
    db_usuarios = cargar_usuarios_drive()
    
    if token in db_usuarios:
        pin_real = str(db_usuarios[token]['pin']).strip()
        if pin_intento == pin_real:
            session['user_token'] = token
            session['auth_logged'] = True
            session.permanent = True # La sesión persiste según config del navegador
            return jsonify({"status": "success", "msg": "Bienvenido"})
            
    return jsonify({"status": "error", "msg": "Credenciales inválidas"}), 401

@app.route('/logout')
def logout():
    """ Finaliza la sesión del usuario """
    token_previo = session.get('user_token')
    session.clear()
    logger.info(f"Sesión cerrada para token: {token_previo}")
    return redirect(f"/?token={token_previo}")

# --- API DE ADMINISTRADOR (EXCLUSIVO ANGEL CASTILLO) ---

@app.route('/api/admin/usuarios', methods=['GET', 'POST', 'PUT'])
def gestion_usuarios():
    """ 
    Panel de control de usuarios. 
    Solo accesible si el token de sesión es 'angel0301'.
    """
    if session.get('user_token') != 'angel0301':
        return jsonify({"error": "Acceso restringido al administrador"}), 403

    if request.method == 'GET':
        # Retorna la lista completa para el panel de moderador
        return jsonify(cargar_usuarios_drive())

    data = request.json

    if request.method == 'POST':
        # CREAR NUEVO OPERADOR
        try:
            nombre = data.get('nombre', 'Nuevo Usuario')
            contacto = data.get('contacto', 'S/C')
            nuevo_tkn = generar_token_unico(nombre)
            nuevo_pin = data.get('pin') if data.get('pin') else generar_pin_aleatorio()
            
            # Guardar en Google Sheets (Token, Nombre, Contacto, PIN, Rol)
            sheet.append_row([nuevo_tkn, nombre, contacto, nuevo_pin, "operador"])
            
            logger.info(f"Admin creó usuario: {nuevo_tkn}")
            return jsonify({
                "status": "created",
                "token": nuevo_tkn,
                "pin": nuevo_pin
            }), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    if request.method == 'PUT':
        # ACTUALIZAR OPERADOR EXISTENTE
        try:
            token_target = data.get('token')
            celda = sheet.find(token_target)
            if not celda:
                return jsonify({"error": "Usuario no encontrado"}), 404
            
            fila = celda.row
            # Actualizamos columnas específicas
            sheet.update_cell(fila, 2, data.get('nombre'))
            sheet.update_cell(fila, 3, data.get('contacto'))
            
            if data.get('nuevo_pin'):
                sheet.update_cell(fila, 4, data.get('nuevo_pin').strip())
                
            return jsonify({"status": "success", "msg": "Datos actualizados"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

@app.route('/api/admin/eliminar/<token_id>', methods=['DELETE'])
def eliminar_usuario(token_id):
    """ Elimina la fila de un usuario basado en su token """
    if session.get('user_token') != 'angel0301':
        return jsonify({"error": "No autorizado"}), 403
        
    try:
        celda = sheet.find(token_id)
        if celda:
            sheet.delete_rows(celda.row)
            logger.info(f"Usuario {token_id} eliminado de la base de datos.")
            return jsonify({"status": "deleted"})
        return jsonify({"error": "No encontrado"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- GESTIÓN DE HISTORIAL DE PRODUCCIÓN ---

@app.route('/api/save', methods=['POST'])
def guardar_calculo():
    """ 
    Recibe los cálculos de eficiencia del front-end 
    y los guarda en una pestaña separada de historial si se desea,
    o en una estructura de datos log.
    """
    user_tkn = session.get('user_token', 'anonimo')
    data = request.json
    ahora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Aquí podrías conectar a una segunda pestaña llamada 'Historial'
    # Por ahora simulamos la respuesta exitosa
    logger.info(f"Registro guardado por {user_tkn}: {data.get('info')}")
    return jsonify({"status": "saved", "timestamp": ahora})

@app.route('/api/load', methods=['GET'])
def cargar_historial():
    """ 
    Retorna los últimos movimientos del usuario actual 
    """
    # En un sistema real, filtrarías la hoja 'Historial' por el token del usuario
    return jsonify([]) # Retornamos vacío por ahora

# --- INICIO DE LA APLICACIÓN ---

if __name__ == '__main__':
    # Configuración para despliegue en Render, Heroku o Railway
    port = int(os.environ.get("PORT", 5000))
    
    # En producción, debug debe ser False
    app.run(host='0.0.0.0', port=port, debug=True)
