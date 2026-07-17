
async function checkForUpdates() {
  try {
    const response = await fetch('/version.json');
    const data = await response.json();
    const currentVersion = "1.0"; // Tu versión actual

    if (data.version !== currentVersion) {
      const updateBanner = document.createElement('div');
      updateBanner.innerHTML = `
        <div style="position:fixed; bottom:0; width:100%; background:#ffcc00; padding:15px; text-align:center; z-index:9999;">
          ¡Nueva versión ${data.version} disponible! 
          <a href="${data.apkUrl}" style="color:black; font-weight:bold; margin-left:10px;">Descargar aquí</a>
        </div>
      `;
      document.body.appendChild(updateBanner);
    }
  } catch (e) {
    console.log("No se pudo verificar actualizaciones.");
  }
}
checkForUpdates();
