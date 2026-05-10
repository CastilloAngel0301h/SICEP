from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import random
import string

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'madrid_cr7_2026_secure')

# --- CONFIGURACIÓN DE GOOGLE SHEETS ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
try:
    creds = ServiceAccountCredentials.from_json_keyfile_name('credenciales.json', scope)
    client = gspread.authorize(creds)
    sheet = client.open("Base_Datos_Calculadora").sheet1
except Exception as e:
    print(f"Error de conexión: {e}")

def cargar_usuarios_drive():
    try:
        records = sheet.get_all_records()
        return {str(r['token']).strip(): r for r in records}
    except:
        return {}

@app.route('/')
def index():
    token = request.args.get('token')
    usuarios_actuales = cargar_usuarios_drive()
    
    if not token or token not in usuarios_actuales:
        error_html = f"""
        <div style='background: #001c44; color:white; text-align:center; padding:100px; font-family:sans-serif; height:100vh;'>
            <img src='https://upload.wikimedia.org/wikipedia/en/5/56/Real_Madrid_CF.svg' style='width:100px;'>
            <h1>ACCESO DENEGADO</h1>
            <p>Token inválido para el Bernabéu.</p>
        </div>
        """
        return error_html, 403

    if session.get('user_token') == token and session.get('auth_logged'):
        user_data = usuarios_actuales[token]
        return render_template('index.html', user=user_data, token=token)
    
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
        if pin_ingresado == str(user_data['pin']).strip():
            session['user_token'] = token
            session['user_name'] = user_data['nombre']
            session['auth_logged'] = True
            return jsonify({"status": "success"})
    
    # Mensaje especial si Fernando falla el PIN
    msg = "PIN Incorrecto"
    if token == 'amigazo020':
        msg = "¡SIUUU! PIN EQUIVOCADO, COMANDANTE"
        
    return jsonify({"status": "error", "message": msg}), 401

@app.route('/logout')
def logout():
    session.clear()
    return "Sesión cerrada."

# --- API DE ADMINISTRADOR ---
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
