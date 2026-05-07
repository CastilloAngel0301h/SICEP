from flask import Flask, render_template, request, jsonify, session
import os
import random
import string
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'angel_lion_uth_2026')

# --- BASE DE DATOS DE USUARIOS (Simulada) ---
# angel0301 es el único con rol 'admin'
USUARIOS_DB = {
    "angel0301": {"nombre": "Angel Castillo", "rol": "admin", "id": "99887766"},
    "equipo5": {"nombre": "Equipo de Trabajo #5", "rol": "user", "id": "11223344"}
}

db = {"historial": [], "feedback": []}

def generar_token():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

@app.route('/')
def index():
    token = request.args.get('token')
    if token in USUARIOS_DB:
        session['user_token'] = token
        session['user_data'] = USUARIOS_DB[token]
    
    if 'user_token' in session:
        return render_template('index.html', user=session['user_data'], token=session['user_token'])
    
    return "<h1 style='color:red;text-align:center;margin-top:50px;'>ACCESO RESTRINGIDO - CONTACTE AL ADMINISTRADOR</h1>", 403

# API para el Administrador (Angel)
@app.route('/api/admin/usuarios', methods=['GET', 'POST', 'DELETE'])
def gestionar_usuarios():
    if session.get('user_data', {}).get('rol') != 'admin':
        return jsonify({"status": "denied"}), 403
    
    if request.method == 'POST':
        data = request.json
        nuevo_token = generar_token()
        USUARIOS_DB[nuevo_token] = {
            "nombre": data['nombre'],
            "rol": "user",
            "id": data['contacto']
        }
        link = f"{request.url_root}?token={nuevo_token}"
        return jsonify({"status": "created", "token": nuevo_token, "link": link})
    
    if request.method == 'DELETE':
        token_del = request.args.get('token')
        if token_del in USUARIOS_DB and token_del != "angel0301":
            del USUARIOS_DB[token_del]
        return jsonify({"status": "deleted"})

    return jsonify(USUARIOS_DB)

@app.route('/api/save', methods=['POST'])
def save_data():
    if 'user_token' not in session: return jsonify({"status": "error"}), 403
    data = request.json
    data['user'] = session['user_data']['nombre']
    data['date'] = datetime.now().strftime("%H:%M")
    db['historial'].append(data)
    return jsonify({"status": "success"})

@app.route('/api/load')
def load_data():
    return jsonify(db)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
