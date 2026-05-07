from flask import Flask, render_template, request, jsonify, session
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'angel_industrial_2026')

# --- SEGURIDAD: ACCESO POR ENLACE PERSONAL ---
USUARIOS = {
    "angel0301": "Angel Castillo",
    "equipo5": "Equipo de Trabajo #5",
    "admin": "Control de Producción"
}

# Base de datos temporal
db = {
    "historial": [],
    "feedback": []
}

@app.route('/')
def index():
    token = request.args.get('token')
    if token in USUARIOS:
        session['user'] = USUARIOS[token]
    
    if 'user' in session:
        return render_template('index.html', usuario=session['user'])
    
    return "<h1 style='color:red; text-align:center; margin-top:50px;'>ACCESO DENEGADO</h1>", 403

@app.route('/api/save', methods=['POST'])
def save_data():
    if 'user' not in session: return jsonify({"status": "error"}), 403
    data = request.json
    data['id'] = len(db['historial']) + 1
    data['user'] = session['user']
    data['date'] = datetime.now().strftime("%H:%M")
    db['historial'].append(data)
    return jsonify({"status": "success"})

@app.route('/api/rate', methods=['POST'])
def save_rate():
    if 'user' not in session: return jsonify({"status": "error"}), 403
    db['feedback'].append(request.json)
    return jsonify({"status": "success"})

@app.route('/api/load')
def load_data():
    return jsonify(db)

if __name__ == '__main__':
    app.run(debug=True)