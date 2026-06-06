import os
import json
import requests
import base64
from datetime import datetime, timedelta
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import config
from config import bot, SUPER_ADMIN_ID, ADMIN_LINK, db_lock

# ========================================================
# CONFIGURACIÓN AUTOMÁTICA DESDE RENDER / GITHUB
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = "futis417-jpg/mi-db-bot"  # Asegúrate de que el nombre del repo coincide
GITHUB_FILE = "database.json"
# ========================================================

URL_API = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"
HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

def init_db():
    """Lee la base de datos de GitHub y genera perfiles de emergencia para evitar KeyErrors."""
    with db_lock:
        default_db = {
            'cookies_list': [], 'admins': [str(SUPER_ADMIN_ID), int(SUPER_ADMIN_ID)], 'maintenance_mode': False,
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
            else:
                db = default_db
        except Exception as e:
            print(f"Error cargando DB desde GitHub: {e}")
            db = default_db

        # Asegurar que existan todas las estructuras base
        for key in default_db:
            if key not in db: db[key] = default_db[key]
        
        db['admins'] = list(set([str(a) for a in db.get('admins', [])] + [int(a) for a in db.get('admins', []) if str(a).isdigit()]))

        # Limpiar y parsear perfiles existentes
        profiles_limpios = {}
        for uid, profile in list(db.get('user_profiles', {}).items()):
            if not profile: continue
            if 'plan' not in profile: profile['plan'] = 'free'
            if 'vip_expiry' not in profile: profile['vip_expiry'] = None
            if 'daily_activations' not in profile: profile['daily_activations'] = 0
            if 'last_reset_date' not in profile: profile['last_reset_date'] = datetime.now().strftime("%Y-%m-%d")
            if 'referrals' not in profile: profile['referrals'] = 0
            if 'bonus_daily' not in profile: profile['bonus_daily'] = 0
            
            profiles_limpios[str(uid)] = profile
            profiles_limpios[int(uid)] = profile
        
        # 🚨 PARCHE DEFINITIVO: Si tu ID de Super Admin no está en el JSON, crearlo de emergencia
        # Esto evita que 'user_handlers.py' rompa al intentar leer tu menú de referidos.
        for admin_id in [str(SUPER_ADMIN_ID), int(SUPER_ADMIN_ID)]:
            if admin_id not in profiles_limpios:
                perfil_admin = {
                    'first_seen': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'username': "Admin",
                    'first_name': "Creador",
                    'activations': 0,
                    'plan': 'vip',  # Te ponemos VIP directamente por ser el dueño
                    'daily_activations': 0,
                    'last_reset_date': datetime.now().strftime("%Y-%m-%d"),
                    'vip_expiry': "2036-01-01 00:00:00",
                    'referrals': 0,
                    'bonus_daily': 0
                }
                profiles_limpios[str(SUPER_ADMIN_ID)] = perfil_admin
                profiles_limpios[int(SUPER_ADMIN_ID)] = perfil_admin
        
        db['user_profiles'] = profiles_limpios
        return db

def save_db(db_data):
    """Limpia los IDs duplicados e hilos antes de subir el archivo a GitHub."""
    with db_lock:
        try:
            db_to_save = dict(db_data)
            
            # Limpiar perfiles para que en GitHub solo queden guardados como String (formato estándar JSON)
            if 'user_profiles' in db_to_save:
                profiles_clean = {}
                for uid, profile in db_to_save['user_profiles'].items():
                    profiles_clean[str(uid)] = profile
                db_to_save['user_profiles'] = profiles_clean
                
            if 'admins' in db_to_save:
                db_to_save['admins'] = list(set([str(a) for a in db_to_save['admins']]))
            
            response = requests.get(URL_API, headers=HEADERS)
            sha = ""
            if response.status_code == 200:
                sha = response.json()['sha']
            
            contenido_json = json.dumps(db_to_save, indent=4)
            contenido_b64 = base64.b64encode(contenido_json.encode('utf-8')).decode('utf-8')
            
            payload = {
                "message": "Update database via Kant Flix Bot",
                "content": contenido_b64,
                "sha": sha
            }
            
            requests.put(URL_API, headers=HEADERS, json=payload)
        except Exception as e:
            print(f"Error guardando DB en GitHub: {e}")

def is_admin(user_id):
    db = init_db()
    return str(user_id) in [str(a) for a in db.get('admins', [])]

def check_and_reset_daily_limits(uid_str, db):
    uid_key = str(uid_str)
    profile = db['user_profiles'].get(uid_key)
    
    if not profile:
        profile = {
            'first_seen': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'username': "Unknown",
            'first_name': "User",
            'activations': 0,
            'plan': 'free',
            'daily_activations': 0,
            'last_reset_date': datetime.now().strftime("%Y-%m-%d"),
            'vip_expiry': None,
            'referrals': 0,
            'bonus_daily': 0
        }
        db['user_profiles'][str(uid_str)] = profile
        db['user_profiles'][int(uid_str)] = profile
        save_db(db)
    else:
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
    profile = db['user_profiles'].get(str(user_id)) or db['user_profiles'].get(int(user_id))
    
    if profile and profile.get('plan') == 'vip' and profile.get('vip_expiry'):
        try:
            expiry_date = datetime.strptime(profile['vip_expiry'], "%Y-%m-%d %H:%M:%S")
            if datetime.now() > expiry_date:
                profile['plan'] = 'free'
                profile['vip_expiry'] = None
                save_db(db)
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("🔄 Renovar VIP Ahora", url=ADMIN_LINK))
                bot.send_message(int(user_id), "⚠️ **Tu suscripción VIP ha caducado.** Has vuelto al plan Gratuito.\n\nPulsa abajo para renovar con el Administrador.", reply_markup=markup, parse_mode="Markdown")
                return False
            return True
        except:
            return False
    return False

