from flask import Flask, render_template, request, jsonify, session
import os
import random
import string
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'angel_admin_2026_secure')

# Base de datos en memoria (Se recomienda usar DB externa para producción real)
db = {
    "usuarios": {
        "angel0301": {"nombre": "Angel Castillo", "rol": "admin", "pin": "0000", "contacto": "Admin Principal"}
    },
    "historial": {}, # {token: [{"tipo": "eficiencia/tiempo", "datos": {...}}]}
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
    return "<h1 style='color:white;background:black;text-align:center;padding:50px;'>ACCESO DENEGADO: TOKEN INVÁLIDO</h1>", 403

# --- GESTIÓN DE ADMINISTRADOR (EXCLUSIVO ANGEL) ---
@app.route('/api/admin/usuarios', methods=['GET', 'POST'])
def admin_users():
    if session.get('user_token') != 'angel0301': return jsonify({"error": "No autorizado"}), 403
    
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
    
    return jsonify(db["usuarios"])

@app.route('/api/admin/eliminar/<tkn>', methods=['DELETE'])
def eliminar_usuario(tkn):
    if session.get('user_token') != 'angel0301' or tkn == "angel0301": return jsonify({"error": "Prohibido"}), 403
    if tkn in db["usuarios"]: del db["usuarios"][tkn]
    return jsonify({"status": "deleted"})

@app.route('/api/admin/historial_global')
def historial_global():
    if session.get('user_token') != 'angel0301': return jsonify({}), 403
    return jsonify({"historial": db["historial"], "usuarios": db["usuarios"]})

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
    return jsonify(db["historial"].get(tkn, []))

@app.route('/api/rate', methods=['POST'])
def rate_app():
    db["feedback"].append({
        "usuario": session.get('user_name'),
        "estrellas": request.json.get('estrellas'),
        "comentario": request.json.get('comentario')
    })
    return jsonify({"status": "success"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
