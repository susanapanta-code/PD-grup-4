
from flask import Flask, render_template
import os

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('indexMQTT.html')

if __name__ == '__main__':
    # Verificar que existen los certificados
    if not os.path.exists('cert.pem') or not os.path.exists('key.pem'):
        print("[ERROR] Certificados SSL no encontrados!")
        print("Los certificados se han generado automáticamente.")
        exit(1)
    
    print("[✓] Servidor HTTPS iniciado")
    print("    https://127.0.0.1:5002")
    print("")
    
    # Ejecutar con HTTPS usando certificados autofirmados
    app.run(host='0.0.0.0', port=5002, debug=True, use_reloader=False, 
            ssl_context=('cert.pem', 'key.pem'))

