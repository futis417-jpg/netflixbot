import json
import requests
import base64
from datetime import datetime, timedelta
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import config
from config import bot, SUPER_ADMIN_ID, ADMIN_LINK, db_lock

# ========================================================
# CONFIGURACIÓN DE TU NUEVA BASE DE DATOS EN GITHUB
GITHUB_TOKEN = "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"  # <-- Asegúrate de poner tu token aquí
GITHUB_REPO = "futis417-jpg/mi-bot-db"
GITHUB_FILE = "database.json"
# ========================================================

URL_API = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"
HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

def init_db():
    """Lee la base de datos desde GitHub y asegura que los IDs sean strings."""
    with db_lock:
        default_db = {
            'cookies_list': [], 'admins': [str(SUPER_ADMIN_ID)], 'maintenance_mode': False,
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
                contenido_b64 = datos_recurso['content']
                contenido_json = base64.b64decode(contenido_b64).decode('utf-8')
                db = json.loads(contenido_json)
                
                # Forzar que todo lo que necesite el bot esté bien estructurado
                for key in default_db:
                    if key not in db: db[key] = default_db[key]
                
                # Convertir la lista de admins a strings para evitar conflictos de tipo
                db['admins'] = [str(a) for a in db.get('admins', [])]
                if str(SUPER_ADMIN_ID) not in db['admins']: 
                    db['admins'].append(str(SUPER_ADMIN_ID))
                
                # Asegurar que cada perfil tenga todos sus datos limpios
                for uid, profile in list(db['user_profiles'].items()):
                    if not profile: continue
                    if 'plan' not in profile: profile['plan'] = 'free'
                    if 'vip_expiry' not in profile: profile['vip_expiry'] = None
                    if 'daily_activations' not in profile: profile['daily_activations'] = 0
                    if 'last_reset_date' not in profile: profile['last_reset_date'] = datetime.now().strftime("%Y-%m-%d")
                    if 'referrals' not in profile: profile['referrals'] = 0
                    if 'bonus_daily' not in profile: profile['bonus_daily'] = 0
                return db
            else:
                print(f"Error API GitHub: Status {response.status_code}. Usando DB por defecto.")
                return default_db
        except Exception as e:
            print(f"Error cargando DB desde GitHub: {e}")
            return default_db

def save_db(db_data):
    """Guarda los cambios en GitHub de forma síncrona."""
    with db_lock:
        try:
            # Obtener el SHA actual para poder hacer el commit correctamente
            response = requests.get(URL_API, headers=HEADERS)
            sha = ""
            if response.status_code == 200:
                sha = response.json()['sha']
            
            contenido_json = json.dumps(db_data, indent=4)
            contenido_b64 = base64.b64encode(contenido_json.encode('utf-8')).decode('utf-8')
            
            payload = {
                "message": "Update database via Kant Flix Bot",
                "content": contenido_b64,
                "sha": sha
            }
            
            res_put = requests.put(URL_API, headers=HEADERS, json=payload)
            if res_put.status_code not in [200, 201]:
                print(f"Error al guardar en GitHub API: {res_put.status_code} - {res_put.text}")
        except Exception as e:
            print(f"Error guardando DB en GitHub: {e}")

def is_admin(user_id):
    db = init_db()
    return str(user_id) in db.get('admins', [])

def check_and_reset_daily_limits(uid_str, db):
    uid_str = str(uid_str)
    profile = db['user_profiles'].get(uid_str)
    
    if profile:
        today = datetime.now().strftime("%Y-%m-%d")
        if profile.get('last_reset_date') != today:
            profile['daily_activations'] = 0
            profile['last_reset_date'] = today
            save_db(db)
    
    try:
        from utils import auto_repair_system
        auto_repair_system()
    except: pass
    return profile

def check_vip_status(user_id):
    db = init_db()
    uid_str = str(user_id)
    profile = db['user_profiles'].get(uid_str, {})
    
    if profile and profile.get('plan') == 'vip' and profile.get('vip_expiry'):
        try:
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
        except:
            return False
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
        
        if referred_by and str(referred_by) in db['user_profiles'] and str(referred_by) != user_id:
            ref_str = str(referred_by)
            db['user_profiles'][ref_str]['referrals'] += 1
            refs = db['user_profiles'][ref_str]['referrals']
            
            if refs % 2 == 0:
                current_expiry = db['user_profiles'][ref_str].get('vip_expiry')
                now = datetime.now()
                
                if db['user_profiles'][ref_str]['plan'] == 'vip' and current_expiry:
                    try:
                        new_expiry = datetime.strptime(current_expiry, "%Y-%m-%d %H:%M:%S") + timedelta(days=1)
                    except:
                        new_expiry = now + timedelta(days=1)
                else:
                    new_expiry = now + timedelta(days=1)
                    
                db['user_profiles'][ref_str]['plan'] = 'vip'
                db['user_profiles'][ref_str]['vip_expiry'] = new_expiry.strftime("%Y-%m-%d %H:%M:%S")
                db['user_profiles'][ref_str]['daily_activations'] = 0
                
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