def track_user(message, referred_by=None):
    db = init_db()
    user_id = message.from_user.id
    is_new = False
    
    if str(user_id) not in db['user_profiles'] and int(user_id) not in db['user_profiles']:
        is_new = True
        bonus = 1 if referred_by else 0 
        nuevo_perfil = {
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
        db['user_profiles'][str(user_id)] = nuevo_perfil
        db['user_profiles'][int(user_id)] = nuevo_perfil
        
        if referred_by:
            for r_key in [str(referred_by), int(referred_by)]:
                if r_key in db['user_profiles']:
                    db['user_profiles'][r_key]['referrals'] += 1
                    refs = db['user_profiles'][r_key]['referrals']
                    
                    if refs % 2 == 0:
                        current_expiry = db['user_profiles'][r_key].get('vip_expiry')
                        now = datetime.now()
                        if db['user_profiles'][r_key]['plan'] == 'vip' and current_expiry:
                            try:
                                new_expiry = datetime.strptime(current_expiry, "%Y-%m-%d %H:%M:%S") + timedelta(days=1)
                            except:
                                new_expiry = now + timedelta(days=1)
                        else:
                            new_expiry = now + timedelta(days=1)
                            
                        db['user_profiles'][r_key]['plan'] = 'vip'
                        db['user_profiles'][r_key]['vip_expiry'] = new_expiry.strftime("%Y-%m-%d %H:%M:%S")
                        db['user_profiles'][r_key]['daily_activations'] = 0
                        
                        try:
                            bot.send_message(int(referred_by), f"🎉 **¡ENHORABUENA!** 🎉\n\nHas invitado a tu referido número {refs}. ¡Acabas de ganar **1 DÍA VIP GRATIS** de forma automática! 💎", parse_mode="Markdown")
                        except: pass
                    else:
                        try:
                            bot.send_message(int(referred_by), f"👤 **¡Nuevo invitado unido!** (Llevas {refs}).\n¡Solo te falta 1 más para ganar 1 Día VIP! 💎", parse_mode="Markdown")
                        except: pass
                    break
        save_db(db)
    else:
        for u_key in [str(user_id), int(user_id)]:
            if u_key in db['user_profiles']:
                db['user_profiles'][u_key]['username'] = message.from_user.username
                db['user_profiles'][u_key]['first_name'] = message.from_user.first_name
        save_db(db)
    return is_new
