"""
============================================================
  Orchestrateur multi-fournisseurs de génération vidéo
============================================================
Ce module regroupe plusieurs des générateurs vidéo IA les plus
reconnus du marché et choisit automatiquement le meilleur disponible,
avec bascule (fallback) en cascade si un fournisseur n'est pas
configuré ou échoue :

  1. HeyGen   -> avatar IA "présentateur" qui lit le script à voix
                 haute (voix + visage générés, le plus "clé en main")
  2. Runway   -> génération de clips vidéo cinématiques par IA à
                 partir du texte (gen4_turbo)
  3. Pexels + ElevenLabs -> solution de secours gratuite/économique :
                 banque de vidéos B-roll réelles + voix off IA,
                 assemblées avec MoviePy (montage + sous-titres)

⚠️ Chaque fournisseur nécessite sa propre clé API (voir README.md).
Si aucune clé n'est configurée, l'orchestrateur lève une erreur claire
expliquant quoi configurer plutôt que d'échouer silencieusement.
============================================================
"""

import os
import time
import tempfile
import requests

RUNWAY_API_KEY = os.environ.get("RUNWAYML_API_SECRET")
HEYGEN_API_KEY = os.environ.get("HEYGEN_API_KEY")
HEYGEN_AVATAR_ID = os.environ.get("HEYGEN_AVATAR_ID")
HEYGEN_VOICE_ID = os.environ.get("HEYGEN_VOICE_ID")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")


class ProviderUnavailable(Exception):
    """Levée quand un fournisseur n'est pas configuré ou a échoué."""
    pass


