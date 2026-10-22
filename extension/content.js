// SecretLin — script ajouté aux pages web : repère les champs de connexion et propose,
// sous le champ, les comptes SecretLin de ce site. Les identifiants ne sont remplis
// qu'après un clic (et le code PIN si SecretLin le demande).

(() => {
  if (window.top !== window || window.__secretlin) {
    return;
  }
  window.__secretlin = true;

  // Icône intégrée au script : une image de l'extension chargée par la page permettrait
  // aux sites de savoir que SecretLin est installé.
  const ICONE = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAIvElEQVR42pWXa4xdVRXHf2ufc+69c2funduZTh+0nZk+gQbk0YKFQrFAA5SSGhCIr6ho9IOaGEz8zAf95gdjQtQoYogGJNrQAAWspRQs5VECaEvpi7aUvuY9nZn7OOfsvfywz70zLZjITvbd9969z16v//qvdYTPGJs3P7hoYOz8qrhanT/9r+HzDQeAqkhbPj9UKlXeeemlp4+q6gWnZOaPjRvv7Ts3MPjwxOTUfUmSzFZ1eZCLTn2Oof5DRJIwDEfbi+1bu7t6frljxzOHPqXAjTduuHp4dOTJeq16mXVuxu5F0uV/a6POgVq/oiCCIK3VBAGFQtvHPd0939u9+x/bW7dv2nR/7+EjR1+cmpq8vCVULtJRDIICgqqiKILgXArqMCYi116h0NFNvjgLCQLUJjSq46T1SRq1MWxcQxXa2trOLlqw8M6dO59/X1RVrll186+Hh4d+5JxFZloogmIyK0Ay4blihSAqkDSmKPcsYe6SNXT3XkVHdy+F0hzEGOLaGPWJs0wMnWBq5DSTIyc5e/AV6hNDiDF0VmZtXbvmoftl8+YHF+374MCbtVp1vojMcHHTdcZbrN6lNo3pWXwd1937c2zaoFieR5TvwDnL5PBxzhzcxeDxvUycO0xcGyeNq6iziBFETAZMRz7fNtHfu2x9eG5oZHWaxLNBm5jJ3C2gghOlUOohV5yFswndvdewZNVXMLkKEgnVao2xQ3s4tf9FBo/vJa6NgSrG+DvEhIgJUBRV1xSATZOO85Mja8O41pjvVCOvGTNCICAms9xwxYaHKfUsRUyEdUoprDK3lHL60Gvs2/MkH588SS6XJ4zaM0HWr+oQzS5vygCcc5IkyYLQiWSQujB9nDqcpoBQ6llB1NaFtaBJnRuWxly7sE4hUuylV/HlW5azddt2/vbMNlwGTjTDjIDispQUvKc9hBXREKxXS7MUU1AxlOeuoNSzlOKsXhZesZEgzBHHCWuXpaxbHlOPlX0HT+CsZUn/Qr563z0kseXvz75IFAT+ulZMvRdx1iuhimaJFmZUkUXGfwdI4inmXX4HlflXYJMpktQSNM6wqrcTpyF/+PMWtm57BQTu3nAT33pgE3duWMeuPXsZHRnFiKCmSYhNHxsfGkCykBha7skcIYK1CUhIVOgirp3HOcPAx//h/KEtdHbkOTc0xvZde8FEIBE7d7/L4PAolXIH8+fNw6qgEgCBxxHi+UNaUGitphX0LATGRJR6VrDsph9iog6sg9EzH3Jg12+wSQ0xAWEQkM+3ISZCTEQu10YYhoBgghAkBOOF+xm0CAwTgRpvs2uFINNIha7Fa+m79htEbZ3YNCapT3D0zSeI61P+4YxiHQaX6e9ahUpxKl6gKEjgAYgXKGEHQXsf6ch7PkQXlzjnLKOfvEuaNLBpQpokfPT2X5gaO40lJJfPYa3n+nK5g0pnmUpnmc5yKROutBUKpA5UTXa9tDwczb0ZWz/XrFLTIPT7iksbdPfdRJCvYK1j6NhuRk69hwRtfH3z7Wy+6xaq1RqFfMQvfvZtmqVVRCi25THG8JMfPMiVK5fyxFPP+jRWQZ0luuQuXDKOq572HtGm76ynRiSgZ/kd9Cy/A5sk1CYGOf3B86QWLl/RzzcfuItyqUiSeIIpl4p0Vcp0VcqUS8XMg472Yhv333MrN6y+kjiOUXVECzYh7YtIBl4DCbOQ+7zwGMjYLmrvgbCItY6Bwy8T10ZwGjG3pwsQGo0YXy6EoaEhHnv8jwB89zsPUS53oqqkqcUY4ZK5FZxG5HrvQ/Jd1A/9NvOYZLR8QRYIaWOC2vhpnBVqEwOMnnwLkQBUsWmCtSnOWay1BEHItue2sPP4QnYeX8i257YQBCHWWn8mTbCmQtT3NUx+No2jj6PJmBfXJL0s9Fl5coBQKPeiDs6f/TdxbThjLe9ym3rh1lriOKGvfxky+Coy+Cp9/cuI46S1b5MEiv3gGtSP/QnXGPaZoc57QV2rZTOOZh0Ugvws0rTOxMB+T5fZA845rJ2ejUaN1dffyMoFIf1dMatWr6HRqE2fUbATh2ic+CuuMepB55y/Dzd9L24aA8241CeHqY0cyYjDW69u2vomi4Wh4+prr2dycgKANHWtVsLagLQ2iKZVNAgzy5t3qTcui0PYbBBwDuegPv4JSX0MExTA+Zx31mKdB1hz1Ot1Vq36InHcoF5vtJQDr5w6RdWCmzaE1pyuvaEXoigOm8ak9THUJaiJQIVAhMNHjzI2Nkq5owPrPBOqwtw5czwrOocxHk7GGCanptj3wQGMKOpS1E0roGpBXYYAR6iKoOobyMlB1FbBpaim4MCYgJOfnOBXv3uaDbfdSi4EtTXUxZ/qwQXBWsvO1/7F/gMfks/lMgVS782m9eq7BmuRMCoUhxBSVRfWx44Qts3JQmJRVcQoxXm3cnB0Afseewk3dQSNRzMUy3Q++WKCqlc6XyhkIUgzq23LetRhJCAIwjPhnO4575w+dWys0ZDZ9fEj5CXyqeJSQInm3I4pXYYM7CCoHiXAQj7vq9xnKCDqfIic9Uq2FJh2vzpHLleoVboqe80LLzx1rKO9/IwxIWltgPrw+54qbYOgtBKCDuof/R43vg/BIhJgxGCET83We4xaVBPUJh6Azk+yVASlvVh85fYvPfSWAKxbd/fyw0f2vzw5cX6hGN+MikSE3WtJx94GTRATeSYTme6aZ3hA0RbCfQ/oBZLlfnPPOUd7R8d435IVd761+59vBAAnThweuXTlF/Y16vXb4iQuqXpLXf0MahsZJzRbajeDpOyMFLOt2bT2QuGZ5e2lkcX9S3785p6XX8D3TH6cOXXio+tWr92RWDvfWrtQXZpDU0Satoo3vtlgicu+K4JDNFszPAgOEb9vjJDLF6qVzq7ti/uXfP/1173wz3jzhKef1uDRRzdeMzw2vCaJ7QJQ8RXDNxjm/3opz7jeAYiGoZyb3TVv7yOP/PSN9evXpzPP/xfGlV37xGuWwQAAAABJRU5ErkJggg==";
  const t = (cle, ...valeurs) => chrome.i18n.getMessage(cle, valeurs) || cle;
  const envoyer = (message) => new Promise((resoudre) => {
    try {
      chrome.runtime.sendMessage(message, (r) => resoudre(chrome.runtime.lastError ? {} : r || {}));
    } catch (e) {
      resoudre({});
    }
  });

  // --- Champs de connexion ---------------------------------------------------------

  const visible = (champ) => {
    const r = champ.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(champ).visibility !== "hidden";
  };

  function champsMotDePasse() {
    return [...document.querySelectorAll("input[type=password]")].filter(visible);
  }

  function champIdentifiant(motDePasse) {
    const portee = motDePasse.form || document;
    const candidats = [...portee.querySelectorAll(
      "input[type=email], input[type=text], input[type=tel], input:not([type])")]
      .filter((c) => visible(c) && !c.readOnly && !c.disabled);
    const avant = candidats.filter(
      (c) => c.compareDocumentPosition(motDePasse) & Node.DOCUMENT_POSITION_FOLLOWING);
    return avant[avant.length - 1] || null;
  }

  function champsConnexion(cible) {
    const mdps = champsMotDePasse();
    if (cible && cible.type === "password") {
      return { identifiant: champIdentifiant(cible), motDePasse: cible };
    }
    for (const mdp of mdps) {
      const identifiant = champIdentifiant(mdp);
      if (!cible || identifiant === cible) {
        return { identifiant, motDePasse: mdp };
      }
    }
    // Page en deux temps (identifiant d'abord, mot de passe ensuite) : champ seul.
    if (cible && /user|login|email|mail|identifi|account/i.test(
      `${cible.name} ${cible.id} ${cible.autocomplete} ${cible.type}`)) {
      return { identifiant: cible, motDePasse: null };
    }
    return null;
  }

  function ecrire(champ, valeur) {
    if (!champ || !valeur) {
      return;
    }
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
    champ.focus();
    setter.call(champ, valeur);
    champ.dispatchEvent(new Event("input", { bubbles: true }));
    champ.dispatchEvent(new Event("change", { bubbles: true }));
  }

  let rempliLe = 0;

  function remplir(champs, utilisateur, motDePasse) {
    rempliLe = Date.now();  // les champs reçoivent le focus : pas de menu juste après
    ecrire(champs.identifiant, utilisateur);
    ecrire(champs.motDePasse, motDePasse);
  }

  // --- Menu sous le champ (Shadow DOM : la page ne peut pas le lire ni le styliser) ---

  let hote = null;
  let racine = null;
  let champsActifs = null;

  const STYLE = `
    :host { all: initial; }
    .boite { position: fixed; z-index: 2147483647; min-width: 260px; max-width: 360px;
      background: #141417; color: #ececef; border: 1px solid #2a2a30; border-radius: 12px;
      box-shadow: 0 12px 32px rgba(0,0,0,.45); font: 13px/1.4 system-ui, sans-serif;
      padding: 6px; }
    .entete { display: flex; align-items: center; gap: 6px; padding: 6px 8px; color: #8e8e98;
      font-size: 11px; font-weight: 600; letter-spacing: .02em; }
    .entete img { width: 14px; height: 14px; }
    .compte { display: block; width: 100%; text-align: left; border: 0; background: none;
      color: inherit; padding: 8px 10px; border-radius: 8px; cursor: pointer; font: inherit; }
    .compte:hover, .compte:focus { background: #26262b; outline: none; }
    .site { font-weight: 600; }
    .detail { color: #8e8e98; font-size: 12px; }
    .texte { padding: 6px 10px 8px; color: #8e8e98; }
    .erreur { color: #e5484d; }
    input { width: 100%; box-sizing: border-box; margin: 4px 0 6px; padding: 8px; font: 18px
      monospace; letter-spacing: .5em; text-align: center; background: #0b0b0d; color: #ececef;
      border: 1px solid #2a2a30; border-radius: 8px; }
    .bouton { border: 0; background: #e4e4e7; color: #0b0b0d; font: 600 12px system-ui;
      padding: 7px 12px; border-radius: 8px; cursor: pointer; margin: 0 10px 8px; }
  `;

  function fermer() {
    if (hote) {
      hote.remove();
    }
    hote = racine = null;
  }

  function ouvrir(champ) {
    fermer();
    hote = document.createElement("secretlin-menu");
    racine = hote.attachShadow({ mode: "closed" });
    const style = document.createElement("style");
    style.textContent = STYLE;
    const boite = document.createElement("div");
    boite.className = "boite";
    const r = champ.getBoundingClientRect();
    boite.style.left = `${Math.max(4, r.left)}px`;
    boite.style.top = `${r.bottom + 4}px`;
    const entete = document.createElement("div");
    entete.className = "entete";
    const icone = document.createElement("img");
    icone.src = ICONE;
    entete.append(icone, "SecretLin");
    boite.append(entete);
    racine.append(style, boite);
    document.documentElement.append(hote);
    return boite;
  }

  function texte(boite, contenu, classe = "texte") {
    const div = document.createElement("div");
    div.className = classe;
    div.textContent = contenu;
    boite.append(div);
    return div;
  }

  function afficherComptes(champ, comptes) {
    const boite = ouvrir(champ);
    for (const c of comptes) {
      const bouton = document.createElement("button");
      bouton.className = "compte";
      const site = document.createElement("div");
      site.className = "site";
      site.textContent = c.site;
      const detail = document.createElement("div");
      detail.className = "detail";
      detail.textContent = c.utilisateur || c.email || "—";
      bouton.append(site, detail);
      bouton.addEventListener("mousedown", (e) => e.preventDefault());
      bouton.addEventListener("click", () => choisir(champ, c));
      boite.append(bouton);
    }
  }

  function afficherVerrouille(champ) {
    const boite = ouvrir(champ);
    texte(boite, t("verrouille"));
    const bouton = document.createElement("button");
    bouton.className = "bouton";
    bouton.textContent = t("ouvrir");
    bouton.addEventListener("mousedown", (e) => e.preventDefault());
    bouton.addEventListener("click", () => {
      envoyer({ type: "montrer" });
      fermer();
    });
    boite.append(bouton);
  }

  function demanderPin(champ, compte, message = "") {
    const boite = ouvrir(champ);
    texte(boite, t("codePin", compte.site));
    const saisie = document.createElement("input");
    saisie.type = "password";
    saisie.inputMode = "numeric";
    saisie.maxLength = 4;
    saisie.autocomplete = "off";
    boite.append(saisie);
    if (message) {
      texte(boite, message, "texte erreur");
    }
    saisie.addEventListener("input", async () => {
      if (saisie.value.length < 4) {
        return;
      }
      const code = saisie.value;
      saisie.value = "";
      const reponse = await envoyer({ type: "pin", pin: code });
      if (reponse.ok) {
        choisir(champ, compte);
      } else if (reponse.verrouille) {
        demanderPin(champ, compte, t("tropErreurs"));
      } else if ("restants" in reponse) {
        demanderPin(champ, compte, t("codeFaux", String(reponse.restants)));
      } else {
        afficherVerrouille(champ);
      }
    });
    setTimeout(() => saisie.focus(), 0);
  }

  async function choisir(champ, compte) {
    const reponse = await envoyer({ type: "remplir", id: compte.id });
    if (reponse.besoinPin) {
      demanderPin(champ, compte);
    } else if (reponse.ok) {
      remplir(champsActifs, reponse.utilisateur || reponse.email, reponse.mot_de_passe);
      fermer();
    } else {
      afficherVerrouille(champ);
    }
  }

  // --- Déclenchement ----------------------------------------------------------------

  let comptesPage = null;  // comptes du site, demandés une fois par page
  let aucunSignale = false;  // « aucun compte » n'est montré qu'une fois par page

  function afficherAucun(champ) {
    const boite = ouvrir(champ);
    texte(boite, t("aucun"));
    texte(boite, t("aucunAide"));
    setTimeout(() => {
      if (racine && boite.isConnected) {
        fermer();
      }
    }, 4000);
  }

  async function auFocus(e) {
    const champ = e.target;
    if (!(champ instanceof HTMLInputElement) || (racine && e.composedPath().includes(hote))) {
      return;
    }
    const champs = champsConnexion(champ);
    if (!champs || Date.now() - rempliLe < 1500) {
      return;
    }
    champsActifs = champs;
    const etat = await envoyer({ type: "etat" });
    if (etat.etat !== "ouvert" && etat.etat !== "pin") {
      if (etat.etat === "ferme" && champ.type === "password") {
        afficherVerrouille(champ);
      }
      return;
    }
    if (comptesPage === null) {
      comptesPage = (await envoyer({ type: "comptes" })).comptes || [];
    }
    if (document.activeElement !== champ) {
      return;
    }
    if (comptesPage.length) {
      afficherComptes(champ, comptesPage);
    } else if (!aucunSignale) {
      aucunSignale = true;
      afficherAucun(champ);
    }
  }

  document.addEventListener("focusin", auFocus, true);
  document.addEventListener("mousedown", (e) => {
    if (hote && !e.composedPath().includes(hote)) {
      fermer();
    }
  }, true);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      fermer();
    }
  }, true);
  window.addEventListener("scroll", fermer, true);
  window.addEventListener("resize", fermer);

  // Remplissage demandé depuis le menu de l'extension.
  chrome.runtime.onMessage.addListener((message, expediteur) => {
    if (expediteur.id !== chrome.runtime.id || message.type !== "remplir") {
      return;
    }
    const champs = champsActifs || champsConnexion(champsMotDePasse()[0] || null) ||
      champsConnexion(document.activeElement);
    if (champs) {
      remplir(champs, message.utilisateur, message.motDePasse);
    }
  });
})();
