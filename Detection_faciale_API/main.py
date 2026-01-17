import cv2
import numpy as np
import os
from datetime import datetime
import time
import pickle
from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
import base64

class FaceRecognitionSystem:
    def __init__(self):
        # Détecteur de visages Haar Cascade
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        
        # Recognizer LBPH (Local Binary Patterns Histograms)
        self.recognizer = cv2.face.LBPHFaceRecognizer_create()
        
        self.known_faces = []
        self.known_names = []
        self.face_id_to_name = {}
        self.is_trained = False
        
        self.model_file = "face_recognition_model.yml"
        self.names_file = "face_names.pkl"
        
        # État pour l'API
        self.last_recognition = {
            "recognized": False,
            "name": "Unknown",
            "confidence": 0,
            "timestamp": None
        }
        
        # Charger le modèle s'il existe
        self.load_model()
        
    def load_model(self):
        """Charge le modèle entraîné s'il existe"""
        if os.path.exists(self.model_file) and os.path.exists(self.names_file):
            try:
                self.recognizer.read(self.model_file)
                with open(self.names_file, 'rb') as f:
                    self.face_id_to_name = pickle.load(f)
                self.is_trained = True
                print(f"✓ Modèle chargé avec {len(self.face_id_to_name)} personne(s)")
            except:
                print("⚠️  Erreur lors du chargement du modèle")
    
    def save_model(self):
        """Sauvegarde le modèle entraîné"""
        try:
            self.recognizer.write(self.model_file)
            with open(self.names_file, 'wb') as f:
                pickle.dump(self.face_id_to_name, f)
            print("✓ Modèle sauvegardé")
        except Exception as e:
            print(f"✗ Erreur de sauvegarde: {e}")
    
    def delete_user(self, name):
        """Supprime un utilisateur et ses données"""
        import shutil
        
        # Trouver l'ID de l'utilisateur
        user_id = None
        for face_id, face_name in self.face_id_to_name.items():
            if face_name.lower() == name.lower():
                user_id = face_id
                break
        
        if user_id is None:
            print(f"❌ Utilisateur '{name}' non trouvé!")
            return False
        
        print(f"\n🗑️  Suppression de '{name}'...")
        
        # Supprimer du dictionnaire
        del self.face_id_to_name[user_id]
        
        # Supprimer les données d'entraînement du dossier
        person_folder = os.path.join("training_data", name)
        if os.path.exists(person_folder):
            try:
                shutil.rmtree(person_folder)
                print(f"  ✓ Dossier supprimé: {person_folder}")
            except Exception as e:
                print(f"  ⚠️  Erreur lors de la suppression du dossier: {e}")
        
        # Supprimer de la liste known_faces
        self.known_faces = [(fid, img) for fid, img in self.known_faces if fid != user_id]
        
        print(f"✓ Utilisateur '{name}' supprimé!")
        print("⚠️  Pensez à réentraîner le modèle (option [2]) pour appliquer les changements")
        
        # Sauvegarder les changements
        self.save_model()
        
        return True
    
    def list_users(self):
        """Affiche la liste des utilisateurs enregistrés"""
        if not self.face_id_to_name:
            print("\n⚠️  Aucune personne enregistrée")
            return []
        
        print("\n📋 Personnes enregistrées:")
        for face_id, name in self.face_id_to_name.items():
            # Compter les échantillons
            person_folder = os.path.join("training_data", name)
            sample_count = 0
            if os.path.exists(person_folder):
                sample_count = len([f for f in os.listdir(person_folder) if f.endswith('.jpg')])
            print(f"  • {name} (ID: {face_id}, Échantillons: {sample_count})")
        
        return list(self.face_id_to_name.values())
    
    def collect_training_data(self, name, num_samples=30):
        """Collecte des échantillons de visage pour l'entraînement"""
        print(f"\n📸 Collecte de {num_samples} échantillons pour: {name}")
        print("➤ Bougez légèrement la tête dans différentes directions")
        
        cap = cv2.VideoCapture(0)
        
        if not cap.isOpened():
            print("❌ Impossible d'ouvrir la caméra!")
            return None
        
        time.sleep(0.5)
        
        cv2.namedWindow('Collecte echantillons', cv2.WINDOW_NORMAL)
        
        folder = "training_data"
        if not os.path.exists(folder):
            os.makedirs(folder)
        
        person_folder = os.path.join(folder, name)
        if not os.path.exists(person_folder):
            os.makedirs(person_folder)
        
        face_id = len(self.face_id_to_name)
        self.face_id_to_name[face_id] = name
        
        samples_collected = 0
        frame_count = 0
        
        print(f"✓ Caméra ouverte! Collecte en cours...")
        
        while samples_collected < num_samples:
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_count += 1
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Détecter les visages
            faces = self.face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.3,
                minNeighbors=5,
                minSize=(100, 100)
            )
            
            for (x, y, w, h) in faces:
                # Dessiner le rectangle
                cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 3)
                
                # Sauvegarder une image tous les 3 frames
                if frame_count % 3 == 0:
                    # Extraire et redimensionner le visage
                    face_roi = gray[y:y+h, x:x+w]
                    face_resized = cv2.resize(face_roi, (200, 200))
                    
                    # Sauvegarder
                    filename = os.path.join(person_folder, f"{name}_{samples_collected}.jpg")
                    cv2.imwrite(filename, face_resized)
                    
                    self.known_faces.append((face_id, face_resized))
                    samples_collected += 1
                    
                    print(f"✓ Échantillon {samples_collected}/{num_samples} collecté", end='\r')
                
                # Afficher le progrès
                progress = int((samples_collected / num_samples) * 100)
                cv2.putText(frame, f"Echantillons: {samples_collected}/{num_samples} ({progress}%)", 
                           (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            # Instructions
            cv2.putText(frame, f"Collecte pour: {name}", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            cv2.putText(frame, "Bougez legerement la tete", (10, 70),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            cv2.imshow('Collecte echantillons', frame)
            
            if cv2.waitKey(1) & 0xFF == 27:  # ESC
                print("\n❌ Collecte annulée")
                cap.release()
                cv2.destroyAllWindows()
                return None
        
        cap.release()
        cv2.destroyAllWindows()
        time.sleep(0.3)
        
        print(f"\n✓ Collecte terminée: {samples_collected} échantillons")
        return face_id
    
    def train_recognizer(self):
        """Entraîne le recognizer avec toutes les données collectées"""
        if not self.known_faces:
            # Charger depuis le dossier training_data
            folder = "training_data"
            if not os.path.exists(folder):
                print("❌ Aucune donnée d'entraînement trouvée!")
                return
            
            print("\n🔄 Chargement des données d'entraînement...")
            
            for person_name in os.listdir(folder):
                person_path = os.path.join(folder, person_name)
                if os.path.isdir(person_path):
                    face_id = len(self.face_id_to_name)
                    self.face_id_to_name[face_id] = person_name
                    
                    for img_name in os.listdir(person_path):
                        img_path = os.path.join(person_path, img_name)
                        img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
                        if img is not None:
                            self.known_faces.append((face_id, img))
                    
                    print(f"  ✓ {person_name}: {len(os.listdir(person_path))} images")
        
        if not self.known_faces:
            print("❌ Aucun visage à entraîner!")
            return
        
        print(f"\n🤖 Entraînement du modèle avec {len(self.known_faces)} échantillons...")
        
        # Préparer les données
        face_ids = [face_id for face_id, _ in self.known_faces]
        face_images = [img for _, img in self.known_faces]
        
        # Entraîner
        self.recognizer.train(face_images, np.array(face_ids))
        self.is_trained = True
        
        # Sauvegarder
        self.save_model()
        
        print(f"✓ Modèle entraîné avec succès!")
        print(f"  Personnes enregistrées: {', '.join(self.face_id_to_name.values())}")
    
    def recognize_from_camera_single(self):
        """Capture une seule image et reconnaît le visage (pour l'API)"""
        if not self.is_trained:
            return {"recognized": False, "name": "Unknown", "confidence": 0, "error": "Model not trained"}
        
        cap = cv2.VideoCapture(0)
        
        if not cap.isOpened():
            return {"recognized": False, "name": "Unknown", "confidence": 0, "error": "Camera error"}
        
        time.sleep(0.3)  # Laisser la caméra s'initialiser
        
        # Capturer plusieurs frames pour avoir une meilleure image
        for _ in range(5):
            ret, frame = cap.read()
        
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            return {"recognized": False, "name": "Unknown", "confidence": 0, "error": "Frame capture error"}
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Détecter les visages
        faces = self.face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.3,
            minNeighbors=5,
            minSize=(100, 100)
        )
        
        if len(faces) == 0:
            return {"recognized": False, "name": "Unknown", "confidence": 0, "error": "No face detected"}
        
        # Prendre le premier visage détecté
        (x, y, w, h) = faces[0]
        face_roi = gray[y:y+h, x:x+w]
        face_resized = cv2.resize(face_roi, (200, 200))
        
        # Prédire
        face_id, confidence = self.recognizer.predict(face_resized)
        
        # Plus la confiance est basse, meilleure est la correspondance
        if confidence < 70:
            name = self.face_id_to_name.get(face_id, "Unknown")
            confidence_percent = int(100 - confidence)
            
            result = {
                "recognized": True,
                "name": name,
                "confidence": confidence_percent,
                "timestamp": datetime.now().isoformat()
            }
        else:
            result = {
                "recognized": False,
                "name": "Unknown",
                "confidence": 0,
                "timestamp": datetime.now().isoformat()
            }
        
        self.last_recognition = result
        return result


# Instance globale
face_system = FaceRecognitionSystem()

# Flask API
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

@app.after_request
def after_request(response):
    """Ajoute les headers pour éviter les problèmes CORS et ngrok"""
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization,ngrok-skip-browser-warning')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "message": "Face Recognition API",
        "trained": face_system.is_trained,
        "users": list(face_system.face_id_to_name.values())
    })

@app.route('/recognize', methods=['GET', 'OPTIONS'])
def recognize():
    """Endpoint pour reconnaître un visage"""
    if request.method == 'OPTIONS':
        return '', 200
    
    print(f"\n🔔 Requête /recognize reçue de {request.remote_addr}")
    result = face_system.recognize_from_camera_single()
    print(f"📤 Réponse envoyée: {result}")
    return jsonify(result)

@app.route('/status', methods=['GET'])
def status():
    """Endpoint pour vérifier le statut du système"""
    return jsonify({
        "trained": face_system.is_trained,
        "users": list(face_system.face_id_to_name.values()),
        "last_recognition": face_system.last_recognition
    })

@app.route('/users', methods=['GET'])
def get_users():
    """Endpoint pour obtenir la liste des utilisateurs"""
    return jsonify({
        "users": list(face_system.face_id_to_name.values()),
        "count": len(face_system.face_id_to_name)
    })


def run_flask():
    """Lance le serveur Flask"""
    print("\n🌐 Démarrage du serveur Flask...")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)


