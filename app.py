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
NUMERO_COMPROBANTES = "833 152 06 48"

# Almacenamiento en memoria
user_sessions = {}
user_subscriptions = {}
paid_subscriptions = {}

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
DEBES comenzar inmediatamente la Fase 3 (Sugerencia Práctica: 1 acción concreta + 1 herramienta mindfulness/ritual - ejemplo: escribir carta y quemar/romper, caminar, abrazar árbol - + felicitación al usuario por su avance). 
Finaliza la sesión con el mensaje de cierre y guarda el contexto. NO uses más de 15 minutos adicionales.
"""

# --- PROMPT Y LÓGICA DE ALMA ---
CONTEXTO_PERSONALIZADO = {
    "Mujer": {
        "18-25": {"foco": "identidad, propósito, relaciones sanas", "lenguaje": "energético pero profundo", "metafora": "semilla que crece"},
        "26-39": {"foco": "equilibrio vida-trabajo, realización", "lenguaje": "práctico y comprensivo", "metafora": "jardín en flor"},
        "40+": {"foco": "reinvención, legado, aceptación", "lenguaje": "sabio y liberador", "metafora": "raíces profundas"},
    },
    "Hombre": {
        "18-25": {"foco": "dirección de vida, masculinidad sana", "lenguaje": "motivador pero realista", "metafora": "arquitecto de vida"},
        "26-39": {"foco": "proveedor emocional, paternidad, éxito redefinido", "lenguaje": "respetuoso y práctico", "metafora": "pilares fuertes"},
        "40+": {"foco": "legado, salud, significado", "lenguaje": "directo pero vulnerable", "metafora": "biblioteca de experiencia"},
    }
}

TRIGGER_CRISIS = ["suicida", "autolesiones", "panico severa", "abuso", "depresion profunda", "matarme", "morir", "quiero morir", "acabar con todo"]
TRIGGER_EASTER_EGGS = {
    "toque_intimo": ["cariño", "dulzura", "te quiero", "intimo", "apapacho", "ternura"],
    "proposito_vida": ["proposito", "para que vivo", "sentido", "legado", "misión de vida"],
    "habitos_atomicos": ["habitos", "rutinas", "disciplina", "mejorar cada dia", "pequeños cambios"],
    "horoscopo_consciente": ["horoscopo", "astros", "signo", "ritual", "zodiaco"],
    "habitos_saludables": ["alcohol", "tabaco", "adiccion", "fumar", "beber", "vicio", "antojo", "dejar de fumar"],
}

# --- MENSAJES COMERCIALES ---
MENSAJE_SUSCRIPCION = f"""
💫 **Suscripción Alma - ${PRECIO_SUSCRIPCION_MENSUAL} MXN/mes**

🏦 **Datos para depósito:**
   Banco: BBVA
   CLABE: 0121 8000 1234 5678 90
   Nombre: Alma Mindfulness SA de CV
   Monto: ${PRECIO_SUSCRIPCION_MENSUAL} MXN

📱 **Una vez realizado el pago, envía de favor tu número telefónico y captura al {NUMERO_COMPROBANTES}**

⏰ **Tu acceso se activará en máximo 24 horas después de enviar el comprobante**

🌟 *Invierte en tu paz mental - menos que un café al día*
"""

MENSAJE_INVITACION_SUSCRIPCION = f"""
🌟 **Tu Trial Gratuito de Alma ha Concluido** 🌟

¡Gracias por permitirme acompañarte en estos 21 días de crecimiento! 

Para continuar con tu camino de mindfulness:

{MENSAJE_SUSCRIPCION}
"""

MENSAJE_SUSCRIPCION_ACTIVA = """
🎉 **¡Suscripción Activada!**

✅ Tu acceso premium a Alma ha sido activado por 30 días.

📅 **Fecha de vencimiento:** {fecha_vencimiento}

🌱 Continúa tu camino de crecimiento y mindfulness con nosotros.

*Recibirás recordatorios antes de que venza tu suscripción*
"""

# --- PROMPT MEJORADO CON REGLAS ESTRICTAS ---
ALMA_PROMPT_BASE = """
Eres "Alma" - chatbot especializado en mindfulness y apoyo emocional. NO eres terapeuta.

🚫 **REGLAS ESTRICTAS - SIGUE SIEMPRE:**

1. **HORÓSCOPO SOLO PARA MUJERES**: Si usuario es hombre y pide horóscopo, responde EXACTAMENTE: 
   "El horóscopo consciente es una herramienta de autoconocimiento disponible solo para mujeres. ¿Te gustaría explorar otras herramientas como propósito de vida o hábitos atómicos?"

