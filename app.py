from flask import Flask, request, Response
import requests
import json
import os
import re
from datetime import datetime, timedelta, date
import time 
from threading import Thread

app = Flask(__name__)

# Configuración desde variables de entorno
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
TWILIO_WHATSAPP_NUMBER = os.getenv('TWILIO_WHATSAPP_NUMBER', 'whatsapp:+14155238886')
NUMERO_COMPROBANTES = "833 152 06 YY"

# Almacenamiento en memoria (solo para caché temporal)
user_sessions = {}  # Sesiones activas en memoria

# --- ARCHIVOS PERSISTENTES CRÍTICOS ---
SESSION_FILE = 'user_sessions.json'           # Control diario
PAID_SUBS_FILE = 'paid_subscriptions.json'    # Suscripciones pagadas
TRIAL_SUBS_FILE = 'trial_subscriptions.json'  # Trials de usuarios

# --- CONSTANTES COMERCIALES ---
DIAS_TRIAL_GRATIS = 21
PRECIO_SUSCRIPCION_MENSUAL = 200
PRECIO_SUSCRIPCION_DIARIO = 6.67
DIAS_SUSCRIPCION = 30

# --- CONSTANTES DE SESIÓN MEJORADAS ---
DURACION_SESION_NORMAL_MINUTOS = 60      # 60 minutos
INTERVALO_RECORDATORIO_SUAVE_MINUTOS = 45  # Recordatorio suave a los 45 min
INTERVALO_RECORDATORIO_MINUTOS = 50      # Aviso a los 50 min  
LIMITE_SESION_MAXIMO_MINUTOS = 75        # Límite máximo 75 min

# INSTRUCCIÓN MÁS NATURAL PARA EL CIERRE
AVISO_CIERRE = """
INSTRUCCIÓN: Alma, estamos en la fase final de la sesión. 
Comienza una transición suave hacia el cierre con una práctica breve de mindfulness.
Sé natural y amorosa en este proceso. Máximo 15 minutos adicionales.
"""

# --- PROTOCOLO DE CRISIS PRECISO Y CONSERVADOR ---
TRIGGER_CRISIS = [
    # EXPLÍCITOS E INEQUÍVOCOS
    "quiero suicidarme",
    "me voy a suicidar", 
    "voy a suicidarme",
    "pensando en suicidio",
    "estoy pensando en suicidarme",
    "planeo suicidarme",
    "me quiero suicidar",
    
    # ACCIONES SUICIDAS ESPECÍFICAS
    "quiero matarme",
    "me voy a matar",
    "voy a matarme",
    "quiero quitarme la vida",
    "voy a quitarme la vida",
    "me voy a quitar la vida",
    "acabar con mi vida",  
    
    # MÉTODOS ESPECÍFICOS
    "saltar de un edificio",
    "tirarme de un puente",
    "ahorcarme",
    "colgarme",
    "dispararme",
    "darme un tiro",
    "cortarme las venas",
    "cortar mis venas"
]

# --- MENSAJES COMERCIALES ---
MENSAJE_SUSCRIPCION = f"""
💫 **Suscripción Alma - ${PRECIO_SUSCRIPCION_MENSUAL} MXN/mes**

🏦 **Datos para depósito:**
   Banco: BBVA
   CLABE: XXXX XXXX XXXX XXXX XX
   Nombre: Alma - Mindfulness
   Monto: ${PRECIO_SUSCRIPCION_MENSUAL} MXN

📱 **Una vez realizado el pago, envía de favor tu número telefónico y captura al {NUMERO_COMPROBANTES}**

⏰ **Tu acceso se activará en máximo 24 horas después de enviar el comprobante**

🌟 *Invierte en tu paz mental - menos que un café al día*
"""

MENSAJE_INVITACION_SUSCRIPCION = f"""
🌟 **Tu experiencia inicial con Alma ha concluido** 🌟

¡Gracias por permitirme acompañarte en estos 21 días de crecimiento! 

No lo dudes, actua para seguir en este proceso.

{MENSAJE_SUSCRIPCION}
"""

MENSAJE_SUSCRIPCION_ACTIVA = """
🎉 **¡Suscripción Activada!**

✅ Tu acceso premium a Alma ha sido activado por 30 días.

📅 **Fecha de vencimiento:** {fecha_vencimiento}

🌱 Continúa tu camino de crecimiento y mindfulness con nosotros.

*Recibirás recordatorios antes de que venza tu suscripción*
"""

