from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import database
from database import init_db, is_admin

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
    markup.add(InlineKeyboardButton("📄 Exportar BD", callback_data="admin_backup"), InlineKeyboardButton("📤 Restaurar BD", callback_data="admin_restore"))
    markup.add(InlineKeyboardButton("📄 Exportar Usuarios", callback_data="admin_export_users"), InlineKeyboardButton("🧹 Limpiar Agotadas", callback_data="admin_clear_dead_cookies"))
    markup.add(InlineKeyboardButton("⚙️ Forzar Limpieza", callback_data="admin_clear_cache"))
    maint_text = "🔴 Quitar Mantenimiento" if db.get('maintenance_mode', False) else "🟢 Poner Mantenimiento"
    markup.add(InlineKeyboardButton(maint_text, callback_data="admin_toggle_maint"))
    return markup

def admin_plans_keyboard(db):

def admin_plans_keyboard(db):
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(f"✏️ Editar Límite Gratis ({db['plans']['free']['daily_limit']}/día)", callback_data="admin_edit_plan_free"),
        InlineKeyboardButton(f"✏️ Editar Límite VIP ({db['plans']['vip']['daily_limit']}/día)", callback_data="admin_edit_plan_vip"),
        InlineKeyboardButton("🔙 Volver al Panel", callback_data="admin_back_panel")
    )
    return markup