def start_ngrok():
    """Démarre ngrok et affiche l'URL publique"""
    try:
        from pyngrok import ngrok
        
        print("\n🚀 Démarrage de ngrok...")
        
        # Fermer tous les tunnels existants
        ngrok.kill()
        
        # Créer un tunnel ngrok
        public_url = ngrok.connect(5000, bind_tls=True)
        public_url_str = str(public_url)
        
        print(f"\n{'='*60}")
        print(f"✅ NGROK URL PUBLIQUE: {public_url_str}")
        print(f"{'='*60}")
        print(f"\n📱 Utilisez cette URL dans votre Arduino:")
        print(f"   String serverURL = \"{public_url_str}\";")
        print(f"\n🔗 Endpoints disponibles:")
        print(f"   GET {public_url_str}/            - Test connexion")
        print(f"   GET {public_url_str}/recognize    - Reconnaître un visage")
        print(f"   GET {public_url_str}/status       - Statut du système")
        print(f"   GET {public_url_str}/users        - Liste des utilisateurs")
        print(f"\n🧪 Testez dans votre navigateur:")
        print(f"   {public_url_str}/")
        print(f"{'='*60}\n")
        
        return public_url_str
    except ImportError:
        print("\n⚠️  pyngrok n'est pas installé!")
        print("Installez-le avec: pip install pyngrok")
        print("\nServeur Flask accessible localement sur: http://localhost:5000")
        return None
    except Exception as e:
        print(f"\n❌ Erreur ngrok: {e}")
        print("Vérifiez que le port 5000 n'est pas déjà utilisé")
        return None


