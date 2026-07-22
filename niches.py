# ------------------------------------------------------------------
# Types de vidéos virales proposés (formats > 1 minute, adaptés au
# storytelling long-format qui performe bien sur TikTok)
# ------------------------------------------------------------------

NICHES = [
    {
        "id": "storytelling",
        "titre": "Histoires vécues (storytime)",
        "description": "Récits personnels captivants racontés face caméra ou en voix off, avec un twist à la fin.",
        "duree_conseillee": "1 à 3 min",
    },
    {
        "id": "faits_divers",
        "titre": "Faits divers & mystères non résolus",
        "description": "Affaires intrigantes, disparitions ou énigmes présentées comme un mini-documentaire.",
        "duree_conseillee": "1 à 4 min",
    },
    {
        "id": "motivation",
        "titre": "Motivation & développement personnel",
        "description": "Discours inspirants, leçons de vie et conseils de productivité avec montage dynamique.",
        "duree_conseillee": "1 à 2 min",
    },
    {
        "id": "reddit_stories",
        "titre": "Histoires Reddit (AITA / confessions)",
        "description": "Lecture dramatisée de posts Reddit populaires avec voix off et sous-titres.",
        "duree_conseillee": "1 à 3 min",
    },
    {
        "id": "resume_films",
        "titre": "Résumés de films & séries",
        "description": "Synthèse d'une intrigue ou d'un twist marquant, sans spoiler la fin.",
        "duree_conseillee": "1 à 3 min",
    },
    {
        "id": "histoire_faits",
        "titre": "Faits historiques surprenants",
        "description": "Anecdotes historiques peu connues racontées de façon vivante et rythmée.",
        "duree_conseillee": "1 à 3 min",
    },
    {
        "id": "debats",
        "titre": "Débats & 'qui a raison ?'",
        "description": "Mise en scène d'un dilemme moral ou d'une situation controversée pour susciter les commentaires.",
        "duree_conseillee": "1 à 2 min",
    },
    {
        "id": "life_hacks",
        "titre": "Astuces & tutoriels pratiques",
        "description": "Tutoriels rapides sur un sujet précis (productivité, cuisine, bricolage...) avec démonstration.",
        "duree_conseillee": "1 à 2 min",
    },
]


def get_niche(niche_id: str):
    for n in NICHES:
        if n["id"] == niche_id:
            return n
    return NICHES[0]
