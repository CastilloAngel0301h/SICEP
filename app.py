from flask import Flask, render_template, request, jsonify, session
import os
import random
import string
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'uth_lion_key_2026')

# Base de datos en memoria (Se resetea al reiniciar Render)
# Angel es el ADMIN único
db = {
    "usuarios": {
        "angel0301": {"nombre": "Angel Castillo", "rol": "admin", "pin": "2004"}
    },
    "historial": {}, # {token: []}
    "feedback": []
}

def generar_token(nombre):
    num = "".join(random.choices(string.digits, k=3))
    return f"{nombre.split()[0].lower()}{num}"

def generar_pin():
    return "".join(random.choices(string.digits, k=4))

@app.route('/')
def index():
    token = request.args.get('token')
    if token in db["usuarios"]:
        session['user_token'] = token
        session['user_name'] = db["usuarios"][token]["nombre"]
        session['user_rol'] = db["usuarios"][token]["rol"]
        return render_template('index.html', user=db["usuarios"][token], token=token)
    return "<h1 style='color:red;text-align:center;'>ACCESO DENEGADO: TOKEN INVÁLIDO</h1>", 403

# --- RUTAS DE ADMINISTRACIÓN (SOLO ANGEL) ---
@app.route('/api/admin/crear', methods=['POST'])
def crear_usuario():
    if session.get('user_rol') != 'admin': return jsonify({"error": "No autorizado"}), 403
    data = request.json
    nuevo_token = generar_token(data['nombre'])
    pin = generar_pin()
    db["usuarios"][nuevo_token] = {
        "nombre": data['nombre'],
        "id_contacto": data['contacto'],
        "rol": "operador",
        "pin": pin
    }
    return jsonify({"token": nuevo_token, "pin": pin})

@app.route('/api/admin/usuarios', methods=['GET'])
def listar_usuarios():
    if session.get('user_rol') != 'admin': return jsonify([]), 403
    return jsonify(db["usuarios"])

@app.route('/api/admin/eliminar/<tkn>', methods=['DELETE'])
def eliminar_usuario(tkn):
    if session.get('user_rol') != 'admin' or tkn == "angel0301": return jsonify({"error": "No"}), 403
    del db["usuarios"][tkn]
    return jsonify({"status": "deleted"})

# --- RUTAS DE OPERACIÓN ---
@app.route('/api/save', methods=['POST'])
def save_data():
    tkn = session.get('user_token')
    if not tkn: return jsonify({"error": "Sesion expirada"}), 403
    if tkn not in db["historial"]: db["historial"][tkn] = []
    
    data = request.json
    data['hora'] = datetime.now().strftime("%H:%M")
    db["historial"][tkn].append(data)
    return jsonify({"status": "success"})

@app.route('/api/load')
def load_data():
    tkn = session.get('user_token')
    return jsonify(db["historial"].get(tkn, []))

@app.route('/api/rate', methods=['POST'])
def rate_app():
    db["feedback"].append(request.json)
    return jsonify({"status": "success"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
