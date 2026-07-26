import os
import io
import sys
import logging
from logging.handlers import RotatingFileHandler
import pandas as pd
from flask import Flask, request, jsonify, render_template
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2.service_account import Credentials
from google.auth.exceptions import DefaultCredentialsError
from typing import List, Dict, Any, Optional, Tuple

# =============================================================================
# CONFIGURACIÓN GLOBAL Y CONSTANTES
# =============================================================================

# ID de la carpeta principal 'SICEP' en Google Drive
SICEP_FOLDER_ID = '1PbH8767Q86O-TntoxDxozaGiBl3WJqE0'

# Configuración del archivo de credenciales de Google Drive API
SCOPES = ['https://www.googleapis.com/auth/drive']
SERVICE_ACCOUNT_FILE = 'credentials.json'

# ID del documento de Sheets para las METAS
SHEET_ID = '1U9rvF4Uj55N9kV-sVuwP0y6OutkP___H'
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"

# ID del documento de Sheets para los USUARIOS 
SHEET_USUARIOS_ID = '1flxIGd4eBiGYe2vrSsPU318Feg2KHFV4Ip9oTF2aPvA'
URL_USUARIOS = f"https://docs.google.com/spreadsheets/d/{SHEET_USUARIOS_ID}/export?format=csv"

# =============================================================================
# INICIALIZACIÓN DE LA APLICACIÓN FLASK
# =============================================================================

app = Flask(__name__)

# =============================================================================
# CONFIGURACIÓN DE LOGGING (REGISTROS)
# =============================================================================

def configurar_logging() -> None:
    """
    Configura el sistema de registro (logging) de la aplicación.
    Crea un archivo 'sicep_backend.log' que guarda el historial de eventos
    y errores, rotando el archivo cuando alcanza 5MB.
    """
    log_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
    )
    
    # Crear manejador para archivo
    file_handler = RotatingFileHandler(
        'sicep_backend.log', 
        maxBytes=5000000, 
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(logging.INFO)
    
    # Crear manejador para consola
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_formatter)
    console_handler.setLevel(logging.DEBUG)

    # Añadir manejadores al logger de Flask
    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)
    app.logger.setLevel(logging.DEBUG)
    app.logger.info("Sistema de logging inicializado correctamente.")

# Ejecutar configuración de logging
configurar_logging()

# =============================================================================
# CLASES DE EXCEPCIONES PERSONALIZADAS
# =============================================================================

class SicepError(Exception):
    """Clase base para excepciones personalizadas del sistema SICEP."""
    pass

class DriveAuthError(SicepError):
    """Excepción lanzada cuando hay problemas de autenticación con Google Drive."""
    pass

class DataFetchError(SicepError):
    """Excepción lanzada cuando falla la obtención de datos de Google Sheets."""
    pass

# =============================================================================
# SERVICIOS DE GOOGLE DRIVE
# =============================================================================

def get_drive_service() -> Any:
    """
    Autentica y devuelve el servicio de Google Drive API.
    """
    try:
        if not os.path.exists(SERVICE_ACCOUNT_FILE):
            app.logger.error(f"Archivo de credenciales no encontrado: {SERVICE_ACCOUNT_FILE}")
            raise DriveAuthError(f"Falta el archivo {SERVICE_ACCOUNT_FILE}")
            
        creds = Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, 
            scopes=SCOPES
        )
        service = build('drive', 'v3', credentials=creds)
        app.logger.debug("Servicio de Google Drive inicializado con éxito.")
        return service
        
    except DefaultCredentialsError as e:
        app.logger.error(f"Error de credenciales por defecto: {str(e)}")
        raise DriveAuthError("Credenciales inválidas o expiradas.")
    except Exception as e:
        app.logger.error(f"Error inesperado al conectar con Drive: {str(e)}")
        raise DriveAuthError(f"Fallo de conexión: {str(e)}")

