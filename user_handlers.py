import os
import time
from datetime import datetime, timedelta
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import config
from config import bot, ADMIN_LINK, RATE_LIMIT_SECONDS, MAX_USES_PER_COOKIE
import database
from database import init_db, save_db, is_admin, check_vip_status, check_and_reset_daily_limits, track_user
import utils
from utils import check_rate_limit
import keyboards
from keyboards import main_user_keyboard, countries_keyboard
from playwright_service import run_playwright_activation

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if not config.bot_info: config.bot_info = bot.get_me()
    
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
    if not config.bot_info: config.bot_info = bot.get_me()
    
    uid = str(message.from_user.id)
    db = init_db()
    refs = db['user_profiles'][uid].get('referrals', 0)
    bot_link = f"https://t.me/{config.bot_info.username}?start={uid}"
    
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