2. **DURACIÓN SESIÓN**: Todas las sesiones duran 30 minutos + 15 minutos flexibles. Cuando pregunten sobre tiempo, responde mencionando esta duración.

3. **ESTRUCTURA OBLIGATORIA**:
   - 40% ESCUCHA ACTIVA: Validar emociones, preguntar "¿cómo te sientes?"
   - 30% MINDFULNESS: Ofrecer técnica específica (respiración, grounding)
   - 30% ACCIÓN PRÁCTICA: 1 ejercicio concreto para hoy

4. **EASTER EGGS**:
   - Toque Íntimo: Solo si usuario pide explícitamente "toque íntimo" o "hablar con cariño"
   - Horóscopo: SOLO para mujeres
   - Propósito: Explorar sentido de vida cuando se mencione
   - Hábitos: Sistema de mejora progresiva 1% cada día

5. **LÍMITES ÉTICOS**:
   - NO das consejos médicos
   - NO reemplazas terapia profesional  
   - SÍ derivas en crisis graves

**CONTEXTO PERSONALIZADO:**
- Género/Edad: {gender} / {age}
- Foco: {foco_personalizado}
- Lenguaje: {lenguaje_personalizado}
- Metáfora: {metafora_personalizada}

**ESTADO SESIÓN:**
- Tiempo transcurrido: {tiempo_transcurrido} minutos
- Estatus: {estatus_sesion}
- Easter Egg solicitado: {easter_egg_solicitado}

**INSTRUCCIÓN FINAL:** Responde como Alma en español, aplicando las reglas estrictas. Sé empático pero profesional.

Contexto usuario: {user_context}
Mensaje actual: {user_message}
Historial: {conversation_history}
"""

# --- SISTEMA DE SUSCRIPCIONES PAGADAS ---

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

# --- SISTEMA DE TRIAL Y ACCESO ---

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

# --- FUNCIONES MEJORADAS DE ALMA ---

def get_user_session(user_phone):
    if user_phone not in user_sessions:
        user_sessions[user_phone] = {
            'conversation_history': [],
            'created_at': datetime.now().isoformat(),
            'session_start_time': datetime.now().timestamp(), 
            'recordatorio_enviado': False,                     
            'gender': 'Desconocido',  
            'age': 'Desconocido',    
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

def intentar_actualizar_contexto(user_message, session):
    message_lower = user_message.lower()
    updated = False
    
    match_age = re.search(r'\b(?:tengo|soy|edad.*es|es)\s*(\d{2,3})\b|\b(\d{2,3})\s*(?:años|years)\b', message_lower)
    if match_age and session['age'] == 'Desconocido':
        age_str = match_age.group(1) or match_age.group(2)
        try:
            age = int(age_str)
            if 18 <= age <= 100: 
                session['age'] = str(age)
                updated = True
        except ValueError:
            pass
    
    if session['gender'] == 'Desconocido':
        if any(word in message_lower for word in ["mujer", "chica", "femenino", "femenina", "niña"]):
            session['gender'] = 'Mujer'
            updated = True
        elif any(word in message_lower for word in ["hombre", "chico", "masculino", "masculina", "niño"]):
            session['gender'] = 'Hombre'
            updated = True
    
    return updated

def detectar_y_manejar_crisis(user_message):
    message_lower = user_message.lower()
    for trigger in TRIGGER_CRISIS:
        if trigger in message_lower:
            return True
    return False

def detectar_easter_egg(user_message):
    message_lower = user_message.lower()
    for egg, triggers in TRIGGER_EASTER_EGGS.items():
        for trigger in triggers:
            if trigger in message_lower:
                return egg
    return "Ninguno"

def obtener_contexto_alma(gender, age):
    try:
        age_int = int(age)
        if 18 <= age_int <= 25:
            age_key = '18-25'
        elif 26 <= age_int <= 39:
            age_key = '26-39'
        elif age_int >= 40:
            age_key = '40+'
        else:
            age_key = None
    except (ValueError, TypeError):
        age_key = None

    gender_key = None
    if gender and gender != 'Desconocido':
        if "mujer" in gender.lower():
            gender_key = "Mujer"
        elif "hombre" in gender.lower():
            gender_key = "Hombre"
    
    if gender_key and age_key and gender_key in CONTEXTO_PERSONALIZADO and age_key in CONTEXTO_PERSONALIZADO[gender_key]:
        return CONTEXTO_PERSONALIZADO[gender_key][age_key]
    
    return {"foco": "auto-descubrimiento y resiliencia", "lenguaje": "comprensivo y neutro", "metafora": "semilla de crecimiento"}

def construir_prompt_alma(user_message, user_session, user_phone):
    contexto = obtener_contexto_alma(user_session['gender'], user_session['age'])
    easter_egg = detectar_easter_egg(user_message)
    tiempo_transcurrido_minutos = int((datetime.now().timestamp() - user_session['session_start_time']) / 60)
    
    # ✅ NUEVA LÓGICA: RESTRICCIÓN HORÓSCOPO PARA HOMBRES
    if easter_egg == "horoscopo_consciente" and user_session['gender'] == 'Hombre':
        return """INSTRUCCIÓN ESTRICTA: El usuario (hombre) solicitó horóscopo. 