def buscar_carpeta_en_drive(service: Any, nombre_carpeta: str, parent_id: str) -> Optional[str]:
    """
    Busca una carpeta específica por nombre dentro de un directorio padre en Drive.
    """
    app.logger.debug(f"Buscando carpeta '{nombre_carpeta}' en el padre '{parent_id}'")
    query = (
        f"'{parent_id}' in parents and "
        f"name = '{nombre_carpeta}' and "
        f"mimeType = 'application/vnd.google-apps.folder' and "
        f"trashed = false"
    )
    
    try:
        response = service.files().list(
            q=query, 
            spaces='drive', 
            fields='files(id, name)'
        ).execute()
        
        files = response.get('files', [])
        if files:
            folder_id = files[0]['id']
            app.logger.debug(f"Carpeta encontrada. ID: {folder_id}")
            return folder_id
        return None
        
    except Exception as e:
        app.logger.error(f"Error al buscar la carpeta {nombre_carpeta}: {str(e)}")
        raise

def crear_carpeta_en_drive(service: Any, nombre_carpeta: str, parent_id: str) -> str:
    """
    Crea una nueva carpeta en Google Drive dentro del directorio especificado.
    """
    app.logger.info(f"Creando nueva carpeta '{nombre_carpeta}'...")
    file_metadata = {
        'name': nombre_carpeta,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id]
    }
    
    try:
        folder = service.files().create(
            body=file_metadata, 
            fields='id'
        ).execute()
        
        folder_id = folder.get('id')
        app.logger.info(f"Carpeta '{nombre_carpeta}' creada exitosamente. ID: {folder_id}")
        return folder_id
        
    except Exception as e:
        app.logger.error(f"Fallo al crear la carpeta {nombre_carpeta}: {str(e)}")
        raise

def obtener_o_crear_carpeta_usuario(service: Any, nombre_usuario: str) -> str:
    """
    Busca la subcarpeta del usuario en SICEP. Si no existe, la crea dinámicamente.
    """
    if not nombre_usuario:
        nombre_usuario = "OPERADOR_DESCONOCIDO"
        
    nombre_limpio = nombre_usuario.strip().upper()
    
    # Paso 1: Intentar buscar la carpeta
    folder_id = buscar_carpeta_en_drive(service, nombre_limpio, SICEP_FOLDER_ID)
    
    # Paso 2: Si no existe, crearla
    if not folder_id:
        folder_id = crear_carpeta_en_drive(service, nombre_limpio, SICEP_FOLDER_ID)
        
    return folder_id

# =============================================================================
# SERVICIOS DE PROCESAMIENTO DE DATOS (PANDAS)
# =============================================================================

def procesar_dataframe_metas(df: pd.DataFrame) -> Tuple[List[str], List[str], List[str], List[Dict[str, Any]]]:
    """
    Limpia y procesa el DataFrame extraído de Google Sheets.
    """
    app.logger.debug("Iniciando limpieza y procesamiento del DataFrame de metas.")
    
    df.columns = df.columns.str.strip()

    df.iloc[:, 0] = df.iloc[:, 0].astype(str).str.strip()
    df.iloc[:, 1] = df.iloc[:, 1].astype(str).str.strip()
    df.iloc[:, 3] = df.iloc[:, 3].astype(str).str.strip()

    estilos = sorted([e for e in df.iloc[:, 0].unique() if e.lower() != 'nan'])
    tallas = sorted([t for t in df.iloc[:, 1].unique() if t.lower() != 'nan'])
    procesos = sorted([p for p in df.iloc[:, 3].unique() if p.lower() != 'nan'])

    datos_estructurados = []
    
    for indice, row in df.iterrows():
        try:
            meta_val = float(row.iloc[5]) if pd.notnull(row.iloc[5]) else 0.0
            dz_hora_val = float(row.iloc[6]) if pd.notnull(row.iloc[6]) else 0.0
            pz_minuto_val = float(row.iloc[7]) if pd.notnull(row.iloc[7]) else 0.0
        except ValueError:
            meta_val, dz_hora_val, pz_minuto_val = 0.0, 0.0, 0.0

        datos_estructurados.append({
            'estilo': str(row.iloc[0]).strip(),
            'talla': str(row.iloc[1]).strip(),
            'proceso': str(row.iloc[3]).strip(),
            'meta': meta_val,
            'dz_hora': dz_hora_val,
            'pz_minuto': pz_minuto_val
        })
        
    app.logger.info(f"Procesamiento completo. Registros procesados: {len(datos_estructurados)}")
    return estilos, tallas, procesos, datos_estructurados

