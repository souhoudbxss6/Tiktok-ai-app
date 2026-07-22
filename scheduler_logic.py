"""
Calcule les prochains créneaux horaires optimaux pour publier sur TikTok.

Les heures ci-dessous sont des heures générales, souvent recommandées
par les études d'engagement TikTok (pics le matin avant le travail/
les cours, à la pause déjeuner, et en soirée). Ce ne sont PAS des
données en temps réel : pour un ciblage précis, il est recommandé de
croiser ces créneaux avec les statistiques d'audience réelles du
compte (disponibles dans TikTok Analytics une fois que le compte a
du volume de publication).
"""

from datetime import datetime, timedelta
import pytz

# Heures de forte audience (heure locale de l'audience), à ajuster
# selon les retours d'analytics une fois le compte actif.
PEAK_HOURS = [7, 12, 19, 22]


def get_next_optimal_slots(timezone_name: str = "Europe/Paris", count: int = 1):
    """
    Retourne une liste de `count` prochains créneaux (datetime en UTC)
    correspondant aux heures de forte audience, en partant de maintenant.
    """
    tz = pytz.timezone(timezone_name or "Europe/Paris")
    now_local = datetime.now(tz)

    candidate_slots = []
    day_offset = 0
    while len(candidate_slots) < count:
        base_day = now_local + timedelta(days=day_offset)
        for hour in PEAK_HOURS:
            slot = tz.localize(
                datetime(base_day.year, base_day.month, base_day.day, hour, 0, 0)
            ) if base_day.tzinfo is None else base_day.replace(
                hour=hour, minute=0, second=0, microsecond=0
            )
            if slot > now_local:
                candidate_slots.append(slot)
        day_offset += 1
        if day_offset > 7:
            break

    candidate_slots.sort()
    return [slot.astimezone(pytz.utc) for slot in candidate_slots[:count]]
