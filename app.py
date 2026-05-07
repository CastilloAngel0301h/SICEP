from flask import Flask, render_template, request, jsonify, session
import os
import random
import string
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'angel_admin_2026_secure')

# Base de datos en memoria 
db = {
    "usuarios": {
        "angel0301": {"nombre": "Angel Castillo", "rol": "admin", "pin": "0000", "contacto": "Admin Principal"}
    },
    "historial": {}, 
    "feedback": []
}

def generar_token(nombre):
    prefijo = nombre.split()[0].lower()
    num = "".join(random.choices(string.digits, k=3))
    return f"{prefijo}{num}"

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
    return "<h1 style='color:white;background:#0d1b2a;text-align:center;padding:50px;font-family:sans-serif;'>ACCESO DENEGADO: TOKEN INVÁLIDO</h1>", 403

# --- GESTIÓN DE ADMINISTRADOR (EXCLUSIVO ANGEL) ---
@app.route('/api/admin/usuarios', methods=['GET', 'POST', 'PUT'])
def admin_users():
    if session.get('user_token') != 'angel0301': return jsonify({"error": "No autorizado"}), 403
    
    # Crear usuario
    if request.method == 'POST':
        data = request.json
        nuevo_tkn = generar_token(data['nombre'])
        pin = generar_pin()
        db["usuarios"][nuevo_tkn] = {
            "nombre": data['nombre'],
            "contacto": data['contacto'],
            "rol": "operador",
            "pin": pin
        }
        return jsonify({"token": nuevo_tkn, "pin": pin})
    
    # Editar usuario
    if request.method == 'PUT':
        data = request.json
        tkn = data['token']
        if tkn in db["usuarios"] and tkn != 'angel0301':
            db["usuarios"][tkn]['nombre'] = data['nombre']
            db["usuarios"][tkn]['contacto'] = data['contacto']
            if data.get('nuevo_pin'):
                db["usuarios"][tkn]['pin'] = data['nuevo_pin']
            return jsonify({"status": "updated", "pin": db["usuarios"][tkn]['pin']})
        return jsonify({"error": "Usuario no encontrado o protegido"}), 400
    
    return jsonify(db["usuarios"])

@app.route('/api/admin/eliminar/<tkn>', methods=['DELETE'])
def eliminar_usuario(tkn):
    if session.get('user_token') != 'angel0301' or tkn == "angel0301": return jsonify({"error": "Prohibido"}), 403
    if tkn in db["usuarios"]: del db["usuarios"][tkn]
    return jsonify({"status": "deleted"})

# --- OPERACIONES DE USUARIO ---
@app.route('/api/save', methods=['POST'])
def save_data():
    tkn = session.get('user_token')
    if not tkn: return jsonify({"error": "Sesion expirada"}), 403
    if tkn not in db["historial"]: db["historial"][tkn] = []
    
    data = request.json
    data['fecha_hora'] = datetime.now().strftime("%d/%m %H:%M")
    db["historial"][tkn].append(data)
    return jsonify({"status": "success"})

@app.route('/api/load')
def load_data():
    tkn = session.get('user_token')
    if tkn == 'angel0301':
        # El admin ve todo el historial
        historial_completo = []
        for user_token, registros in db["historial"].items():
            user_name = db["usuarios"].get(user_token, {}).get("nombre", "Desconocido")
            for reg in registros:
                reg_copy = reg.copy()
                reg_copy['usuario'] = user_name
                historial_completo.append(reg_copy)
        return jsonify(historial_completo)
    
    return jsonify(db["historial"].get(tkn, []))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
