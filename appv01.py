import time
import os

import json
import sqlite3
import sys
import io
import numpy as np
import requests

import librosa

from scipy.signal import spectrogram
from pydub import AudioSegment


# Configurations

YOUTUBE_API_KEY = "AIzaSyBsW5rmxbbQyqbMwS3_ncgLJw55arzxszY"
DISCOGS_TOKEN = "hPhhxRSsnysfQlaTIqTehWemjZMrbvgqbxBLofPf"
ACRCLOUD_ACCESS_KEY = "3abbc8780d156ad396dd5cc797d6265"
ACRCLOUD_ACCESS_SECRET = "dENc4902TobyOMxLyyRFTZOglNc4rFZE6362cTR"
ACRCLOUD_HOST = "identify-eu-west-1.acrcloud.com"


# Ajout de messages de débogage pour ACRCloud

print(" ")
print(" ")
print("Tentative d'importation d'ACRCloud...")
try:
    from acrcloud.recognizer import ACRCloudRecognizer
    print("...ACRCloud importé avec succès.")
except ImportError as e:
    print(f"Erreur lors de l'importation d'ACRCloud: {e}")
    print("Vérifiez que ACRCloud est installé correctement.")
    print("Vous pouvez l'installer avec: pip install git+https://github.com/acrcloud/acrcloud_sdk_python")
    ACRCloudRecognizer = None


# Initialisation d'ACRCloud avec débogage

if ACRCloudRecognizer:
    print("Configuration d'ACRCloud...")
    acrcloud_config = {
        'host': ACRCLOUD_HOST,
        'access_key': ACRCLOUD_ACCESS_KEY,
        'access_secret': ACRCLOUD_ACCESS_SECRET,
        'timeout': 10
    }
    try:
        acrcloud_recognizer = ACRCloudRecognizer(acrcloud_config)
        print("...ACRCloud configuré avec succès.")
    except Exception as e:
        print(f"Erreur lors de la configuration d'ACRCloud: {e}")
        acrcloud_recognizer = None
else:
    print("ACRCloud n'est pas disponible. La reconnaissance audio sera limitée.")
    acrcloud_recognizer = None

# Le reste du code reste inchangé...




#   ----------    identify_track

def identify_track(audio_path):
    if acrcloud_recognizer:
        print(" ")
        print(f" --- Tentative d'identification de la piste avec ACRCloud: {audio_path}")
        try:
            result = acrcloud_recognizer.recognize_by_file(audio_path, 0)
            print(f" --- Résultat ACRCloud: {result}")
            if result and 'metadata' in result:
                metadata = result['metadata']
                if 'music' in metadata and metadata['music']:
                    music_info = metadata['music'][0]
                    return (music_info.get('title', ''), 
                            music_info.get('artists', [{}])[0].get('name', ''),
                            music_info.get('album', {}).get('name', ''),
                            music_info.get('genre', [''])[0])
        except Exception as e:
            print(f"Erreur lors de l'identification avec ACRCloud: {e}")
    else:
        print("ACRCloud n'est pas disponible. Utilisation de la méthode de secours.")
    
    return fallback_identify_track(audio_path)