def _download_to_temp(url: str, suffix: str) -> str:
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    tmp_path = tempfile.mktemp(suffix=suffix)
    with open(tmp_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    return tmp_path


# ------------------------------------------------------------------
# 1. HeyGen — avatar IA complet (voix + visage inclus)
# ------------------------------------------------------------------
def generate_with_heygen(script_text: str, title: str) -> str:
    if not (HEYGEN_API_KEY and HEYGEN_AVATAR_ID):
        raise ProviderUnavailable("HeyGen non configuré (HEYGEN_API_KEY / HEYGEN_AVATAR_ID manquants).")

    resp = requests.post(
        "https://api.heygen.com/v3/videos",
        headers={"x-api-key": HEYGEN_API_KEY, "Content-Type": "application/json"},
        json={
            "type": "avatar",
            "avatar_id": HEYGEN_AVATAR_ID,
            "script": script_text,
            "voice_id": HEYGEN_VOICE_ID,
            "title": title,
            "resolution": "1080p",
            "aspect_ratio": "9:16",
        },
        timeout=30,
    )
    if resp.status_code >= 400:
        raise ProviderUnavailable(f"Erreur HeyGen ({resp.status_code}): {resp.text[:300]}")

    body = resp.json()
    video_id = (body.get("data") or {}).get("video_id") or body.get("video_id")
    if not video_id:
        raise ProviderUnavailable(f"Réponse HeyGen inattendue: {resp.text[:300]}")

    status_url = f"https://api.heygen.com/v1/video_status.get?video_id={video_id}"
    for _ in range(60):
        time.sleep(10)
        status_resp = requests.get(status_url, headers={"x-api-key": HEYGEN_API_KEY}, timeout=15)
        data = (status_resp.json() or {}).get("data", {})
        if data.get("status") == "completed":
            return _download_to_temp(data["video_url"], ".mp4")
        if data.get("status") == "failed":
            raise ProviderUnavailable(f"Échec du rendu HeyGen: {data.get('error')}")

    raise ProviderUnavailable("Timeout HeyGen : le rendu prend trop de temps.")


# ------------------------------------------------------------------
# 2. Runway — clips vidéo générés par IA à partir du texte
# ------------------------------------------------------------------
def generate_with_runway(prompt_text: str, duration: int = 5) -> str:
    if not RUNWAY_API_KEY:
        raise ProviderUnavailable("Runway non configuré (RUNWAYML_API_SECRET manquant).")
    try:
        from runwayml import RunwayML
    except ImportError:
        raise ProviderUnavailable("Le SDK officiel 'runwayml' n'est pas installé (pip install runwayml).")

    client = RunwayML(api_key=RUNWAY_API_KEY)
    task = client.text_to_video.create(
        model="gen4_turbo",
        prompt_text=prompt_text,
        ratio="768:1280",
        duration=duration,
    ).wait_for_task_output()

    video_url = task.output[0] if getattr(task, "output", None) else None
    if not video_url:
        raise ProviderUnavailable("Runway n'a retourné aucune vidéo exploitable.")
    return _download_to_temp(video_url, ".mp4")


# ------------------------------------------------------------------
# 3a. ElevenLabs — voix off professionnelle
# ------------------------------------------------------------------
def generate_voiceover_elevenlabs(text: str) -> str:
    if not ELEVENLABS_API_KEY:
        raise ProviderUnavailable("ElevenLabs non configuré (ELEVENLABS_API_KEY manquant).")
    from elevenlabs.client import ElevenLabs

    client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    audio_stream = client.text_to_speech.convert(
        voice_id=ELEVENLABS_VOICE_ID,
        model_id="eleven_multilingual_v2",
        text=text,
    )
    tmp_path = tempfile.mktemp(suffix=".mp3")
    with open(tmp_path, "wb") as f:
        for chunk in audio_stream:
            f.write(chunk)
    return tmp_path


# ------------------------------------------------------------------
# 3b. Pexels — banque de vidéos B-roll (solution de secours gratuite)
# ------------------------------------------------------------------
def fetch_broll_pexels(query: str, count: int = 3) -> list:
    if not PEXELS_API_KEY:
        raise ProviderUnavailable("Pexels non configuré (PEXELS_API_KEY manquant).")

    resp = requests.get(
        "https://api.pexels.com/videos/search",
        headers={"Authorization": PEXELS_API_KEY},
        params={"query": query, "per_page": count, "orientation": "portrait"},
        timeout=15,
    )
    if resp.status_code >= 400:
        raise ProviderUnavailable(f"Erreur Pexels ({resp.status_code}): {resp.text[:300]}")

    clips = []
    for video in resp.json().get("videos", []):
        files = sorted(video["video_files"], key=lambda f: f.get("width", 0))
        best = next((f for f in files if f.get("width", 0) >= 720), files[-1])
        clips.append(_download_to_temp(best["link"], ".mp4"))

    if not clips:
        raise ProviderUnavailable(f"Aucun B-roll Pexels trouvé pour '{query}'.")
    return clips


def assemble_video(video_clips: list, audio_path: str, script_data: dict) -> str:
    """Assemble des clips B-roll + une voix off + un titre incrusté avec MoviePy."""
    from moviepy.editor import (
        VideoFileClip, concatenate_videoclips, AudioFileClip,
        CompositeVideoClip, TextClip,
    )

    audio = AudioFileClip(audio_path)
    target_duration = audio.duration

    clips = [VideoFileClip(c).without_audio() for c in video_clips]
    sequence = concatenate_videoclips(clips, method="compose")

    loops_needed = int(target_duration // sequence.duration) + 1
    sequence = concatenate_videoclips([sequence] * loops_needed).subclip(0, target_duration)
    sequence = sequence.resize(height=1920).crop(x_center=sequence.w / 2, width=1080)

    subtitle = TextClip(
        script_data["title"], fontsize=48, color="white", font="Arial-Bold",
        stroke_color="black", stroke_width=2, size=(1000, None), method="caption",
    ).set_position(("center", 100)).set_duration(min(4, target_duration))

    final = CompositeVideoClip([sequence, subtitle]).set_audio(audio)

    output_path = tempfile.mktemp(suffix=".mp4")
    final.write_videofile(output_path, fps=30, codec="libx264", audio_codec="aac", logger=None)
    return output_path


# ------------------------------------------------------------------
# Orchestrateur principal
# ------------------------------------------------------------------
def generate_final_video(script_data: dict, niche: str, preferred_provider: str = "auto"):
    """
    Génère la vidéo finale (fichier .mp4 prêt à publier) en s'appuyant
    sur le meilleur fournisseur disponible, avec bascule automatique.

    Retourne un tuple (chemin_du_fichier_video, nom_du_fournisseur_utilisé).
    Lève ProviderUnavailable si aucun fournisseur n'est configuré/fonctionnel.
    """
    order = [preferred_provider] if preferred_provider != "auto" else ["heygen", "runway", "broll"]
    errors = []

    for provider in order:
        try:
            if provider == "heygen":
                path = generate_with_heygen(script_data["script"], script_data["title"])
                return path, "heygen"

            elif provider == "runway":
                prompt = f"{script_data.get('hook', '')} {script_data['script'][:400]}"
                path = generate_with_runway(prompt)
                return path, "runway"

            elif provider == "broll":
                clips = fetch_broll_pexels(niche, count=3)
                audio_path = generate_voiceover_elevenlabs(script_data["script"])
                path = assemble_video(clips, audio_path, script_data)
                return path, "broll+elevenlabs"

        except ProviderUnavailable as e:
            errors.append(f"{provider}: {e}")
            continue

    raise ProviderUnavailable(
        "Aucun générateur vidéo n'est disponible actuellement. Configure au moins "
        "une clé API (HeyGen, Runway, ou Pexels+ElevenLabs). Détails : " + " | ".join(errors)
    )