# =============================================================================
# RUTAS DE LA API (ENDPOINTS)
# =============================================================================

@app.route('/')
def index():
    """
    Ruta raíz. Sirve la interfaz gráfica (Frontend HTML).
    """
    app.logger.info("Solicitud recibida en la ruta raíz '/'")
    return render_template('index.html')

@app.route('/api/health', methods=['GET'])
def health_check():
    """
    Endpoint de monitoreo de estado.
    """
    return jsonify({
        'status': 'online',
        'service': 'SICEP_NEXUS_API',
        'version': '1.0.0'
    }), 200

@app.route('/api/login', methods=['POST'])
def validar_acceso():
    """
    Endpoint para validar el PIN de usuario contra la base de datos de Google Sheets.
    """
    app.logger.info("Iniciando solicitud de validación de acceso (/api/login)")
    try:
        data = request.get_json()
        if not data:
            return jsonify({'status': 'error', 'message': 'No se enviaron datos.'}), 400
            
        # Recibir el PIN y asegurar que sea texto sin espacios
        pin_ingresado = str(data.get('pin', '')).strip()
        
        # Leer el archivo de usuarios mediante pandas
        app.logger.debug(f"Intentando descargar datos de usuarios desde: {URL_USUARIOS}")
        df_usuarios = pd.read_csv(URL_USUARIOS)
        
        # Asegurar que la columna de PINs en el dataframe se trate como texto (string)
        # Asume que la columna en tu Excel se llama 'PIN'. Cambia esto si se llama diferente.
        if 'PIN' not in df_usuarios.columns:
            raise DataFetchError("La columna 'PIN' no existe en el documento de usuarios.")
            
        df_usuarios['PIN'] = df_usuarios['PIN'].astype(str).str.strip()
        
        # Buscar el PIN ingresado en la base de datos
        usuario_match = df_usuarios[df_usuarios['PIN'] == pin_ingresado]
        
        if not usuario_match.empty:
            # Asume que tienes columnas 'NOMBRE' y 'ROL' en tu documento. 
            # Ajusta los nombres de las columnas según tu estructura real.
            nombre = str(usuario_match.iloc[0].get('NOMBRE', 'Usuario Desconocido')).strip()
            rol = str(usuario_match.iloc[0].get('ROL', 'OPERADOR')).strip()
            
            app.logger.info(f"Acceso concedido para el usuario: {nombre} ({rol})")
            return jsonify({
                'status': 'success',
                'message': 'Acceso concedido',
                'usuario': nombre,
                'rol': rol
            }), 200
        else:
            app.logger.warning(f"Intento de acceso fallido con PIN: {pin_ingresado}")
            return jsonify({
                'status': 'error',
                'message': 'PIN incorrecto o usuario no encontrado'
            }), 401
            
    except Exception as e:
        app.logger.error(f"Error al validar PIN: {str(e)}")
        return jsonify({
            'status': 'error', 
            'message': 'Fallo interno al consultar la base de datos',
            'details': str(e)
        }), 500

@app.route('/api/metas/datos', methods=['GET'])
def obtener_metas():
    """
    Endpoint principal para obtener la base de datos de metas.
    """
    app.logger.info("Iniciando solicitud de obtención de metas (/api/metas/datos)")
    
    try:
        app.logger.debug(f"Intentando descargar datos desde: {CSV_URL}")
        df = pd.read_csv(CSV_URL)
        
        if df.empty:
            raise DataFetchError("El archivo de origen está vacío o no se pudo leer.")
            
        estilos, tallas, procesos, datos = procesar_dataframe_metas(df)

        response_payload = {
            'status': 'success',
            'estilos': estilos,
            'tallas': tallas,
            'procesos': procesos,
            'datos': datos,
            'total_registros': len(datos)
        }
        
        app.logger.info("Metas obtenidas y enviadas correctamente al cliente.")
        return jsonify(response_payload), 200

    except Exception as e:
        app.logger.error(f"Error crítico en obtener_metas: {str(e)}")
        return jsonify({
            'status': 'error', 
            'message': 'Error al procesar la base de datos',
            'details': str(e)
        }), 500

