# Système Intégré: Arrosage Automatique et Contrôle d'Accès par Sonnette (Corrigé)
# Version avec seulement LCD 16x2 (pas d'OLED)
import network
import urequests
import time
import json
from machine import Pin, I2C, PWM
import dht

'''------------------------------ CONFIGURATIONS ------------------------------------'''
# --- System Timers ---
TIEMPO_ACTIVACION_HIDROCAM = 180
COMMAND_CHECK_INTERVAL = 5
LCD_UPDATE_INTERVAL = 10

# --- API & Bot URLs ---
DOOR_SERVER_URL = "https://pq7nmnhf-5000.uks1.devtunnels.ms"
API_CLIMA_URL = "http://api.weatherstack.com/current?access_key=5f9685320c910465401de4e462183c00&query=rabat"

TELEGRAM_CONFIG = {
    "bot_token": "8311573110:AAFA2aJmLpZ6cXW8mGzrOFqZ4Y_ru72QKoI",
    "chat_id": "5455039697"
}

# --- PIN Definitions ---
LED_PUMP_PIN = 21
DHT_PIN = 22
SERVO_VALVE_PIN = 23
PIR_PIN = 25
ECHO_PIN = 26
TRIG_PIN = 27
DOORBELL_PIN = 32
SERVO_DOOR_PIN = 2
LED_GREEN_PIN = 13
LED_RED_PIN = 12

# LCD I2C Pins (selon votre schéma: SDA=19, SCL=18)
LCD_SDA_PIN = 19
LCD_SCL_PIN = 18
LCD_ADDR = 0x27

'''------------------------------ LCD DRIVER CORRIGÉ ------------------------------------'''
class I2CLcd:
    def __init__(self, i2c, i2c_addr, num_lines, num_columns):
        self.i2c = i2c
        self.i2c_addr = i2c_addr
        self.num_lines = num_lines
        self.num_columns = num_columns
        self.display_on = 0x04
        self.backlight_on = 0x08
        
        # Initialisation en mode 4 bits
        self._write_4bits(0x03 << 4)
        time.sleep_ms(5)
        self._write_4bits(0x03 << 4)
        time.sleep_ms(5)
        self._write_4bits(0x03 << 4)
        time.sleep_ms(1)
        self._write_4bits(0x02 << 4)  # Mode 4 bits
        
        # Configuration LCD
        self.command(0x28)  # 4-bit, 2 lignes, 5x8
        self.command(0x0C)  # Display ON, cursor OFF
        self.command(0x06)  # Entry mode
        self.command(0x01)  # Clear
        time.sleep_ms(2)
    
    def _write_4bits(self, data):
        """Écrire 4 bits sur le bus I2C avec PCF8574"""
        # PCF8574 format: D7 D6 D5 D4 BL E RW RS
        # Pour nous: BL=1 (backlight), E=1 puis 0, RW=0 (write)
        data = data | self.backlight_on | 0x04  # Enable HIGH
        self.i2c.writeto(self.i2c_addr, bytes([data]))
        time.sleep_us(1)
        data = data & ~0x04  # Enable LOW
        self.i2c.writeto(self.i2c_addr, bytes([data]))
        time.sleep_us(50)
    
    def command(self, cmd, rs=0):
        """Envoyer une commande au LCD"""
        # RS=0 pour commande
        data = rs  # RS bit
        self._write_4bits(data | (cmd & 0xF0))           # 4 bits hauts
        self._write_4bits(data | ((cmd << 4) & 0xF0))   # 4 bits bas
    
    def write_char(self, char):
        """Écrire un caractère"""
        data = 0x01  # RS=1 pour données
        self._write_4bits(data | (char & 0xF0))        # 4 bits hauts
        self._write_4bits(data | ((char << 4) & 0xF0)) # 4 bits bas
    
    def putstr(self, string):
        """Écrire une chaîne de caractères"""
        for char in string:
            self.write_char(ord(char))
    
    def clear(self):
        """Effacer l'écran"""
        self.command(0x01)
        time.sleep_ms(2)
    
    def move_to(self, col, row):
        """Positionner le curseur"""
        addr = 0x80 | (col & 0x0F)
        if row == 1:
            addr |= 0x40
        self.command(addr)

