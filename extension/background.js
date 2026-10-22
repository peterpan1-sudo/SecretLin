// SecretLin — partie de l'extension qui parle à l'application (native messaging).
//
// Règles de sécurité :
// - une page web ne parle jamais à SecretLin : seul ce script le fait, à la demande du
//   script de page (content.js) ou du menu de l'extension (popup) ;
// - pour une page, l'adresse utilisée est celle que donne le navigateur (sender.tab.url),
//   jamais une adresse fournie par la page ;
// - une page ne reçoit que les identifiants d'un compte associé à son propre site ;
// - le jeton obtenu avec le code PIN reste dans la mémoire de session de l'extension.

const HOTE = "fr.secretlin.navigateur";
const DUREE_JETON_MS = 110 * 1000;  // un peu moins que les 2 minutes de SecretLin

function natif(message) {
  return new Promise((resoudre) => {
    try {
      chrome.runtime.sendNativeMessage(HOTE, message, (reponse) => {
        if (chrome.runtime.lastError || !reponse) {
          resoudre({ erreur: "absent" });
        } else {
          resoudre(reponse);
        }
      });
    } catch (e) {
      resoudre({ erreur: "absent" });
    }
  });
}

async function lireJeton() {
  const { jeton, fin } = await chrome.storage.session.get(["jeton", "fin"]);
  return jeton && fin > Date.now() ? jeton : null;
}

async function garderJeton(jeton) {
  if (jeton) {
    await chrome.storage.session.set({ jeton, fin: Date.now() + DUREE_JETON_MS });
  }
}

async function oublierJeton() {
  await chrome.storage.session.remove(["jeton", "fin"]);
}

function adresseWeb(adresse) {
  return typeof adresse === "string" && /^https?:\/\//.test(adresse);
}

async function identifiants(id) {
  const reponse = await natif({ action: "identifiants", id, jeton: await lireJeton() });
  if (reponse.erreur === "pin") {
    await oublierJeton();
    return { besoinPin: true };
  }
  return reponse;
}

async function traiter(message, expediteur) {
  const depuisPage = Boolean(expediteur.tab);
  switch (message.type) {
    case "etat":
      return natif({ action: "etat" });
    case "montrer":
      return natif({ action: "montrer" });
    case "pin": {
      const reponse = await natif({ action: "pin", pin: String(message.pin || "") });
      if (reponse.ok) {
        await garderJeton(reponse.jeton);
      }
      return reponse;
    }
    case "comptes": {
      const adresse = depuisPage ? expediteur.tab.url : message.adresse;
      if (!adresseWeb(adresse)) {
        return { comptes: [] };
      }
      return natif({ action: "chercher", adresse });
    }
    case "chercher":
      if (depuisPage) {
        return { erreur: "refusé" };
      }
      return natif({ action: "chercher", texte: String(message.texte || "") });
    case "remplir": {
      // Depuis une page : le compte doit être associé au site de cette page.
      if (!depuisPage || !adresseWeb(expediteur.tab.url)) {
        return { erreur: "refusé" };
      }
      const liste = await natif({ action: "chercher", adresse: expediteur.tab.url });
      if (!(liste.comptes || []).some((c) => c.id === message.id)) {
        return { erreur: "refusé" };
      }
      return identifiants(message.id);
    }
    case "remplirOnglet": {
      // Depuis le menu de l'extension : l'utilisateur a choisi le compte lui-même.
      if (depuisPage) {
        return { erreur: "refusé" };
      }
      const reponse = await identifiants(message.id);
      if (reponse.ok) {
        await chrome.tabs.sendMessage(message.onglet, {
          type: "remplir",
          utilisateur: reponse.utilisateur || reponse.email,
          motDePasse: reponse.mot_de_passe,
        });
        return { ok: true };
      }
      return reponse;
    }
    default:
      return { erreur: "inconnu" };
  }
}

chrome.runtime.onMessage.addListener((message, expediteur, repondre) => {
  if (expediteur.id !== chrome.runtime.id) {
    return false;
  }
  traiter(message, expediteur).then(repondre, () => repondre({ erreur: "absent" }));
  return true;  // réponse envoyée plus tard
});
