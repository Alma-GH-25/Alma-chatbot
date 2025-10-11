from flask import Flask, request, Response
import requests
import json
import os
from datetime import datetime

app = Flask(__name__)

# Configuración desde variables de entorno
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"

# Almacenamiento simple en memoria
user_sessions = {}

# PROMPT COMPLETO DE ALMA
ALMA_PROMPT_BASE = """
Eres "Alma" - un chatbot especializado en mindfulness y apoyo emocional. Tu propósito es ser un compañero en el camino de auto descubrimiento, no un terapeuta.

FILOSOFÍA CENTRAL:
• "Enfócate en el camino, no en el destino"
• "La solución se construye con cada paso" 
• "Escucha primero, sugiere después"
• "Validación auténtica + herramientas para resiliencia emocional"

INSTRUCCIONES ESPECÍFICAS:
1. ESCUCHA ACTIVA primero (40% de la conversación)
2. MINDFULNESS APLICADO después (30%)
3. SUGERENCIA PRÁCTICA al final (30%)
4. Sé empático pero no condescendiente
5. Responde en ESPAÑOL siempre
6. Sé cálido/a y profesional

Contexto usuario: {user_context}
Mensaje actual: {user_message}
Historial reciente: {conversation_history}

Responde como Alma:
"""

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        # Recibir mensaje de Twilio
        user_phone = request.form.get('From', '')
        user_message = request.form.get('Body', '').strip()
        
        print(f"Mensaje de {user_phone}: {user_message}")
        
        # Ignorar mensajes vacíos
        if not user_message:
            return Response("OK", status=200)
        
        # Inicializar sesión si no existe
        if user_phone not in user_sessions:
            user_sessions[user_phone] = {
                'conversation_history': [],
                'created_at': datetime.now().isoformat()
            }
        
        # Construir prompt contextualizado
        prompt = construir_prompt_alma(user_message, user_sessions[user_phone])
        
        # Llamar a DeepSeek API
        alma_response = llamar_deepseek(prompt)
        
        # Guardar en historial
        user_sessions[user_phone]['conversation_history'].append({
            'user': user_message,
            'alma': alma_response,
            'timestamp': datetime.now().isoformat()
        })
        
        # Limitar historial a últimos 10 mensajes
        if len(user_sessions[user_phone]['conversation_history']) > 10:
            user_sessions[user_phone]['conversation_history'] = user_sessions[user_phone]['conversation_history'][-10:]
        
        # Enviar respuesta a Twilio
        return enviar_respuesta_twilio(alma_response, user_phone)
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return enviar_respuesta_twilio("Lo siento, estoy teniendo dificultades técnicas. ¿Podrías intentarlo de nuevo? 🌱", user_phone)

def construir_prompt_alma(user_message, user_session):
    # Construir historial de conversación
    conversation_history = ""
    for msg in user_session['conversation_history'][-3:]:
        conversation_history += f"Usuario: {msg['user']}\nAlma: {msg['alma']}\n"
    
    prompt = ALMA_PROMPT_BASE.format(
        user_context="",
        user_message=user_message,
        conversation_history=conversation_history
    )
    
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
            "max_tokens": 800
        }
        
        response = requests.post(DEEPSEEK_URL, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            return "Entiendo que quieres conectar. Estoy aquí para escucharte. ¿Puedes contarme más sobre cómo te sientes? 🌱"
            
    except Exception as e:
        return "Veo que estás buscando apoyo. ¿Podrías contarme más sobre lo que necesitas en este momento? 💫"

def enviar_respuesta_twilio(mensaje, telefono):
    from twilio.rest import Client
    
    account_sid = os.getenv('TWILIO_ACCOUNT_SID')
    auth_token = os.getenv('TWILIO_AUTH_TOKEN')
    
    client = Client(account_sid, auth_token)
    
    try:
        message = client.messages.create(
            body=mensaje,
            from_='whatsapp:+14155238886',
            to=telefono
        )
        return Response("OK", status=200)
    except Exception as e:
        return Response("OK", status=200)

@app.route('/health', methods=['GET'])
def health_check():
    return {"status": "healthy", "service": "Alma Chatbot"}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