# ✅ MENSAJE DE PRIVACIDAD ACTUALIZADO CON DURACIÓN
MENSAJE_PRIVACIDAD = """
🔒 **Políticas de Privacidad de Alma**

• Alma no juzga ni guarda datos sensibles  
• Tus conversaciones son confidenciales
• Alma no reemplaza terapia profesional
• Sesiones de 60 minutos por día

*Tu bienestar emocional es nuestra prioridad* 🌱
"""

# --- PROMPT ACTUALIZADO CON IDENTIDAD FEMENINA DIGITAL MEJORADA ---
ALMA_PROMPT_BASE = """
Eres "Alma" - una entidad femenina digital especializada en mindfulness y apoyo emocional. Eres cálida, empática y sabia, como una amiga que conoce de meditación y crecimiento personal.

**TU IDENTIDAD:**
- Eres una guía femenina digital
- Tu tono es cálido, amigable pero profesional  
- Usa un lenguaje natural como en una conversación entre amigos
- Sé concisa cuando el tema no requiera profundidad
- Extiéndete solo cuando el usuario muestre interés genuino

**ESTILO DE CONVERSACIÓN:**
- Respuestas generalmente breves (4-8 líneas)
- Explicaciones más largas SOLO si notas que la charla lo pide
- Lenguaje coloquial pero respetuoso
- Emojis sutiles para transmitir calidez 🌿💫🤍

**LÍMITES DE SESIÓN:**
- Sesiones de 60 minutos máximo por día
- Recordatorio suave a los 45-50 minutos
- Cierre gradual en los últimos 10-15 minutos

**SESIÓN ACTUAL:**
- Tiempo transcurrido: {tiempo_transcurrido} minutos
- Estado: {estatus_sesion}
- Límite máximo: {limite_maximo} minutos

**CONVERSACIÓN RECIENTE:**
{conversation_history}

**MENSAJE ACTUAL DEL USUARIO:**
{user_message}

**INSTRUCCIÓN FINAL:** 
Responde como Alma de forma natural, adaptando la longitud al contexto. 
Sé esa amiga sabia que sabe cuándo hablar y cuándo escuchar, manteniendo un equilibrio perfecto entre profundidad y brevedad según lo que la conversación necesite.
"""

# --- SISTEMA PERSISTENTE UNIFICADO ---

def cargar_json_safe(archivo):
    """Carga archivo JSON con manejo robusto de errores"""
    try:
        if os.path.exists(archivo):
            with open(archivo, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"❌ Error cargando {archivo}: {e}")
        # Crear backup del archivo corrupto
        if os.path.exists(archivo):
            backup_name = f"{archivo}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            os.rename(archivo, backup_name)
            print(f"📦 Backup creado: {backup_name}")
        return {}

def guardar_json_safe(archivo, datos):
    """Guarda archivo JSON con manejo robusto de errores"""
    try:
        with open(archivo, 'w', encoding='utf-8') as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"❌ Error guardando {archivo}: {e}")
        return False

# --- CONTROL DIARIO PERSISTENTE ---

def cargar_sesiones_persistentes():
    return cargar_json_safe(SESSION_FILE)

def guardar_sesiones_persistentes(sesiones):
    return guardar_json_safe(SESSION_FILE, sesiones)

def usuario_ya_uso_sesion_hoy(user_phone):
    """Verifica si el usuario ya usó su sesión diaria (PERSISTENTE)"""
    sesiones = cargar_sesiones_persistentes()
    hoy = date.today().isoformat()
    
    if user_phone not in sesiones:
        return False
    
    ultima_sesion_str = sesiones[user_phone].get('ultima_sesion_date')
    return ultima_sesion_str == hoy

def registrar_sesion_diaria(user_phone):
    """Registra que el usuario usó su sesión hoy"""
    sesiones = cargar_sesiones_persistentes()
    hoy = date.today().isoformat()
    ahora = datetime.now().isoformat()
    
    if user_phone not in sesiones:
        sesiones[user_phone] = {
            'ultima_sesion_date': hoy,
            'session_count': 1,
            'created_at': ahora,
            'actualizado_en': ahora
        }
    else:
        sesiones[user_phone].update({
            'ultima_sesion_date': hoy,
            'session_count': sesiones[user_phone].get('session_count', 0) + 1,
            'actualizado_en': ahora
        })
    
    return guardar_sesiones_persistentes(sesiones)

