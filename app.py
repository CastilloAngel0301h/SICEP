from flask import Flask, render_template, request, jsonify, session
import os
import json
import random
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'lion_power_uth_2026')

# --- PERSISTENCIA DE USUARIOS (Simulada para Render) ---
USERS_FILE = 'users.json'

def load_users():
    if not os.path.exists(USERS_FILE):
        # Usuario Admin por defecto
        initial = {"angel0301": {"name": "Angel Castillo", "pin": "0301", "role": "admin"}}
        save_users(initial)
        return initial
    with open(USERS_FILE, 'r') as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f)

@app.route('/')
def index():
    # El acceso es vía token en URL o sesión activa
    token = request.args.get('token')
    users = load_users()
    
    if token in users:
        # Si el token es válido, pedimos el PIN en el cliente
        session['pending_token'] = token
        return render_template('index.html', step='login')
    
    if 'user' in session:
        return render_template('index.html', usuario=session['user'], role=session.get('role'))
    
    return "<h1 style='color:red;text-align:center;'>ACCESO DENEGADO</h1>", 403

@app.route('/api/verify_pin', methods=['POST'])
def verify_pin():
    data = request.json
    token = session.get('pending_token')
    pin = data.get('pin')
    users = load_users()
    
    if token in users and users[token]['pin'] == pin:
        session['user'] = users[token]['name']
        session['user_id'] = token
        session['role'] = users[token]['role']
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "PIN Incorrecto"})

@app.route('/api/admin/add_user', methods=['POST'])
def add_user():
    if session.get('role') != 'admin': return jsonify({"status": "error"}), 403
    data = request.json
    name = data.get('name', 'operador')
    # Generar Token y PIN
    token = f"{name.lower().replace(' ', '')}{random.randint(100, 999)}"
    pin = f"{random.randint(1000, 9999)}"
    
    users = load_users()
    users[token] = {"name": name, "pin": pin, "role": "user"}
    save_users(users)
    
    return jsonify({"status": "success", "token": token, "pin": pin})

@app.route('/api/admin/list_users')
def list_users():
    if session.get('role') != 'admin': return jsonify({"status": "error"}), 403
    return jsonify(load_users())

# --- HISTORIAL Y VALORACIONES ---
db = {"historial": [], "feedback": []}

@app.route('/api/save', methods=['POST'])
def save_data():
    if 'user' not in session: return jsonify({"status": "error"}), 403
    data = request.json
    data['user'] = session['user']
    data['date'] = datetime.now().strftime("%H:%M")
    db['historial'].append(data)
    return jsonify({"status": "success"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
