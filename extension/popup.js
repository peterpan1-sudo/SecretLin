// SecretLin — menu de l'extension (bouton de la barre d'outils) : état de SecretLin,
// comptes du site ouvert, et recherche pour remplir avec un autre compte.

const t = (cle, ...valeurs) => chrome.i18n.getMessage(cle, valeurs) || cle;
const envoyer = (message) => new Promise((resoudre) => {
  chrome.runtime.sendMessage(message, (r) => resoudre(chrome.runtime.lastError ? {} : r || {}));
});
const contenu = document.getElementById("contenu");
let onglet = null;
let comptesSite = [];

function vider() {
  contenu.replaceChildren();
}

function texte(valeur, classe = "texte") {
  const div = document.createElement("div");
  div.className = classe;
  div.textContent = valeur;
  contenu.append(div);
  return div;
}

function bouton(valeur, action) {
  const b = document.createElement("button");
  b.className = "bouton";
  b.textContent = valeur;
  b.addEventListener("click", action);
  contenu.append(b);
}

function liste(comptes) {
  const bloc = document.createElement("div");
  for (const c of comptes) {
    const b = document.createElement("button");
    b.className = "compte";
    const site = document.createElement("div");
    site.className = "site";
    site.textContent = c.site;
    const detail = document.createElement("div");
    detail.className = "detail";
    detail.textContent = c.utilisateur || c.email || "—";
    b.append(site, detail);
    b.addEventListener("click", () => choisir(c));
    bloc.append(b);
  }
  return bloc;
}

async function choisir(compte, message = "") {
  if (!comptesSite.some((c) => c.id === compte.id) && !message) {
    // Compte d'un autre site : on prévient avant de remplir (hameçonnage).
    if (!confirm(t("autreSite", compte.site))) {
      return;
    }
  }
  const reponse = await envoyer({ type: "remplirOnglet", id: compte.id, onglet: onglet.id });
  if (reponse.ok) {
    window.close();
  } else if (reponse.besoinPin) {
    demanderPin(compte, message);
  } else {
    afficherEtat();
  }
}

function demanderPin(compte, message = "") {
  vider();
  texte(t("codePin", compte.site));
  const saisie = document.createElement("input");
  saisie.type = "password";
  saisie.className = "pin";
  saisie.inputMode = "numeric";
  saisie.maxLength = 4;
  contenu.append(saisie);
  if (message) {
    texte(message, "texte erreur");
  }
  saisie.addEventListener("input", async () => {
    if (saisie.value.length < 4) {
      return;
    }
    const reponse = await envoyer({ type: "pin", pin: saisie.value });
    if (reponse.ok) {
      choisir(compte, "pin");
    } else if (reponse.verrouille) {
      vider();
      texte(t("tropErreurs"), "texte erreur");
    } else {
      demanderPin(compte, t("codeFaux", String(reponse.restants ?? 0)));
    }
  });
  saisie.focus();
}

async function afficherEtat() {
  vider();
  const etat = await envoyer({ type: "etat" });
  if (etat.erreur === "absent") {
    texte(t("pasLance"));
    return;
  }
  if (etat.etat !== "ouvert" && etat.etat !== "pin") {
    texte(t("verrouille"));
    bouton(t("ouvrir"), () => {
      envoyer({ type: "montrer" });
      window.close();
    });
    return;
  }
  const web = onglet && /^https?:/.test(onglet.url || "");
  comptesSite = web ? (await envoyer({ type: "comptes", adresse: onglet.url })).comptes || [] : [];
  texte(web ? t("pourCeSite") : t("pageSansConnexion"), "titre");
  if (comptesSite.length) {
    contenu.append(liste(comptesSite));
  } else if (web) {
    texte(t("aucun"));
  }
  if (!web) {
    return;
  }
  texte(t("rechercher"), "titre");
  const recherche = document.createElement("input");
  recherche.placeholder = t("rechercher");
  contenu.append(recherche);
  const resultats = document.createElement("div");
  contenu.append(resultats);
  recherche.addEventListener("input", async () => {
    const texteCherche = recherche.value.trim();
    const comptes = texteCherche
      ? (await envoyer({ type: "chercher", texte: texteCherche })).comptes || []
      : [];
    resultats.replaceChildren(liste(comptes.slice(0, 6)));
  });
}

chrome.tabs.query({ active: true, currentWindow: true }, (onglets) => {
  onglet = onglets[0] || null;
  afficherEtat();
});
