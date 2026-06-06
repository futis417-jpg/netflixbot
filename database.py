import json
import requests
import base64
from datetime import datetime, timedelta
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import config
from config import bot, SUPER_ADMIN_ID, ADMIN_LINK, db_lock

# ========================================================
# CONFIGURACIÓN DE TU NUEVA BASE DE DATOS EN GITHUB (100% GRATIS)
GITHUB_TOKEN = "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"
GITHUB_REPO = "futis417-jpg/mi-bot-db" # Ej: "ishak/mi-bot-db"
GITHUB_FILE = "database.json"
# ========================================================

URL_API = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"
HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

def init_db():
    """Lee la base de datos directamente desde GitHub de forma automática."""
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
        
        try:
            response = requests.get(URL_API, headers=HEADERS)
            if response.status_code == 200:
                datos_recurso = response.json()
                # Decodificar el contenido que viene en Base64 desde GitHub
                contenido_b64 = datos_recurso['content']
                contenido_json = base64.b64decode(contenido_b64).decode('utf-8')
                db = json.loads(contenido_json)
                
                # Asegurar que todas las llaves por defecto existan
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
            else:
                return default_db
        except Exception as e:
            print(f"Error cargando DB desde GitHub: {e}")
            return default_db

def save_db(db_data):
    """Guarda y sube los cambios a GitHub automáticamente haciendo un commit silencioso."""
    with db_lock:
        try:
            # Primero necesitamos obtener el 'sha' del archivo actual para poder actualizarlo
            response = requests.get(URL_API, headers=HEADERS)
            sha = ""
            if response.status_code == 200:
                sha = response.json()['sha']
            
            # Convertir el diccionario de datos a JSON ordenado
            contenido_json = json.dumps(db_data, indent=4)
            contenido_b64 = base64.b64encode(contenido_json.encode('utf-8')).decode('utf-8')
            
            payload = {
                "message": "Update database via Kant Flix Bot",
                "content": contenido_b64,
                "sha": sha
            }
            
            # Hacer el PUT para guardar los datos en la nube
            requests.put(URL_API, headers=HEADERS, json=payload)
        except Exception as e:
            print(f"Error guardando DB en GitHub: {e}")

def is_admin(user_id):
    if user_id == SUPER_ADMIN_ID: return True
    db = init_db()
    return user_id in db.get('admins', [])

def check_and_reset_daily_limits(uid_str, db):
    today = datetime.now().strftime("%Y-%m-%d")
    profile = db['user_profiles'].get(uid_str)
    
    if profile:
        if profile.get('last_reset_date') != today:
            profile['daily_activations'] = 0
            profile['last_reset_date'] = today
            save_db(db)
    
    from utils import auto_repair_system
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
