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

# Almacenamiento en memoria
user_sessions = {}
user_subscriptions = {}
paid_subscriptions = {}
user_profiles = {}

# --- CONSTANTES COMERCIALES ---
DIAS_TRIAL_GRATIS = 21
PRECIO_SUSCRIPCION_MENSUAL = 200
PRECIO_SUSCRIPCION_DIARIO = 6.67
DIAS_SUSCRIPCION = 30

# --- CONSTANTES DE SESIÓN DIARIA FLEXIBLE ---
DURACION_SESION_NORMAL_MINUTOS = 30
INTERVALO_RECORDATORIO_MINUTOS = 25 
LIMITE_SESION_MAXIMO_MINUTOS = 45

# INSTRUCCIÓN CLARA para DeepSeek
AVISO_CIERRE = """
INSTRUCCIÓN CRÍTICA DE CIERRE: Alma, la sesión de 30 minutos ha terminado. 
DEBES comenzar inmediatamente la fase de cierre con una sugerencia práctica de mindfulness.
Finaliza la sesión con el mensaje de cierre y guarda el contexto. NO uses más de 15 minutos adicionales.
"""

# --- PROTOCOLO DE CRISIS PRECISO Y CONSERVADOR ---
TRIGGER_CRISIS = [
    # EXPLÍCITOS E INEQUÍVOCOS
    "quiero suicidarme",
    "me voy a suicidar", 
    "voy a suicidarme",
    "pensando en suicidarme",
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
    
    # DESPEDIDAS SUICIDAS
    "esta es la despedida",
    "adiós para siempre",
    "nunca más me verán",
    
    # MÉTODOS ESPECÍFICOS
    "tomarme todas las pastillas",
    "saltar de un edificio",
    "ahorcarme",
    "dispararme"
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

# ✅ MENSAJE DE PRIVACIDAD PARA SESIÓN 1
MENSAJE_PRIVACIDAD = """
🔒 **Política de privacidad de Alma**

🌱 **Cada sesión es nueva** - La conversación diaria no guarda datos sensibles.
"""

# --- PROMPT SIMPLIFICADO Y NATURAL ---
ALMA_PROMPT_BASE = """
Eres "Alma" - chatbot especializado en mindfulness y apoyo emocional. NO eres terapeuta.

**TU ENFOQUE:**
- Escucha activa y respuesta natural
- Adapta tu estilo al tono del usuario
- Integra mindfulness de forma orgánica
- Sé empático, compasivo y genuino
- Sugiere prácticas cuando sea apropiado

**SESIÓN ACTUAL:**
- Tiempo transcurrido: {tiempo_transcurrido} minutos
- Estado: {estatus_sesion}

**CONVERSACIÓN RECIENTE:**
{conversation_history}

**MENSAJE ACTUAL DEL USUARIO:**
{user_message}

**INSTRUCCIÓN FINAL:** Responde como Alma de forma natural y adaptativa, sin restricciones artificiales.
"""

# ✅ SISTEMA DE PERFILES SIMPLIFICADO
def get_user_profile(user_phone):
    """Obtiene el perfil básico del usuario"""
    if user_phone not in user_profiles:
        user_profiles[user_phone] = {
            'sesiones_completadas': 0,
            'ultimo_tema': '',
            'primer_uso': True,
            'creado_en': datetime.now().isoformat()
        }
    return user_profiles[user_phone]

def save_user_profile(user_phone, profile_data):
    """Guarda el perfil del usuario"""
    user_profiles[user_phone] = {
        **get_user_profile(user_phone),
        **profile_data,
        'actualizado_en': datetime.now().isoformat()
    }

def extraer_tema_general(conversation_history):
    """Extrae el tema general de la conversación"""
    if not conversation_history:
        return "bienestar general"
    
    primer_mensaje = conversation_history[0]['user'].lower()
    temas = ["trabajo", "familia", "relaciones", "propósito", "estrés", "ansiedad", "autoestima", "crecimiento"]
    
    for tema in temas:
        if tema in primer_mensaje:
            return tema
    return "bienestar emocional"

# --- SISTEMA DE SUSCRIPCIONES PAGADAS (MANTENIDO) ---
def inicializar_suscripcion_paga(user_phone):
    fecha_activacion = datetime.now().date()
    fecha_vencimiento = fecha_activacion + timedelta(days=DIAS_SUSCRIPCION)
    
    paid_subscriptions[user_phone] = {
        'fecha_activacion': fecha_activacion.isoformat(),
        'fecha_vencimiento': fecha_vencimiento.isoformat(),
        'estado': 'activo',
        'recordatorio_7d_enviado': False,
        'recordatorio_3d_enviado': False,
        'recordatorio_0d_enviado': False,
        'activado_por_admin': False
    }
    return paid_subscriptions[user_phone]

def activar_suscripcion(user_phone):
    if user_phone in paid_subscriptions:
        fecha_activacion = datetime.now().date()
        fecha_vencimiento = fecha_activacion + timedelta(days=DIAS_SUSCRIPCION)
    else:
        fecha_activacion = datetime.now().date()
        fecha_vencimiento = fecha_activacion + timedelta(days=DIAS_SUSCRIPCION)
        
    paid_subscriptions[user_phone] = {
        'fecha_activacion': fecha_activacion.isoformat(),
        'fecha_vencimiento': fecha_vencimiento.isoformat(),
        'estado': 'activo',
        'recordatorio_7d_enviado': False,
        'recordatorio_3d_enviado': False,
        'recordatorio_0d_enviado': False,
        'activado_por_admin': True
    }
    return paid_subscriptions[user_phone]

def verificar_suscripcion_activa(user_phone):
    if user_phone not in paid_subscriptions:
        return False
    
    sub = paid_subscriptions[user_phone]
    fecha_vencimiento = datetime.strptime(sub['fecha_vencimiento'], '%Y-%m-%d').date()
    hoy = datetime.now().date()
    
    if hoy > fecha_vencimiento:
        sub['estado'] = 'vencido'
        return False
    
    return True

def dias_restantes_suscripcion(user_phone):
    if user_phone not in paid_subscriptions:
        return 0
    
    sub = paid_subscriptions[user_phone]
    fecha_vencimiento = datetime.strptime(sub['fecha_vencimiento'], '%Y-%m-%d').date()
    hoy = datetime.now().date()
    
    return max(0, (fecha_vencimiento - hoy).days)

# --- SISTEMA DE RECORDATORIOS AUTOMÁTICOS (MANTENIDO) ---
def ejecutar_recordatorios_automaticos():
    """Envía recordatorios automáticos de suscripción."""
    def tarea_background():
        while True:
            try:
                hoy = datetime.now().date()
                print(f"🔔 Verificando recordatorios para {hoy}")
                
                for user_phone, sub in paid_subscriptions.items():
                    if sub['estado'] != 'activo':
                        continue
                        
                    fecha_vencimiento = datetime.strptime(sub['fecha_vencimiento'], '%Y-%m-%d').date()
                    dias_restantes = (fecha_vencimiento - hoy).days
                    
                    if dias_restantes == 7 and not sub['recordatorio_7d_enviado']:
                        mensaje = f"""
🔔 **Recordatorio de Suscripción**

📅 Tu suscripción de Alma vence en **7 días** ({fecha_vencimiento.strftime('%d/%m/%Y')})

Para renovar y evitar interrupciones en tu acompañamiento:
• Envía "RENOVAR" para recibir los datos de pago

🌱 *Tu bienestar emocional es nuestra prioridad*
"""
                        enviar_respuesta_twilio(mensaje, user_phone)
                        sub['recordatorio_7d_enviado'] = True
                        print(f"📤 Recordatorio 7d enviado a {user_phone}")
                        
                    elif dias_restantes == 3 and not sub['recordatorio_3d_enviado']:
                        mensaje = f"""
⚠️ **Recordatorio Urgente**

📅 Tu suscripción de Alma vence en **3 días** ({fecha_vencimiento.strftime('%d/%m/%Y')})

🔄 Renueva ahora para mantener tu acceso continuo:
• Envía "RENOVAR" para datos de pago

💫 *No pierdas tu ritmo de crecimiento*
"""
                        enviar_respuesta_twilio(mensaje, user_phone)
                        sub['recordatorio_3d_enviado'] = True
                        print(f"📤 Recordatorio 3d enviado a {user_phone}")
                        
                    elif dias_restantes == 0 and not sub['recordatorio_0d_enviado']:
                        mensaje = f"""
🚨 **Suscripción por Vencer Hoy**

📅 **Hoy {fecha_vencimiento.strftime('%d/%m/%Y')}** vence tu suscripción de Alma

⚡ Actúa ahora para mantener tu acceso:
• Envía "RENOVAR" inmediatamente

🌿 *Tu camino de mindfulness es importante*
"""
                        enviar_respuesta_twilio(mensaje, user_phone)
                        sub['recordatorio_0d_enviado'] = True
                        print(f"📤 Recordatorio 0d enviado a {user_phone}")
                
                time.sleep(3600)
            except Exception as e:
                print(f"❌ Error en recordatorios automáticos: {e}")
                time.sleep(300)
    
    thread = Thread(target=tarea_background, daemon=True)
    thread.start()
    print("✅ Sistema de recordatorios automáticos INICIADO")

# --- SISTEMA DE TRIAL Y ACCESO (MANTENIDO) ---
def get_user_subscription(user_phone):
    if user_phone not in user_subscriptions:
        user_subscriptions[user_phone] = {
            'trial_start_date': datetime.now().strftime('%Y-%m-%d'),
            'trial_end_date': (datetime.now() + timedelta(days=DIAS_TRIAL_GRATIS)).strftime('%Y-%m-%d'),
            'is_subscribed': False
        }
    return user_subscriptions[user_phone]

def verificar_trial_activo(subscription):
    trial_end = datetime.strptime(subscription['trial_end_date'], '%Y-%m-%d').date()
    hoy = datetime.now().date()
    return hoy <= trial_end

def dias_restantes_trial(subscription):
    trial_end = datetime.strptime(subscription['trial_end_date'], '%Y-%m-%d').date()
    hoy = datetime.now().date()
    return max(0, (trial_end - hoy).days)

def usuario_puede_chatear(user_phone):
    if verificar_suscripcion_activa(user_phone):
        return True
    
    subscription = get_user_subscription(user_phone)
    return verificar_trial_activo(subscription)

# --- FUNCIONES SIMPLIFICADAS DE ALMA ---
def get_user_session(user_phone):
    if user_phone not in user_sessions:
        user_sessions[user_phone] = {
            'conversation_history': [],
            'created_at': datetime.now().isoformat(),
            'session_start_time': datetime.now().timestamp(), 
            'recordatorio_enviado': False,                     
            'crisis_count': 0,
            'last_contact': datetime.now().isoformat(),
            'last_session_date': None
        }
    return user_sessions[user_phone]

def save_user_session(user_phone, session):
    session['last_contact'] = datetime.now().isoformat()
    user_sessions[user_phone] = session

def puede_iniciar_sesion(session):
    last_date_str = session.get('last_session_date')
    
    if not last_date_str:
        return True
    
    today = date.today()
    
    try:
        last_date = datetime.strptime(last_date_str, '%Y-%m-%d').date()
    except ValueError:
        return True
        
    if last_date < today:
        return True
    else:
        tomorrow = today + timedelta(days=1)
        medianoche = datetime(tomorrow.year, tomorrow.month, tomorrow.day)
        
        tiempo_restante = medianoche - datetime.now()
        horas = int(tiempo_restante.total_seconds() // 3600)
        minutos = int((tiempo_restante.total_seconds() % 3600) // 60)
        return {"horas": horas, "minutos": minutos}

def debe_recordar_cierre(session):
    if session.get('recordatorio_enviado', False):
        return False
    
    start_time = session['session_start_time']
    current_time = datetime.now().timestamp()
    tiempo_transcurrido_segundos = current_time - start_time
    intervalo_recordatorio_segundos = INTERVALO_RECORDATORIO_MINUTOS * 60
    
    if tiempo_transcurrido_segundos >= intervalo_recordatorio_segundos:
        session['recordatorio_enviado'] = True
        return True
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
        r"planeo suicidarme"
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
    user_profile = get_user_profile(user_phone)
    
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
            "max_tokens": 400,
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
🆘 **Línea de la Vida:** 800 911 2000
💙 **SAPTEL:** 55 5259 8121
🚑 **Urgencias:** 911

**No estás solo. Por favor busca ayuda profesional inmediata.**
Estaré aquí cuando te sientas más estable 🌱
"""
    return enviar_respuesta_twilio(MENSAJE_CRISIS, telefono)

def manejar_comando_suscripcion(user_phone, user_message):
    message_lower = user_message.lower()
    
    if "suscribir" in message_lower or "renovar" in message_lower:
        return MENSAJE_SUSCRIPCION
        
    return None

# ✅ LIMPIEZA CADA 30 DÍAS DE INACTIVIDAD
def ejecutar_limpieza_automatica():
    """Limpia datos de usuarios inactivos por 30 días"""
    def tarea_limpieza():
        while True:
            try:
                print("🧹 Ejecutando limpieza de usuarios inactivos...")
                hoy = datetime.now()
                
                # Limpiar sesiones de usuarios inactivos > 30 días
                for phone in list(user_sessions.keys()):
                    session = user_sessions[phone]
                    last_contact = datetime.fromisoformat(session['last_contact'])
                    if (hoy - last_contact).days > 30:
                        user_sessions.pop(phone, None)
                        print(f"🧹 Sesión limpiada: {phone}")
                
                # Limpiar perfiles de usuarios inactivos > 30 días sin suscripción
                for phone in list(user_profiles.keys()):
                    profile = user_profiles[phone]
                    ultima_actividad = profile.get('actualizado_en', profile['creado_en'])
                    last_activity = datetime.fromisoformat(ultima_actividad)
                    
                    if (hoy - last_activity).days > 30 and not usuario_puede_chatear(phone):
                        user_profiles.pop(phone, None)
                        print(f"🧹 Perfil limpiado: {phone}")
                
                time.sleep(86400 * 15)  # Ejecutar cada 15 días
                
            except Exception as e:
                print(f"❌ Error en limpieza: {e}")
                time.sleep(3600)
    
    thread = Thread(target=tarea_limpieza, daemon=True)
    thread.start()
    print("✅ Sistema de limpieza automática INICIADO")

# --- ENDPOINT PRINCIPAL SIMPLIFICADO ---
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        user_phone = request.form.get('From', '')
        user_message = request.form.get('Body', '').strip()
        
        if not user_message:
            return Response("OK", status=200)
        
        print(f"🔔 MENSAJE RECIBIDO de {user_phone}: {user_message}")
        
        # ✅ OBTENER PERFIL ACTUAL
        user_profile = get_user_profile(user_phone)
        
        # ✅ VERIFICAR SI ES PRIMER USO (mostrar política solo una vez)
        if user_profile['primer_uso']:
            save_user_profile(user_phone, {
                'primer_uso': False
            })
            return enviar_respuesta_twilio(MENSAJE_PRIVACIDAD, user_phone)
        
        # 1. VERIFICAR ACCESO
        if not usuario_puede_chatear(user_phone):
            return enviar_respuesta_twilio(MENSAJE_INVITACION_SUSCRIPCION, user_phone)
        
        # 2. MANEJAR COMANDOS DE SUSCRIPCIÓN
        respuesta_suscripcion = manejar_comando_suscripcion(user_phone, user_message)
        if respuesta_suscripcion:
            return enviar_respuesta_twilio(respuesta_suscripcion, user_phone)
        
        # 3. OBTENER SESIÓN
        session = get_user_session(user_phone)

        # 4. GESTIÓN DE RESTRICCIÓN DIARIA
        restriccion = puede_iniciar_sesion(session)
        if restriccion is not True:
            horas = restriccion['horas']
            minutos = restriccion['minutos']
            alma_response = f"¡Hola! Tu sesión de Alma de hoy ya ha concluido. Podrás iniciar tu próxima sesión mañana (en {horas} horas y {minutos} minutos). ¡Estaré aquí para ti! 🌱"
            return enviar_respuesta_twilio(alma_response, user_phone)
        
        # 5. PROTOCOLO DE CRISIS PRECISO
        if detectar_crisis_real(user_message):
            session['crisis_count'] += 1
            save_user_session(user_phone, session)
            return enviar_respuesta_crisis(user_phone)

        # 6. GESTIÓN DE TIEMPO: LÍMITE FORZADO
        tiempo_transcurrido_minutos = int((datetime.now().timestamp() - session['session_start_time']) / 60)
        
        if tiempo_transcurrido_minutos >= LIMITE_SESION_MAXIMO_MINUTOS:
            tema_hoy = extraer_tema_general(session['conversation_history'])
            
            save_user_profile(user_phone, {
                'sesiones_completadas': user_profile['sesiones_completadas'] + 1,
                'ultimo_tema': tema_hoy
            })
            
            session['last_session_date'] = datetime.now().strftime('%Y-%m-%d')
            save_user_session(user_phone, session) 
            
            alma_response = f"Gracias por tu tiempo. Hemos alcanzado el límite máximo de {LIMITE_SESION_MAXIMO_MINUTOS} minutos por hoy. Tu progreso está guardado. ¡Podrás iniciar tu próxima sesión mañana! 🌱"
            
            user_sessions.pop(user_phone, None)
            return enviar_respuesta_twilio(alma_response, user_phone)
        
        # 7. RECORDATORIO DE CIERRE
        if debe_recordar_cierre(session):
            print(f"[{user_phone}] Inyectando instrucción de cierre a DeepSeek.")
            user_message = AVISO_CIERRE + " ||| Mensaje real del usuario: " + user_message

        # 8. GENERAR RESPUESTA CON ALMA
        prompt = construir_prompt_alma(user_message, session, user_phone)
        print(f"📝 PROMPT ENVIADO A DEEPSEEK:\n{prompt}")
        
        alma_response = llamar_deepseek(prompt)
        print(f"💬 RESPUESTA DE ALMA: {alma_response}")
        
        # 9. GUARDAR HISTORIAL
        session['conversation_history'].append({
            'user': user_message,
            'alma': alma_response,
            'timestamp': datetime.now().isoformat()
        })
        
        if len(session['conversation_history']) > 10:
            session['conversation_history'] = session['conversation_history'][-10:]
            
        save_user_session(user_phone, session)
        
        # 10. ENVIAR RESPUESTA
        return enviar_respuesta_twilio(alma_response, user_phone)
        
    except Exception as e:
        print(f"❌ ERROR CRÍTICO en webhook: {str(e)}")
        import traceback
        traceback.print_exc()
        return enviar_respuesta_twilio("Lo siento, estoy teniendo dificultades técnicas. ¿Podrías intentarlo de nuevo? 🌱", user_phone)

# --- ENDPOINTS TWILIO Y ADMIN (MANTENIDOS) ---
def enviar_respuesta_twilio(mensaje, telefono):
    from twilio.rest import Client
    
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
    except Exception as e:
        print(f"❌ Error al enviar mensaje Twilio: {e}")
        return Response("OK", status=200)

@app.route('/admin/activar/<user_phone>', methods=['POST'])
def admin_activar_suscripcion(user_phone):
    try:
        activar_suscripcion(user_phone)
        sub = paid_subscriptions[user_phone]
        
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

@app.route('/health', methods=['GET'])
def health_check():
    return {
        "status": "healthy", 
        "service": "Alma Chatbot",
        "users_activos": len(user_sessions),
        "perfiles_registrados": len(user_profiles),
        "suscripciones_activas": sum(1 for s in paid_subscriptions.values() if s['estado'] == 'activo'),
        "timestamp": datetime.now().isoformat()
    }

if __name__ == '__main__':
    # Iniciar sistemas automáticos
    ejecutar_recordatorios_automaticos()
    ejecutar_limpieza_automatica()
    
    print("🤖 Alma Chatbot INICIADO - Versión Natural y Adaptativa")
    print(f"📞 Número comprobantes: {NUMERO_COMPROBANTES}")
    print("🎯 CARACTERÍSTICAS IMPLEMENTADAS:")
    print("   ✅ Alma completamente natural y adaptable")
    print("   ✅ Protocolo de crisis PRECISO y conservador")
    print("   ✅ No activa con expresiones normales de desahogo")
    print("   ✅ Sistema de suscripciones mantenido")
    print("   ✅ Conversación orgánica y fluida")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