def fallback_identify_track(audio_path):
    print(" --- Utilisation de la méthode de secours pour l'identification.")
    fingerprint = create_audio_fingerprint(audio_path)
    if not fingerprint:
        print("Impossible de créer l'empreinte audio.")
        return None
    
    fingerprint_data = json.loads(fingerprint)
    
    # Recherche dans la base de données
    cursor.execute("""
    SELECT title, artist, album, genre
    FROM tracks
    WHERE json_extract(audio_fingerprint, '$.tempo') BETWEEN ? AND ?
    """, (fingerprint_data['tempo'] - 5, fingerprint_data['tempo'] + 5))
    
    potential_matches = cursor.fetchall()
    print(f"Nombre de correspondances potentielles trouvées : {len(potential_matches)}")
    
    if not potential_matches:
        print("Aucune correspondance potentielle trouvée dans la base de données.")
        return None

    # Comparaison plus détaillée des empreintes
    best_match = None
    best_score = float('inf')
    for match in potential_matches:
        stored_fingerprint = json.loads(match[5])  # Supposons que audio_fingerprint est à l'index 5
        score = np.linalg.norm(np.array(fingerprint_data['spectrogram_mean']) - np.array(stored_fingerprint['spectrogram_mean']))
        score += np.linalg.norm(np.array(fingerprint_data['mfccs_mean']) - np.array(stored_fingerprint['mfccs_mean']))
        score += np.linalg.norm(np.array(fingerprint_data['chroma_mean']) - np.array(stored_fingerprint['chroma_mean']))
        if score < best_score:
            best_score = score
            best_match = match
    
    if best_match and best_score < 1500:
        print(f"Meilleure correspondance trouvée avec un score de {best_score}")
        return best_match
    else:
        print(f"Aucune correspondance suffisamment proche trouvée. Meilleur score : {best_score}")
        return None

#   ----------    fin du identify_track
#   ---------------------------------------




# Gestion des importations conditionnelles
try:
    from scipy.signal import spectrogram
except ImportError:
    print("Module scipy non trouvé. Certaines fonctionnalités audio seront limitées.")
    spectrogram = None

try:
    from googleapiclient.discovery import build
except ImportError:
    print("Module google-api-python-client non trouvé. Les fonctionnalités YouTube seront désactivées.")
    build = None

try:
    import librosa
except ImportError:
    print("Module librosa non trouvé. Certaines fonctionnalités audio seront limitées.")
    librosa = None

try:
    import discogs_client
except ImportError:
    print("Module discogs_client non trouvé. Les fonctionnalités Discogs seront désactivées.")
    discogs_client = None

try:
    import youtube_dl
except ImportError:
    print("Module youtube_dl non trouvé. Le téléchargement audio sera désactivé.")
    youtube_dl = None

try:
    from pydub import AudioSegment
except ImportError:
    print("Module pydub non trouvé. Certaines fonctionnalités audio seront limitées.")
    AudioSegment = None


# Genres ciblés
TARGET_GENRES = ['Minimal', 'Jungle', 'Drum and Bass', 'Breakbeat', 'IDM', 'Techno', 'House', 'Dubstep']

# Initialisation des clients
youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY) if build else None

if discogs_client:
    discogs = discogs_client.Client('YourApp/0.1', user_token=DISCOGS_TOKEN)
else:
    discogs = None



# Connexion à la base de données
conn = sqlite3.connect('electronic_music_database.db')
cursor = conn.cursor()

