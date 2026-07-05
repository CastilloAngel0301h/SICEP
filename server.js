const express = require('express');
const fs = require('fs');
const path = require('path');
const { google } = require('googleapis');
const app = express();

app.use(express.json());

const CARPETA_RAIZ_DRIVE = '1PbH8767Q86O-TntoxDxozaGiBl3WJqE0';
const SPREADSHEET_ID_MASTER = '1_COMPARTIDA_CON_GOOGLE_SHEETS_S_I_C_E_P'; 

const auth = new google.auth.GoogleAuth({
    keyFile: path.join(__dirname, 'credenciales.json'),
    scopes: ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
});
const drive = google.drive({ version: 'v3', auth });
const sheets = google.sheets({ version: 'v4', auth });

let baseUsuarios = {
    "angel0301": { nombre: "Angel Castillo", pin: "1234", rol: "admin", hibernacion: false },
    "libny534": { nombre: "Libny", pin: "5678", rol: "admin", hibernacion: false }
};

async function syncConGoogleSheets(userToken, dataUsuario) {
    try {
        await sheets.spreadsheets.values.append({
            spreadsheetId: SPREADSHEET_ID_MASTER,
            range: 'Hibernaciones!A:E',
            valueInputOption: 'USER_ENTERED',
            requestBody: {
                values: [[new Date().toISOString(), userToken, dataUsuario.nombre, dataUsuario.hibernacion ? 'BLOQUEADO' : 'ACTIVO', 'MANUAL_SWITCH']]
            }
        });
    } catch (e) {
        console.error("Error sincronizando logs con Sheets:", e.message);
    }
}

async function obtenerOCrearCarpetaUsuario(nombreUsuario) {
    try {
        const query = `mimeType = 'application/vnd.google-apps.folder' and '${CARPETA_RAIZ_DRIVE}' in parents and name = '${nombreUsuario}' and trashed = false`;
        const res = await drive.files.list({ q: query, fields: 'files(id, name)' });
        
        if (res.data.files.length > 0) {
            return res.data.files[0].id;
        }
        
        const folderMetadata = {
            name: nombreUsuario,
            mimeType: 'application/vnd.google-apps.folder',
            parents: [CARPETA_RAIZ_DRIVE]
        };
        const folder = await drive.files.create({ resource: folderMetadata, fields: 'id' });
        return folder.data.id;
    } catch (e) {
        return CARPETA_RAIZ_DRIVE;
    }
}

app.post('/api/login', async (req, requireResponse) => {
    const { token, pin } = req.body;
    const usuario = baseUsuarios[token];
    
    if (usuario && usuario.pin === pin) {
        if (usuario.hibernacion === true) {
            return requireResponse.json({ status: 'blocked', hibernacion: true, message: "SISTEMA Y SERVER EN MODO HIBERNACION" });
        }
        usuario.ultima_conexion = new Date().toLocaleString();
        return requireResponse.json({ status: 'success', user: usuario });
    }
    return requireResponse.status(401).json({ status: 'error', message: 'Acceso Denegado' });
});

app.post('/api/admin/hibernar', async (req, res) => {
    const { token, status } = req.body;
    if (baseUsuarios[token]) {
        baseUsuarios[token].hibernacion = status;
        await syncConGoogleSheets(token, baseUsuarios[token]);
        return res.json({ status: 'success', message: 'Estado de hibernación actualizado en memoria y Sheets' });
    }
    return res.status(404).json({ status: 'error', message: 'Usuario no encontrado' });
});

app.post('/api/save', async (req, res) => {
    const { tipo, info, extenso } = req.body;
    const tokenUser = req.headers['x-user-token'] || 'angel0301';
    const usuario = baseUsuarios[tokenUser] || { nombre: "Anonimo" };
    
    const idCarpetaDestino = await obtenerOCrearCarpetaUsuario(usuario.nombre);
    const nombreArchivo = `${tipo}_Calculo_${Date.now()}`;
    
    let fileMetadata = { parents: [idCarpetaDestino] };
    let media = {};

    if (extenso === true) {
        fileMetadata.name = `${nombreArchivo}.docx`;
        fileMetadata.mimeType = 'application/vnd.google-apps.document'; 
        const stream = require('stream');
        const bufferStream = new stream.PassThrough();
        bufferStream.end(Buffer.from(`<h1>Reporte SICEP - ${tipo}</h1><p>Resultado: ${info.res}</p><p>Detalles: ${info.detalle}</p>`));
        media = { mimeType: 'text/html', body: bufferStream };
    } else {
        fileMetadata.name = `${nombreArchivo}.png`;
        fileMetadata.mimeType = 'image/png';
        const stream = require('stream');
        const bufferStream = new stream.PassThrough();
        bufferStream.end(Buffer.from('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7', 'base64')); 
        media = { mimeType: 'image/png', body: bufferStream };
    }

    try {
        const fileDrive = await drive.files.create({ resource: fileMetadata, media: media, fields: 'id, webViewLink' });
        return res.json({ status: 'success', url: fileDrive.data.webViewLink });
    } catch (err) {
        return res.status(500).json({ status: 'error', error: err.message });
    }
});

app.post('/api/admin/usuarios', (req, res) => {
    const { nombre, contacto } = req.body;
    const newToken = 'TK_' + Math.random().toString(36).substr(2, 6);
    const newPin = Math.floor(1000 + Math.random() * 9000).toString();
    
    baseUsuarios[newToken] = { nombre, contacto, pin: newPin, rol: 'user', hibernacion: false };
    res.json({ token: newToken, pin: newPin });
});

app.get('/api/admin/usuarios', (req, res) => res.json(baseUsuarios));

app.listen(3000, () => console.log('Servidor SICEP Corriendo Óptimamente en puerto 3000'));