'''------------------------------ HARDWARE INITIALIZATION ------------------------------------'''
print("Initialisation du système...")
print("Configuration I2C pour LCD...")

# Initialiser I2C pour LCD (seulement LCD sur GPIO18/19)
i2c_lcd = I2C(0, scl=Pin(LCD_SCL_PIN), sda=Pin(LCD_SDA_PIN), freq=100000)
time.sleep_ms(100)

# Scanner bus I2C
devices = i2c_lcd.scan()
print("Périphériques I2C détectés:", [hex(addr) for addr in devices])

# Initialiser LCD
if LCD_ADDR in devices:
    print(f"Initialisation LCD à l'adresse {hex(LCD_ADDR)}...")
    lcd = I2CLcd(i2c_lcd, LCD_ADDR, 2, 16)
    print("LCD initialisé avec succès!")
    # Test LCD
    lcd.clear()
    lcd.putstr("LCD OK!")
    time.sleep(1)
else:
    print(f"ERREUR: LCD non détecté à l'adresse {hex(LCD_ADDR)}!")
    print("Adresses disponibles:", [hex(addr) for addr in devices])
    # Créer un LCD simulé pour continuer
    class FakeLCD:
        def clear(self): print("[LCD] Clear")
        def putstr(self, text): print(f"[LCD]: {text}")
        def move_to(self, col, row): print(f"[LCD] Move to col:{col}, row:{row}")
    lcd = FakeLCD()

# Initialiser les autres composants
led_pump = Pin(LED_PUMP_PIN, Pin.OUT)
dht_sensor = dht.DHT22(Pin(DHT_PIN))
trigger = Pin(TRIG_PIN, Pin.OUT)
echo = Pin(ECHO_PIN, Pin.IN)
servo_valve = PWM(Pin(SERVO_VALVE_PIN), freq=50)
pir = Pin(PIR_PIN, Pin.IN)
led_green = Pin(LED_GREEN_PIN, Pin.OUT)
led_red = Pin(LED_RED_PIN, Pin.OUT)
servo_door = PWM(Pin(SERVO_DOOR_PIN), freq=50)
doorbell = Pin(DOORBELL_PIN, Pin.IN, Pin.PULL_DOWN)

last_update_id = 0

'''------------------------------ CORE FUNCTIONS ------------------------------------'''
def wifi_is_connected():
    wlan = network.WLAN(network.STA_IF)
    return wlan.active() and wlan.isconnected()

def conecte_wifi():
    print("Connexion WiFi...")
    lcd.clear()
    lcd.putstr("Connexion WiFi")
    
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect("Wokwi-GUEST", "")
    
    attempts = 0
    while not wlan.isconnected() and attempts < 20:
        time.sleep(0.5)
        print(".", end="")
        lcd.move_to(attempts % 16, 1)
        lcd.putstr(".")
        attempts += 1
    
    if wlan.isconnected():
        ip = wlan.ifconfig()[0]
        print(f"\n✓ WiFi connecté! IP: {ip}")
        lcd.clear()
        lcd.putstr("WiFi OK!")
        lcd.move_to(0, 1)
        lcd.putstr(ip[:16])
        time.sleep(2)
        return True
    else:
        print("\n✗ Échec connexion WiFi")
        lcd.clear()
        lcd.putstr("Erreur WiFi!")
        time.sleep(2)
        return False

def send_telegram_message(message):
    token, chat_id = TELEGRAM_CONFIG["bot_token"], TELEGRAM_CONFIG["chat_id"]
    msg = message.replace(" ", "%20").replace("\n", "%0A")
    url = f"https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&text={msg}"
    try:
        r = urequests.get(url)
        r.close()
        print("Telegram message sent.")
    except Exception as e:
        print(f"Telegram API error: {e}")

'''------------------------------ DOOR LOCK SYSTEM (version corrigée) ------------------------------------'''
def set_servo_angle(servo_pwm, angle):
    """Positionner un servo à un angle spécifique (0-180 degrés)"""
    min_us = 500
    max_us = 2500
    us = int(min_us + (max_us - min_us) * (angle / 180))
    duty = int(us * 65535 / 20000)
    servo_pwm.duty_u16(duty)