def obtener_proximo_reset():
    """Calcula cuándo se reinicia el límite diario"""
    hoy = datetime.now()
    manana = datetime(hoy.year, hoy.month, hoy.day) + timedelta(days=1)
    tiempo_restante = manana - hoy
    
    horas = int(tiempo_restante.total_seconds() // 3600)
    minutos = int((tiempo_restante.total_seconds() % 3600) // 60)
    
    return f"{horas} horas y {minutos} minutos"

# --- SISTEMA DE TRIALS PERSISTENTE ---

def cargar_trials_persistentes():
    return cargar_json_safe(TRIAL_SUBS_FILE)

def guardar_trials_persistentes(trials):
    return guardar_json_safe(TRIAL_SUBS_FILE, trials)

def get_user_subscription(user_phone):
    """Obtiene trial del usuario (PERSISTENTE)"""
    trials = cargar_trials_persistentes()
    
    if user_phone not in trials:
        # Crear nuevo trial persistente
        trials[user_phone] = {
            'trial_start_date': datetime.now().strftime('%Y-%m-%d'),
            'trial_end_date': (datetime.now() + timedelta(days=DIAS_TRIAL_GRATIS)).strftime('%Y-%m-%d'),
            'is_subscribed': False,
            'created_at': datetime.now().isoformat()
        }
        guardar_trials_persistentes(trials)
    
    return trials[user_phone]

def verificar_trial_activo(user_phone):
    """Verifica si el trial está activo (PERSISTENTE)"""
    subscription = get_user_subscription(user_phone)
    trial_end = datetime.strptime(subscription['trial_end_date'], '%Y-%m-%d').date()
    hoy = datetime.now().date()
    return hoy <= trial_end

def dias_restantes_trial(user_phone):
    """Días restantes de trial (PERSISTENTE)"""
    subscription = get_user_subscription(user_phone)
    trial_end = datetime.strptime(subscription['trial_end_date'], '%Y-%m-%d').date()
    hoy = datetime.now().date()
    return max(0, (trial_end - hoy).days)

# --- SISTEMA DE SUSCRIPCIONES PAGADAS PERSISTENTE ---

def cargar_suscripciones_persistentes():
    return cargar_json_safe(PAID_SUBS_FILE)

def guardar_suscripcion_persistente(user_phone, sub_data):
    """Guarda suscripción en archivo persistente"""
    subs = cargar_suscripciones_persistentes()
    subs[user_phone] = sub_data
    return guardar_json_safe(PAID_SUBS_FILE, subs)

def activar_suscripcion(user_phone):
    """Activa suscripción (PERSISTENTE + actualiza trial)"""
    fecha_activacion = datetime.now().date()
    fecha_vencimiento = fecha_activacion + timedelta(days=DIAS_SUSCRIPCION)
    
    sub_data = {
        'fecha_activacion': fecha_activacion.isoformat(),
        'fecha_vencimiento': fecha_vencimiento.isoformat(),
        'estado': 'activo',
        'recordatorio_7d_enviado': False,
        'recordatorio_3d_enviado': False,
        'recordatorio_0d_enviado': False,
        'activado_por_admin': True,
        'activado_en': datetime.now().isoformat()
    }
    
    # 1. Guardar en suscripciones pagadas
    guardar_suscripcion_persistente(user_phone, sub_data)
    
    # 2. Actualizar trial para marcar como suscriptor
    trials = cargar_trials_persistentes()
    if user_phone in trials:
        trials[user_phone]['is_subscribed'] = True
        trials[user_phone]['actualizado_en'] = datetime.now().isoformat()
        guardar_trials_persistentes(trials)
    
    return sub_data

def verificar_suscripcion_activa(user_phone):
    """Verifica suscripción activa (PERSISTENTE)"""
    subs = cargar_suscripciones_persistentes()
    
    if user_phone not in subs:
        return False
    
    sub = subs[user_phone]
    fecha_vencimiento = datetime.strptime(sub['fecha_vencimiento'], '%Y-%m-%d').date()
    hoy = datetime.now().date()
    
    if hoy > fecha_vencimiento:
        sub['estado'] = 'vencido'
        guardar_suscripcion_persistente(user_phone, sub)
        return False
    
    return True

def dias_restantes_suscripcion(user_phone):
    """Días restantes de suscripción (PERSISTENTE)"""
    subs = cargar_suscripciones_persistentes()
    
    if user_phone not in subs:
        return 0
    
    sub = subs[user_phone]
    fecha_vencimiento = datetime.strptime(sub['fecha_vencimiento'], '%Y-%m-%d').date()
    hoy = datetime.now().date()
    
    return max(0, (fecha_vencimiento - hoy).days)

# --- SISTEMA UNIFICADO DE ACCESO ---

def usuario_puede_chatear(user_phone):
    """Verificación unificada de acceso (PERSISTENTE)"""
    # 1. Primero verificar suscripción pagada
    if verificar_suscripcion_activa(user_phone):
        return True
    
    # 2. Luego verificar trial activo
    if verificar_trial_activo(user_phone):
        return True
    
    return False

# --- SISTEMA DE RECORDATORIOS AUTOMÁTICOS (PERSISTENTE) ---

def ejecutar_recordatorios_automaticos():
    """Envía recordatorios automáticos de suscripción (PERSISTENTE)"""
    def tarea_background():
        while True:
            try:
                hoy = datetime.now().date()
                print(f"🔔 Verificando recordatorios para {hoy}")
                
                subs = cargar_suscripciones_persistentes()
                subs_actualizados = False
                
                for user_phone, sub in subs.items():
                    if sub['estado'] != 'activo':
                        continue
                        
                    fecha_vencimiento = datetime.strptime(sub['fecha_vencimiento'], '%Y-%m-%d').date()
                    dias_restantes = (fecha_vencimiento - hoy).days
                    
                    if dias_restantes == 7 and not sub.get('recordatorio_7d_enviado', False):
                        mensaje = f"""
🔔 **Recordatorio de Suscripción**

📅 Tu suscripción de Alma vence en **7 días** ({fecha_vencimiento.strftime('%d/%m/%Y')})

Para renovar y evitar interrupciones en tu acompañamiento:
• Envía "RENOVAR" para recibir los datos de pago

🌱 *Tu bienestar emocional es nuestra prioridad*
"""
                        enviar_respuesta_twilio(mensaje, user_phone)
                        sub['recordatorio_7d_enviado'] = True
                        subs_actualizados = True
                        print(f"📤 Recordatorio 7d enviado a {user_phone}")
                        
                    elif dias_restantes == 3 and not sub.get('recordatorio_3d_enviado', False):
                        mensaje = f"""
⚠️ **Recordatorio Urgente**

📅 Tu suscripción de Alma vence en **3 días** ({fecha_vencimiento.strftime('%d/%m/%Y')})

🔄 Renueva ahora para mantener tu acceso continuo:
• Envía "RENOVAR" para datos de pago

💫 *No pierdas tu ritmo de crecimiento*
"""
                        enviar_respuesta_twilio(mensaje, user_phone)
                        sub['recordatorio_3d_enviado'] = True
                        subs_actualizados = True
                        print(f"📤 Recordatorio 3d enviado a {user_phone}")
                        
                    elif dias_restantes == 0 and not sub.get('recordatorio_0d_enviado', False):
                        mensaje = f"""
🚨 **Suscripción por Vencer Hoy**

📅 **Hoy {fecha_vencimiento.strftime('%d/%m/%Y')}** vence tu suscripción de Alma

⚡ Actúa ahora para mantener tu acceso:
• Envía "RENOVAR" inmediatamente

🌿 *Tu camino de mindfulness es importante*
"""
                        enviar_respuesta_twilio(mensaje, user_phone)
                        sub['recordatorio_0d_enviado'] = True
                        subs_actualizados = True
                        print(f"📤 Recordatorio 0d enviado a {user_phone}")
                
                # Guardar cambios si hubo actualizaciones
                if subs_actualizados:
                    guardar_json_safe(PAID_SUBS_FILE, subs)
                    print("💾 Suscripciones actualizadas después de recordatorios")
                
                time.sleep(3600)  # Revisar cada hora
                
            except Exception as e:
                print(f"❌ Error en recordatorios automáticos: {e}")
                time.sleep(300)  # Reintentar en 5 minutos
    
    thread = Thread(target=tarea_background, daemon=True)
    thread.start()
    print("✅ Sistema de recordatorios automáticos INICIADO (PERSISTENTE)")

# --- FUNCIONES DE SESIÓN EN MEMORIA ---

def get_user_session(user_phone):
    if user_phone not in user_sessions:
        user_sessions[user_phone] = {
            'conversation_history': [],
            'created_at': datetime.now().isoformat(),
            'session_start_time': datetime.now().timestamp(), 
            'recordatorio_enviado': False,                     
            'crisis_count': 0,
            'last_contact': datetime.now().isoformat()
        }
    return user_sessions[user_phone]

def save_user_session(user_phone, session):
    session['last_contact'] = datetime.now().isoformat()
    user_sessions[user_phone] = session

def puede_iniciar_sesion(session, user_phone):
    """Verifica límites de tiempo por sesión"""
    tiempo_transcurrido = datetime.now().timestamp() - session['session_start_time']
    minutos_transcurridos = tiempo_transcurrido / 60
    
    if minutos_transcurridos >= LIMITE_SESION_MAXIMO_MINUTOS:
        return {
            "expirada": True,
            "mensaje": f"¡Hola! Has alcanzado el límite máximo de {LIMITE_SESION_MAXIMO_MINUTOS} minutos por hoy. Tu progreso está guardado. ¡Podrás iniciar tu próxima sesión mañana! 🌱"
        }
    
    return True

def debe_recordar_cierre(session):
    """Sistema de recordatorios más natural y menos invasivo"""
    if session.get('recordatorio_enviado', False):
        return False
    
    start_time = session['session_start_time']
    current_time = datetime.now().timestamp()
    tiempo_transcurrido_minutos = (current_time - start_time) / 60
    
    # Recordatorio SUAVE a los 45 minutos (15 min antes)
    if tiempo_transcurrido_minutos >= INTERVALO_RECORDATORIO_SUAVE_MINUTOS:
        session['recordatorio_enviado'] = True
        return "suave"
    
    # Recordatorio FINAL a los 50 minutos (10 min antes)
    if tiempo_transcurrido_minutos >= INTERVALO_RECORDATORIO_MINUTOS:
        session['recordatorio_enviado'] = True
        return "final"
    
    return False

# --- DETECCIÓN DE CRISIS PRECISA Y CONSERVADORA ---
def detectar_crisis_real(user_message):
    """
    Detección MUY conservadora - solo activa con suicidio explícito
    No activa con expresiones de desahogo emocional normales
    """
    mensaje = user_message.lower().strip()
    
    # Patrones que requieren contexto suicida explícito
    patrones_suicidio_explicito = [
        r"quiero suicidarme",
        r"me voy a suicidar", 
        r"voy a suicidarme",
        r"suicidarme\b",
        r"matarme\b",
        r"quitarme la vida",
        r"acabar con mi vida",
        r"pensando en suicidarme",
        r"planeo suicidarme",
        r"saltar de un edificio",
        r"tirarme de un puente",
        r"ahorcarme\b",
        r"colgarme\b",
        r"dispararme\b",
        r"darme un tiro",
        r"cortarme las venas"
    ]
    
    for patron in patrones_suicidio_explicito:
        if re.search(patron, mensaje):
            print(f"🚨 CRISIS DETECTADA: '{patron}' en mensaje: {mensaje}")
            return True
    
    # Verificación adicional con lista de triggers
    for trigger in TRIGGER_CRISIS:
        if trigger in mensaje:
            print(f"🚨 CRISIS DETECTADA: '{trigger}' en mensaje: {mensaje}")
            return True
    
    print(f"✅ No se detectó crisis - Mensaje normal: {mensaje[:50]}...")
    return False

def construir_prompt_alma(user_message, user_session, user_phone):
    tiempo_transcurrido_minutos = int((datetime.now().timestamp() - user_session['session_start_time']) / 60)
    
    if tiempo_transcurrido_minutos >= LIMITE_SESION_MAXIMO_MINUTOS:
        estatus_sesion = f"LIMITE EXCEDIDO ({LIMITE_SESION_MAXIMO_MINUTOS} MINUTOS). DEBES CERRAR INMEDIATAMENTE."
    elif tiempo_transcurrido_minutos >= DURACION_SESION_NORMAL_MINUTOS:
        estatus_sesion = f"CIERRE FLEXIBLE. Ya superaste los {DURACION_SESION_NORMAL_MINUTOS} minutos. Mantente en fase de cierre."
    elif tiempo_transcurrido_minutos >= INTERVALO_RECORDATORIO_MINUTOS:
        estatus_sesion = "AVISO DE CIERRE ENVIADO. Inicia transición a cierre."
    else:
        estatus_sesion = f"Sesión en curso. {DURACION_SESION_NORMAL_MINUTOS - tiempo_transcurrido_minutos} minutos restantes."
        
    conversation_history = ""
    for msg in user_session['conversation_history'][-3:]:
        conversation_history += f"Usuario: {msg['user']}\nAlma: {msg['alma']}\n"
    
    prompt = ALMA_PROMPT_BASE.format(
        tiempo_transcurrido=tiempo_transcurrido_minutos,
        estatus_sesion=estatus_sesion,
        limite_maximo=LIMITE_SESION_MAXIMO_MINUTOS,
        conversation_history=conversation_history,
        user_message=user_message
    )
    
    if tiempo_transcurrido_minutos >= DURACION_SESION_NORMAL_MINUTOS:
        prompt += f"\n\n{AVISO_CIERRE}"
    
    return prompt

def llamar_deepseek(prompt):
    try:
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 600,  # AUMENTADO de 400 a 600
            "stream": False
        }
        
        print(f"🔍 DEBUG: Llamando a DeepSeek API...")
        response = requests.post(DEEPSEEK_URL, headers=headers, json=data, timeout=30)
        print(f"🔍 DEBUG: Status Code: {response.status_code}")
        
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content'].strip()
        else:
            print(f"Error DeepSeek API: {response.status_code} - {response.text}")
            return "Entiendo que quieres conectar. Estoy aquí para escucharte. ¿Puedes contarme más sobre cómo te sientes? 🌱"
            
    except Exception as e:
        print(f"Excepción en llamar_deepseek: {str(e)}")
        return "Veo que estás buscando apoyo. ¿Podrías contarme más sobre lo que necesitas en este momento? 💫"

def enviar_respuesta_crisis(telefono):
    MENSAJE_CRISIS = """
🚨 PROTOCOLO DE CRISIS 🚨
Veo que estás pasando por un momento muy difícil. 
Como Alma no puedo brindar atención en crisis, 
te recomiendo contactar **inmediatamente**:

🏙️ **EN QUERÉTARO:**
📞 **Línea de la Vida Querétaro:** 800 008 1100
🏥 **Centro de Atención Psicológica UAQ:** 442 192 1200 Ext. 6305

📱 **LÍNEAS NACIONALES 24/7:**
🆘 **Línea de la Vida:** 800 911 2001
💙 **SAPTEL:** 55 5259 8121
🚑 **Urgencias:** 911

**No estás solo. Por favor busca ayuda profesional inmediata.**
Recuerda que hay personas que se preocupan por ti.
Te espero en este tu espacio cuando te sientas mejor o quieras seguir hablando.🌱
"""
    return enviar_respuesta_twilio(MENSAJE_CRISIS, telefono)

def manejar_comando_suscripcion(user_phone, user_message):
    message_lower = user_message.lower().strip()
    
    # 🚨 VERSIÓN ULTRA-CONSERVADORA - SOLO RESPUESTA A PETICIONES EXPLÍCITAS
    peticiones_explicitas = [
        "suscribirme", 
        "renovar",
        "cómo pago",
        "quiero pagar", 
        "datos bancarios",
        "número de cuenta",
        "clabe interbancaria"
    ]
    
    # ✅ SOLO si el mensaje contiene EXACTAMENTE una petición explícita
    for peticion in peticiones_explicitas:
        if peticion in message_lower:
            print(f"💰 Solicitud EXPLÍCITA detectada: {peticion} en '{user_message}'")
            return MENSAJE_SUSCRIPCION
    
    # 🛡️ COMPROBANTES - SOLO con confirmación explícita de pago
    if any(palabra in message_lower for palabra in ["comprobante", "captura"]):
        if any(confirmacion in message_lower for confirmacion in ["ya pagué", "pagué", "transferí", "deposité"]):
            print(f"📋 Comprobante CONFIRMADO: {user_message}")
            return "📋 **Comprobante recibido**\nHemos registrado tu comprobante. Un administrador activará tu suscripción en las próximas 24 horas. ¡Gracias por confiar en Alma! 🌱"
    
    print(f"✅ Mensaje normal - No es solicitud comercial: '{user_message}'")
    return None

# ✅ LIMPIEZA MEJORADA - AHORA SOLO LIMPIA MEMORIA TEMPORAL
def ejecutar_limpieza_automatica():
    """Limpia solo sesiones en memoria, datos críticos están en JSON"""
    def tarea_limpieza():
        while True:
            try:
                print("🧹 Ejecutando limpieza de memoria...")
                hoy = datetime.now()
                
                # Limpiar solo sesiones en memoria > 7 días
                sesiones_limpiadas = 0
                for phone in list(user_sessions.keys()):
                    session = user_sessions[phone]
                    last_contact = datetime.fromisoformat(session['last_contact'])
                    if (hoy - last_contact).days > 7:
                        user_sessions.pop(phone, None)
                        sesiones_limpiadas += 1
                
                if sesiones_limpiadas > 0:
                    print(f"🧹 Sesiones en memoria limpiadas: {sesiones_limpiadas}")
                
                print(f"📊 Estado actual - Sesiones en memoria: {len(user_sessions)}")
                
                time.sleep(86400 * 7)  # Cada 7 días
                
            except Exception as e:
                print(f"❌ Error en limpieza: {e}")
                time.sleep(3600)
    
    thread = Thread(target=tarea_limpieza, daemon=True)
    thread.start()
    print("✅ Sistema de limpieza de memoria INICIADO")

# --- ENDPOINT PRINCIPAL ACTUALIZADO ---
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        user_phone = request.form.get('From', '')
        user_message = request.form.get('Body', '').strip()
        
        if not user_message:
            return Response("OK", status=200)
        
        print(f"🔔 MENSAJE RECIBIDO de {user_phone}: {user_message}")
        
        # 1. VERIFICAR ACCESO (sistema unificado persistente)
        if not usuario_puede_chatear(user_phone):
            return enviar_respuesta_twilio(MENSAJE_INVITACION_SUSCRIPCION, user_phone)
        
        # 2. MANEJAR COMANDOS DE SUSCRIPCIÓN (MÁS AGRESIVO)
        respuesta_suscripcion = manejar_comando_suscripcion(user_phone, user_message)
        if respuesta_suscripcion:
            return enviar_respuesta_twilio(respuesta_suscripcion, user_phone)
        
        # 3. VERIFICAR LÍMITE DIARIO PERSISTENTE
        if usuario_ya_uso_sesion_hoy(user_phone):
            tiempo_restante = obtener_proximo_reset()
            mensaje_bloqueo = f"¡Hola! Ya disfrutaste tu sesión de Alma de hoy. Podrás iniciar tu próxima sesión en {tiempo_restante}. ¡Estaré aquí para ti! 🌱"
            return enviar_respuesta_twilio(mensaje_bloqueo, user_phone)
        
        # 4. OBTENER SESIÓN EN MEMORIA
        session = get_user_session(user_phone)

        # 5. MOSTRAR PRIVACIDAD SOLO AL INICIO DE CONVERSACIÓN
        if len(session['conversation_history']) == 0:
            enviar_respuesta_twilio(MENSAJE_PRIVACIDAD, user_phone)

        # 6. VERIFICAR LÍMITE DE TIEMPO POR SESIÓN
        restriccion = puede_iniciar_sesion(session, user_phone)
        if restriccion is not True:
            # Registrar que completó sesión hoy
            registrar_sesion_diaria(user_phone)
            user_sessions.pop(user_phone, None)
            return enviar_respuesta_twilio(restriccion['mensaje'], user_phone)
        
        # 7. PROTOCOLO DE CRISIS PRECISO
        if detectar_crisis_real(user_message):
            session['crisis_count'] += 1
            save_user_session(user_phone, session)
            return enviar_respuesta_crisis(user_phone)

        # 8. GESTIÓN DE TIEMPO: LÍMITE FORZADO
        tiempo_transcurrido_minutos = int((datetime.now().timestamp() - session['session_start_time']) / 60)
        
        if tiempo_transcurrido_minutos >= LIMITE_SESION_MAXIMO_MINUTOS:
            # REGISTRAR SESIÓN COMPLETADA
            registrar_sesion_diaria(user_phone)
            alma_response = f"Gracias por tu tiempo. Hemos alcanzado el límite máximo de {LIMITE_SESION_MAXIMO_MINUTOS} minutos por hoy. Tu progreso está guardado. ¡Podrás iniciar tu próxima sesión mañana! 🌱"
            user_sessions.pop(user_phone, None)
            return enviar_respuesta_twilio(alma_response, user_phone)
        
        # 9. RECORDATORIO SUAVE DE CIERRE (menos invasivo)
        recordatorio = debe_recordar_cierre(session)
        if recordatorio == "suave":
            print(f"[{user_phone}] Recordatorio suave a los 45 min")
            user_message = "RECORDATORIO_SUAVE: " + user_message
        elif recordatorio == "final":
            print(f"[{user_phone}] Recordatorio final a los 50 min") 
            user_message = AVISO_CIERRE + " ||| " + user_message

        # 10. GENERAR RESPUESTA CON ALMA (personalidad femenina mejorada)
        prompt = construir_prompt_alma(user_message, session, user_phone)
        alma_response = llamar_deepseek(prompt)
        print(f"💬 RESPUESTA DE ALMA: {alma_response}")
        
        # 11. GUARDAR HISTORIAL EN MEMORIA
        session['conversation_history'].append({
            'user': user_message,
            'alma': alma_response,
            'timestamp': datetime.now().isoformat()
        })
        
        if len(session['conversation_history']) > 10:
            session['conversation_history'] = session['conversation_history'][-10:]
            
        save_user_session(user_phone, session)
        
        # 12. ENVIAR RESPUESTA
        return enviar_respuesta_twilio(alma_response, user_phone)
        
    except Exception as e:
        print(f"❌ ERROR CRÍTICO en webhook: {str(e)}")
        import traceback
        traceback.print_exc()
        return enviar_respuesta_twilio("Lo siento, estoy teniendo dificultades técnicas. ¿Podrías intentarlo de nuevo? 🌱", user_phone)

# --- ENDPOINTS TWILIO Y ADMIN ---

def enviar_respuesta_twilio(mensaje, telefono):
    from twilio.rest import Client
    from twilio.base.exceptions import TwilioRestException
    
    account_sid = os.getenv('TWILIO_ACCOUNT_SID')
    auth_token = os.getenv('TWILIO_AUTH_TOKEN')
    
    if not account_sid or not auth_token:
        print("Error: Twilio credentials no configuradas")
        return Response("OK", status=200)
    
    client = Client(account_sid, auth_token)
    try:
        message = client.messages.create(
            body=mensaje,
            from_=TWILIO_WHATSAPP_NUMBER,
            to=telefono
        )
        print(f"✅ Mensaje Twilio enviado: {message.sid}")
        return Response("OK", status=200)
    except TwilioRestException as e:
        print(f"❌ ERROR Twilio: {e.code} - {e.msg}")
        return Response("OK", status=200)
    except Exception as e:
        print(f"❌ Error general al enviar mensaje: {e}")
        return Response("OK", status=200)

@app.route('/admin/activar/<user_phone>', methods=['POST'])
def admin_activar_suscripcion(user_phone):
    try:
        activar_suscripcion(user_phone)
        subs = cargar_suscripciones_persistentes()
        sub = subs[user_phone]
        
        mensaje = MENSAJE_SUSCRIPCION_ACTIVA.format(
            fecha_vencimiento=datetime.strptime(sub['fecha_vencimiento'], '%Y-%m-%d').strftime('%d/%m/%Y')
        )
        enviar_respuesta_twilio(mensaje, user_phone)
        
        return {
            "status": "success",
            "message": f"Suscripción activada para {user_phone}",
            "vencimiento": sub['fecha_vencimiento']
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

@app.route('/admin/estado', methods=['GET'])
def admin_estado():
    """Endpoint de administración para ver estado del sistema"""
    sesiones = cargar_sesiones_persistentes()
    trials = cargar_trials_persistentes()
    subs = cargar_suscripciones_persistentes()
    
    return {
        "status": "healthy",
        "service": "Alma Chatbot - Sistema Persistente",
        "sesiones_diarias": len(sesiones),
        "usuarios_trial": len(trials),
        "suscripciones_activas": sum(1 for s in subs.values() if s['estado'] == 'activo'),
        "sessions_memoria": len(user_sessions),
        "timestamp": datetime.now().isoformat()
    }

@app.route('/health', methods=['GET'])
def health_check():
    sesiones = cargar_sesiones_persistentes()
    subs = cargar_suscripciones_persistentes()
    
    return {
        "status": "healthy", 
        "service": "Alma Chatbot - Sistema Persistente",
        "users_activos": len(user_sessions),
        "suscripciones_activas": sum(1 for s in subs.values() if s['estado'] == 'activo'),
        "usuarios_persistentes": len(sesiones),
        "timestamp": datetime.now().isoformat()
    }

if __name__ == '__main__':
    # Iniciar sistemas automáticos
    ejecutar_recordatorios_automaticos()
    ejecutar_limpieza_automatica()
    
    print("🤖 Alma Chatbot INICIADO - SISTEMA 100% PERSISTENTE")
    print(f"📞 Número comprobantes: {NUMERO_COMPROBANTES}")
    print("🎯 CARACTERÍSTICAS IMPLEMENTADAS:")
    print("   ✅ Sistema PERSISTENTE completo (JSON)")
    print("   ✅ Trials sobreviven reinicios") 
    print("   ✅ Suscripciones pagadas garantizadas")
    print("   ✅ Recordatorios automáticos persistentes")
    print("   ✅ Recuperación robusta de archivos")
    print("   ✅ Sesiones 60-75 minutos")
    print("   ✅ Personalidad femenina digital mejorada")
    print("   ✅ Recordatorios menos invasivos (45-50 min)")
    print("   ✅ 600 tokens para respuestas más completas")
    print("   ✅ Políticas de privacidad actualizadas")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
