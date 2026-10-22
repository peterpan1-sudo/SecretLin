"""Liste des textes à traduire : arguments littéraux de t() et tn() dans le code, plus les
noms traduits à l'affichage (thèmes, couleurs, tailles, niveaux de force…)."""

import ast
from pathlib import Path

from gestionnaire import apparence

DOSSIER = Path(__file__).resolve().parent.parent / "gestionnaire"
NOMS_AFFICHES = [*apparence.THEMES, *apparence.ACCENTS, *apparence.TAILLES,
                 "Activées", "Désactivées", "Faible", "Moyen", "Fort", "Très fort"]


def cles() -> list[str]:
    trouvees = []
    for fichier in sorted(DOSSIER.glob("*.py")):
        for noeud in ast.walk(ast.parse(fichier.read_text(encoding="utf-8"))):
            if not isinstance(noeud, ast.Call):
                continue
            nom = getattr(noeud.func, "id", None) or getattr(noeud.func, "attr", None)
            n_textes = {"t": 1, "tn": 2}.get(nom, 0)
            for arg in noeud.args[:n_textes]:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    trouvees.append(arg.value)
    return list(dict.fromkeys(trouvees + NOMS_AFFICHES))
