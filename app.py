from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import random
import string

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
    # Pasamos el nombre del usuario para que aparezca en la bienvenida
    user_name = usuarios_actuales[token]['nombre']
    return render_template('login.html', token=token, nombre=user_name)

@app.route('/api/login', methods=['POST'])
def login_verificar():
    data = request.json
    token = data.get('token')
    pin_ingresado = str(data.get('pin')).strip()
    
    usuarios_actuales = cargar_usuarios_drive()
    
    if token in usuarios_actuales:
        user_data = usuarios_actuales[token]
        pin_correcto = str(user_data['pin']).strip()
        
        if pin_ingresado == pin_correcto:
            # Guardamos en la sesión que este usuario ya se autenticó
            session['user_token'] = token
            session['user_name'] = user_data['nombre']
            session['auth_logged'] = True
            return jsonify({"status": "success"})
    
    return jsonify({"status": "error", "message": "PIN Incorrecto"}), 401

@app.route('/logout')
def logout():
    session.clear()
    return "Sesión cerrada. Cierre esta ventana."

# --- API DE ADMINISTRADOR (ANGEL) ---

@app.route('/api/admin/usuarios', methods=['GET', 'POST', 'PUT'])
def admin_drive():
    # Solo angel0301 puede gestionar usuarios
    if session.get('user_token') != 'angel0301': 
        return jsonify({"error": "No autorizado"}), 403
    
    if request.method == 'GET':
        return jsonify(cargar_usuarios_drive())

    data = request.json
    
    if request.method == 'POST':
        # Al crear usuarios, ahora el administrador puede elegir el PIN o dejar uno al azar
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