def setup_database():
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tracks
    (id INTEGER PRIMARY KEY, youtube_id TEXT, title TEXT, artist TEXT, 
    album TEXT, year INTEGER, genre TEXT, discogs_id TEXT, 
    isrc TEXT, label TEXT, duration_ms INTEGER, 
    audio_fingerprint TEXT, youtube_audio_path TEXT, source TEXT)
    ''')
    conn.commit()

def search_youtube_tracks(query, max_results=25):
    if not youtube:
        print("Recherche YouTube non disponible.")
        return []
    full_query = f"{query} {' '.join(TARGET_GENRES)}"
    request = youtube.search().list(
        q=full_query,
        type='video',
        videoCategoryId='10',
        part='id,snippet',
        maxResults=max_results
    )
    return request.execute().get('items', [])

def get_youtube_audio_url(video_id):
    return f"https://youtube.com/watch?v={video_id}"








def create_audio_fingerprint(audio_path):
    if not librosa:
        print("La création d'empreintes digitales n'est pas disponible (librosa manquant).")
        return None

    try:
        print(f" --- Chargement du fichier audio : {audio_path}")
        y, sr = librosa.load(audio_path, duration=30)  # Charge les 30 premières secondes
        print(f" --- Fichier audio chargé. Durée : {librosa.get_duration(y=y, sr=sr)} secondes")

        # Analyse de fréquence
        if spectrogram:
            f, t, Sxx = spectrogram(y, fs=sr, nperseg=1024, noverlap=512)
            bass_energy = np.sum(Sxx[f < 250])
            mid_energy = np.sum(Sxx[(f >= 250) & (f < 2000)])
            high_energy = np.sum(Sxx[f >= 2000])
        else:
            bass_energy = mid_energy = high_energy = 0
        
        # Détection de beats
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        
        # Caractéristiques spécifiques
        mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        chroma = librosa.feature.chroma_stft(y=y, sr=sr)
        
        fingerprint = {
            'spectrogram_mean': np.mean(Sxx, axis=1).tolist() if spectrogram else [],
            'bass_energy': float(bass_energy),
            'mid_energy': float(mid_energy),
            'high_energy': float(high_energy),
            'tempo': float(tempo[0]) if isinstance(tempo, np.ndarray) else float(tempo),
            'mfccs_mean': np.mean(mfccs, axis=1).tolist(),
            'chroma_mean': np.mean(chroma, axis=1).tolist()
        }
        
        print(" --- Empreinte audio créée avec succès.")
        print(" ")
        print(fingerprint)
        print(" ")
        return json.dumps(fingerprint)
    except Exception as e:
        print(f"Erreur lors de la création de l'empreinte audio: {e}")
        return None








def filter_target_releases(releases):
    return [release for release in releases if any(genre in TARGET_GENRES for genre in release.genres)]

def search_discogs(query):
    if not discogs:
        print("La recherche Discogs n'est pas disponible.")
        return []
    results = discogs.search(query, type='release')
    return filter_target_releases(results)

def add_track_to_database(youtube_id, title, artist, discogs_info, audio_fingerprint, audio_path, source):
    cursor.execute('''
    INSERT INTO tracks (youtube_id, title, artist, album, year, genre, discogs_id, 
    isrc, label, duration_ms, audio_fingerprint, youtube_audio_path, source)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        youtube_id,
        title,
        artist,
        discogs_info.get('album', ''),
        discogs_info.get('year', ''),
        ', '.join(discogs_info.get('genre', [])),
        str(discogs_info.get('id', '')),
        discogs_info.get('isrc', ''),
        discogs_info.get('label', ''),
        discogs_info.get('duration_ms', 0),
        audio_fingerprint,
        audio_path,
        source
    ))
    conn.commit()

def process_youtube_tracks(query):
    tracks = search_youtube_tracks(query)
    for track in tracks:
        video_id = track['id']['videoId']
        title = track['snippet']['title']
        
        print(f"Traitement de : {title}")
        
        audio_url = get_youtube_audio_url(video_id)
        audio_fingerprint = create_audio_fingerprint(audio_url)
        
        audio_path = f"youtube_audio/{video_id}.mp3"
        if youtube_dl:
            os.makedirs(os.path.dirname(audio_path), exist_ok=True)
            download_youtube_audio(video_id, audio_path)
        
        discogs_info = {}
        if discogs:
            discogs_results = search_discogs(title)
            if discogs_results:
                release = discogs_results[0]
                discogs_info = {
                    'album': release.title,
                    'year': release.year,
                    'genre': release.genres,
                    'id': release.id,
                    'label': release.labels[0].name if release.labels else '',
                    'isrc': release.identifiers.get('isrc', [''])[0] if release.identifiers else ''
                }
        
        artist = track['snippet']['channelTitle']
        
        add_track_to_database(video_id, title, artist, discogs_info, audio_fingerprint, audio_path, 'YouTube')
        
        print(f"Ajouté à la base de données : {title}")

def download_youtube_audio(video_id, output_path):
    if not youtube_dl:
        print("Le téléchargement audio n'est pas disponible.")
        return

    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': output_path
    }
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        ydl.download([f'https://www.youtube.com/watch?v={video_id}'])