def check_face_recognition():
    """Vérification de la reconnaissance faciale - CORRIGÉE SANS TIMEOUT"""
    if not wifi_is_connected():
        print("⚠️ WiFi déconnecté")
        lcd.clear()
        lcd.putstr("WiFi Error")
        conecte_wifi()
        return False, "Erreur WiFi", 0

    endpoint = DOOR_SERVER_URL + "/recognize"
    print("\n🔍 Vérification reconnaissance faciale...")
    print("URL:", endpoint)

    lcd.clear()
    lcd.putstr("Verification...")
    lcd.move_to(0, 1)
    lcd.putstr("Analyse visage")

    try:
        # IMPORTANT: Ne pas utiliser timeout pour éviter l'erreur -116
        r = urequests.get(
            endpoint,
            headers={"ngrok-skip-browser-warning": "true"}
            # Pas de timeout ici!
        )
        code = r.status_code
        print("HTTP Code:", code)

        if code == 200:
            payload = r.text
            print("Réponse reçue:", payload[:100] + "..." if len(payload) > 100 else payload)

            data = json.loads(payload)
            recognized = bool(data.get("recognized", False))
            name = data.get("name", "")
            confidence = int(data.get("confidence", 0))

            print("✓ Reconnu:", "OUI" if recognized else "NON")
            print("Nom:", name)
            print("Confiance:", confidence, "%")

            r.close()
            return recognized, name, confidence

        # Non-200
        print(f"✗ Code HTTP: {code}")
        lcd.clear()
        lcd.putstr("Erreur Serveur")
        lcd.move_to(0, 1)
        lcd.putstr(f"Code: {code}")
        r.close()
        return False, "Erreur Serveur", 0

    except Exception as e:
        print(f"✗ Erreur HTTP/JSON: {e}")
        lcd.clear()
        lcd.putstr("Erreur Serveur")
        lcd.move_to(0, 1)
        lcd.putstr("Connexion Err")
        time.sleep(1)
        return False, "Erreur Connexion", 0

def open_door(name):
    """Ouvrir la porte pour une personne reconnue"""
    print("\n🔓 Ouverture de la porte...")
    
    # Allumer LED verte, éteindre rouge
    led_green.on()
    led_red.off()
    
    # Affichage LCD
    lcd.clear()
    lcd.putstr("Face Recognized!")
    lcd.move_to(0, 1)
    
    # Tronquer le nom si trop long
    display_name = name[:16] if len(name) <= 16 else name[:13] + "..."
    lcd.putstr(display_name)
    
    # Ouvrir la porte progressivement
    for pos in range(0, 91, 3):
        set_servo_angle(servo_door, pos)
        time.sleep(0.015)
    
    # Attendre 3 secondes
    time.sleep(3)
    
    # Fermer la porte
    print("🔒 Fermeture de la porte...")
    lcd.clear()
    lcd.putstr("Fermeture...")
    lcd.move_to(0, 1)
    lcd.putstr("Porte")
    
    for pos in range(90, -1, -3):
        set_servo_angle(servo_door, pos)
        time.sleep(0.015)
    
    # Éteindre LED verte
    led_green.off()
    print("✓ Porte fermée")
    
    # Envoyer notification Telegram
    send_telegram_message(f"✅ Porte ouverte pour: {name}")

def keep_locked():
    """Garder la porte verrouillée"""
    print("\n🚫 ACCES REFUSE - Porte verrouillée")
    
    # Allumer LED rouge, éteindre verte
    led_green.off()
    led_red.on()
    
    # Affichage LCD
    lcd.clear()
    lcd.putstr("INTRUDER ALERT!")
    lcd.move_to(0, 1)
    lcd.putstr("Access Denied")
    
    # Envoyer alerte Telegram
    send_telegram_message("🚨 ALERTE: Personne inconnue détectée à la porte ! Accès refusé.")
    
    # Clignotement LED rouge
    for _ in range(5):
        led_red.off()
        time.sleep(0.2)
        led_red.on()
        time.sleep(0.2)
    
    led_red.off()
    print("✓ Porte restée verrouillée")

