"""
Cœur de l'IA de l'application : écrit le script de la vidéo (Claude),
puis délègue la génération de la vidéo finale à l'orchestrateur
multi-fournisseurs (video_providers.py).
"""

import os
import json
import anthropic

from niches import get_niche
import video_providers

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


def generate_video_script(niche_id: str) -> dict:
    """Génère un script de vidéo TikTok viral pour la niche donnée.

    Retourne un dict : {"title": ..., "hook": ..., "script": ...}
    """
    niche = get_niche(niche_id)

    prompt = f"""Tu es un scénariste spécialisé en vidéos TikTok virales.
Niche : {niche['titre']} — {niche['description']}
Durée cible : {niche['duree_conseillee']}

Écris le script complet d'une vidéo TikTok originale pour cette niche.
Réponds UNIQUEMENT en JSON valide, sans texte autour, avec ce format exact :
{{
  "title": "titre accrocheur de la vidéo (moins de 100 caractères)",
  "hook": "phrase d'accroche des 3 premières secondes",
  "script": "script complet, découpé en plans numérotés avec indications de voix off et de visuels"
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )

    raw_text = message.content[0].text.strip()
    raw_text = raw_text.replace("```json", "").replace("```", "").strip()

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        data = {"title": f"Vidéo {niche['titre']}", "hook": "", "script": raw_text}

    return data


def generate_complete_video(niche_id: str, preferred_provider: str = "auto") -> dict:
    """
    Pipeline complet : script (Claude) -> vidéo finale (meilleur
    fournisseur disponible parmi HeyGen / Runway / Pexels+ElevenLabs).

    Retourne un dict :
      {
        "title": ..., "hook": ..., "script": ...,
        "video_path": chemin local du fichier .mp4 généré,
        "provider_used": nom du fournisseur ayant produit la vidéo,
      }
    """
    script_data = generate_video_script(niche_id)
    video_path, provider_used = video_providers.generate_final_video(
        script_data, niche_id, preferred_provider
    )
    script_data["video_path"] = video_path
    script_data["provider_used"] = provider_used
    return script_data