def get_database_stats():
    cursor.execute("SELECT COUNT(*) FROM tracks")
    total_tracks = cursor.fetchone()[0]
    print(f"Nombre total de pistes dans la base de données : {total_tracks}")
    cursor.execute("SELECT genre, COUNT(*) FROM tracks GROUP BY genre")
    genre_stats = cursor.fetchall()
    print("Répartition par genre :")
    for genre, count in genre_stats:
        print(f"- {genre}: {count}")

def list_stored_tracks(limit=10):
    cursor.execute("SELECT title, artist, genre, source FROM tracks LIMIT ?", (limit,))
    tracks = cursor.fetchall()
    print(f"Pistes stockées (limité à {limit}):")
    print(" ")
    for track in tracks:
        print(f"- {track[0]} par {track[1]} (Genre: {track[2]}, Source: {track[3]})")


# Fonction pour effacer l'écran

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

# Fonction pour l'initialisation avec un effet de chargement

def initialization():
    print(" ")
    for i in range(1, 4):
        print(".." * (i))
        time.sleep(0.2)
    print(" ")
    print("Initialisation du programme...")
    print(" ")
    for i in range(1, 4):
        print(".." * (4-i))
        time.sleep(0.2)
    time.sleep(0.2)


# Fonction pour afficher le menu

def display_menu():
    print(" ")
    print("╔═════════════════════════════════════════════════════════════╗")
    print("║                        Welcome Bruh                         ║")
    print("╠═════════════════════════════════════════════════════════════╣")
    print("║                   ♫   BRAIN NEW SHHH   ♫                    ║")
    print("╠═════════════════════════════════════════════════════════════╣")
    print("║             by  Quentin Dente  &  Loan Nguema               ║")
    print("╠═════════════════════════════════════════════════════════════╣")
    print("║ 1. Rechercher et ajouter des pistes (Minimal, Jungle, etc.) ║")
    print("║ 2. Identifier une piste audio                               ║")
    print("║ 3. Afficher les statistiques de la base de données          ║")
    print("║ 4. Lister les pistes stockées                               ║")
    print("║ 5. Quitter                                                  ║")
    print("╚═════════════════════════════════════════════════════════════╝")



def main():
    initialization()
    setup_database()

    
    while True:
        display_menu()
        choice = input("\n            Choix : ")
        print("---------------------------------")
        print(" ")

        if choice == '1':
            if youtube:
                query = input("Entrez votre requête de recherche (ex: 'minimal techno', 'jungle breaks'): ")
                process_youtube_tracks(query)
            else:
                print("La recherche YouTube n'est pas disponible.")



 

        #elif choice == '2':
        #    if librosa and AudioSegment:
        #        audio_path = input("Entrez le chemin du fichier audio à identifier: ")
        #        result = identify_track(audio_path)
        #        if result:
        #            print(f"Piste identifiée : {result[0]} par {result[1]} (Genre: {result[3]})")
        #        else:
        #            print("Piste non identifiée")
        #    else:
        #        print("L'identification de pistes n'est pas disponible.")





        elif choice == '2':
            audio_path = input("Entrez le chemin du fichier audio à identifier: ")
            result = identify_track(audio_path)
            if result:
                print(f"Piste identifiée : {result[0]} par {result[1]} (Album: {result[2]}, Genre: {result[3]})")
            else:
                print("Piste non identifiée")





        elif choice == '3':
            get_database_stats()
        elif choice == '4':
            limit = int(input("Combien de pistes voulez-vous lister ? "))
            print(" ")
            list_stored_tracks(limit)
        elif choice == '5':
            for i in range(1, 4):
                print(".." * (i))
                time.sleep(0.2)
            print(" ")
            print("Fermeture du programme...")
            print(" ")
            for i in range(1, 4):
                print(".." * (4-i))
                time.sleep(0.2)
            time.sleep(0.2)
            print(" ")
            break
        else:
            print("Option invalide. Veuillez réessayer.")

if __name__ == "__main__":
    main()
    conn.close()
    