def check_doorbell():
    """Vérifier si la sonnette est pressée"""
    if doorbell.value() == 1:
        print("\n🔔 Sonnette pressée!")
        time.sleep(0.1)  # Anti-rebond
        
        # Récupérer les 3 valeurs
        recognized, name, confidence = check_face_recognition()
        
        # CORRECTION ICI : Pas de seuil de confiance !
        # Dans le code qui fonctionne, vous ouvrez la porte dès que recognized=True
        if recognized:
            open_door(name)
        else:
            keep_locked()
        
        # Retour à l'état normal
        time.sleep(1)
        lcd.clear()
        lcd.putstr("Systeme Pret")
        lcd.move_to(0, 1)
        lcd.putstr("En attente...")

'''------------------------------ WATERING SYSTEM ------------------------------------'''
def fetch_weather_data():
    try:
        # Pas de timeout ici non plus pour éviter les erreurs SSL
        r = urequests.get(API_CLIMA_URL)
        data = r.json()
        r.close()
        return data
    except Exception as e:
        print(f"Weather API error: {e}")
        return None

def measure_distance():
    """Mesurer la distance avec le capteur ultrasonique"""
    trigger.off()
    time.sleep_us(2)
    trigger.on()
    time.sleep_us(10)
    trigger.off()
    
    start = time.ticks_us()
    timeout = 100000
    
    # Attente echo LOW
    while echo.value() == 0:
        if time.ticks_diff(time.ticks_us(), start) > timeout:
            return None
    
    start = time.ticks_us()
    
    # Attente echo HIGH
    while echo.value() == 1:
        if time.ticks_diff(time.ticks_us(), start) > timeout:
            return None
    
    return (time.ticks_diff(time.ticks_us(), start) * 0.0343) / 2

def manage_irrigation(weather_data_current):
    if not weather_data_current:
        return "Meteo N/A"
    
    humidity = weather_data_current.get('humidity', 100)
    temperature = weather_data_current.get('temperature', 0)
    
    if humidity > 75:
        return "Humidite elevee"
    elif temperature > 28:
        activate_pump(10, "Arrosage intensif")
        return "Arrosage intensif"
    
    return "Conditions OK"

def activate_pump(duration, reason):
    print(f"Activation pompe: {duration}s - {reason}")
    led_pump.on()
    
    # Affichage sur LCD
    lcd.clear()
    lcd.putstr("Arrosage en cours")
    lcd.move_to(0, 1)
    lcd.putstr(f"{duration}s")
    
    send_telegram_message(f"💧 Pompe activée: {duration}s.\nRaison: {reason}")
    time.sleep(duration)
    led_pump.off()

def detect_motion():
    if pir.value() == 1:
        print("⚠️ Motion detected!")
        send_telegram_message("⚠️ ALERTE: Mouvement détecté dans le jardin!")
        time.sleep(10)

def check_telegram_commands(full_weather_data):
    global last_update_id
    url = f"https://api.telegram.org/bot{TELEGRAM_CONFIG['bot_token']}/getUpdates?offset={last_update_id + 1}"
    try:
        r = urequests.get(url)
        data = r.json()
        r.close()
        
        for update in data.get("result", []):
            last_update_id = update["update_id"]
            if "message" not in update or "text" not in update["message"]:
                continue
            
            command = update["message"]["text"]

            if command == "/status":
                print("Action: Sending detailed status report to Telegram.")
                
                try:
                    dht_sensor.measure()
                    temp_local = dht_sensor.temperature()
                    local_humidity = dht_sensor.humidity()
                except:
                    temp_local = "N/A"
                    local_humidity = "N/A"
                
                distance = measure_distance()
                tank_height = 100
                if distance:
                    water_level_cm = tank_height - distance
                    water_percentage = ((tank_height - distance) / tank_height) * 100
                else:
                    water_level_cm, water_percentage = "N/A", "N/A"
                
                current_data = full_weather_data.get('current', {})
                location_data = full_weather_data.get('location', {})
                
                ville = location_data.get('name', 'N/A')
                temp = current_data.get('temperature', 'N/A')
                humedad = current_data.get('humidity', 'N/A')
                descripcion_list = current_data.get('weather_descriptions', ['N/A'])
                descripcion = descripcion_list[0]
                
                message = (
                    "📊 SYSTÈME D'ARROSAGE\n\n"
                    "**Informations météo de la ville:**\n"
                    "📍 Ville: " + str(ville) + "\n"
                    "🌡️ Température: " + str(temp) + "°C\n"
                    "💧 Humidité: " + str(humedad) + "%\n"
                    "⛅ Conditions: " + str(descripcion) + "\n\n"
                    "**Informations locales:**\n"
                    "🌡️ Température locale: " + str(temp_local) + "°C\n"
                    "💧 Humidité sol: " + str(local_humidity) + "%\n\n"
                    "**Informations réservoir d'eau:**\n"
                    "💦 Niveau eau: " + (f"{water_percentage:.0f}" if isinstance(water_percentage, float) else "N/A") + "%\n"
                )
                send_telegram_message(message)
                
    except Exception as e:
        print(f"Error checking Telegram: {e}")

