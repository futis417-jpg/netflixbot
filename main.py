import threading
import time
import os
from config import app, bot
import database
import user_handlers  # No borrar: Importante para registrar los manejadores de usuario
import admin_handlers  # No borrar: Importante para registrar los manejadores del admin

@app.route('/')
def home():
    return "🚀 Servidor KANT FLIX Operativo y Despierto"

def run_web_server():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    database.init_db()
    # Ejecutamos el servidor Web de Flask en un hilo independiente
    threading.Thread(target=run_web_server, daemon=True).start()
    
    # Bucle infinito del Bot con control de fallos automático
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            time.sleep(5)