def main():
    print("=" * 60)
    print("   🎯 SYSTÈME DE RECONNAISSANCE FACIALE")
    print("   (Version OpenCV + Flask + Ngrok)")
    print("=" * 60)
    
    while True:
        print("\n" + "=" * 60)
        print("📋 MENU PRINCIPAL")
        print("=" * 60)
        print("[1] 📸 Enregistrer un nouveau visage")
        print("[2] 🤖 Entraîner le modèle")
        print("[3] 📊 Afficher les personnes enregistrées")
        print("[4] 🗑️  Supprimer un utilisateur")
        print("[5] 🌐 Démarrer le serveur API (Flask + Ngrok)")
        print("[6] 🧪 Tester la reconnaissance")
        print("[7] 🚪 Quitter")
        print("=" * 60)
        
        choice = input("\n➤ Votre choix (1-7): ").strip()
        
        if choice == "1":
            name = input("\n➤ Nom de la personne: ").strip()
            if name:
                num_samples = input("➤ Nombre d'échantillons (défaut: 30): ").strip()
                num_samples = int(num_samples) if num_samples.isdigit() else 30
                
                face_id = face_system.collect_training_data(name, num_samples)
                
                if face_id is not None:
                    print(f"\n✓ Visage de {name} collecté!")
                    train_now = input("➤ Entraîner maintenant? (o/n): ").strip().lower()
                    if train_now == 'o':
                        face_system.train_recognizer()
            else:
                print("❌ Nom invalide!")
        
        elif choice == "2":
            face_system.train_recognizer()
        
        elif choice == "3":
            face_system.list_users()
        
        elif choice == "4":
            users = face_system.list_users()
            if users:
                name = input("\n➤ Nom de la personne à supprimer: ").strip()
                if name:
                    confirm = input(f"⚠️  Confirmer la suppression de '{name}' ? (o/n): ").strip().lower()
                    if confirm == 'o':
                        if face_system.delete_user(name):
                            retrain = input("➤ Réentraîner le modèle maintenant? (o/n): ").strip().lower()
                            if retrain == 'o':
                                face_system.train_recognizer()
                    else:
                        print("❌ Suppression annulée")
                else:
                    print("❌ Nom invalide!")
        
        elif choice == "5":
            if not face_system.is_trained:
                print("\n⚠️  Le modèle n'est pas entraîné!")
                print("➤ Enregistrez au moins un visage et entraînez le modèle d'abord")
                continue
            
            print("\n🌐 Démarrage du serveur Flask + Ngrok...")
            
            # Démarrer ngrok
            ngrok_url = start_ngrok()
            
            if ngrok_url:
                print(f"\n✅ Serveur prêt!")
                print(f"🔗 URL à utiliser dans Arduino: {ngrok_url}")
                print(f"\n🧪 TESTEZ D'ABORD dans votre navigateur:")
                print(f"   1. Ouvrez: {ngrok_url}/")
                print(f"   2. Vous devriez voir: {{\"status\": \"online\"}}")
                print(f"   3. Ensuite testez: {ngrok_url}/recognize")
                print(f"\n▶️  Serveur en cours d'exécution...")
                print("   Appuyez sur Ctrl+C pour arrêter\n")
            
            try:
                run_flask()
            except KeyboardInterrupt:
                print("\n\n✓ Serveur arrêté")
                try:
                    from pyngrok import ngrok
                    ngrok.kill()
                except:
                    pass
        
        elif choice == "6":
            if not face_system.is_trained:
                print("\n⚠️  Le modèle n'est pas entraîné!")
                continue
            
            print("\n🧪 Test de reconnaissance...")
            result = face_system.recognize_from_camera_single()
            
            print("\n📊 Résultat:")
            print(f"  Reconnu: {result['recognized']}")
            print(f"  Nom: {result['name']}")
            print(f"  Confiance: {result.get('confidence', 0)}%")
            if 'error' in result:
                print(f"  Erreur: {result['error']}")
        
        elif choice == "7":
            print("\n👋 Au revoir!")
            break
        
        else:
            print("\n❌ Choix invalide!")


if __name__ == "__main__":
    main()