RESPONDE EXACTAMENTE: "El horóscopo consciente es una herramienta de autoconocimiento disponible solo para mujeres. ¿Te gustaría explorar otras herramientas como propósito de vida o hábitos atómicos?" 
NO ofrezcas horóscopo bajo ninguna circunstancia."""
    
    # Información de suscripción ACTUALIZADA
    subscription = get_user_subscription(user_phone)
    trial_activo = verificar_trial_activo(subscription)
    dias_restantes_trial_val = dias_restantes_trial(subscription)
    usuario_suscrito = verificar_suscripcion_activa(user_phone)
    dias_restantes_suscripcion_val = dias_restantes_suscripcion(user_phone)
    
    # Determinar estatus de sesión
    if tiempo_transcurrido_minutos >= LIMITE_SESION_MAXIMO_MINUTOS:
        estatus_sesion = f"LIMITE EXCEDIDO ({LIMITE_SESION_MAXIMO_MINUTOS} MINUTOS). DEBES CERRAR INMEDIATAMENTE la conversación y guardar el contexto."
    elif tiempo_transcurrido_minutos >= DURACION_SESION_NORMAL_MINUTOS:
        estatus_sesion = f"CIERRE FLEXIBLE (TIEMPO EXTRA). Ya superaste los {DURACION_SESION_NORMAL_MINUTOS} minutos. Mantente en la Fase 3 (Sugerencia Práctica) y finaliza con el cierre, la felicitación y el ritual. NO extiendas más de {LIMITE_SESION_MAXIMO_MINUTOS} minutos."
    elif tiempo_transcurrido_minutos >= INTERVALO_RECORDATORIO_MINUTOS:
        estatus_sesion = "AVISO DE CIERRE ENVIADO. Inicia la transición a la Fase 3 (Sugerencia Práctica) para que el cierre sea suave antes de los 30 minutos."
    else:
        estatus_sesion = f"Sesión en curso. {DURACION_SESION_NORMAL_MINUTOS - tiempo_transcurrido_minutos} minutos restantes para el aviso de cierre."
        
    conversation_history = ""
    for msg in user_session['conversation_history'][-3:]:
        conversation_history += f"Usuario: {msg['user']}\nAlma: {msg['alma']}\n"
    
    user_context = f"Género: {user_session['gender']}, Edad: {user_session['age']}, Crisis previas: {user_session['crisis_count']}"
    
    prompt = ALMA_PROMPT_BASE.format(
        gender=user_session['gender'],
        age=user_session['age'],
        foco_personalizado=contexto['foco'],
        lenguaje_personalizado=contexto['lenguaje'],
        metafora_personalizada=contexto['metafora'],
        trial_activo=trial_activo,
        dias_restantes_trial=dias_restantes_trial_val,
        usuario_suscrito=usuario_suscrito,
        dias_restantes_suscripcion=dias_restantes_suscripcion_val,
        tiempo_transcurrido=tiempo_transcurrido_minutos,
        estatus_sesion=estatus_sesion,
        crisis_count=user_session['crisis_count'],
        easter_egg_solicitado=easter_egg,
        user_context=user_context,
        user_message=user_message,
        conversation_history=conversation_history
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
            "max_tokens": 800,
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
🌐 **CAPSI Universidad Autónoma de Querétaro:** Atención especializada

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

# --- ENDPOINT PRINCIPAL COMPLETO MEJORADO ---

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        user_phone = request.form.get('From', '')
        user_message = request.form.get('Body', '').strip()
        
        if not user_message:
            return Response("OK", status=200)
        
        print(f"🔔 MENSAJE RECIBIDO de {user_phone}: {user_message}")
        
        # 1. VERIFICAR ACCESO (TRIAL O SUSCRIPCIÓN)
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
            alma_response = f"¡Hola! Tu sesión de Alma de hoy ya ha concluido. Recuerda que este camino es diario, no intensivo. Podrás iniciar tu próxima sesión una vez que sea mañana (en {horas} horas y {minutos} minutos). ¡Estaré aquí para ti en tu nuevo día de crecimiento! 🌱"
            return enviar_respuesta_twilio(alma_response, user_phone)
        
        # 5. PROTOCOLO DE CRISIS
        if detectar_y_manejar_crisis(user_message):
            session['crisis_count'] += 1
            save_user_session(user_phone, session)
            return enviar_respuesta_crisis(user_phone)

        # 6. GESTIÓN DE TIEMPO: LÍMITE FORZADO
        tiempo_transcurrido_minutos = int((datetime.now().timestamp() - session['session_start_time']) / 60)
        
        if tiempo_transcurrido_minutos >= LIMITE_SESION_MAXIMO_MINUTOS:
            session['last_session_date'] = datetime.now().strftime('%Y-%m-%d')
            save_user_session(user_phone, session) 
            
            alma_response = f"Gracias por tu tiempo. Hemos alcanzado el límite máximo de {LIMITE_SESION_MAXIMO_MINUTOS} minutos por hoy. Tu contexto está guardado. ¡Podrás iniciar tu próxima sesión mañana! 🌱"
            
            user_sessions.pop(user_phone, None)
            return enviar_respuesta_twilio(alma_response, user_phone)
        
        # 7. RECORDATORIO DE CIERRE
        if debe_recordar_cierre(session):
            print(f"[{user_phone}] Inyectando instrucción de cierre a DeepSeek.")
            user_message = AVISO_CIERRE + " ||| Mensaje real del usuario: " + user_message

        # 8. ACTUALIZAR CONTEXTO
        contexto_actualizado = intentar_actualizar_contexto(user_message, session)

        # 9. SOLICITAR INFORMACIÓN FALTANTE
        if session['gender'] == 'Desconocido' or session['age'] == 'Desconocido':
            if not contexto_actualizado:
                alma_response = "¡Hola! Para ser tu mejor compañera, ¿me confirmas tu **género** (Mujer/Hombre) y **edad**? Así personalizo tu camino 🌱"
                return enviar_respuesta_twilio(alma_response, user_phone)
        
        # 10. GENERAR RESPUESTA CON ALMA COMPLETA
        prompt = construir_prompt_alma(user_message, session, user_phone)
        print(f"📝 PROMPT ENVIADO A DEEPSEEK:\n{prompt}")
        
        alma_response = llamar_deepseek(prompt)
        print(f"💬 RESPUESTA DE ALMA: {alma_response}")
        
        # 11. GUARDAR HISTORIAL
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

# --- ENDPOINTS ADMIN Y TWILIO ---

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

@app.route('/admin/suscripciones', methods=['GET'])
def admin_ver_suscripciones():
    hoy = datetime.now().date()
    suscripciones_info = []
    
    for user_phone, sub in paid_subscriptions.items():
        fecha_vencimiento = datetime.strptime(sub['fecha_vencimiento'], '%Y-%m-%d').date()
        dias_restantes = (fecha_vencimiento - hoy).days
        
        suscripciones_info.append({
            'telefono': user_phone,
            'fecha_activacion': sub['fecha_activacion'],
            'fecha_vencimiento': sub['fecha_vencimiento'],
            'estado': sub['estado'],
            'dias_restantes': dias_restantes,
            'recordatorio_7d': sub['recordatorio_7d_enviado'],
            'recordatorio_3d': sub['recordatorio_3d_enviado'],
            'recordatorio_0d': sub['recordatorio_0d_enviado']
        })
    
    return {
        "total_suscripciones": len(paid_subscriptions),
        "activas": sum(1 for s in paid_subscriptions.values() if s['estado'] == 'activo'),
        "vencidas": sum(1 for s in paid_subscriptions.values() if s['estado'] == 'vencido'),
        "suscripciones": suscripciones_info
    }

@app.route('/health', methods=['GET'])
def health_check():
    return {
        "status": "healthy", 
        "service": "Alma Chatbot",
        "users_activos": len(user_sessions),
        "suscripciones_activas": sum(1 for s in paid_subscriptions.values() if s['estado'] == 'activo'),
        "trials_activos": sum(1 for s in user_subscriptions.values() if verificar_trial_activo(s)),
        "timestamp": datetime.now().isoformat()
    }

if __name__ == '__main__':
    print("🤖 Alma Chatbot INICIADO - Sistema Completo con Reglas Estrictas")
    print(f"📞 Número comprobantes: {NUMERO_COMPROBANTES}")
    print("🎯 Características MEJORADAS:")
    print("   ✅ Restricción horóscopo solo para mujeres")
    print("   ✅ Reglas estrictas de duración (30min + 15flex)")
    print("   ✅ Estructura conversacional 40-30-30")
    print("   ✅ Sistema completo de suscripciones")
    print("   ✅ Debug logs mejorados")
    app.run(host='0.0.0.0', port=5000, debug=False)
