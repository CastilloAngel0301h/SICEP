from flask import Flask, render_template, request, jsonify, session
import os
import random
import string
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'angel_lion_king_2026')

# Base de datos en memoria (Se reinicia con el servidor)
# Angel es el único ADMIN por defecto
db = {
    "usuarios": {
        "angel0301": {"nombre": "Angel Castillo", "rol": "admin", "pass": "2026"}
    },
    "historial": [],
    "feedback": []
}

def generar_token(nombre):
    nums = ''.join(random.choices(string.digits, k=3))
    return f"{nombre.lower().replace(' ', '')}{nums}"

def generar_pass():
    return ''.join(random.choices(string.digits, k=4))

@app.route('/')
def index():
    token = request.args.get('token')
    if token in db["usuarios"]:
        session['user_id'] = token
        session['user_name'] = db["usuarios"][token]["nombre"]
        session['rol'] = db["usuarios"][token]["rol"]
        return render_template('index.html', usuario=session['user_name'], rol=session['rol'])
    
    return "<h1 style='color:red;text-align:center;margin-top:50px;'>ACCESO DENEGADO: TOKEN INVÁLIDO</h1>", 403

@app.route('/api/admin/crear', methods=['POST'])
def crear_usuario():
    if session.get('rol') != 'admin': return jsonify({"error": "No autorizado"}), 403
    data = request.json
    nuevo_token = generar_token(data['nombre'])
    nueva_pass = generar_pass()
    db["usuarios"][nuevo_token] = {
        "nombre": data['nombre'],
        "identificador": data['contacto'], # Correo o Tel
        "rol": "user",
        "pass": nueva_pass
    }
    return jsonify({"token": nuevo_token, "pass": nueva_pass})

@app.route('/api/save', methods=['POST'])
def save_data():
    if 'user_id' not in session: return jsonify({"status": "error"}), 403
    data = request.json
    data['user'] = session['user_name']
    data['date'] = datetime.now().strftime("%d/%m %H:%M")
    db['historial'].append(data)
    return jsonify({"status": "success"})

@app.route('/api/load')
def load_data():
    return jsonify({
        "historial": db["historial"],
        "usuarios": db["usuarios"] if session.get('rol') == 'admin' else {}
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
