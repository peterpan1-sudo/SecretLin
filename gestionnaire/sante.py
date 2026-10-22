"""Bilan de santé des mots de passe : faibles, réutilisés sur plusieurs comptes, pas
changés depuis longtemps, ou apparus dans des fuites de données (si la vérification en
ligne a été faite, voir fuites.py)."""

import datetime
from collections import Counter

from gestionnaire.coffre import evaluer_force

FORCE_MIN = 3  # « Fort » : en dessous, le mot de passe est signalé comme faible
AGE_MAX_JOURS = 365


def age_jours(entree: dict, aujourdhui: datetime.date | None = None) -> int | None:
    """Jours depuis le dernier changement du mot de passe ; None si la date est inconnue."""
    try:
        change = datetime.date.fromisoformat(entree["change_le"])
    except (KeyError, TypeError, ValueError):
        return None
    return ((aujourdhui or datetime.date.today()) - change).days


def bilan(entrees: list[dict], aujourdhui: datetime.date | None = None,
          fuites: dict[str, int] | None = None) -> dict:
    """Comptes à problème, par catégorie, et note globale de 0 à 100 (part des comptes
    sans aucun problème). « fuites » : mot de passe → nombre de fuites où il apparaît."""
    fuites = fuites or {}
    usages = Counter(e["mot_de_passe"] for e in entrees if e["mot_de_passe"])
    faibles = [e for e in entrees if evaluer_force(e["mot_de_passe"]) < FORCE_MIN]
    reutilises = [e for e in entrees if usages[e["mot_de_passe"]] > 1]
    anciens = [e for e in entrees if (age_jours(e, aujourdhui) or 0) > AGE_MAX_JOURS]
    pirates = [e for e in entrees if fuites.get(e["mot_de_passe"], 0) > 0]
    a_probleme = {e["id"] for e in faibles + reutilises + anciens + pirates}
    note = round(100 * (len(entrees) - len(a_probleme)) / len(entrees)) if entrees else 100
    return {"faibles": faibles, "reutilises": reutilises, "anciens": anciens,
            "pirates": pirates, "usages": usages, "note": note, "a_probleme": len(a_probleme)}
