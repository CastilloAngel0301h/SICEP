from flask import Flask, render_template, request, jsonify, session
import os
from datetime import datetime

app = Flask(__name__)
# Usamos una clave secreta para las sesiones
app.secret_key = os.environ.get('SECRET_KEY', 'angel_uth_2026_key')

# --- SEGURIDAD ---
USUARIOS = {
    "angel0301": "Angel Castillo",
    "equipo5": "Equipo de Trabajo #5",
    "admin": "Admin"
}

# Base temporal
db = {"historial": [], "feedback": []}

@app.route('/')
def index():
    token = request.args.get('token')
    if token in USUARIOS:
        session['user'] = USUARIOS[token]
    
    if 'user' in session:
        # IMPORTANTE: El archivo index.html debe estar en la carpeta /templates
        return render_template('index.html', usuario=session['user'])
    
    return "<h1 style='color:red;text-align:center;'>ACCESO DENEGADO</h1>", 403

@app.route('/api/save', methods=['POST'])
def save_data():
    if 'user' not in session: return jsonify({"status": "error"}), 403
    data = request.json
    data['user'] = session['user']
    data['date'] = datetime.now().strftime("%H:%M")
    db['historial'].append(data)
    return jsonify({"status": "success"})

@app.route('/api/load')
def load_data():
    return jsonify(db)

if __name__ == '__main__':
    # ESTO CORRIGE EL INTERNAL SERVER ERROR EN RENDER
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