@app.route('/api/save', methods=['POST'])
def guardar_reporte():
    """
    Endpoint para guardar un reporte de producción.
    """
    app.logger.info("Iniciando solicitud para guardar reporte en Drive (/api/save)")
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'status': 'error', 'message': 'No se enviaron datos JSON.'}), 400
            
        usuario = data.get('usuario', 'OPERADOR_GENERAL')
        tipo_reporte = data.get('tipo', 'FICHA_TECNICA')
        lineas = data.get('lineas', [])

        if not lineas:
            return jsonify({'status': 'error', 'message': 'Las líneas del reporte están vacías.'}), 400

        service = get_drive_service()
        if not service:
            raise DriveAuthError("No se pudo iniciar el servicio de Google Drive.")
            
        user_folder_id = obtener_o_crear_carpeta_usuario(service, usuario)

        contenido_texto = "\n".join(lineas)
        timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
        nombre_archivo = f"{tipo_reporte}_{usuario}_{timestamp}.txt"
        
        file_metadata = {
            'name': nombre_archivo,
            'parents': [user_folder_id],
            'description': 'Reporte generado automáticamente por SICEP Nexus PWA'
        }
        
        app.logger.debug(f"Subiendo archivo {nombre_archivo} a Drive...")
        media = MediaIoBaseUpload(
            io.BytesIO(contenido_texto.encode('utf-8')), 
            mimetype='text/plain',
            resumable=True
        )
        
        file_creado = service.files().create(
            body=file_metadata, 
            media_body=media, 
            fields='id, name, webViewLink'
        ).execute()

        app.logger.info(f"Archivo guardado exitosamente. ID: {file_creado.get('id')}")
        
        return jsonify({
            'status': 'success',
            'file_name': file_creado.get('name'),
            'drive_url': file_creado.get('webViewLink'),
            'message': 'Reporte sincronizado con Google Drive.'
        }), 201

    except Exception as e:
        app.logger.error(f"Error en el guardado de reporte: {str(e)}")
        return jsonify({
            'status': 'error', 
            'message': 'Fallo interno al guardar el archivo.',
            'details': str(e)
        }), 500

@app.route('/api/historial/archivos', methods=['GET'])
def listar_historial():
    """
    Endpoint para consultar el historial de archivos.
    """
    usuario = request.args.get('usuario', 'OPERADOR_GENERAL')
    app.logger.info(f"Solicitud de historial recibida para el usuario: {usuario}")
    
    try:
        service = get_drive_service()
        user_folder_id = obtener_o_crear_carpeta_usuario(service, usuario)

        query = f"'{user_folder_id}' in parents and trashed = false"
        
        app.logger.debug(f"Ejecutando consulta de listado en Drive. Query: {query}")
        response = service.files().list(
            q=query, 
            spaces='drive', 
            fields='files(id, name, createdTime, webViewLink)',
            orderBy='createdTime desc'
        ).execute()
        
        files = response.get('files', [])
        
        reportes_lista = []
        for f in files:
            reportes_lista.append({
                'id_archivo': f.get('id'),
                'nombre': f.get('name'),
                'fecha_hora': f.get('createdTime'),
                'drive_url': f.get('webViewLink')
            })

        app.logger.info(f"Historial consultado con éxito. Archivos encontrados: {len(reportes_lista)}")
        return jsonify(reportes_lista), 200

    except Exception as e:
        app.logger.error(f"Error al consultar el historial: {str(e)}")
        return jsonify({
            'status': 'error', 
            'message': 'No se pudo recuperar el historial.',
            'details': str(e)
        }), 500

# =============================================================================
# EJECUCIÓN PRINCIPAL DEL SERVIDOR
# =============================================================================

if __name__ == '__main__':
    print("="*60)
    print(" SICEP NEXUS - INICIANDO SERVIDOR BACKEND ".center(60, "="))
    print("="*60)
    print(f"[*] Modo Debug: Activado")
    print(f"[*] Puerto por defecto: 5000")
    print(f"[*] Logs guardándose en: sicep_backend.log")
    print("="*60)
    
    app.run(host='0.0.0.0', port=5000, debug=True)
