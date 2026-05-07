from flask import Flask, render_template, request, jsonify, session
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import random
import string
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'angel_admin_2026_secure')

# --- CONFIGURACIÓN DE GOOGLE SHEETS ---
# Asegúrate de tener el archivo 'credenciales.json' en la misma carpeta
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
try:
    creds = ServiceAccountCredentials.from_json_keyfile_name('credenciales.json', scope)
    client = gspread.authorize(creds)
    # Abre la hoja por su nombre exacto
    sheet = client.open("Base_Datos_Calculadora").sheet1
except Exception as e:
    print(f"Error de conexión a Google: {e}")

# --- FUNCIONES DE SOPORTE ---
def cargar_usuarios_drive():
    """Trae los usuarios actualizados desde Google Sheets"""
    try:
        records = sheet.get_all_records()
        return {str(r['token']): r for r in records}
    except:
        return {}

def generar_token(nombre):
    prefijo = nombre.split()[0].lower()
    num = "".join(random.choices(string.digits, k=3))
    return f"{prefijo}{num}"

def generar_pin():
    return "".join(random.choices(string.digits, k=4))

# --- RUTAS DE LA APLICACIÓN ---

@app.route('/')
def index():
    token = request.args.get('token')
    usuarios_actuales = cargar_usuarios_drive()
    
    if token in usuarios_actuales:
        user_data = usuarios_actuales[token]
        session['user_token'] = token
        session['user_name'] = user_data['nombre']
        # Pasamos token=token para que el HTML reconozca si eres angel0301
        return render_template('index.html', user=user_data, token=token)
    
    return "<h1 style='color:white;background:#0b132b;text-align:center;padding:50px;font-family:sans-serif;'>ACCESO DENEGADO: TOKEN INVÁLIDO</h1>", 403

# --- API EXCLUSIVA PARA ADMINISTRADOR (ANGEL) ---

@app.route('/api/admin/usuarios', methods=['GET', 'POST', 'PUT'])
def admin_drive():
    if session.get('user_token') != 'angel0301': 
        return jsonify({"error": "No autorizado"}), 403
    
    if request.method == 'GET':
        return jsonify(cargar_usuarios_drive())

    data = request.json
    
    if request.method == 'POST':
        nuevo_tkn = generar_token(data['nombre'])
        nuevo_pin = generar_pin()
        # Insertar en Google Sheets: token, nombre, contacto, pin, rol
        sheet.append_row([nuevo_tkn, data['nombre'], data['contacto'], nuevo_pin, "operador"])
        return jsonify({"token": nuevo_tkn, "pin": nuevo_pin})

    if request.method == 'PUT':
        # Buscar usuario por token para editar
        try:
            celda = sheet.find(data['token'])
            fila = celda.row
            sheet.update_cell(fila, 2, data['nombre'])   # Columna B: Nombre
            sheet.update_cell(fila, 3, data['contacto']) # Columna C: Contacto
            if data.get('nuevo_pin') and data['nuevo_pin'].strip() != "":
                sheet.update_cell(fila, 4, data['nuevo_pin']) # Columna D: PIN
            return jsonify({"status": "updated"})
        except:
            return jsonify({"error": "Usuario no encontrado"}), 404

@app.route('/api/admin/eliminar/<tkn>', methods=['DELETE'])
def eliminar_drive(tkn):
    if session.get('user_token') != 'angel0301' or tkn == 'angel0301':
        return jsonify({"error": "Acción no permitida"}), 403
    
    try:
        celda = sheet.find(tkn)
        sheet.delete_rows(celda.row)
        return jsonify({"status": "deleted"})
    except:
        return jsonify({"error": "No se pudo eliminar"}), 404

# --- INICIO DEL SERVIDOR ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