'''------------------------------ LCD DISPLAY UPDATE ------------------------------------'''
def update_lcd_display():
    """Mettre à jour l'affichage LCD avec les données actuelles"""
    try:
        lcd.clear()
        
        # Ligne 1: Température et humidité
        try:
            dht_sensor.measure()
            temp = dht_sensor.temperature()
            hum = dht_sensor.humidity()
            line1 = f"T:{temp:.0f}C H:{hum:.0f}%"
        except:
            line1 = "Capteurs..."
        
        lcd.putstr(line1[:16])
        
        # Ligne 2: Niveau d'eau
        lcd.move_to(0, 1)
        dist = measure_distance()
        if dist:
            reservoir = int(((100 - dist) / 100) * 100)
            line2 = f"Eau: {reservoir}%"
        else:
            line2 = "Eau: N/A"
        
        lcd.putstr(line2[:16])
        
    except Exception as e:
        print(f"Erreur mise à jour LCD: {e}")

'''------------------------------ MAIN LOOP ------------------------------------'''
if __name__ == "__main__":
    print("\n" + "="*60)
    print("DÉMARRAGE DU SYSTÈME INTÉGRÉ")
    print("="*60)
    
    # Initialisation
    conecte_wifi()
    
    # Initialiser les servos
    set_servo_angle(servo_door, 0)  # Porte fermée
    time.sleep(1)
    
    # Éteindre toutes les LEDs
    led_pump.off()
    led_green.off()
    led_red.off()
    
    # Variables de timing
    last_cmd_check = 0
    last_weather_update = 0
    last_lcd_update = 0
    riego_realizado = True
    full_weather_data = {}
    
    # Message de démarrage
    send_telegram_message("✅ Système Intégré démarré avec succès!")
    
    # Affichage initial
    lcd.clear()
    lcd.putstr("Systeme Pret")
    lcd.move_to(0, 1)
    lcd.putstr("En fonctionnement")
    time.sleep(2)
    
    print("\n✅ SYSTÈME PRÊT - EN FONCTIONNEMENT")
    print("\nAttente des événements...")
    print("- Appuyez sur la sonnette pour tester la reconnaissance faciale")
    print("- Envoyez /status sur Telegram pour obtenir le statut")
    print("="*60)
    
    # Boucle principale
    while True:
        current_time = time.time()
        
        # 1. Vérifier sonnette (priorité haute)
        check_doorbell()
        
        # 2. Détection mouvement
        detect_motion()
        
        # 3. Vérifier commandes Telegram
        if current_time - last_cmd_check > COMMAND_CHECK_INTERVAL:
            check_telegram_commands(full_weather_data)
            last_cmd_check = current_time
        
        # 4. Mise à jour météo
        if current_time - last_weather_update > TIEMPO_ACTIVACION_HIDROCAM:
            print("\n[Météo] Mise à jour...")
            clima = fetch_weather_data()
            if clima:
                full_weather_data = clima
                riego_realizado = False
                print(f"  Température: {clima.get('current', {}).get('temperature', 'N/A')}°C")
                print(f"  Humidité: {clima.get('current', {}).get('humidity', 'N/A')}%")
            last_weather_update = current_time
        
        # 5. Irrigation automatique
        if not riego_realizado and full_weather_data:
            status = manage_irrigation(full_weather_data.get('current', {}))
            print(f"[Irrigation] {status}")
            riego_realizado = True
        
        # 6. Mise à jour LCD
        if current_time - last_lcd_update > LCD_UPDATE_INTERVAL:
            update_lcd_display()
            last_lcd_update = current_time
        
        # Petite pause
        time.sleep(0.1)