// Le front de l'atelier : sommaire (structure.yaml), lecture d'un chapitre, et —
// pour un chapitre migré — la fiche de chaque bloc : son plan, son micro-récit,
// les assertions du verrou qu'il porte.
// Pas de build : modules ES servis tels quels par le serveur.

const etat = { version: "recit", slug: null, chapitres: [], atelier: null, bloc: null, blocEssai: null, survol: null, essai: null,
  garde: null, defil: {}, docs: {}, sources: {},
  recitMode: "storyboard",                  // le récit s'ouvre avec son storyboard en regard
  planOn: true,                             // (ancien interrupteur ; le plan est un volet à gauche)
  edition: lirePref("atelier-edition", "annoter"),   // annoter | corriger : ce que fait un clic dans le texte
  essaiMode: "texte", noteChoisie: null, noteFocus: null, sourceChoisie: null,
  annots: [], annotFocus: null };

const api = (chemin) =>
  fetch("/api" + chemin).then((r) => (r.ok ? r.json() : Promise.reject(r.status)));

const el = (tag, cls, texte) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (texte != null) e.textContent = texte;
  return e;
};

// ------------------------------------------------------------------ sommaire

function sommaire() {
  const nav = document.getElementById("sommaire");
  nav.replaceChildren();
  const pres = el("a", "lien-livre" + (etat.accueil ? " actif" : ""), etat.livre?.titre || "Le livre");
  pres.href = "#livre";
  nav.append(pres);
  let partie;
  for (const c of etat.chapitres) {
    if (c.partie !== partie) {
      partie = c.partie;
      nav.append(el("h3", null, c.partie_titre ?? "Ouverture"));
    }
    const a = el("a");
    a.href = "#" + adresse(c.slug);
    a.dataset.slug = c.slug;
    const niv = c.avancement?.[versionSommaire()] ?? (c.atelier ? "brouillon" : "vide");
    const st = el("span", "st av av-" + niv, LIB_AVANCEMENT[niv] ?? niv);
    st.title = `${versionSommaire() === "essai" ? "essai" : "récit"} : ${TITRE_AVANCEMENT[niv] ?? niv}`;
    a.append(el("span", "n", c.numero ?? "—"), el("span", null, c.title), st);
    if (c.a_revalider) {
      const v = el("span", "nb-reval", "◐" + c.a_revalider);
      v.title = `${c.a_revalider} paragraphe(s) à revalider (modifiés, nouveaux, ou cadre changé)`;
      a.lastChild.before(v);
    }
    if (c.annotations) {
      const n = el("span", "nb-annot", String(c.annotations));
      n.title = `${c.annotations} annotation(s) ouverte(s)`;
      a.lastChild.before(n);
    }
    const dispo = etat.version === "storyboard" ? c.atelier : c.versions.includes(etat.version);
    if (!dispo) a.classList.add("mut");
    if (c.slug === etat.slug) a.classList.add("actif");
    nav.append(a);
  }
}

// L'avancement d'un chapitre, par version : vide → synopsis → brief → brouillon → relu → validé.
const LIB_AVANCEMENT = { vide: "vide", synopsis: "synopsis", brief: "brief", brouillon: "brouillon", relu: "relu", valide: "validé" };
const TITRE_AVANCEMENT = { vide: "ni synopsis ni texte", synopsis: "le synopsis seul, rien d'écrit",
  brief: "préparé : squelette ou verrou (essai), storyboard (récit) — pas encore de texte",
  brouillon: "du texte, en brouillon", relu: "du texte, relu (revised)", valide: "du texte, validé (locked)" };

// La version dont le sommaire montre l'avancement : celle qu'on lit (le storyboard est du récit).
function versionSommaire() {
  return etat.version === "essai" ? "essai" : "recit";
}

function badgesAvancement(c) {
  const s = el("span", "avs");
  for (const v of ["recit", "essai"]) {
    const n = c.avancement?.[v];
    if (!n) continue;
    const b = el("span", "st av av-" + n, `${v === "essai" ? "essai" : "récit"} · ${LIB_AVANCEMENT[n]}`);
    b.title = TITRE_AVANCEMENT[n];
    s.append(b);
  }
  return s;
}

// ------------------------------------------------------------------ page

// Chaque vue garde son état : la sélection (récit et storyboard partagent la leur,
// l'essai a la sienne), le défilement, et pour la vue parallèle le DOM entier —
// plans dépliés, panneau ouvert — qu'on remet tel quel en revenant.
async function ouvre(slug) {
  if (slug !== etat.slug) {
    Object.assign(etat, { bloc: null, blocEssai: null, essai: null, garde: null, defil: {}, docs: {}, sectionChoisie: null,
      noteChoisie: null, noteFocus: null, sourceChoisie: null });
  }
  etat.slug = slug;
  const vue = etat.version;
  const sel = vue === "essai" ? etat.blocEssai : etat.bloc;
  document.body.dataset.vue = vue;
  document.body.dataset.essai = etat.essaiMode;
  delete document.body.dataset.panneau;
  sommaire();
  barreOutils();
  const page = document.getElementById("page");
  const c = etat.chapitres.find((x) => x.slug === slug);
  etat.atelier = c?.atelier ? await api(`/chapitres/${slug}/atelier`).catch(() => null) : null;
  if (etat.atelier) await chargeDocs(slug);
  etat.validation = etat.atelier ? await api(`/chapitres/${slug}/validation`).catch(() => null) : null;
  barreOutils();                          // les données du chapitre sont là : la barre complète
  colonnePlan();
  etat.annots = etat.atelier ? await api(`/chapitres/${slug}/annotations`).catch(() => []) : [];
  await chargeDemandes();
  if (etat.tiroirApres) { const id = etat.tiroirApres; etat.tiroirApres = null; setTimeout(() => tiroir(id), 0); }
  if (etat.annotApres) {
    const id = etat.annotApres;
    etat.annotApres = null;
    setTimeout(() => {
      const a = etat.annots.find((x) => x.id === id);
      if (a) { blocEl(a.bloc)?.scrollIntoView({ block: "center" }); ouvreAnnotation(a); }
    }, 60);
  }

  if (vue === "storyboard" && etat.garde?.slug === slug) {        // retour : on remet tout
    const g = etat.garde;
    page.replaceChildren(...g.page);
    document.getElementById("fiche").replaceChildren(...g.fiche);
    if (g.panneau) document.body.dataset.panneau = g.panneau;
    poseAnnotations();                                            // elles ont pu changer ailleurs
    marquesDemandes();
    marquesValidation();
    if (sel && sel !== g.bloc) choisis(sel, true);                // choisi ailleurs entre-temps
    else zone().scrollTo(0, g.scroll);
    return;
  }

  if (vue === "storyboard") {
    await storyboard(page);
    poseAnnotations();
    marquesDemandes();
    marquesValidation();
  } else {
    try {
      const t = await api(`/chapitres/${slug}/${vue}`);
      page.innerHTML = t.html;
      page.append(el("p", "origine", t.origine));
      document.body.dataset.numerotation = t.numerotation ?? "aucune";
      enrichit(page);
    } catch {
      await vueSansTexte(page, slug, vue);
    }
    if (vue === "essai" && c?.avancement?.essai === "brief" && page.querySelector("[data-block]")) page.prepend(banniereSquelette(slug));
    marges();
    poseAnnotations();
    marquesDemandes();
    marquesValidation();
    if (vue === "essai") {
      page.querySelectorAll("h2").forEach((h) => {             // le titre de la liste de notes
        if (h.textContent.trim() === "Notes") h.classList.add("titre-notes");
      });
      if (etat.essaiMode === "notes") return vueNotes(page);
      if (etat.essaiMode === "biblio") return vueBiblio(page);
    }
  }
  fiche();
  if (etat.blocApres && etat.blocApres.version === (vue === "storyboard" ? "recit" : vue)) {
    const b = etat.blocApres.bloc;
    etat.blocApres = null;
    setTimeout(() => choisis(b, true), 60);
    return;
  }
  if (etat.cibleSection && vue === "essai") {
    const h = document.getElementById("sec-" + etat.cibleSection);
    etat.cibleSection = null;
    if (h) { h.scrollIntoView({ block: "start" }); return; }
  }
  const d = etat.defil[cleVue()];
  if (sel && document.querySelector(`#page [data-block="${sel}"]`)) {
    const memeSel = d && d.bloc === sel;
    const focus = etat.noteFocus;
    etat.noteFocus = null;
    choisis(sel, !memeSel && !focus, focus);
    if (focus) document.querySelector(`#page [data-block="${sel}"]`).scrollIntoView({ block: "center" });
    else if (memeSel) zone().scrollTo(0, d.scroll);
    return;
  }
  zone().scrollTo(0, d ? d.scroll : 0);
}

// La clé d'état d'une vue : l'essai en a une par mode (texte, notes, bibliographie).
function cleVue() {
  return etat.version === "essai" ? "essai/" + etat.essaiMode : etat.version;
}

// ------------------------------------------------------------------ essai : notes, bibliographie

// Tout ce que l'essai rendu sait de ses notes : clé, numéro, contenu, paragraphes appelants.
function indexNotes(page) {
  const lis = [...page.querySelectorAll(".footnote li[id^='fn:']")];
  return lis.map((li, i) => {
    const cle = li.id.slice(3);
    const appels = [...page.querySelectorAll(`a[href="#fn:${CSS.escape(cle)}"]`)]
      .map((a) => a.closest("[data-block]")).filter(Boolean);
    const uniques = [...new Set(appels)];
    // l'intertitre se lit maintenant : le mode notes détache ces paragraphes de la page
    return { cle, num: i + 1, li, appels: uniques, sections: uniques.map(sectionDe) };
  });
}

function contenuNote(li) {
  const c = li.cloneNode(true);
  c.querySelectorAll(".footnote-backref").forEach((x) => x.remove());
  return [...c.childNodes];
}

// L'intertitre sous lequel se trouve un paragraphe.
function sectionDe(p) {
  for (let n = p.previousElementSibling; n; n = n.previousElementSibling) {
    if (/^H[23]$/.test(n.tagName)) return n.textContent.trim();
  }
  return "ouverture";
}

// Mode notes : les notes en plein ; en marge, le texte qui les appelle.
function vueNotes(page) {
  const notes = indexNotes(page);
  const c = etat.chapitres.find((x) => x.slug === etat.slug);
  const liste = el("ol", "notes-pleines");
  for (const n of notes) {
    const li = el("li", "note-pleine");
    li.dataset.note = n.cle;
    li.append(el("span", "note-num", String(n.num)));
    const corps = el("div", "note-corps");
    corps.append(...contenuNote(n.li));
    enrichit(corps);
    li.append(corps);
    li.append(el("span", "note-cle", n.cle + (n.appels.length ? "" : " · non appelée")), boutonRef(`@chapitre/${etat.slug}/note/${n.cle}`));
    const fs = fichesDeNote(n.cle);
    if (fs.length) {
      const d = el("span", "note-fiches");
      d.append(...fs.map((x) => puceFiche(x)));
      li.append(d);
    }
    liste.append(li);
  }
  page.replaceChildren(el("h1", null, c?.title ?? etat.slug),
    el("p", "sous", `Notes de l'essai · ${notes.length}`), liste);
  page._notes = notes;
  document.getElementById("fiche").replaceChildren(
    el("p", "mut", "Choisir une note : le texte qui l'appelle s'affiche en marge."));
  if (etat.noteApres) { etat.noteChoisie = etat.noteApres; etat.noteApres = null; }
  if (etat.noteChoisie) choisisNote(etat.noteChoisie, true);
  else zone().scrollTo(0, etat.defil[cleVue()]?.scroll ?? 0);
}

function choisisNote(cle, defile = false) {
  const page = document.getElementById("page");
  const n = page._notes?.find((x) => x.cle === cle);
  const li = page.querySelector(`.note-pleine[data-note="${CSS.escape(cle)}"]`);
  if (!n || !li) return;
  etat.noteChoisie = cle;
  page.querySelectorAll(".note-pleine").forEach((x) => x.classList.toggle("choisi", x === li));
  page.querySelectorAll(".texte-marge").forEach((x) => x.remove());
  const aside = el("aside", "notes-marge texte-marge");
  if (!n.appels.length) aside.append(el("p", "mut", "Aucun paragraphe n'appelle cette note."));
  n.appels.forEach((p, i) => {
    const d = el("div", "note-marge");
    d.append(el("span", "appui-lieu", n.sections[i]));
    const copie = p.cloneNode(true);
    copie.removeAttribute("data-block");
    copie.classList.remove("choisi");
    copie.querySelectorAll(`a[href="#fn:${CSS.escape(cle)}"]`).forEach((a) => a.classList.add("appel-ici"));
    copie.querySelectorAll("a").forEach((a) => a.removeAttribute("href"));
    const aller = el("button", "pan-lien", "voir dans le texte →");
    aller.onclick = () => {
      etat.blocEssai = p.dataset.block;
      etat.noteFocus = cle;
      location.hash = `${etat.slug}/essai/texte`;
    };
    d.append(copie, aller);
    aside.append(d);
  });
  li.after(aside);
  pose(aside, li);
  if (n.appels[0]) fiche(n.appels[0].dataset.block);
  if (defile) li.scrollIntoView({ block: "center" });
}

// ------------------------------------------------------------------ barre d'affichage

function lirePref(cle, defaut) { try { return localStorage.getItem(cle) ?? defaut; } catch { return defaut; } }
function ecrisPref(cle, v) { try { localStorage.setItem(cle, v); } catch { /* navigation privée */ } }

// La barre de la page : ce qui règle l'affichage du chapitre dans la version courante.
// Récit : le storyboard en regard (interrupteur). Essai : texte · notes · bibliographie, le
// plan dans la colonne (interrupteur), la numérotation.
function barreOutils() {
  const o = document.getElementById("outils");
  o.replaceChildren();
  if (etat.accueil || !etat.slug) { o.hidden = true; return; }
  o.hidden = false;
  const bouton = (txt, actif, f, cls = "", titre = "") => {
    const b = el("button", cls + (actif ? " actif" : ""), txt);
    b.onclick = f;
    if (titre) b.title = titre;
    return b;
  };
  const v = etat.version;
  const texte = v === "recit" || v === "storyboard" || (v === "essai" && etat.essaiMode === "texte");
  if (texte && etat.atelier) {
    const g = el("span", "groupe mode-edition");
    for (const [m, lib, titre] of [["annoter", "✎ annoter", "sélectionner un passage pour l'annoter"],
      ["corriger", "✐ corriger", "cliquer un paragraphe pour le corriger directement"]]) {
      g.append(bouton(lib, etat.edition === m, () => {
        etat.edition = m;
        ecrisPref("atelier-edition", m);
        document.body.dataset.edition = m;
        barreOutils();
      }, "", titre));
    }
    o.append(g);
  }
  document.body.dataset.edition = etat.edition;
  if (v === "recit" || v === "storyboard") {
    const sb = v === "storyboard";
    o.append(bouton("storyboard", sb, () => { location.hash = `${etat.slug}/recit/${sb ? "texte" : "storyboard"}`; },
      "bascule", "le storyboard en regard du récit, ligne à ligne"));
    o.append(boutonsPdf("recit", "⎙ PDF", "recit.pdf", titrePdf("recit"))[0]);
  } else if (v === "essai") {
    const g = el("span", "groupe");
    for (const [m, lib] of [["texte", "texte"], ["notes", "notes"], ["biblio", "bibliographie"]]) {
      g.append(bouton(lib, etat.essaiMode === m, () => { location.hash = `${etat.slug}/essai/${m}`; }));
    }
    o.append(g);
    o.append(el("span", "espace"));
    o.append(boutonsPdf("essai", "⎙ PDF", "essai.pdf", titrePdf("essai"))[0]);
    o.append(el("span", "etiq", "numérotation"));
    const sel = el("select");
    for (const [val, lib] of [["aucune", "aucune"], ["sections", "sections"], ["paragraphes", "sections + §"]]) {
      const op = el("option", null, lib);
      op.value = val;
      if ((etat.livre.numerotation_essai ?? "aucune") === val) op.selected = true;
      sel.append(op);
    }
    sel.onchange = async () => {
      const r = await fetch("/api/livre", { method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ champs: { numerotation_essai: sel.value }, version: etat.livre._version }) });
      if (r.ok) etat.livre = await r.json();
      etat.docs = {};
      await ouvre(etat.slug);
    };
    o.append(sel);
  }
  if (!o.querySelector(".espace")) o.append(el("span", "espace"));
  const EV = etat.validation?.versions?.[versionVue()];
  if (EV) {
    const n = Object.values(EV).filter((x) => x.etat !== "valide").length;
    const bval = el("button", "b-validation" + (n ? " a-revalider" : ""), n ? `◐ ${n} à revalider` : "● validé");
    bval.title = "ce qui a changé depuis la dernière validation";
    bval.onclick = () => panneauValidation(bval);
    o.append(bval);
  }
  if (etat.atelier && (v === "recit" || v === "storyboard" || v === "essai")) {
    o.append(boutonRef(`@chapitre/${etat.slug}`, "b-versions"));
    const bh = el("button", "b-validation b-harnais", "✓ harnais");
    bh.title = "les portes du chapitre (verrou, budget, garde-fous, répétitions, lecture naïve…) puis la validation";
    bh.onclick = () => tiroirHarnais(versionVue());
    o.append(bh);
    api(`/chapitres/${etat.slug}/harnais/${versionVue()}`).then((R) => {
      if (R.absent) return bh.remove();                  // pas encore de texte dans cette version
      bh.textContent = R.ok ? "✓ harnais" : `✗ harnais · ${R.bloquantes.length}`;
      bh.classList.toggle("a-revalider", !R.ok);
      bh.title = R.ok ? "toutes les portes bloquantes passent" : "portes à passer : " + R.bloquantes.join(", ");
    }).catch(() => {});
  }
  const bv = el("button", "b-versions", "⎇ versions");
  bv.title = "enregistrer une version du livre (git)";
  bv.onclick = () => panneauVersions(bv);
  o.append(bv);
  majVersions(bv);
}

// ------------------------------------------------------------------ plan de l'essai (colonne)

// L'arbre de l'essai dans la colonne de droite : il accompagne le texte, les notes ou la
// bibliographie. Glisser-déposer un paragraphe ou une section ; ← → pour le niveau ;
// double-clic pour renommer ; ＋ pour un intertitre ; ✕ pour en retirer un. Aucun
// identifiant ne change ; chaque opération est au journal.
const plisPlan = new Set();                   // les sections dont on montre les paragraphes

async function colonnePlan() {
  const col = document.getElementById("plan-col");
  const volet = document.getElementById("volet-chapitre");
  if (etat.accueil || !etat.atelier) { volet.hidden = true; return; }
  volet.hidden = false;
  const c = etat.chapitres.find((x) => x.slug === etat.slug);
  volet.querySelector(".volet-titre").textContent = `Plan du chapitre · ${c?.numero ?? ""} ${c?.title ?? ""}`;
  if (etat.version !== "essai") return planRecit(col);
  let P;
  try { P = await api(`/chapitres/${etat.slug}/essai/plan`); }
  catch { col.replaceChildren(el("p", "mut", "Pas d'essai dans l'atelier.")); return; }
  etat.planEssai = P;
  const avecNum = P.numerotation !== "aucune";
  const racine = el("div", "pl-arbre");
  const ligneBloc = (b, niv) => {
    const r = el("div", "pl-ligne pl-bloc");
    r.dataset.type = "bloc";
    r.dataset.id = b.id;
    r.draggable = true;
    r.style.paddingLeft = (niv * .9 + 1.1) + "rem";
    r.append(el("span", "pl-poignee", "⋮⋮"));
    if (avecNum && P.numerotation === "paragraphes") r.append(el("span", "pl-num", b.num ?? ""));
    const d = el("span", "pl-debut", b.debut);
    d.title = "aller au paragraphe";
    d.onclick = () => allerDansEssai({ bloc: b.id });
    r.append(d);
    const ins = el("button", "pl-bouton", "＋");
    ins.title = "insérer un intertitre avant ce paragraphe";
    ins.onclick = () => saisieTitre(r, (titre) => opPlan({ op: "insere", titre, niveau: Math.max(2, niv + 1),
      cible: { type: "bloc", id: b.id, place: "avant" } }));
    const m = el("span", "pl-meta");
    m.append(ins);
    r.append(m);
    return r;
  };
  const section = (s, niv) => {
    const boite = el("div", "pl-section-boite");
    if (s.id) {
      const h = el("div", "pl-ligne pl-section n" + s.niveau);
      h.dataset.type = "section";
      h.dataset.id = s.id;
      h.draggable = true;
      h.style.paddingLeft = ((niv - 1) * .9) + "rem";
      const pl = el("button", "pl-plier", plisPlan.has(s.id) ? "▾" : "▸");
      pl.title = "montrer ses paragraphes";
      pl.onclick = () => { plisPlan.has(s.id) ? plisPlan.delete(s.id) : plisPlan.add(s.id); colonnePlan(); };
      h.append(pl);
      if (avecNum) h.append(el("span", "pl-num", s.num ?? ""));
      const t = el("span", "pl-titre", s.titre);
      t.title = "clic : y aller · double-clic : renommer";
      t.onclick = () => { marqueSection(s.id); allerDansEssai({ section: s.id }); };
      t.ondblclick = () => saisieTitre(h, (titre) => opPlan({ op: "renomme", section: s.id, titre }), s.titre);
      h.append(t);
      const act = el("span", "pl-meta");
      const b = (txt, titre, f) => { const x = el("button", "pl-bouton", txt); x.title = titre; x.onclick = f; act.append(x); };
      b("←", "monter d'un niveau", () => opPlan({ op: "niveau", section: s.id, delta: -1 }));
      b("→", "descendre d'un niveau", () => opPlan({ op: "niveau", section: s.id, delta: 1 }));
      b("＋", "insérer une sous-section au début", () => saisieTitre(h, (titre) => opPlan({ op: "insere", titre,
        niveau: Math.min(6, s.niveau + 1), cible: { type: "section", id: s.id, place: "debut" } })));
      b("✕", "retirer l'intertitre (le contenu rejoint la section précédente)", () => {
        if (confirm(`Retirer l'intertitre « ${s.titre} » ? Ses paragraphes restent, dans la section précédente.`)) {
          opPlan({ op: "supprime", section: s.id });
        }
      });
      h.append(act);
      boite.append(h);
      if (plisPlan.has(s.id)) for (const bl of s.blocs) boite.append(ligneBloc(bl, niv));
    } else {
      // l'ouverture : ses paragraphes, repliables comme une section
      const h = el("div", "pl-ligne pl-ouverture");
      const pl = el("button", "pl-plier", plisPlan.has("#ouverture") ? "▾" : "▸");
      pl.onclick = () => { plisPlan.has("#ouverture") ? plisPlan.delete("#ouverture") : plisPlan.add("#ouverture"); colonnePlan(); };
      h.append(pl, el("span", "pl-debut", `ouverture · ${s.blocs.length} §`));
      boite.append(h);
      if (plisPlan.has("#ouverture")) for (const bl of s.blocs) boite.append(ligneBloc(bl, 0));
    }
    for (const e of s.enfants) boite.append(section(e, niv + 1));
    return boite;
  };
  racine.append(section(P.arbre, 1));
  const tete = el("h4", null, "Plan de l'essai");
  const tout = el("button", "pan-lien", plisPlan.size ? "replier les paragraphes" : "déplier les paragraphes");
  tout.onclick = () => {
    if (plisPlan.size) plisPlan.clear();
    else { plisPlan.add("#ouverture"); const aj = (s) => { if (s.id) plisPlan.add(s.id); s.enfants.forEach(aj); }; aj(P.arbre); }
    colonnePlan();
  };
  col.replaceChildren(tete, tout, racine);
  glisser(racine);
  if (etat.sectionChoisie) marqueSection(etat.sectionChoisie, false);
  surPlan();
  marquesValidation();
}

// Le volet chapitre, côté récit : ses plans (A, B…), cliquables — le titre mène au plan
// dans le texte, et ouvre son détail (modifiable) dans la vue storyboard.
function planRecit(col) {
  const beats = etat.atelier?.brief?.beats ?? [];
  const L = [el("h4", null, "Plans du récit")];
  for (const b of beats) {
    const l = el("div", "pl-recit");
    l.append(el("b", null, b.id), el("span", null, b.title));
    l.onclick = () => {
      const m = document.querySelector(`#page [data-plan-titre="${b.id}"]`);
      m?.scrollIntoView({ block: "start", behavior: "smooth" });
      if (etat.version === "storyboard") panneauPlan(b.id);
    };
    L.push(l);
  }
  if (!beats.length) L.push(el("p", "mut", "Pas de storyboard."));
  col.replaceChildren(...L);
}

// Une section choisie : allumée dans le plan (et dans le texte, si demandé).
function marqueSection(id, dansTexte = true) {
  etat.sectionChoisie = id;
  const col = document.getElementById("plan-col");
  col.querySelectorAll(".pl-section").forEach((x) => x.classList.toggle("choisie", x.dataset.id === id));
  col.querySelector(`.pl-section[data-id="${id}"]`)?.scrollIntoView({ block: "nearest" });
  if (dansTexte) {
    const h = document.getElementById("sec-" + id);
    if (h) { h.classList.add("eclair"); setTimeout(() => h.classList.remove("eclair"), 1400); }
  }
}

// Renommer un intertitre directement dans le texte de l'essai (double-clic).
function editeTitreTexte(h) {
  const id = h.dataset.section;
  const ancien = h.textContent.trim();
  const i = el("input", "titre-edit");
  i.value = ancien;
  h.replaceChildren(i);
  i.focus();
  i.select();
  const fin = (garder) => {
    if (i.dataset.fini) return;
    i.dataset.fini = "1";
    if (garder && i.value.trim() && i.value.trim() !== ancien) opPlan({ op: "renomme", section: id, titre: i.value.trim() });
    else h.textContent = ancien;
  };
  i.onkeydown = (e) => { if (e.key === "Enter") fin(true); if (e.key === "Escape") fin(false); };
  i.onblur = () => fin(true);
}

// Aller à une section ou un paragraphe de l'essai : dans le texte (on y passe si besoin).
function allerDansEssai({ section, bloc }) {
  if (etat.essaiMode !== "texte") {
    if (bloc) etat.blocEssai = bloc;
    etat.cibleSection = section;
    location.hash = `${etat.slug}/essai/texte`;
    return;
  }
  if (bloc) { choisis(bloc, true); return; }
  document.getElementById("sec-" + section)?.scrollIntoView({ block: "start", behavior: "smooth" });
}

// La section courante (celle qu'on lit) s'allume dans le plan.
function surPlan() {
  const col = document.getElementById("plan-col");
  if (etat.version !== "essai" || etat.essaiMode !== "texte") return;
  let courante = null;
  for (const h of document.querySelectorAll("#page [data-section]")) {
    if (!h.getClientRects().length) continue;            // intertitre masqué (la liste des notes)
    if (h.getBoundingClientRect().top < 140) courante = h.dataset.section;
  }
  col.querySelectorAll(".pl-section").forEach((x) => x.classList.toggle("courante", x.dataset.id === courante));
}
// Le texte défile dans sa zone, sous la barre de la page (sur petit écran : la fenêtre).
function zone() {
  return matchMedia("(max-width:760px)").matches ? document.scrollingElement : document.getElementById("defile");
}
for (const cible of [document.getElementById("defile"), window]) {
  cible.addEventListener("scroll", () => { if (etat.version === "essai") surPlan(); }, { passive: true });
}

function saisieTitre(ligne, envoie, valeur = "") {
  const i = el("input", "dem-motif pl-saisie");
  i.value = valeur;
  i.placeholder = "titre de l'intertitre, ↵ pour valider, Échap pour annuler";
  ligne.after(i);
  i.focus();
  i.onkeydown = (e) => {
    if (e.key === "Escape") i.remove();
    if (e.key === "Enter" && i.value.trim()) { i.remove(); envoie(i.value.trim()); }
  };
}

async function opPlan(corps) {
  const r = await fetch(`/api/chapitres/${etat.slug}/essai/structure`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...corps, empreinte: etat.planEssai?.empreinte }) });
  if (!r.ok) {
    const m = (await r.json().catch(() => ({}))).detail ?? r.status;
    alert(r.status === 409 ? "L'essai a changé ailleurs : le plan est rechargé." : "Refusé : " + m);
  }
  etat.docs = {};                        // l'essai a changé : les appuis le relisent
  const y = zone().scrollTop;
  await ouvre(etat.slug);
  zone().scrollTo(0, y);
  surPlan();
}

// Glisser-déposer dans l'arbre : une ligne tirée (paragraphe ou section) se pose avant une
// ligne, ou — sur la moitié basse d'un intertitre — au début de sa section.
function glisser(racine) {
  let tire = null;
  const repere = el("div", "pl-repere");
  racine.addEventListener("dragstart", (e) => {
    const l = e.target.closest(".pl-ligne");
    if (!l) return;
    tire = { type: l.dataset.type, id: l.dataset.id };
    l.classList.add("tiree");
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", l.dataset.id);
  });
  racine.addEventListener("dragend", (e) => {
    e.target.closest(".pl-ligne")?.classList.remove("tiree");
    repere.remove();
  });
  const cibleDe = (e) => {
    const l = e.target.closest(".pl-ligne");
    if (!l || !tire || l.dataset.id === tire.id) return null;
    const r = l.getBoundingClientRect();
    const bas = e.clientY > r.top + r.height / 2;
    if (l.dataset.type === "section") return { l, cible: { type: "section", id: l.dataset.id, place: bas ? "debut" : "avant" }, apres: bas };
    return { l, cible: { type: "bloc", id: l.dataset.id, place: bas ? "apres" : "avant" }, apres: bas };
  };
  racine.addEventListener("dragover", (e) => {
    const c = cibleDe(e);
    if (!c) return;
    e.preventDefault();
    if (c.apres) c.l.after(repere); else c.l.before(repere);
    repere.style.marginLeft = c.l.style.paddingLeft;
  });
  racine.addEventListener("drop", (e) => {
    const c = cibleDe(e);
    repere.remove();
    if (!c) return;
    e.preventDefault();
    opPlan({ op: "deplace", quoi: tire, cible: c.cible });
  });
}

// Mode bibliographie : les œuvres citées par les notes du chapitre (bibliographie.yaml),
// chacune sélectionnable — en marge, les notes qui la citent.
function vueBiblio(page) {
  const notes = indexNotes(page);
  const parNote = Object.fromEntries(notes.map((n) => [n.cle, n]));
  const c = etat.chapitres.find((x) => x.slug === etat.slug);
  let sources = etat.atelier?.bibliographie ?? [];
  if (!sources.length) {                       // pas encore de fichier : les seules clés [@…]
    const m = new Map();
    for (const n of notes) for (const ci of n.li.querySelectorAll("cite[data-cle]")) {
      if (!m.has(ci.dataset.cle)) m.set(ci.dataset.cle, []);
      m.get(ci.dataset.cle).push(n.cle);
    }
    sources = [...m].map(([cle, ns]) => ({ cle, ref: null, centrale: !!etat.sources[cle],
      citation: "cle", notes: [...new Set(ns)] }));
  }
  const nb = (f) => sources.filter(f).length;
  const out = [el("h1", null, c?.title ?? etat.slug), el("p", "sous", "Bibliographie de l'essai")];
  out.push(el("p", "biblio-bilan",
    `${sources.length} œuvres · ${nb((s) => s.centrale)} dans la base centrale · ` +
    `${nb((s) => !s.centrale)} à y ajouter · ${nb((s) => s.citation === "clair")} citées en clair ` +
    `(sans clé [@…]) · ${nb((s) => s.doi)} avec DOI`));
  const ul = el("ul", "biblio-liste");
  for (const s of sources) {
    const li = el("li", "source");
    li.dataset.source = s.cle;
    const ref = el("div", "biblio-ref");
    const html = s.ref ? mdLigne(s.ref) : etat.sources[s.cle];
    if (html) ref.innerHTML = html; else ref.append(el("code", null, s.cle));
    const meta = el("div", "biblio-ou");
    meta.append(el("span", "appui-lieu", courte(s.cle)));
    if (s.citation === "clair") meta.append(el("span", "badge", "en clair"));
    if (!s.centrale) meta.append(el("span", "badge hors", "hors base"));
    if (s.doute) { const d = el("span", "badge doute", "doute"); d.title = s.doute; meta.append(d); }
    meta.append(liensSource(s.doi, s.ref ?? html));
    for (const k of s.notes ?? []) if (parNote[k]) meta.append(el("span", "puce", "note " + parNote[k].num));
    for (const fs of s.fiches ?? []) meta.append(puceFiche(fs));
    li.append(ref, meta);
    ul.append(li);
  }
  out.push(ul);
  page.replaceChildren(...out);
  page._notes = notes;
  page._sources = sources;
  document.getElementById("fiche").replaceChildren(
    el("p", "mut", "Choisir une œuvre : les notes qui la citent s'affichent en marge."),
    el("p", "mut petit", "Base centrale : noosphereV2/Books/UneVie-book/livre/bibliographie.md " +
      `(${Object.keys(etat.sources).length} entrées), en lecture seule. Fichier du chapitre : ` +
      `UneVie/book-atelier/chapters/${etat.slug}/bibliographie.yaml.`));
  if (etat.sourceChoisie) choisisSource(etat.sourceChoisie, true);
  else zone().scrollTo(0, etat.defil[cleVue()]?.scroll ?? 0);
}

function choisisSource(cle, defile = false) {
  const page = document.getElementById("page");
  const s = page._sources?.find((x) => x.cle === cle);
  const li = page.querySelector(`.source[data-source="${CSS.escape(cle)}"]`);
  if (!s || !li) return;
  etat.sourceChoisie = cle;
  page.querySelectorAll(".source").forEach((x) => x.classList.toggle("choisi", x === li));
  page.querySelectorAll(".texte-marge").forEach((x) => x.remove());
  const aside = el("aside", "notes-marge texte-marge");
  for (const k of s.notes ?? []) {
    const n = page._notes.find((x) => x.cle === k);
    if (!n) continue;
    const d = el("div", "note-marge");
    d.append(el("span", "note-num", String(n.num)));
    const corps = el("span");
    corps.append(...contenuNote(n.li));
    enrichit(corps);
    d.append(corps);
    const nav = el("div", "marge-nav");
    const versNote = el("button", "pan-lien", "la note →");
    versNote.onclick = () => { etat.noteChoisie = k; location.hash = `${etat.slug}/essai/notes`; };
    nav.append(versNote);
    if (n.appels[0]) {
      const versTexte = el("button", "pan-lien", "dans le texte →");
      versTexte.onclick = () => {
        etat.blocEssai = n.appels[0].dataset.block;
        etat.noteFocus = k;
        location.hash = `${etat.slug}/essai/texte`;
      };
      nav.append(versTexte);
    }
    d.append(nav);
    aside.append(d);
  }
  li.after(aside);
  pose(aside, li);
  if (defile) li.scrollIntoView({ block: "center" });
}

// Place une marge à la hauteur de son ancre, et allonge la page si elle déborde.
function pose(aside, ancre) {
  const page = document.getElementById("page");
  page.style.minHeight = "";
  aside.style.top = ancre.offsetTop + "px";
  if (getComputedStyle(aside).position !== "absolute") return;
  const bas = ancre.offsetTop + aside.offsetHeight + 48;
  if (bas > page.scrollHeight) page.style.minHeight = bas + "px";
}

// Markdown d'une ligne de référence : *italique* et **gras** seulement.
function mdLigne(s) {
  const esc = s.replace(/&/g, "&amp;").replace(/</g, "&lt;");
  return esc.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>").replace(/\*([^*]+)\*/g, "<em>$1</em>");
}

// Les liens d'une œuvre : son DOI s'il est connu, sinon une recherche (Google Scholar).
function liensSource(doi, ref) {
  const s = el("span", "liens-source");
  const lien = (href, texte, titre) => {
    const a = el("a", "lien-ext", texte);
    a.href = href; a.target = "_blank"; a.rel = "noopener"; a.title = titre;
    return a;
  };
  if (doi) s.append(lien("https://doi.org/" + doi, "doi ↗", doi));
  const ax = (ref ?? "").match(/arXiv:\s?(\d{4}\.\d{4,5})/i);
  if (ax) s.append(lien("https://arxiv.org/abs/" + ax[1], "arXiv ↗", "arXiv:" + ax[1]));
  const q = (ref ?? "").replace(/<[^>]+>/g, "").replace(/[*«»]/g, "").replace(/\s+/g, " ").trim();
  if (q) s.append(lien("https://scholar.google.com/scholar?q=" + encodeURIComponent(q.slice(0, 250)),
    "chercher ↗", "Chercher dans Google Scholar"));
  return s;
}

// Citations lisibles et DOI cliquables. Le texte ne change pas : on enveloppe, on n'ajoute rien.
function enrichit(racine) {
  citations(racine);
  const DOI = /\b10\.\d{4,9}\/[^\s,;)»<]*[^\s,;)».<]|arXiv:\s?\d{4}\.\d{4,5}/gi;
  const w = document.createTreeWalker(racine, NodeFilter.SHOW_TEXT);
  const aTraiter = [];
  while (w.nextNode()) {
    DOI.lastIndex = 0;
    if (DOI.test(w.currentNode.data) && !w.currentNode.parentElement.closest("a")) aTraiter.push(w.currentNode);
  }
  for (const n of aTraiter) {
    const frag = document.createDocumentFragment();
    let i = 0;
    for (const m of n.data.matchAll(DOI)) {
      frag.append(n.data.slice(i, m.index));
      const a = el("a", "lien-ext", m[0]);
      a.href = /^arxiv/i.test(m[0]) ? "https://arxiv.org/abs/" + m[0].replace(/^arXiv:\s?/i, "")
        : "https://doi.org/" + m[0];
      a.target = "_blank"; a.rel = "noopener";
      frag.append(a);
      i = m.index + m[0].length;
    }
    frag.append(n.data.slice(i));
    n.replaceWith(frag);
  }
}

// Avant de quitter une vue : noter où l'on était. La vue parallèle garde son DOM.
function quitte() {
  if (etat.wiki) return;                    // les fiches ne gardent pas l'état d'un chapitre
  const vue = etat.version;
  if (etat.accueil || !etat.slug || !vue) return;
  const sel = vue === "essai" ? etat.blocEssai : etat.bloc;
  etat.defil[cleVue()] = { scroll: zone().scrollTop, bloc: sel };
  if (vue === "storyboard") {
    etat.garde = {
      slug: etat.slug, scroll: zone().scrollTop, bloc: etat.bloc,
      page: [...document.getElementById("page").childNodes],
      fiche: [...document.getElementById("fiche").childNodes],
      panneau: document.body.dataset.panneau,
    };
  }
}

// Les blocs du récit groupés par plan, dans l'ordre du texte. links.yaml est écrit
// dans l'ordre du texte ; le rang d'un bloc dans son plan désigne son micro-récit.
function parPlan() {
  const out = {};
  for (const [id, l] of Object.entries(etat.atelier?.links?.recit ?? {})) {
    (out[l.plan] ??= []).push(id);
  }
  return out;
}

function rangDe(id) {
  const l = etat.atelier?.links?.recit?.[id];
  return l ? parPlan()[l.plan].indexOf(id) : -1;
}

// Pour le récit d'un chapitre migré : chaque bloc sait son plan ; on pose une
// étiquette de marge au premier bloc de chaque plan, et le rang dans le plan
// (qui désigne le micro-récit du storyboard).
function marges() {
  const liens = etat.atelier?.links?.[etat.version] ?? {};
  const beats = Object.fromEntries((etat.atelier?.brief?.beats ?? []).map((b) => [b.id, b]));
  const vus = new Set();
  for (const p of document.querySelectorAll("#page [data-block]")) {
    const l = liens[p.dataset.block];
    if (!l?.plan) continue;              // l'essai n'a pas de plans
    p.dataset.plan = l.plan;
    if (l.ajout) p.classList.add("ajout");
    if (!vus.has(l.plan)) {
      vus.add(l.plan);
      const m = el("span", "marge cliquable", `${l.plan} — ${beats[l.plan]?.title ?? ""}`);
      m.dataset.planTitre = l.plan;
      m.title = "Détail du plan";
      p.before(m);   // hors du bloc : son texte reste la prose seule
    }
  }
}

document.getElementById("page").addEventListener("click", (e) => {
  // appels et retours de note : jamais de navigation (l'adresse porte chapitre/vue)
  const rv = e.target.closest("a.renvoi");
  if (rv) {
    e.preventDefault();
    document.getElementById("sec-" + rv.dataset.sec)?.scrollIntoView({ block: "start", behavior: "smooth" });
    return;
  }
  const fn = e.target.closest('a[href^="#fn"]');
  if (fn) {
    e.preventDefault();
    const h = fn.getAttribute("href");
    if (h.startsWith("#fn:")) {
      const p = fn.closest("[data-block]");
      if (p) choisis(p.dataset.block, false, h.slice(4));
    } else {                                   // ↩ depuis la liste des notes
      const appel = document.getElementById(h.slice(1));
      const p = appel?.closest("[data-block]");
      if (p) choisis(p.dataset.block, true, fn.closest("li")?.id?.slice(3));
    }
    return;
  }
  const so = e.target.closest(".source");
  if (so && !e.target.closest("a")) { choisisSource(so.dataset.source); return; }
  const hs = e.target.closest("#page [data-section]");
  if (hs && !e.target.closest("input")) { marqueSection(hs.dataset.section, false); return; }
  const np = e.target.closest(".note-pleine");
  if (np && !e.target.closest("a")) { choisisNote(np.dataset.note); return; }
  const pl = e.target.closest("[data-plan-titre]");
  if (pl) { panneauPlan(pl.dataset.planTitre); return; }
  const pu = e.target.closest("[data-assertion]");
  if (pu) panneauAssertion(pu.dataset.assertion);
  if (e.target.closest(".panneau-bloc, .editeur")) return;
  if (etat.edition !== "corriger" && window.getSelection().isCollapsed) {
    const touchee = annotationSous(e);
    if (touchee) { ouvreAnnotation(touchee); return; }
  }
  const b = e.target.closest("[data-block]");
  if (!b || e.target.closest("a, button")) return;
  if (etat.edition === "corriger" && !e.target.closest(".par-sb, .par-gout")) {
    const cible = etat.version === "storyboard" ? b.closest(".par-texte") ?? b : b;
    if (cible.dataset.block && (etat.version !== "storyboard" || cible.classList.contains("par-texte"))) {
      choisis(cible.dataset.block);
      editeBloc(cible.dataset.block);
      return;
    }
  }
  // la marque de réécriture, dans la marge droite du paragraphe
  if (b.dataset.reecr && e.clientX > b.getBoundingClientRect().right) { tiroir(b.dataset.demande); return; }
  // un clic sur la pastille (dans la marge, à gauche du bloc) ouvre ses annotations
  if (b.dataset.annot && e.clientX < b.getBoundingClientRect().left) {
    choisis(b.dataset.block);
    panneauBloc(b.dataset.block);
    return;
  }
  choisis(b.dataset.block);
});

function choisis(id, defile = false, note = null) {
  if (etat.version === "essai") etat.blocEssai = id; else etat.bloc = id;
  let premier = null;
  document.querySelectorAll("#page [data-block]").forEach((x) => {
    const oui = x.dataset.block === id;
    x.classList.toggle("choisi", oui);
    if (oui && !premier) premier = x;
  });
  fiche(id);
  if (etat.version === "essai") notesMarge(id, note);
  if (defile && premier) premier.scrollIntoView({ block: "center" });
}

// Les notes d'un paragraphe de l'essai, dans la marge, à sa hauteur. Posées à côté
// du paragraphe (jamais dedans : son texte reste la prose seule).
function notesMarge(id, focus) {
  document.querySelectorAll("#page .notes-marge").forEach((n) => n.remove());
  const p = document.querySelector(`#page [data-block="${id}"]`);
  if (!p) return;
  const appels = [...p.querySelectorAll('a[href^="#fn:"]')];
  if (!appels.length) return;
  const aside = el("aside", "notes-marge");
  for (const a of appels) {
    const cle = a.getAttribute("href").slice(4);
    const li = document.getElementById("fn:" + cle);
    if (!li) continue;
    const n = el("div", "note-marge" + (cle === focus ? " focus" : ""));
    const c = li.cloneNode(true);
    c.querySelectorAll(".footnote-backref").forEach((x) => x.remove());
    n.append(el("span", "note-num", a.textContent));
    n.append(...c.childNodes);
    citations(n);
    aside.append(n);
  }
  p.after(aside);
  pose(aside, p);
  if (focus) aside.querySelector(".focus")?.scrollIntoView({ block: "nearest" });
}


// ------------------------------------------------------------------ récit ⇄ storyboard

// Vue en parallèle : le récit à gauche, le storyboard à droite, alignés ligne à
// ligne. Une ligne = un paragraphe et le micro-récit de même rang dans son plan.
// Un seul défilement : la synchro est structurelle, pas calculée. La gouttière
// centrale dessine le lien — un trait par plan, un repère par paragraphe.
async function storyboard(page) {
  page.replaceChildren();
  const a = etat.atelier;
  const c = etat.chapitres.find((x) => x.slug === etat.slug);
  if (!a) {
    page.append(el("h1", null, c?.title ?? etat.slug),
      el("p", "mut", "Chapitre pas encore migré : pas de storyboard dans l'atelier."));
    return;
  }

  // les paragraphes du récit, rendus par le serveur, dans l'ordre du texte
  const paras = {};
  const tete = [];
  try {
    const t = await api(`/chapitres/${etat.slug}/recit`);
    const doc = new DOMParser().parseFromString(t.html, "text/html");
    for (const n of doc.body.children) {
      if (n.dataset.block) paras[n.dataset.block] = n;
      else if (!Object.keys(paras).length && n.tagName !== "HR") tete.push(n);
    }
  } catch { /* le storyboard reste lisible sans le texte */ }

  const br = a.brief;
  const grille = el("div", "par");

  // en-tête : titre du chapitre | ce qui est suivi
  const g0 = el("div", "par-texte par-tete");
  g0.append(...tete);
  const d0 = el("div", "par-sb par-tete");
  d0.append(el("p", "sous", "Storyboard"));
  const intent = el("div", "sb-intention");
  for (const [k, v] of Object.entries(br.intent ?? {})) {
    const l = el("p");
    l.append(el("span", "nom", k.replace(/_/g, " ") + " "), document.createTextNode(v));
    intent.append(l);
  }
  d0.append(intent);
  const modTete = el("button", "pan-lien", "✎ modifier l'en-tête du storyboard");
  modTete.onclick = () => panneauBrief();
  d0.append(modTete);
  if (br.suivi) {
    const suivi = el("details", "replie");
    suivi.append(el("summary", null, "Ce qui est suivi"));
    for (const para of br.suivi.split(/\n\s*\n/)) suivi.append(md(para));
    d0.append(suivi);
  }
  grille.append(g0, el("div", "par-gout"), d0);

  const blocs = parPlan();
  for (const b of br.beats ?? []) {
    const ids = blocs[b.id] ?? [];
    const recits = b.recits ?? [];
    const ajouts = ids.filter((i) => a.links.recit[i].ajout).length;

    // ligne de plan : étiquette | fiche du plan
    const gp = el("div", "par-texte par-plan");
    const eti = el("span", "marge cliquable", `${b.id} — ${b.title}`);
    eti.dataset.planTitre = b.id;
    eti.title = "Détail du plan";
    gp.append(eti);
    const dp = el("div", "par-sb par-plan");
    const h = el("h2", "cliquable");
    h.dataset.planTitre = b.id;
    h.title = "Détail du plan";
    h.append(el("span", "sb-lettre", b.id), document.createTextNode(b.title));
    const meta = el("dl", "sb-meta");
    for (const k of ["lieu", "temps", "ambiance", "attaque", "chute"]) {
      if (b[k]) meta.append(el("dt", null, k), el("dd", null, b[k]));
    }
    const comptes = el("p", "sb-comptes");
    comptes.append(document.createTextNode(
      `${recits.length} micro-récits · ${ids.length} paragraphes · ` +
      `${b.assertions?.length ?? 0} assertions · ajouts ${ajouts}/${b.ajouts ?? 0}`));
    if (recits.length !== ids.length) comptes.append(el("span", "ecart", " compte faux"));
    const conf = conformite(b, ids);
    if (!conf) comptes.append(el("span", "mut", " · séquence non déclarée"));
    else {
      const k = conf.filter((c) => !c.ok).length;
      comptes.append(k ? el("span", "ecart", ` · séquence : ${k} écart(s)`) : el("span", null, " · séquence conforme"));
    }
    if (ajouts > (b.ajouts ?? 0)) comptes.append(el("span", "ecart", " quota dépassé"));
    // replié par défaut : un en-tête haut à droite creuserait un trou dans le récit à gauche
    const det = el("details", "replie");
    det.append(el("summary", null, [b.lieu, b.temps].filter(Boolean).join(" · ") || "le plan"), meta);
    if (b.sequence?.length) {
      const q = el("p", "sb-sequence");
      q.append(el("span", "nom", "séquence déclarée"), document.createTextNode(b.sequence.join("  /  ")));
      det.append(q);
    }
    if (b.note) det.append(el("p", "sb-note", b.note));
    dp.append(h, det, comptes);
    grille.append(gp, el("div", "par-gout plan-debut"), dp);

    // une ligne par rang : paragraphe | micro-récit
    const n = Math.max(recits.length, ids.length);
    for (let i = 0; i < n; i++) {
      const id = ids[i];
      const l = id ? a.links.recit[id] : null;
      const g = el("div", "par-texte ligne");
      const d = el("div", "par-sb ligne");
      const gout = el("div", "par-gout ligne" + (i === n - 1 ? " plan-fin" : ""));
      if (id) {
        for (const x of [g, gout, d]) x.dataset.block = id;
        const copie = paras[id]?.cloneNode(true);
        copie?.removeAttribute("data-block");       // la ligne porte l'id, pas le <p>
        g.append(copie ?? el("p", "mut", "(paragraphe introuvable)"));
        if (l.ajout) g.classList.add("ajout");
      } else {
        g.append(el("p", "mut orphelin", "aucun paragraphe à ce rang"));
      }
      const rec = el("span", "sb-recit", recits[i] ?? "— (pas de micro-récit)");
      if (recits[i] != null) {
        rec.title = "Double-clic pour recadrer ce micro-récit";
        rec.ondblclick = (e) => { e.stopPropagation(); editeRecit(rec, b.id, i, id); };
      }
      d.append(el("span", "sb-rang", String(i + 1)), rec);
      const cf = conformite(b, ids)?.[i];
      if (cf && !cf.ok) {
        const w = el("span", "sb-seq-ecart", `séquence déclarée : ${cf.attendu} — le texte dit : ${cf.reel || "rien"}`);
        d.append(w);
      }
      if (l) {
        const puces = el("span", "sb-puces");
        if (l.ajout) puces.append(el("span", "puce ajout", "ajout · " + (b.ajouts ?? 0) + " permis"));
        for (const x of l.assertions ?? []) puces.append(puce(x));
        d.append(puces);
        const detail = el("div", "sb-assertions");
        for (const x of l.assertions ?? []) {
          const bloc = el("div", "assertion-appuis");
          bloc.append(assertion(x), ...appuisEssai(x));
          detail.append(bloc);
        }
        d.append(detail);
        // ajouter une assertion à ce paragraphe, à la fin de sa liste (même s'il n'en a aucune)
        const plusA = el("button", "pan-lien sb-plus-assertion", "＋ assertion");
        plusA.title = "ajouter une assertion portée par ce paragraphe, à la fin de sa liste";
        plusA.onclick = (e) => { e.stopPropagation(); plusA.replaceWith(formAssertionBloc(id)); };
        d.append(plusA);
      }
      grille.append(g, gout, d);
    }
  }
  if (!(br.beats ?? []).length) {            // migré sans cadre : pas de plans, le texte est dans la vue récit
    const m = el("div", "par-texte");
    const a = el("a", null, "lire le récit");
    a.href = `#${etat.slug}/recit/texte`;
    m.append(el("p", "mut", "Pas encore de storyboard : ce chapitre a été migré avec ses textes seuls, sans cadre. "), a);
    grille.append(m, el("div", "par-gout"), el("div", "par-sb"));
  }

  if (br.constraints?.length) {
    const d = el("div", "par-sb par-pied");
    d.append(el("h2", null, "Interdits propres au storyboard"));
    const ul = el("ul");
    for (const x of br.constraints) ul.append(el("li", null, x));
    d.append(ul);
    grille.append(el("div", "par-texte par-pied"), el("div", "par-gout"), d);
  }
  page.append(grille);
}

const NOMS_PLAN = { title: "titre", sequence: "séquence déclarée (séparée par /)" };

// Un champ du plan, modifiable : enregistré dans brief.yaml en quittant le champ.
function champPlan(pid, k, valeur) {
  const d = el("label", "champ-edit champ-plan");
  d.append(el("span", "nom", NOMS_PLAN[k] ?? k));
  const x = el("textarea");
  x.value = valeur ?? "";
  x.rows = 1;
  x.placeholder = "—";
  setTimeout(() => ajuste(x), 0);
  x.addEventListener("input", () => ajuste(x));
  x.addEventListener("change", async () => {
    const r = await enregistrePlan(pid, { [k]: x.value });
    if (r) {
      d.classList.add("enregistre");
      setTimeout(() => d.classList.remove("enregistre"), 1200);
      etat.garde = null;                   // la vue parallèle se redessine avec le nouveau cadre
      refaitStoryboard();
    }
  });
  d.append(x);
  return d;
}

// La séquence déclarée d'un plan, morceau par morceau (un par paragraphe), comparée à ce que
// dit le texte (les assertions de chaque paragraphe, dans links.yaml). null : pas de séquence.
function conformite(b, ids) {
  const seq = b.sequence ?? [];
  if (!seq.length) return null;
  const liens = etat.atelier.links.recit;
  return ids.map((id, i) => {
    const g = (seq[i] ?? "").trim();
    const attendu = /^ajout/.test(g) ? "ajout" : g.split(",").map((x) => x.trim()).filter(Boolean).join(",");
    const l = liens[id] ?? {};
    const reel = l.ajout ? "ajout" : (l.assertions ?? []).join(",");
    return { attendu: g || "(rien)", reel, ok: attendu === reel };
  });
}

// La séquence telle que le texte la dit aujourd'hui : de quoi la déclarer d'un clic.
function sequenceActuelle(b) {
  const ids = parPlan()[b.id] ?? [];
  return ids.map((id, i) => {
    const l = etat.atelier.links.recit[id] ?? {};
    return l.ajout ? "ajout : " + (b.recits?.[i] ?? "") : (l.assertions ?? []).join(",");
  });
}

// Redessiner la vue parallèle sans perdre sa place (après un recadrage).
async function refaitStoryboard() {
  if (etat.version !== "storyboard") return;
  const y = zone().scrollTop;
  etat.garde = null;
  await storyboard(document.getElementById("page"));
  poseAnnotations();
  marquesDemandes();
  marquesValidation();
  if (etat.bloc) document.querySelectorAll(`#page [data-block="${etat.bloc}"]`).forEach((x) => x.classList.add("choisi"));
  zone().scrollTo(0, y);
}

// L'en-tête du storyboard, dans la colonne de détail : chaque champ s'enregistre en le quittant.
function panneauBrief() {
  const br = etat.atelier.brief;
  const f = panneau("En-tête du storyboard");
  f.append(el("p", "mut petit", "Modifiable : la prochaine réécriture lira ce cadre. Noté au journal."));
  const groupe = (titre) => f.append(el("h5", null, titre));
  groupe("Intention");
  for (const [k, v] of Object.entries(br.intent ?? {})) f.append(champBrief(`intent.${k}`, k.replace(/_/g, " "), v));
  groupe("Tenue");
  for (const [k, v] of Object.entries(br.tenue ?? {})) f.append(champBrief(`tenue.${k}`, k.replace(/_/g, " "), v));
  groupe("Ce qui est suivi");
  f.append(champBrief("suivi", "suivi (markdown : **gras**)", br.suivi));
  groupe("Contraintes du storyboard");
  f.append(champBrief("constraints", "une par ligne", (br.constraints ?? []).join("\n")));
  groupe("Mots interdits");
  f.append(champBrief("interdits", "séparés par des virgules", (br.interdits ?? []).join(", ")));
  groupe("Formules réservées");
  f.append(champBrief("derogations", "une par ligne ; Claude ne les reformule pas", (br.derogations ?? []).join("\n")));
  groupe("Fiches du chapitre");
  const puces = el("div", "pastilles");
  puces.append(...(br.fiches ?? []).map((x) => puceFiche(x)));
  f.append(puces, champBrief("fiches", "slugs de kb/fiches/, séparés par des virgules ; données à Claude en premier",
    (br.fiches ?? []).join(", ")));
}

function champBrief(cle, nom, valeur) {
  const d = el("label", "champ-edit champ-plan");
  d.append(el("span", "nom", nom));
  const x = el("textarea");
  x.value = valeur ?? "";
  x.rows = 1;
  setTimeout(() => ajuste(x), 0);
  x.addEventListener("input", () => ajuste(x));
  x.addEventListener("change", async () => {
    const r = await fetch(`/api/chapitres/${etat.slug}/brief`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ champs: { [cle]: x.value }, empreinte: etat.atelier.empreinte_brief }) });
    if (r.status === 409) { alert("brief.yaml a changé ailleurs : rechargement."); etat.garde = null; await ouvre(etat.slug); return; }
    if (!r.ok) { alert("échec : " + ((await r.json().catch(() => ({}))).detail ?? r.status)); return; }
    etat.atelier = await api(`/chapitres/${etat.slug}/atelier`);
    d.classList.add("enregistre");
    setTimeout(() => d.classList.remove("enregistre"), 1200);
    refaitStoryboard();
  });
  d.append(x);
  return d;
}

// Recadrer un micro-récit sur place ; la réécriture le lira à la prochaine demande.
function editeRecit(span, pid, rang, bloc) {
  const z = el("textarea", "annot-texte sb-edit");
  z.value = span.textContent;
  const act = el("div", "annot-actions");
  const ok = el("button", "bouton", "Recadrer");
  const non = el("button", "pan-lien", "annuler");
  act.append(ok, non, el("span", "mut petit", "⌘↵ · Échap"));
  const boite = el("div", "sb-edition");
  boite.append(z, act);
  span.replaceWith(boite);
  ajuste(z);
  z.focus();
  z.addEventListener("input", () => ajuste(z));
  const annule = () => boite.replaceWith(span);
  non.onclick = annule;
  z.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.stopPropagation(); annule(); }
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) ok.click();
  });
  ok.onclick = async () => {
    const r = await enregistrePlan(pid, {}, { [rang]: z.value });
    if (!r) return;
    span.textContent = z.value.trim();
    boite.replaceWith(span);
    // le texte ne suit pas encore : proposer de le réécrire selon ce nouveau cadre
    if (bloc) {
      const sugg = el("button", "pan-lien sb-suggestion", "↻ réécrire ce paragraphe selon ce micro-récit");
      sugg.onclick = (e) => { e.stopPropagation(); sugg.replaceWith(formDemande({ portee: "paragraphe", blocs: [bloc] })); };
      span.after(sugg);
    }
  };
}

async function enregistrePlan(pid, champs, recits = {}) {
  const r = await fetch(`/api/chapitres/${etat.slug}/plans/${pid}`, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ champs, recits, empreinte: etat.atelier.empreinte_brief }) });
  if (r.status === 409) { alert("brief.yaml a changé ailleurs : rechargement."); etat.garde = null; await ouvre(etat.slug); return null; }
  if (!r.ok) { alert("échec : " + ((await r.json().catch(() => ({}))).detail ?? r.status)); return null; }
  const res = await r.json();
  etat.atelier = await api(`/chapitres/${etat.slug}/atelier`);    // brief relu : la vue et la réécriture suivent
  return res;
}

// Survol : les trois cellules d'une ligne s'allument ensemble.
document.getElementById("page").addEventListener("mouseover", (e) => {
  const b = e.target.closest("[data-block]")?.dataset.block ?? null;
  if (b === etat.survol) return;
  etat.survol = b;
  document.querySelectorAll("#page .survol").forEach((x) => x.classList.remove("survol"));
  if (b) document.querySelectorAll(`#page [data-block="${b}"]`).forEach((x) => x.classList.add("survol"));
});

function assertion(id) {
  const x = etat.atelier.assertions[id];
  const d = el("div", "assertion cliquable " + (x?.statut ?? "inconnue"));
  d.dataset.assertion = id;
  d.title = "Détail de l'assertion";
  d.append(el("span", "aid", id), el("span", null, x ? x.texte : "absente du verrou"));
  if (x?.note) d.append(el("small", "note", x.note));
  return d;
}

// Markdown minimal du brief : **gras** seulement, et le texte reste du texte.
function md(para) {
  const p = el("p");
  para.split(/(\*\*[^*]+\*\*)/).forEach((m) => {
    if (m.startsWith("**")) p.append(el("strong", null, m.slice(2, -2)));
    else if (m) p.append(document.createTextNode(m.replace(/\s+/g, " ")));
  });
  return p;
}

// ------------------------------------------------------------------ panneau (3e colonne)

// En vue parallèle, la colonne de droite s'ouvre à la demande : détail d'une
// assertion (et les passages de l'essai qui l'étayent), ou détail d'un plan.

function puce(id) {
  const s = el("span", "puce", id);
  s.dataset.assertion = id;
  s.title = etat.atelier.assertions[id]?.texte ?? "";
  if (!essaiPour(id).length) s.classList.add("sans-essai");
  if (etat.atelier.assertions[id]?.ecart) s.classList.add("a-ecart");
  return s;
}

// Les passages de l'essai qui étayent une assertion : ils sont dans le verrou.
function essaiPour(id) {
  return etat.atelier?.assertions?.[id]?.essai ?? [];
}

function force(appui) {
  return el("span", "force " + (appui ?? "inconnu"), appui ?? "?");
}

function ecart(x) {
  if (!x?.ecart) return null;
  const d = el("div", "ecart-bloc " + x.ecart.type);
  d.append(el("span", "ecart-type", "écart · " + x.ecart.type), el("span", null, x.ecart.texte));
  return d;
}

// Les deux textes rendus du chapitre, parsés une fois : les appuis y puisent leurs
// phrases et leurs paragraphes sans refaire d'appel.
async function chargeDocs(slug) {
  for (const v of ["recit", "essai"]) {
    if (etat.docs[v]) continue;
    try {
      const t = await api(`/chapitres/${slug}/${v}`);
      etat.docs[v] = new DOMParser().parseFromString(t.html, "text/html");
    } catch { /* une version absente : ses appuis n'auront que l'id */ }
  }
}

// ------------------------------------------------------------------ appuis

// Un appui = un paragraphe de l'autre version qui porte l'assertion. Replié, il
// montre la phrase qui la porte (la plus proche du texte de l'assertion) ; déplié,
// le paragraphe entier avec cette phrase surlignée, ses notes et ses références.

const VIDES = new Set(("avec dans pour mais plus moins sans sous tout toute tous toutes elle elles " +
  "leur leurs cette celle celui ceux dont être était étaient avait avaient fait faire comme même " +
  "aussi encore très bien donc alors quand entre vers après avant depuis rien autre autres").split(" "));

function racines(s) {
  const out = new Set();
  for (let m of s.toLowerCase().match(/\d+(?:[.,]\d+)?|[a-zàâäçéèêëîïôöùûüœ'’-]+/g) ?? []) {
    if (/^\d/.test(m)) { out.add("#" + m.replace(",", ".")); continue; }
    m = m.split(/['’]/).pop();
    if (m.length < 4 || VIDES.has(m)) continue;
    out.add(m.normalize("NFD").replace(/[\u0300-\u036f]/g, "").slice(0, 6));
  }
  return out;
}

function phrases(texte) {
  return texte.replace(/\s+/g, " ").trim()
    .split(/(?<=[.!?…])\s+(?=[«A-ZÀ-ÖØ-Ý(])/).filter((x) => x.length > 2);
}

// La phrase d'un texte la plus proche d'une assertion.
function meilleure(texte, cible) {
  const c = racines(cible);
  let best = null, score = -1;
  for (const ph of phrases(texte)) {
    const r = racines(ph);
    let s = 0;
    for (const w of r) if (c.has(w)) s += w.startsWith("#") ? 2 : 1;
    s /= Math.sqrt(r.size || 1);
    if (s > score) { score = s; best = ph; }
  }
  return best;
}

function courte(cle) {
  const m = cle.match(/^([a-z-]+?)(\d{4})([a-z]?)$/);
  if (!m) return cle;
  return m[1].charAt(0).toUpperCase() + m[1].slice(1) + " " + m[2] + m[3];
}

// Le texte d'un nœud sans ses appels de note (sinon « l'océan22 »).
function texteSans(n) {
  const c = n.cloneNode(true);
  c.querySelectorAll("sup").forEach((s) => s.remove());
  return c.textContent;
}

// Une citation [@cle] s'affiche « Hunten 1973 », la référence complète en infobulle.
function citations(racine) {
  racine.querySelectorAll("cite[data-cle]").forEach((c) => {
    c.textContent = courte(c.dataset.cle);
    const ref = etat.sources[c.dataset.cle];
    if (ref) c.title = ref.replace(/<[^>]+>/g, "");
  });
}

// Notes appelées par un paragraphe (dans le document rendu).
function notesDe(doc, p, seulement) {
  return [...p.querySelectorAll('a[href^="#fn:"]')]
    .map((a) => a.getAttribute("href").slice(4))
    .filter((k) => !seulement || k === seulement)
    .map((k) => ({ cle: k, li: doc.getElementById("fn:" + k) }))
    .filter((n) => n.li);
}

// Surligne une phrase dans un élément, sans toucher au DOM (Custom Highlight API).
const SURLIGNES = typeof Highlight !== "undefined" ? new Highlight() : null;
if (SURLIGNES) CSS.highlights.set("appui", SURLIGNES);
function surligne(racine, phrase) {
  if (!SURLIGNES || !phrase) return;
  const norm = (s) => s.replace(/\s+/g, " ");
  const noeuds = [];
  let texte = "";
  const w = document.createTreeWalker(racine, NodeFilter.SHOW_TEXT);
  while (w.nextNode()) { noeuds.push([w.currentNode, texte.length]); texte += norm(w.currentNode.data); }
  const debut = texte.indexOf(norm(phrase).trim());
  if (debut < 0) return;
  const fin = debut + norm(phrase).trim().length;
  const pos = (i) => {
    for (let k = noeuds.length - 1; k >= 0; k--) {
      if (noeuds[k][1] <= i) return [noeuds[k][0], Math.min(i - noeuds[k][1], noeuds[k][0].length)];
    }
    return [noeuds[0][0], 0];
  };
  const r = new Range();
  r.setStart(...pos(debut));
  r.setEnd(...pos(fin));
  SURLIGNES.add(r);
}

// Un appui replié/dépliable. vers : "essai" (depuis une assertion du récit) ou "recit".
function appui(vers, bloc, assertionId, opts = {}) {
  const doc = etat.docs[vers];
  const cible = etat.atelier.assertions[assertionId]?.texte ?? "";
  const d = el("div", "appui");
  d.dataset.bloc = bloc;
  const tete = el("div", "appui-tete");
  const plier = el("button", "appui-plier", "▸");
  plier.title = "Déplier le passage";
  tete.append(plier);
  if (opts.appui) tete.append(force(opts.appui));
  if (vers === "recit") {
    const l = etat.atelier.links.recit[bloc];
    tete.append(el("span", "pan-meta", `récit · plan ${l?.plan ?? "?"} · § ${rangDe(bloc) + 1}`));
  }
  const aller = el("button", "pan-lien", vers === "essai" ? "ouvrir dans l'essai →" : "voir dans le récit →");
  aller.onclick = (e) => { e.stopPropagation(); vaVers(vers, bloc); };
  tete.append(aller);
  d.append(tete);

  const src = doc?.querySelector(`[data-block="${bloc}"]`);
  if (!src) { d.append(el("p", "mut", "^" + bloc)); return d; }
  const notes = notesDe(doc, src, opts.note);
  // la phrase : dans la note si l'appui est dans la note, sinon dans le paragraphe
  const dansNote = opts.note && notes.length;
  const texteSrc = texteSans(dansNote ? notes[0].li : src);
  const ph = meilleure(texteSrc, cible);
  const toutes = phrases(texteSrc);
  const rang = toutes.indexOf(ph);
  const phrase = el("p", "appui-phrase");
  phrase.title = "Afficher tout le passage";
  if (dansNote) phrase.append(el("span", "appui-lieu", "note · "));
  if (rang > 0) phrase.append(el("span", "ellipse", "(…) "));
  phrase.append(document.createTextNode(ph ?? ""));
  if (rang < toutes.length - 1) phrase.append(el("span", "ellipse", " (…)"));
  d.append(phrase);

  const refs = [...new Set([...src.querySelectorAll("cite[data-cle]"),
    ...notesDe(doc, src).flatMap((n) => [...n.li.querySelectorAll("cite[data-cle]")])]
    .map((c) => c.dataset.cle))];
  if (refs.length) d.append(el("p", "appui-refs", "réf. " + refs.map(courte).join(" · ")));

  let plein = null;
  plier.onclick = (e) => {
    e.stopPropagation();
    if (!plein) {
      plein = el("div", "appui-plein");
      const copie = src.cloneNode(true);
      copie.removeAttribute("data-block");
      copie.querySelectorAll("a").forEach((a) => a.removeAttribute("href"));
      plein.append(copie);
      for (const n of notesDe(doc, src)) {
        const c = n.li.cloneNode(true);
        c.querySelectorAll(".footnote-backref").forEach((x) => x.remove());
        const div = el("div", "pan-note");
        div.append(el("span", "appui-lieu", "note · "), ...c.childNodes);
        plein.append(div);
      }
      if (refs.length) {
        const ul = el("ul", "appui-biblio");
        for (const k of refs) {
          const li = el("li");
          li.innerHTML = etat.sources[k] ?? `<code>${k}</code> — absente de la bibliographie`;
          const s = (etat.atelier.bibliographie ?? []).find((x) => x.cle === k);
          li.append(" ", liensSource(s?.doi, s?.ref ?? etat.sources[k]));
          ul.append(li);
        }
        plein.append(ul);
      }
      enrichit(plein);
      d.append(plein);
      surligne(copie, dansNote ? null : ph);
      if (dansNote) surligne(plein.querySelector(".pan-note"), ph);
    }
    const ouvert = d.classList.toggle("ouvert");
    plier.textContent = ouvert ? "▾" : "▸";
    phrase.hidden = ouvert;
  };
  phrase.onclick = (e) => { e.stopPropagation(); plier.onclick(e); };
  // replier depuis le texte déplié aussi (hors liens)
  d.addEventListener("click", (e) => {
    if (d.classList.contains("ouvert") && e.target.closest(".appui-plein") && !e.target.closest("a")) {
      e.stopPropagation();
      plier.onclick(e);
    }
  });
  return d;
}

// Les appuis d'une assertion dans l'essai, et dans le récit.
function appuisEssai(id) {
  const liste = essaiPour(id);
  if (!liste.length) return [el("p", "appui-vide", "aucun passage de l'essai")];
  return liste.map((l) => appui("essai", l.bloc, id, l));
}

function appuisRecit(id) {
  const blocs = Object.entries(etat.atelier.links.recit)
    .filter(([, l]) => (l.assertions ?? []).includes(id)).map(([b]) => b);
  if (!blocs.length) return [el("p", "appui-vide", "aucun paragraphe du récit")];
  return blocs.map((b) => appui("recit", b, id));
}

// Aller à un bloc dans une vue (en gardant l'état de celle qu'on quitte).
function vaVers(vue, bloc) {
  if (vue === "essai") etat.blocEssai = bloc; else etat.bloc = bloc;
  // le récit est déjà là, en vis-à-vis, dans la vue parallèle
  const ici = etat.version === vue || (vue === "recit" && etat.version === "storyboard");
  if (ici) choisis(bloc, true); else bascule(vue);
}

function panneau(titre) {
  document.body.dataset.panneau = "1";
  const f = document.getElementById("fiche");
  f.replaceChildren();
  const h = el("div", "pan-tete");
  const x = el("button", "fermer", "×");
  x.title = "Fermer";
  x.onclick = () => {
    delete document.body.dataset.panneau;
    document.querySelectorAll("#page .actif-pan").forEach((n) => n.classList.remove("actif-pan"));
    if (etat.version !== "storyboard") fiche(etat.version === "essai" ? etat.blocEssai : etat.bloc);
  };
  h.append(el("h4", null, titre), x);
  f.append(h);
  f.scrollTop = 0;
  return f;
}

function marque(sel) {
  document.querySelectorAll("#page .actif-pan").forEach((n) => n.classList.remove("actif-pan"));
  document.querySelectorAll(sel).forEach((n) => n.classList.add("actif-pan"));
}

async function panneauAssertion(id) {
  const a = etat.atelier;
  const x = a.assertions[id];
  marque(`#page [data-assertion="${id}"]`);
  const f = panneau("Assertion " + id);
  f.querySelector(".pan-tete h4")?.append(" ", boutonRef(`@chapitre/${etat.slug}/assertion/${id}`));
  if (!x) { f.append(el("p", "mut", "Absente du verrou.")); return; }
  const sec = a.verrou.sections.find((s) => s.id === x.section);
  f.append(el("p", "pan-meta", `${x.statut} · section ${x.section}${sec ? " — " + sec.title : ""}`));
  f.append(el("p", "pan-texte", x.texte));
  if (x.note) champ(f, "note", x.note);
  const ec = ecart(x);
  if (ec) f.append(ec);
  if (x.verifie) f.append(el("p", "mut petit", `vérifiée le ${x.verifie.date} (${x.verifie.verdict ?? "?"})`));
  const vl = liensDemandes((d) => (d.assertions ?? []).includes(id), "vérifications");
  if (vl) f.append(vl);
  const outils = el("div", "annot-actions assertion-outils");
  const mod = el("button", "pan-lien", "✎ modifier");
  mod.onclick = () => outils.replaceWith(formAssertion(id, x));
  const plus = el("button", "pan-lien", "＋ assertion après");
  plus.onclick = () => outils.replaceWith(formNouvelleAssertion(id));
  const ver = el("button", "pan-lien", "🔎 vérifier…");
  ver.onclick = () => outils.replaceWith(formVerif({ assertions: [id] }));
  outils.append(mod, plus, ver);
  f.append(outils);

  f.append(el("h5", null, "Dans le récit — portée par"));
  f.append(...appuisRecit(id).map((n) => avecDetache(n, "recit", id)));
  const br = etat.bloc;
  const lr = etat.atelier.links.recit?.[br];
  if (br && lr && !(lr.assertions ?? []).includes(id)) {
    const at = el("button", "pan-lien", `＋ attacher au paragraphe choisi du récit (^${br})`);
    at.onclick = () => lienAssertion(id, { version: "recit", bloc: br, action: "attacher" });
    f.append(at);
  }
  f.append(el("h5", null, "Dans l'essai — étayée par"));
  f.append(...appuisEssai(id).map((n) => avecDetache(n, "essai", id)));
  const be = etat.blocEssai;
  if (be && !essaiPour(id).some((l) => l.bloc === be)) {
    const ligne = el("div", "annot-actions");
    const sel = el("select", "livre-select");
    for (const v of ["direct", "partiel"]) { const o = el("option", null, v); o.value = v; sel.append(o); }
    const at = el("button", "pan-lien", `＋ attacher le paragraphe choisi de l'essai (^${be})`);
    at.onclick = () => lienAssertion(id, { version: "essai", bloc: be, action: "attacher", appui: sel.value });
    ligne.append(at, sel);
    f.append(ligne);
  }
}

// Un appui (récit ou essai) de l'assertion, avec de quoi le détacher.
function avecDetache(noeud, version, id) {
  const bloc = noeud.dataset?.bloc;
  if (!bloc) return noeud;
  const d = el("button", "pan-lien danger detache", "détacher");
  d.title = version === "recit" ? "ce paragraphe ne porte plus cette assertion" : "ce paragraphe n'étaie plus cette assertion";
  d.onclick = (e) => { e.stopPropagation(); lienAssertion(id, { version, bloc, action: "detacher" }); };
  noeud.querySelector(".appui-tete")?.append(d);
  return noeud;
}

async function lienAssertion(id, corps) {
  const r = await fetch(`/api/chapitres/${etat.slug}/assertions/${encodeURIComponent(id)}/liens`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...corps, empreinte: etat.atelier.empreinte_verrou }) });
  await apresVerrou(r, id);
}

// Après un changement du verrou : relire l'atelier, l'état de validation, et rouvrir le détail.
async function apresVerrou(r, id) {
  if (r.status === 409) alert("verrou.yaml a changé ailleurs : rechargement.");
  else if (!r.ok) { alert("Refusé : " + ((await r.json().catch(() => ({}))).detail ?? r.status)); return; }
  etat.atelier = await api(`/chapitres/${etat.slug}/atelier`);
  etat.validation = await api(`/chapitres/${etat.slug}/validation`).catch(() => etat.validation);
  etat.garde = null;
  if (etat.version === "storyboard") await refaitStoryboard();
  else { marges(); marquesValidation(); }
  barreOutils();
  const res = r.ok ? await r.json().catch(() => ({})) : {};
  if (res.assertion ?? id) panneauAssertion(res.assertion ?? id);
}

const LIB_STATUT = { obligatoire: "obligatoire", supprimable: "supprimable", retiree: "retirée" };

function formAssertion(id, x) {
  const f = el("div", "form-demande");
  const texte = el("textarea", "annot-texte");
  texte.value = x.texte;
  const statut = el("select", "livre-select");
  for (const [v, lib] of Object.entries(LIB_STATUT)) {
    const o = el("option", null, lib);
    o.value = v;
    if (x.statut === v) o.selected = true;
    statut.append(o);
  }
  const note = el("textarea", "annot-texte petit-texte");
  note.value = x.note ?? "";
  note.placeholder = "note (sources, historique)";
  const motif = el("input", "dem-motif");
  motif.placeholder = "motif du changement (obligatoire pour retirer)";
  const ok = el("button", "bouton", "Enregistrer");
  const non = el("button", "pan-lien", "annuler");
  ok.onclick = async () => {
    const champs = { texte: texte.value, statut: statut.value };
    if (note.value !== (x.note ?? "")) champs.note = note.value;
    const r = await fetch(`/api/chapitres/${etat.slug}/assertions/${encodeURIComponent(id)}`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ champs, motif: motif.value, empreinte: etat.atelier.empreinte_verrou }) });
    await apresVerrou(r, id);
  };
  non.onclick = () => panneauAssertion(id);
  const act = el("div", "annot-actions");
  act.append(ok, non);
  f.append(el("span", "appui-lieu", `modifier ${id} — l'ancien texte est gardé dans la note, avec la date et le motif`),
    texte, el("span", "appui-lieu", "statut"), statut, el("span", "appui-lieu", "note"), note, motif, act);
  setTimeout(() => { ajuste(texte); ajuste(note); texte.focus(); }, 0);
  return f;
}

// Une assertion nouvelle pour un paragraphe du récit : le serveur la place après la dernière
// qu'il porte (ou, s'il n'en porte aucune, après celles des paragraphes qui le précèdent).
function formAssertionBloc(bloc) {
  const f = el("div", "form-demande sb-form-assertion");
  f.onclick = (e) => e.stopPropagation();
  const texte = el("textarea", "annot-texte");
  texte.placeholder = "ce que ce paragraphe doit dire (une assertion, un fait)";
  const statut = el("select", "livre-select");
  for (const v of ["obligatoire", "supprimable"]) { const o = el("option", null, v); o.value = v; statut.append(o); }
  const ok = el("button", "bouton", "Ajouter");
  const non = el("button", "pan-lien", "annuler");
  ok.onclick = async () => {
    const r = await fetch(`/api/chapitres/${etat.slug}/assertions`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bloc, texte: texte.value, statut: statut.value, porte_par: [bloc],
        empreinte: etat.atelier.empreinte_verrou }) });
    await apresVerrou(r, null);
  };
  non.onclick = () => refaitStoryboard();
  const act = el("div", "annot-actions");
  act.append(ok, statut, non);
  f.append(el("span", "appui-lieu", `nouvelle assertion portée par ^${bloc}, à la fin de sa liste`), texte, act);
  setTimeout(() => texte.focus(), 0);
  return f;
}

// Un plan sans assertion : la nouvelle va à la fin de la section du plan dans le verrou.
function formAssertionPlan(pid) {
  const f = el("div", "form-demande");
  const texte = el("textarea", "annot-texte");
  texte.placeholder = "ce que ce plan doit dire";
  const ok = el("button", "bouton", "Ajouter");
  ok.onclick = async () => {
    const r = await fetch(`/api/chapitres/${etat.slug}/assertions`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan: pid, texte: texte.value, statut: "obligatoire", porte_par: [],
        empreinte: etat.atelier.empreinte_verrou }) });
    await apresVerrou(r, null);
  };
  const act = el("div", "annot-actions");
  act.append(ok);
  f.append(el("span", "appui-lieu", `nouvelle assertion du plan ${pid} (à attacher ensuite à un paragraphe)`), texte, act);
  setTimeout(() => texte.focus(), 0);
  return f;
}

function formNouvelleAssertion(apres, blocsDefaut = null) {
  const f = el("div", "form-demande");
  const texte = el("textarea", "annot-texte");
  texte.placeholder = "ce que le récit doit dire (une assertion, un fait)";
  const statut = el("select", "livre-select");
  for (const v of ["obligatoire", "supprimable"]) { const o = el("option", null, v); o.value = v; statut.append(o); }
  // par défaut, portée par les mêmes paragraphes du récit que celle après laquelle elle vient
  const porteurs = blocsDefaut ?? Object.entries(etat.atelier.links.recit)
    .filter(([, l]) => (l.assertions ?? []).includes(apres)).map(([b]) => b);
  const choix = el("label", "dem-consulter");
  const cc = el("input");
  cc.type = "checkbox";
  cc.checked = porteurs.length > 0;
  choix.append(cc, document.createTextNode(porteurs.length ? ` portée par ${porteurs.map((b) => "^" + b).join(", ")} (comme ${apres})` : " (aucun paragraphe porteur)"));
  const motif = el("input", "dem-motif");
  motif.placeholder = "motif (facultatif)";
  const ok = el("button", "bouton", "Ajouter");
  const non = el("button", "pan-lien", "annuler");
  ok.onclick = async () => {
    const r = await fetch(`/api/chapitres/${etat.slug}/assertions`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ apres, texte: texte.value, statut: statut.value, porte_par: cc.checked ? porteurs : [],
        motif: motif.value, empreinte: etat.atelier.empreinte_verrou }) });
    await apresVerrou(r, apres);
  };
  non.onclick = () => panneauAssertion(apres);
  const act = el("div", "annot-actions");
  act.append(ok, non);
  f.append(el("span", "appui-lieu", `nouvelle assertion après ${apres} — identifiant suffixé (${apres}a…), rien n'est renuméroté`),
    texte, statut, choix, motif, act);
  setTimeout(() => texte.focus(), 0);
  return f;
}

async function panneauPlan(pid) {
  const a = etat.atelier;
  const b = (a.brief.beats ?? []).find((x) => x.id === pid);
  if (!b) return;
  marque(`#page [data-plan-titre="${pid}"]`);
  const f = panneau(`Plan ${b.id} — ${b.title}`);
  f.querySelector(".pan-tete h4")?.append(" ", boutonRef(`@chapitre/${etat.slug}/plan/${b.id}`));
  f.append(el("p", "mut petit", "Modifiable : la prochaine réécriture lira ce cadre."));
  for (const k of ["title", "lieu", "temps", "ambiance", "attaque", "chute"]) f.append(champPlan(pid, k, b[k]));
  const ids = parPlan()[pid] ?? [];
  const ajouts = ids.filter((i) => a.links.recit[i].ajout).length;
  champ(f, "comptes", `${b.recits?.length ?? 0} micro-récits · ${ids.length} paragraphes · ` +
    `ajouts ${ajouts}/${b.ajouts ?? 0}`);
  const cs = champPlan(pid, "sequence", (b.sequence ?? []).join("  /  "));
  f.append(cs);
  f.append(el("p", "mut petit", "Un morceau par paragraphe, dans l'ordre du plan : les assertions qu'il dit, " +
    "dans l'ordre où il les dit (« ajout : … » = paragraphe hors verrou)."));
  const actuelle = el("button", "pan-lien", "déclarer l'ordre actuel du texte");
  actuelle.title = sequenceActuelle(b).join("  /  ");
  actuelle.onclick = () => {
    const z = cs.querySelector("textarea");
    z.value = sequenceActuelle(b).join("  /  ");
    ajuste(z);
    z.dispatchEvent(new Event("change"));
  };
  f.append(actuelle);
  f.append(champPlan(pid, "note", b.note));

  f.append(el("h5", null, `Assertions du plan (${b.assertions?.length ?? 0})`));
  const manquent = [];
  for (const id of b.assertions ?? []) {
    const d = assertion(id);
    if (!essaiPour(id).length) { d.classList.add("sans-essai"); manquent.push(id); }
    const ec = ecart(etat.atelier.assertions[id]);
    if (ec) d.append(ec);
    f.append(d);
  }
  if (manquent.length) {
    f.append(el("p", "mut petit", `Sans appui dans l'essai : ${manquent.join(", ")}.`));
  }
  const derniere = (b.assertions ?? []).slice(-1)[0];
  const plusA = el("button", "pan-lien", "＋ assertion dans ce plan…");
  plusA.onclick = () => plusA.replaceWith(derniere ? formNouvelleAssertion(derniere) : formAssertionPlan(pid));
  f.append(plusA);
  const re = el("button", "pan-lien", "↻ réécrire le plan…");
  re.onclick = () => re.replaceWith(formDemande({ portee: "plan", plan: pid }));
  f.append(re);
}

document.getElementById("fiche").addEventListener("click", (e) => {
  const d = e.target.closest("[data-assertion]");
  if (d) panneauAssertion(d.dataset.assertion);
});

// ------------------------------------------------------------------ fiche

function fiche(id) {
  ficheBase(id);
  const vue = etat.version;
  if (!etat.atelier || !(vue === "recit" || (vue === "essai" && etat.essaiMode === "texte"))) return;
  // le travail (les annotations) avant la référence (brief, plan, appuis)
  const f = document.getElementById("fiche");
  const s = id ? listeAnnotations(id) : listeChapitre();
  const tete = f.querySelector(":scope > h4");
  if (tete) tete.after(s); else f.prepend(s);
  const ev = id && etatDuBloc(id);
  if (ev) s.before(ev);
}

function ficheBase(id) {
  if (etat.version === "storyboard") return;      // la colonne y sert de panneau
  const f = document.getElementById("fiche");
  f.replaceChildren();
  const a = etat.atelier;
  if (!a) {
    f.append(el("p", "mut", "Chapitre pas encore migré : pas de brief, pas de verrou."));
    return;
  }
  if (!id) {
    const br = a.brief;
    f.append(el("h4", null, "Brief"));
    for (const [k, v] of Object.entries(br.intent ?? {})) champ(f, k.replace(/_/g, " "), v);
    for (const [k, v] of Object.entries(br.tenue ?? {})) champ(f, k.replace(/_/g, " "), v);
    const fc = blocFiches("Fiches du chapitre", br.fiches ?? [], "Aucune fiche listée dans le brief.");
    const nf = el("button", "pan-lien", "◇ il manque une fiche…");
    nf.onclick = () => nf.replaceWith(formFiche({ chapitres: [etat.slug] }));
    fc.append(nf);
    f.append(fc);
    f.append(el("p", "mut petit",
      `${Object.keys(a.assertions).length} assertions · ${br.beats?.length ?? 0} plans · ` +
      (etat.version === "storyboard" ? "cliquer un micro-récit" : "cliquer un paragraphe") +
      " pour sa fiche."));
    return;
  }
  const version = etat.version === "storyboard" ? "recit" : etat.version;
  const l = a.links?.[version]?.[id];
  f.append(el("h4", null, "Bloc ^" + id));
  if (version === "essai") {
    // les fiches de ce passage : celles des œuvres citées par ses notes
    const fs = fichesDuBloc(id);
    if (fs.length) f.append(blocFiches("Fiches de ce passage", fs, null, "par les œuvres que citent ses notes"));
  }
  if (!l) {
    f.append(el("p", "mut", version === "essai"
      ? "Aucune assertion du verrou n'est rapprochée de ce passage."
      : "Aucun lien pour ce bloc."));
    return;
  }
  if (version === "essai") {
    f.append(el("p", "mut petit", "Assertions du verrou que ce passage étaye, et ce qu'en dit le récit."));
    for (const x of l.assertions ?? []) {
      const d = assertion(x);
      d.prepend(force(l.appuis?.[x]));
      const bloc = el("div", "assertion-appuis");
      bloc.append(d, ...appuisRecit(x));
      f.append(bloc);
    }
    return;
  }
  const beat = (a.brief.beats ?? []).find((x) => x.id === l.plan);
  if (beat) {
    f.append(el("h5", null, `Plan ${beat.id} — ${beat.title}`));
    const recit = beat.recits?.[rangDe(id)];
    if (recit) champ(f, "micro-récit", recit);
    for (const k of ["lieu", "temps", "ambiance"]) if (beat[k]) champ(f, k, beat[k]);
  }
  if (l.ajout) {
    f.append(el("p", "ajout-etiquette", "Ajout hors verrou — quota du plan : " + (beat?.ajouts ?? "?")));
  }
  for (const x of l.assertions ?? []) {
    const bloc = el("div", "assertion-appuis");
    bloc.append(assertion(x), ...appuisEssai(x));
    f.append(bloc);
  }
}

function champ(parent, nom, valeur) {
  const d = el("div", "champ");
  d.append(el("span", "nom", nom), el("span", null, valeur));
  parent.append(d);
}

// ------------------------------------------------------------------ annotations

// Une annotation vise un paragraphe (^id) et, si l'on a sélectionné un passage, une
// citation avec quelques caractères de contexte. Le surlignage passe par la Custom
// Highlight API : aucun nœud n'est ajouté au texte. Une citation introuvable rend
// l'annotation « orpheline » : elle reste listée, jamais perdue.

const H_ANNOT = typeof Highlight !== "undefined" ? new Highlight() : null;
const H_RESOLUE = typeof Highlight !== "undefined" ? new Highlight() : null;
const H_FOCUS = typeof Highlight !== "undefined" ? new Highlight() : null;
if (H_ANNOT) {
  CSS.highlights.set("annotation", H_ANNOT);
  CSS.highlights.set("annotation-resolue", H_RESOLUE);
  CSS.highlights.set("annotation-focus", H_FOCUS);
}

const TYPES = { "remarque": "remarque", "question": "question", "a-reecrire": "à réécrire" };
const norm = (s) => (s ?? "").replace(/\s+/g, " ");
const plie = (s) => norm(s).toLowerCase().replace(/[’‘]/g, "'").replace(/[«»“”]/g, '"');

// Le texte d'un paragraphe, sans les appels de note, normalisé (espaces), avec pour
// chaque caractère normalisé sa place (nœud, décalage) dans le DOM.
function indexe(p) {
  const places = [];
  let texte = "";
  const w = document.createTreeWalker(p, NodeFilter.SHOW_TEXT, {
    acceptNode: (n) => n.parentElement.closest("sup, .marge, .panneau-bloc") ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,
  });
  let blanc = false;
  while (w.nextNode()) {
    const n = w.currentNode;
    for (let i = 0; i < n.data.length; i++) {
      const c = n.data[i];
      if (/\s/.test(c)) {
        if (blanc) continue;
        blanc = true;
        texte += " ";
      } else {
        blanc = false;
        texte += c;
      }
      places.push([n, i]);
    }
  }
  return { texte, places };
}

// Retrouve la citation d'une annotation dans son paragraphe : exacte, puis sans
// casse ni typographie ; entre plusieurs occurrences, le contexte départage.
function ancre(p, a) {
  if (!a.citation) return null;
  const { texte, places } = indexe(p);
  for (const f of [norm, plie]) {
    const t = f(texte), q = f(a.citation).trim();
    if (!q) return null;
    const occ = [];
    for (let i = t.indexOf(q); i >= 0; i = t.indexOf(q, i + 1)) occ.push(i);
    if (!occ.length) continue;
    const score = (i) => (f(a.avant) && t.slice(0, i).endsWith(f(a.avant)) ? 2 : 0)
      + (f(a.apres) && t.slice(i + q.length).startsWith(f(a.apres)) ? 1 : 0);
    const i = occ.sort((x, y) => score(y) - score(x))[0];
    const [n1, o1] = places[i], [n2, o2] = places[i + q.length - 1];
    const r = new Range();
    r.setStart(n1, o1);
    r.setEnd(n2, o2 + 1);
    return r;
  }
  return false;                                   // introuvable : orpheline
}

// Ce qu'une sélection dans un paragraphe donne comme ancre.
function capture(p, sel) {
  const r = sel.getRangeAt(0);
  const pre = new Range();
  pre.setStart(p, 0);
  pre.setEnd(r.startContainer, r.startOffset);
  const sans = (range) => {
    const d = document.createElement("div");
    d.append(range.cloneContents());
    d.querySelectorAll("sup, .marge, .panneau-bloc").forEach((x) => x.remove());
    return norm(d.textContent);
  };
  const { texte } = indexe(p);
  const debut = sans(pre).length;
  const citation = sans(r).trim();
  const i = texte.indexOf(citation, Math.max(0, debut - 2));
  const d0 = i >= 0 ? i : debut;
  return {
    citation,
    avant: texte.slice(Math.max(0, d0 - 30), d0),
    apres: texte.slice(d0 + citation.length, d0 + citation.length + 30),
  };
}

// La version annotée dans la vue courante : la vue parallèle montre le récit.
function versionVue() {
  return etat.version === "storyboard" ? "recit" : etat.version;
}

// L'élément qui porte le texte d'un paragraphe : le <p> (récit, essai), ou la
// cellule de texte de sa ligne (vue parallèle).
function blocEl(bloc) {
  return etat.version === "storyboard"
    ? document.querySelector(`#page .par-texte.ligne[data-block="${bloc}"]`)
    : document.querySelector(`#page [data-block="${bloc}"]`);
}

function blocDe(noeud) {
  const e = noeud?.nodeType === 1 ? noeud : noeud?.parentElement;
  if (!e || e.closest(".panneau-bloc, .notes-marge, .par-sb")) return null;
  return etat.version === "storyboard"
    ? e.closest("#page .par-texte.ligne[data-block]")
    : e.closest("#page [data-block]");
}

// Les paragraphes qui ont une réécriture en cours ou à décider portent une marque (clic : le tiroir).
function marquesDemandes() {
  document.querySelectorAll("#page [data-reecr]").forEach((p) => delete p.dataset.reecr);
  if (versionVue() !== "recit") return;
  for (const d of etat.demandes ?? []) {
    if (d.etat !== "prete" && d.etat !== "en_cours") continue;
    for (const b of d.blocs) {
      const e = blocEl(b);
      if (e && !e.dataset.reecr) { e.dataset.reecr = d.etat; e.dataset.demande = d.id; }
    }
  }
}

// Surligne les annotations de la vue et compte celles de chaque paragraphe.
function poseAnnotations() {
  if (!H_ANNOT) return;
  H_ANNOT.clear(); H_RESOLUE.clear(); H_FOCUS.clear();
  etat.rangesAnnot = [];
  const vue = versionVue();
  document.querySelectorAll("#page [data-annot]").forEach((p) => delete p.dataset.annot);
  etat.orphelines = [];
  for (const a of etat.annots.filter((x) => x.version === vue)) {
    const p = blocEl(a.bloc);
    if (!p) { etat.orphelines.push(a); continue; }
    const r = ancre(p, a);
    if (r === false) { etat.orphelines.push(a); }
    else if (r) { (a.etat === "resolue" ? H_RESOLUE : H_ANNOT).add(r); etat.rangesAnnot.push({ a, r }); }
    if (a.etat !== "resolue") p.dataset.annot = String(+(p.dataset.annot ?? 0) + 1);
    if (a.id === etat.annotFocus && r) H_FOCUS.add(r);
  }
}

function focusAnnotation(a) {
  etat.annotFocus = a.id;
  poseAnnotations();
  blocEl(a.bloc)?.scrollIntoView({ block: "center", behavior: "smooth" });
}

// L'annotation dont le passage surligné est sous le pointeur, s'il y en a une.
function annotationSous(e) {
  let noeud, decalage;
  if (document.caretPositionFromPoint) {
    const c = document.caretPositionFromPoint(e.clientX, e.clientY);
    if (!c) return null;
    noeud = c.offsetNode; decalage = c.offset;
  } else if (document.caretRangeFromPoint) {
    const c = document.caretRangeFromPoint(e.clientX, e.clientY);
    if (!c) return null;
    noeud = c.startContainer; decalage = c.startOffset;
  } else return null;
  const touchees = (etat.rangesAnnot ?? []).filter(({ r }) => {
    try { return r.isPointInRange(noeud, decalage); } catch { return false; }
  });
  // la plus précise (la plus courte) l'emporte quand des passages se chevauchent
  touchees.sort((x, y) => x.r.toString().length - y.r.toString().length);
  return touchees[0]?.a ?? null;
}

// Ouvrir une annotation : son paragraphe choisi, son panneau ouvert, elle en évidence.
function ouvreAnnotation(a) {
  etat.annotFocus = a.id;
  choisis(a.bloc);
  poseAnnotations();
  panneauBloc(a.bloc);
  document.querySelector("#page .panneau-bloc .annot.focus")?.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

// Aller à une annotation depuis la liste (dans la bonne vue, le bon chapitre).
function vaAnnotation(a) {
  const slug = a.chapitre ?? etat.slug;
  const vue = a.version === "essai" ? "essai" : "recit";
  if (slug === etat.slug && versionVue() === vue && (vue !== "essai" || etat.essaiMode === "texte")) {
    blocEl(a.bloc)?.scrollIntoView({ block: "center" });
    return ouvreAnnotation(a);
  }
  etat.annotApres = a.id;
  if (vue === "essai") etat.essaiMode = "texte";
  location.hash = vue === "essai" ? `${slug}/essai/texte` : `${slug}/recit`;
}

// Le bouton flottant « annoter » qui suit une sélection dans un paragraphe.
const boutonAnnoter = el("button", "bouton-annoter", "✎ annoter");
boutonAnnoter.hidden = true;
document.body.append(boutonAnnoter);
let selectionEnCours = null;

document.addEventListener("selectionchange", () => {
  const s = window.getSelection();
  const vue = etat.version;
  const permis = etat.atelier && !etat.accueil && etat.edition !== "corriger" &&
    (vue === "recit" || vue === "storyboard" || (vue === "essai" && etat.essaiMode === "texte"));
  if (!permis || !s.rangeCount || s.isCollapsed) { boutonAnnoter.hidden = true; return; }
  const r = s.getRangeAt(0);
  const p1 = blocDe(r.startContainer);
  const p2 = blocDe(r.endContainer);
  if (!p1 || p1 !== p2) { boutonAnnoter.hidden = true; return; }
  selectionEnCours = { p: p1, ancre: capture(p1, s) };
  if (!selectionEnCours.ancre.citation) { boutonAnnoter.hidden = true; return; }
  const b = r.getBoundingClientRect();
  boutonAnnoter.style.top = window.scrollY + b.top - 34 + "px";
  boutonAnnoter.style.left = window.scrollX + b.left + b.width / 2 - 40 + "px";
  boutonAnnoter.hidden = false;
});

boutonAnnoter.addEventListener("mousedown", (e) => e.preventDefault());   // garder la sélection
boutonAnnoter.addEventListener("click", () => {
  if (!selectionEnCours) return;
  const { p, ancre: an } = selectionEnCours;
  boutonAnnoter.hidden = true;
  choisis(p.dataset.block);
  compose({ version: versionVue(), bloc: p.dataset.block, ...an });
  window.getSelection().removeAllRanges();
});

// Le panneau d'un paragraphe, ouvert juste sous lui : ses annotations, et la saisie
// d'une nouvelle (ou la modification d'une existante). Posé à côté du paragraphe,
// jamais dedans — le texte du paragraphe reste la prose seule.
function panneauBloc(bloc, saisie = null) {
  document.querySelectorAll("#page .panneau-bloc").forEach((x) => x.remove());
  const cible = blocEl(bloc);
  if (!cible) return;
  const pan = el("div", "panneau-bloc");
  pan.dataset.pour = bloc;
  const tete = el("div", "pan-tete");
  const x = el("button", "fermer", "×");
  x.title = "Fermer (Échap)";
  x.onclick = () => pan.remove();
  tete.append(el("span", "appui-lieu", "annotations · ^" + bloc), boutonRef(`@chapitre/${etat.slug}/${versionVue()}^${bloc}`), x);
  pan.append(tete);
  if (saisie) pan.append(formulaire(saisie.ancre, saisie.existante, pan));
  const dl = versionVue() === "recit" && liensDemandes((x) => x.blocs.includes(bloc), "réécritures de ce paragraphe");
  if (dl) pan.append(dl);
  const liste = etat.annots.filter((a) => a.bloc === bloc && a.version === versionVue()
    && a.id !== saisie?.existante?.id);
  for (const a of liste.sort((m, n) => (m.etat > n.etat ? 1 : -1))) pan.append(carteAnnotation(a));
  if (!saisie) {
    const pied = el("div", "annot-actions");
    const plus = el("button", "pan-lien", "＋ annoter tout le paragraphe");
    plus.onclick = () => compose({ version: versionVue(), bloc, citation: "", avant: "", apres: "" });
    pied.append(plus);
    if (versionVue() === "recit") {
      const re = el("button", "pan-lien", "↻ réécrire le paragraphe…");
      re.onclick = () => { pied.replaceWith(formDemande({ portee: "paragraphe", blocs: [bloc] })); };
      pied.append(re);
    }
    pan.append(pied);
  }
  // dans la vue parallèle, la cellule de texte grandit ; ailleurs, le panneau suit le <p>
  if (etat.version === "storyboard") cible.append(pan); else cible.after(pan);
  pan.querySelector("textarea")?.focus();
  const r = pan.getBoundingClientRect();
  if (r.bottom > window.innerHeight) pan.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") document.querySelectorAll("#page .panneau-bloc").forEach((x) => x.remove());
});

document.getElementById("page").addEventListener("dblclick", (e) => {
  const h = e.target.closest("#page [data-section]");
  if (h && etat.version === "essai" && !h.querySelector("input")) editeTitreTexte(h);
});

// Les volets de gauche se replient ; leur état est retenu.
for (const b of document.querySelectorAll(".volet-titre")) {
  const v = b.closest(".volet");
  if (lirePref("atelier-volet-" + b.dataset.volet, "ouvert") === "replie") v.classList.add("replie");
  b.onclick = () => {
    v.classList.toggle("replie");
    ecrisPref("atelier-volet-" + b.dataset.volet, v.classList.contains("replie") ? "replie" : "ouvert");
  };
}

function compose(a, existante = null) {
  panneauBloc(a.bloc, { ancre: a, existante });
}

function formulaire(a, existante, pan) {
  const f = el("div", "annot-form");
  if (a.citation) f.append(el("blockquote", "annot-citation", a.citation));
  let type = existante?.type ?? "remarque";
  const types = el("div", "annot-types");
  for (const [k, v] of Object.entries(TYPES)) {
    const b = el("button", "puce" + (k === type ? " actif" : ""), v);
    b.onclick = () => {
      type = k;
      types.querySelectorAll("button").forEach((y) => y.classList.toggle("actif", y === b));
    };
    types.append(b);
  }
  const zone = el("textarea", "annot-texte");
  zone.placeholder = "Ce qui ne va pas, ce qu'il faudrait, pourquoi…";
  zone.value = existante?.texte ?? "";
  // les règles invoquées : choisies parmi les garde-fous de la version, ou créées ici
  const choisies = new Set(existante?.regles ?? []);
  const ligneR = el("div", "annot-regles");
  const dessine = () => {
    ligneR.replaceChildren(el("span", "appui-lieu", "règles"));
    for (const r of reglesDe(a.version)) {
      const b = el("button", "puce regle-puce" + (choisies.has(r.id) ? " actif" : ""), r.id);
      b.title = r.titre;
      b.onclick = () => { choisies.has(r.id) ? choisies.delete(r.id) : choisies.add(r.id); dessine(); };
      ligneR.append(b);
    }
    const nv = el("button", "pan-lien", "＋ nouvelle règle");
    nv.onclick = () => {
      const i = el("input", "dem-motif");
      i.placeholder = "titre de la règle, ↵ pour l'ajouter aux garde-fous";
      i.onkeydown = async (ev) => {
        if (ev.key !== "Enter" || !i.value.trim()) return;
        ev.preventDefault();
        const r = await fetch(`/api/regles/${a.version}`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ titre: i.value, texte: i.value, empreinte: etat.regles[a.version]?.empreinte ?? "" }) });
        if (!r.ok) { alert("échec : " + r.status); return; }
        const res = await r.json();
        etat.regles = await api("/regles").catch(() => etat.regles);
        choisies.add(res.cree.id);
        dessine();
      };
      nv.replaceWith(i);
      i.focus();
    };
    ligneR.append(nv);
  };
  dessine();
  const actions = el("div", "annot-actions");
  const ok = el("button", "bouton", existante ? "Enregistrer" : "Annoter");
  const non = el("button", "pan-lien", "annuler");
  actions.append(ok, non, el("span", "mut petit", "⌘↵ · Échap"));
  f.append(types, ligneR, zone, actions);
  const valide = async () => {
    ok.disabled = true;
    const r = existante
      ? await fetch(`/api/chapitres/${etat.slug}/annotations/${existante.id}`, {
          method: "PATCH", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ texte: zone.value, type, regles: [...choisies] }) })
      : await fetch(`/api/chapitres/${etat.slug}/annotations`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...a, texte: zone.value, type, regles: [...choisies] }) });
    if (!r.ok) { ok.disabled = false; alert("échec : " + r.status); return; }
    const faite = await r.json();
    await rechargeAnnotations();
    etat.annotFocus = faite.id;
    rafraichit(a.bloc, true);
  };
  ok.onclick = valide;
  zone.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) valide(); });
  non.onclick = () => rafraichit(a.bloc, true);
  return f;
}

// Après un changement : surlignage, fiche de droite, et le panneau du paragraphe s'il
// était ouvert (ou si on le demande).
function rafraichit(bloc, garderPanneau = false) {
  poseAnnotations();
  if (etat.version !== "storyboard") fiche(etat.version === "essai" ? etat.blocEssai : etat.bloc);
  const ouvert = document.querySelector("#page .panneau-bloc")?.dataset.pour;
  if (garderPanneau || ouvert === bloc) panneauBloc(bloc);
}

async function rechargeAnnotations() {
  etat.annots = await api(`/chapitres/${etat.slug}/annotations`).catch(() => etat.annots);
  const c = etat.chapitres.find((x) => x.slug === etat.slug);
  if (c) c.annotations = etat.annots.filter((a) => a.etat === "ouverte").length;
  sommaire();
  majCompteAnnotations();
  if (!document.getElementById("tiroir").hidden && document.querySelector("#tiroir .dans-liste, #tiroir .dem-filtres") &&
      document.querySelector("#tiroir h4")?.textContent.startsWith("Annotations")) tiroirAnnotations();
}

async function changeAnnotation(a, champs) {
  await fetch(`/api/chapitres/${etat.slug}/annotations/${a.id}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(champs) });
  await rechargeAnnotations();
  rafraichit(a.bloc);
}

function carteAnnotation(a, avecLieu = false) {
  const d = el("div", `annot ${a.type} ${a.etat}` + (a.id === etat.annotFocus ? " focus" : ""));
  const tete = el("div", "annot-tete");
  tete.append(el("span", "annot-type", TYPES[a.type] ?? a.type));
  if (a.etat === "resolue") tete.append(el("span", "annot-etat", "résolue"));
  if (etat.orphelines?.includes(a)) tete.append(el("span", "annot-orph", "orpheline"));
  tete.append(el("span", "annot-date", `${a.auteur ?? ""} · ${(a.modifie ?? a.cree ?? "").slice(0, 10)}`),
    boutonRef(`@chapitre/${a.chapitre ?? etat.slug}/annotation/${a.id}`));
  d.append(tete);
  setTimeout(() => lieRefs(d), 0);
  if (avecLieu) {
    const l = etat.atelier?.links?.[a.version]?.[a.bloc];
    d.append(el("span", "appui-lieu", `${a.version}${l?.plan ? " · plan " + l.plan : ""} · ^${a.bloc}`));
  }
  if (a.citation) {
    const q = el("blockquote", "annot-citation", a.citation);
    q.title = "Montrer dans le texte";
    q.onclick = () => focusAnnotation(a);
    d.append(q);
  }
  if (a.texte) d.append(el("p", "annot-corps", a.texte));
  const dl = liensDemandes((x) => (x.annotations ?? []).includes(a.id));
  if (dl) d.append(dl);
  if (a.regles?.length) {
    const rr = el("div", "annot-regles");
    for (const r of a.regles) rr.append(puceRegle(a.version, r));
    d.append(rr);
  }
  const act = el("div", "annot-actions");
  const bouton = (txt, f) => { const b = el("button", "pan-lien", txt); b.onclick = f; act.append(b); };
  bouton(a.etat === "resolue" ? "rouvrir" : "résoudre",
    () => changeAnnotation(a, { etat: a.etat === "resolue" ? "ouverte" : "resolue" }));
  bouton("modifier", () => compose(a, a));
  if (a.etat === "ouverte") {
    bouton("🔎 vérifier", () => { const fv = formVerif({ annotation: a.id }); act.after(fv); });
  }
  if (a.version === "recit" && a.etat === "ouverte") {
    bouton("↻ réécrire", () => lanceDemande({ portee: "annotation", annotation: a.id, mode: "retouche" }));
  }
  if (etat.orphelines?.includes(a) && a.citation) {
    bouton("rattacher au paragraphe", () => changeAnnotation(a, { citation: "", avant: "", apres: "" }));
  }
  bouton("supprimer", async () => {
    if (!confirm("Supprimer cette annotation ? (elle reste dans l'historique du journal)")) return;
    await fetch(`/api/chapitres/${etat.slug}/annotations/${a.id}`, { method: "DELETE" });
    await rechargeAnnotations();
    rafraichit(a.bloc);
  });
  if (avecLieu) bouton("aller →", () => vaAnnotation(a));
  d.append(act);
  return d;
}

// Les annotations d'un paragraphe, et de quoi en ajouter une sur tout le paragraphe.
function listeAnnotations(id) {
  const s = el("section", "annots");
  const dl = versionVue() === "recit" && liensDemandes((x) => x.blocs.includes(id), "réécritures de ce paragraphe");
  if (dl) s.append(dl);
  const liste = etat.annots.filter((a) => a.bloc === id && a.version === etat.version);
  const h = el("h5", null, `Annotations (${liste.length})`);
  s.append(h);
  for (const a of liste.sort((x, y) => (x.etat > y.etat ? 1 : -1))) s.append(carteAnnotation(a));
  const plus = el("button", "pan-lien", "＋ annoter ce paragraphe");
  plus.onclick = () => compose({ version: versionVue(), bloc: id, citation: "", avant: "", apres: "" });
  s.append(plus);
  if (!liste.length) s.append(el("p", "mut petit", "Ou sélectionner un passage dans le texte."));
  return s;
}

// Sans paragraphe choisi : toutes les annotations du chapitre dans cette version.
function listeChapitre() {
  const s = el("section", "annots");
  const toutes = etat.annots.filter((a) => a.version === etat.version);
  const ouvertes = toutes.filter((a) => a.etat === "ouverte");
  s.append(el("h5", null, `Annotations du chapitre (${ouvertes.length} ouvertes / ${toutes.length})`));
  if (etat.orphelines?.length) {
    s.append(el("p", "annot-orph-titre", `${etat.orphelines.length} orpheline(s) : leur passage a changé`));
  }
  const ordre = [...document.querySelectorAll("#page [data-block]")].map((p) => p.dataset.block);
  for (const a of toutes.sort((x, y) => ordre.indexOf(x.bloc) - ordre.indexOf(y.bloc))) {
    s.append(carteAnnotation(a, true));
  }
  if (!toutes.length) s.append(el("p", "mut petit", "Sélectionner un passage du texte pour l'annoter."));
  return s;
}

// ------------------------------------------------------------------ réécriture

// Une demande de réécriture part d'une annotation, d'un paragraphe ou d'un plan. Claude
// travaille côté serveur ; le tiroir suit la demande, montre les propositions mot à mot,
// et garde la décision — retenue ou non, avec son motif. Claude ne touche jamais au texte :
// c'est « retenir » qui l'écrit.

const MODES_R = { retouche: "retouche", reecriture: "réécriture" };

// Le modèle d'une demande : « par défaut » (réglage du livre) ou un autre, pour cette demande seulement.
function nomModele(m) {
  return etat.modeles?.modeles?.[m] ?? (m ? m.replace(/^claude-/, "") : "défaut de Claude Code");
}

function choixModele(genre, valeur = "") {
  const l = el("label", "dem-modele");
  const sel = el("select", "livre-select");
  const defaut = etat.modeles?.defaut?.[genre];
  const o0 = el("option", null, `modèle par défaut (${nomModele(defaut)})`);
  o0.value = "";
  sel.append(o0);
  for (const [m, nom] of Object.entries(etat.modeles?.modeles ?? {})) {
    const o = el("option", null, nom);
    o.value = m;
    if (m === valeur) o.selected = true;
    sel.append(o);
  }
  l.append(sel);
  l.title = "Pour cette demande seulement. Le défaut se règle sur la page du livre (section Claude).";
  return { noeud: l, valeur: () => sel.value || null };
}

async function chargeModeles() {
  etat.modeles = await api("/modeles").catch(() => null);
}

function formDemande(base) {
  const f = el("div", "form-demande");
  let mode = base.portee === "plan" ? "reecriture" : "retouche";
  const modes = el("div", "annot-types");
  for (const [k, v] of Object.entries(MODES_R)) {
    const b = el("button", "puce" + (k === mode ? " actif" : ""), v);
    b.title = k === "retouche" ? "changer le moins possible" : "tout reprendre, dans les limites du verrou";
    b.onclick = () => { mode = k; modes.querySelectorAll("button").forEach((y) => y.classList.toggle("actif", y === b)); };
    modes.append(b);
  }
  const zone = el("textarea", "annot-texte");
  zone.placeholder = "Consigne (facultatif) : plus sec, moins d'incises, garder l'image de…";
  const consulte = el("label", "dem-consulter");
  const cc = el("input");
  cc.type = "checkbox";
  cc.checked = true;                         // par défaut : Claude peut aller lire le livre
  consulte.append(cc, document.createTextNode(" Claude peut consulter le livre (essai, fiches, autres chapitres — plus lent)"));
  const mod = choixModele("reecriture");
  const go = el("button", "bouton", "↻ lancer");
  go.onclick = () => lanceDemande({ ...base, mode, consigne: zone.value, consulter: cc.checked, modele: mod.valeur() });
  const ann = el("button", "pan-lien", "annuler");
  ann.onclick = () => f.remove();
  const act = el("div", "annot-actions");
  act.append(go, ann);
  f.append(el("span", "appui-lieu", base.portee === "plan" ? `réécrire le plan ${base.plan}` : "réécrire le paragraphe"),
    modes, zone, consulte, mod.noeud, act);
  setTimeout(() => zone.focus(), 0);
  return f;
}

// Vérifier : une précision facultative, puis Claude cherche (le livre, puis le web).
// Les mots qui comptent (5 lettres et plus, sans accents) : pour rapprocher une citation d'une assertion.
function motsCles(s) {
  return new Set((s ?? "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").match(/[a-z]{5,}/g) ?? []);
}

// Depuis une annotation : les assertions de son paragraphe, à cocher. Pré-cochées, celles qui
// partagent le plus de mots avec la citation et la question — pas tout le paragraphe.
function choixAssertions(a) {
  const ids = (etat.atelier.links[a.version]?.[a.bloc]?.assertions ?? []).map(String);
  const q = motsCles((a.citation ?? "") + " " + (a.texte ?? ""));
  const score = (id) => [...motsCles(etat.atelier.assertions[id]?.texte)].filter((m) => q.has(m)).length;
  const max = Math.max(0, ...ids.map(score));
  const boite = el("div", "choix-assertions");
  const cases = ids.map((id) => {
    const l = el("label", "dem-consulter");
    const c = el("input");
    c.type = "checkbox";
    c.value = id;
    c.checked = max > 0 ? score(id) === max : ids.length === 1;
    l.append(c, document.createTextNode(` ${id} — ${(etat.atelier.assertions[id]?.texte ?? "").slice(0, 90)}`));
    boite.append(l);
    return c;
  });
  return { boite, choisies: () => cases.filter((c) => c.checked).map((c) => c.value), vide: !ids.length };
}

function formVerif(base) {
  const f = el("div", "form-demande");
  const ann = base.annotation ? etat.annots.find((x) => x.id === base.annotation) : null;
  const choix = ann ? choixAssertions(ann) : null;
  const mod = choixModele("verification");
  const zone = el("textarea", "annot-texte");
  zone.placeholder = "Précision (facultatif) : ce qui fait douter, ce qu'il faut trouver…";
  const go = el("button", "bouton", "🔎 lancer la vérification");
  go.onclick = async () => {
    const corps = { ...base, consigne: zone.value, modele: mod.valeur() };
    if (choix && !choix.vide) {
      corps.assertions = choix.choisies();
      if (!corps.assertions.length) { alert("Cocher au moins une assertion à vérifier."); return; }
    }
    go.disabled = true;
    const r = await fetch(`/api/chapitres/${etat.slug}/verifications`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps) });
    if (!r.ok) { go.disabled = false; alert("échec : " + ((await r.json().catch(() => ({}))).detail ?? r.status)); return; }
    const d = await r.json();
    await chargeDemandes();
    tiroir(d.id);
  };
  const non = el("button", "pan-lien", "annuler");
  non.onclick = () => f.remove();
  const act = el("div", "annot-actions");
  act.append(go, non);
  const lim = etat.modeles?.limites?.verification;
  f.append(el("span", "appui-lieu", choix && !choix.vide ? "vérifier — les assertions visées par l'annotation (moins il y en a, plus la recherche est courte)" :
    base.annotation ? "vérifier les assertions de ce paragraphe" : "vérifier " + base.assertions.join(", ")));
  if (choix && !choix.vide) f.append(choix.boite);
  f.append(zone, mod.noeud, el("p", "mut petit", "Recherche dans le livre puis sur le web (plusieurs minutes), dans un budget fixé par livre.yaml" +
    (lim ? ` (${lim.recherches ?? "?"} recherches, ${lim.pages ?? "?"} pages)` : "") + ". Rien n'est modifié sans toi."), act);
  setTimeout(() => zone.focus(), 0);
  return f;
}

async function lanceDemande(corps) {
  const r = await fetch(`/api/chapitres/${etat.slug}/demandes`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps) });
  if (!r.ok) { alert("échec : " + ((await r.json().catch(() => ({}))).detail ?? r.status)); return; }
  const d = await r.json();
  await chargeDemandes();
  marquesDemandes();
  tiroir(d.id);
}

async function chargeDemandes() {
  const avant = Object.fromEntries((etat.demandes ?? []).map((d) => [d.id, d.etat]));
  etat.demandes = etat.atelier ? await api(`/chapitres/${etat.slug}/demandes`).catch(() => []) : [];
  // une demande qui vient d'aboutir : le dire, même tiroir fermé
  for (const d of etat.demandes) {
    if (avant[d.id] === "en_cours" && d.etat !== "en_cours") avise(d);
  }
  clearTimeout(etat.veille);
  if (etat.demandes.some((d) => d.etat === "en_cours")) etat.veille = setTimeout(() => chargeDemandes().then(marquesDemandes), 8000);
  const n = etat.demandes.filter((d) => d.etat === "prete" || d.etat === "en_cours").length;
  const b = document.getElementById("b-demandes");
  b.textContent = n ? `↻ Demandes · ${n}` : "↻ Demandes";
  b.classList.toggle("a-decider", n > 0);
}

const LIB_TYPE_KB = { fiche: "◇ fiche", pistes: "◇ creuser", renvois: "⇄ renvois", reference: "🔎 référence", document: "⤓ original", plan: "✦ plan", redaction: "✎ rédaction" };
const ETIQ_DEM = { en_cours: "en cours", prete: "à décider", erreur: "erreur", remplacee: "remplacée",
  en_attente: "en attente", retiree: "retirée", abandonnee: "abandonnée", a_confirmer: "à confirmer" };

function avise(d) {
  const a = el("button", "avis", `${d.type === "verification" ? "🔎 Vérification" : "↻ Réécriture"} ${d.etat === "prete" ? "prête" : d.etat} — ${(d.titre ?? "").slice(0, 60)} · ouvrir`);
  a.onclick = () => { a.remove(); tiroir(d.id); };
  document.body.append(a);
  setTimeout(() => a.remove(), 15000);
}
function etiquetteDemande(d) {
  if (d.type === "naive" && d.etat === "decidee") return "close";
  return d.etat === "decidee" ? (d.decision?.proposition ? "retenue" + (d.type === "verification" ? "" : " " + d.decision.proposition) : "rejetée")
    : ETIQ_DEM[d.etat] ?? d.etat;
}

// Les réécritures qui touchent un paragraphe, ou qui traitent une annotation : des liens
// pour rouvrir le tiroir là où on les a laissées.
function liensDemandes(filtre, titre) {
  const ds = (etat.demandes ?? []).filter(filtre);
  if (!ds.length) return null;
  const s = el("div", "dem-liens");
  if (titre) s.append(el("span", "appui-lieu", titre));
  for (const d of ds.slice(0, 4)) {
    const b = el("button", "pan-lien dem-lien " + d.etat, `${d.type === "verification" ? "🔎" : "↻"} ${etiquetteDemande(d)} — ${(d.titre ?? d.portee).slice(0, 70)}`);
    b.title = d.titre ?? "";
    b.onclick = (e) => { e.stopPropagation(); tiroir(d.id); };
    s.append(b);
  }
  return s;
}

// La liste des annotations — tes notes sur le texte, distinctes des demandes faites à Claude
// (une demande peut partir d'une annotation ; la carte montre alors ce lien).
async function tiroirAnnotations() {
  clearTimeout(suivi);
  etat.tiroirMontre = null;
  clearTimeout(suivi);
  const t = document.getElementById("tiroir");
  t.hidden = false;
  document.body.dataset.tiroir = "1";
  const F = etat.filtresAnnot ??= { portee: etat.slug && etat.atelier ? "chapitre" : "livre", etat: "ouvertes", type: "tout" };
  let as = await api("/annotations").catch(() => []);
  if (F.portee === "chapitre") as = as.filter((a) => a.chapitre === etat.slug);
  t.replaceChildren(teteTiroir(F.portee === "livre" ? "Annotations du livre" : "Annotations du chapitre"));
  const filtre = (cle, options) => {
    const g = el("span", "groupe filtres");
    for (const [v, lib] of options) {
      const b = el("button", F[cle] === v ? "actif" : null, lib);
      b.onclick = () => { F[cle] = v; tiroirAnnotations(); };
      g.append(b);
    }
    return g;
  };
  const barre = el("div", "dem-filtres");
  barre.append(filtre("portee", [["chapitre", "ce chapitre"], ["livre", "tout le livre"]]),
    filtre("etat", [["ouvertes", "ouvertes"], ["resolues", "résolues"], ["toutes", "toutes"]]),
    filtre("type", [["tout", "tout"], ["remarque", "remarques"], ["question", "questions"], ["a-reecrire", "à réécrire"]]));
  t.append(barre);
  const garde = as.filter((a) => (F.etat === "toutes" || (F.etat === "ouvertes") === (a.etat === "ouverte"))
    && (F.type === "tout" || a.type === F.type));
  if (!garde.length) {
    t.append(el("p", "mut", as.length ? "Aucune annotation pour ces filtres." :
      "Aucune annotation. En mode ✎ annoter, sélectionner un passage du texte."));
    return;
  }
  const ordre = etat.chapitres.map((c) => c.slug);
  const parChap = new Map();
  for (const a of garde) { if (!parChap.has(a.chapitre)) parChap.set(a.chapitre, []); parChap.get(a.chapitre).push(a); }
  for (const slug of [...parChap.keys()].sort((x, y) => ordre.indexOf(x) - ordre.indexOf(y))) {
    const c = etat.chapitres.find((x) => x.slug === slug);
    const liste = parChap.get(slug).sort((x, y) => (x.version > y.version ? 1 : -1) || (x.cree > y.cree ? 1 : -1));
    t.append(el("h5", "dem-chapitre", `${c?.numero ?? ""} · ${c?.title ?? slug} — ${liste.length} annotation(s)`));
    for (const a of liste) {
      if (slug === etat.slug) {
        const carte = carteAnnotation(a, true);
        carte.classList.add("dans-liste");
        t.append(carte);
      } else {
        const l = el("button", "dem-ligne");
        const haut = el("span", "dem-haut");
        haut.append(el("span", "annot-type", TYPES[a.type] ?? a.type), el("span", "dem-etat", a.etat === "ouverte" ? "ouverte" : "résolue"),
          el("span", "annot-date", (a.cree ?? "").slice(0, 10)));
        l.append(haut);
        if (a.citation) l.append(el("span", "dem-titre-ligne", "« " + a.citation + " »"));
        if (a.texte) l.append(el("span", "dem-consigne", a.texte));
        l.onclick = () => vaAnnotation(a);
        t.append(l);
      }
    }
  }
}

function majCompteAnnotations() {
  const n = etat.chapitres.reduce((s, c) => s + (c.annotations || 0), 0);
  const b = document.getElementById("b-annotations");
  b.textContent = n ? `✎ Annotations · ${n}` : "✎ Annotations";
  b.title = `${n} annotation(s) ouverte(s) dans le livre`;
}

// Le tiroir : une demande (suivie jusqu'à la décision), ou l'historique du chapitre.
let suivi = null;
// Le « chapitre » d'une demande : les créations de fiche vivent dans kb/demandes (« _kb »).
function slugDe(ident) {
  return /^[fplrose]-/.test(String(ident ?? "")) ? "_kb" : etat.slug;
}

// Le tiroir ouvert est retenu (session du navigateur) : un rafraîchissement le rouvre.
function retiensTiroir(ident) {
  try {
    if (ident) sessionStorage.setItem("atelier-tiroir", JSON.stringify({ id: ident, slug: slugDe(ident) }));
    else sessionStorage.removeItem("atelier-tiroir");
  } catch { /* navigation privée */ }
}

async function tiroir(ident) {
  clearTimeout(suivi);
  etat.tiroirMontre = ident ?? null;
  retiensTiroir(ident);
  majCompteFiches();
  const t = document.getElementById("tiroir");
  t.hidden = false;
  document.body.dataset.tiroir = "1";
  if ((!etat.slug || !etat.atelier) && !/^[fplrose]-/.test(String(ident ?? ""))) {
    if (!ident) return historique(t, etat.wiki ? "fiches" : null);
    t.replaceChildren(teteTiroir("Réécritures"), el("p", "mut", "Ouvrir un chapitre de l'atelier."));
    return;
  }
  if (!ident) return historique(t);
  const d = await api(`/chapitres/${slugDe(ident)}/demandes/${ident}`);
  if (d.type === "verification") return tiroirVerif(t, d);
  if (d.type === "fiche") return tiroirFiche(t, d);
  if (d.type === "pistes") return tiroirPistes(t, d);
  if (d.type === "renvois") return tiroirRenvois(t, d);
  if (d.type === "reference") return tiroirReference(t, d);
  if (d.type === "naive") return tiroirNaif(t, d);
  if (d.type === "document") return tiroirDocument(t, d);
  if (d.type === "plan") return tiroirPlan(t, d);
  if (d.type === "redaction") return tiroirRedaction(t, d);
  t.replaceChildren(teteTiroir(`Réécriture · ${d.portee}${d.cible.plan ? " " + d.cible.plan : ""} · ${MODES_R[d.mode]}`, () => tiroir(null)));
  if (d.titre) t.append(el("p", "dem-titre", d.titre));
  const cible = el("div", "dem-cible");
  cible.append(el("span", "appui-lieu", d.cible.blocs.map((b) => "^" + b).join(" ")));
  if (d.consigne) cible.append(el("p", "annot-corps", "« " + d.consigne + " »"));
  for (const id of d.cible.annotations) {
    const a = etat.annots.find((x) => x.id === id);
    if (a) cible.append(el("p", "dem-annot", `${TYPES[a.type]} — ${a.citation ? "« " + a.citation + " » : " : ""}${a.texte}`));
  }
  t.append(cible);

  const avant = etat.demandes?.find((x) => x.id === d.id)?.etat;
  if (avant !== d.etat) chargeDemandes().then(marquesDemandes);      // l'état a bougé : badges à jour
  if (d.etat === "en_cours") {
    t.append(enDirect(d));
    suivi = setTimeout(() => rafraichitDirect(ident), 1500);
  } else if (d.etat === "erreur") {
    t.append(el("p", "annot-orph-titre", "Échec : " + d.erreur));
  } else {
    if (d.etat === "prete") {
      t.append(el("div", "que-faire", null));
      t.lastChild.append(el("h5", null, "Que faire ?"), el("p", "mut petit",
        "Lire les propositions (ce qui change est surligné). « Garder celle-ci » remplace le texte du récit " +
        "par cette proposition ; les annotations traitées sont résolues. Si aucune ne convient, le dire en bas, " +
        "avec le motif : il sert aux prochaines demandes."));
    }
    for (const p of d.propositions ?? []) t.append(carteProposition(d, p));
    if (d.etat === "prete") t.append(rejetTout(d));
  }
  if (d.decision) {
    const dec = el("div", "dem-decision");
    dec.append(el("strong", null, d.decision.proposition ? `Retenue : ${d.decision.proposition}` : "Aucune retenue"),
      document.createTextNode(d.decision.motif ? " — " + d.decision.motif : ""),
      el("span", "annot-date", " " + d.decision.date.slice(0, 16).replace("T", " ")));
    t.append(dec);
  }
  piedTiroir(t, d);
}

const VERDICT = { etabli: "établi", nuance: "nuancé", contredit: "contredit", introuvable: "introuvable" };

// Les réponses d'avant une poursuite de la recherche : repliées, pour comparer avec la nouvelle.
function reponsesPrecedentes(d) {
  const P = d.resultats_precedents ?? [];
  if (!P.length) return null;
  const det = el("details", "replie");
  det.append(el("summary", null, `${P.length > 1 ? P.length + " réponses précédentes" : "la réponse précédente"} (avant « poursuivre la recherche »)`));
  P.forEach((x, i) => {
    const b = el("div", "verif-precedente");
    b.append(el("span", "appui-lieu", `réponse ${i + 1} — ${x.date.slice(0, 16).replace("T", " ")}`));
    for (const h of x.resultat.hypotheses ?? []) {
      const tt = el("div", "annot-tete");
      tt.append(el("strong", null, h.assertion), el("span", "verdict " + h.verdict, VERDICT[h.verdict] ?? h.verdict),
        el("span", "mut petit", ` ${(h.sources ?? []).length} source(s), ${(h.sources ?? []).filter((s) => s.verifie).length} lue(s)`));
      b.append(tt, el("p", "annot-corps", h.resume));
    }
    const E = x.resultat.essai ?? {};
    if (E.texte) b.append(el("p", "mut petit", `essai (${E.action}) : ${E.texte.slice(0, 300)}${E.texte.length > 300 ? "…" : ""}`));
    det.append(b);
  });
  return det;
}

async function tiroirVerif(t, d) {
  const ident = d.id;
  t.replaceChildren(teteTiroir(`Vérification · ${d.cible.assertions.join(", ")}`, () => tiroir(null)));
  const cible = el("div", "dem-cible");
  for (const id of d.cible.assertions) {
    const x = etat.atelier.assertions[id];
    cible.append(el("p", "annot-corps", `${id} — ${x?.texte ?? "?"}`));
  }
  const a = etat.annots.find((y) => y.id === d.cible.annotation);
  if (a) cible.append(el("p", "dem-annot", `question — ${a.citation ? "« " + a.citation + " » : " : ""}${a.texte}`));
  if (d.consigne) cible.append(el("p", "annot-corps", "« " + d.consigne + " »"));
  t.append(cible);
  const prec = reponsesPrecedentes(d);
  if (prec) t.append(prec);
  const avant = etat.demandes?.find((y) => y.id === d.id)?.etat;
  if (avant !== d.etat) chargeDemandes().then(marquesDemandes);
  if (d.etat === "en_cours") {
    t.append(enDirect(d));
    suivi = setTimeout(() => rafraichitDirect(ident), 2000);
    return piedTiroir(t, d);
  }
  if (d.etat === "erreur") { t.append(el("p", "annot-orph-titre", "Échec : " + d.erreur)); return piedTiroir(t, d); }
  const R = d.resultat;

  // les verdicts, et leurs sources
  t.append(el("h5", null, "Verdicts"));
  for (const h of R.hypotheses ?? []) {
    const c = el("div", "verif-h " + h.verdict);
    const tt = el("div", "annot-tete");
    tt.append(el("strong", null, h.assertion), el("span", "verdict " + h.verdict, VERDICT[h.verdict] ?? h.verdict));
    c.append(tt, el("p", "annot-corps", h.resume));
    for (const s of h.sources ?? []) {
      const so = el("div", "verif-source");
      const ref = el("span", "verif-ref");
      ref.innerHTML = mdLigne(s.ref);
      so.append(ref);
      if (s.doi) { const l = el("a", "lien-ext", "doi ↗"); l.href = "https://doi.org/" + s.doi; l.target = "_blank"; so.append(" ", l); }
      if (s.url) { const l = el("a", "lien-ext", "page ↗"); l.href = s.url; l.target = "_blank"; so.append(" ", l); }
      so.append(el("span", s.verifie ? "verif-ok" : "verif-non", s.verifie ? " lu" : " non vérifié"));
      if (s.extrait) so.append(el("blockquote", "verif-extrait", s.extrait));
      c.append(so);
    }
    t.append(c);
  }

  if ((R.fiches_consultees ?? []).length) {
    t.append(el("h5", null, "Fiches consultées"));
    for (const f of R.fiches_consultees) {
      const p = el("p", "petit");
      p.append(puceFiche(f.fiche), " " + f.apport);
      t.append(p);
    }
  }
  if (d.etat !== "en_cours") {
    const ff = el("button", "pan-lien", "◇ en faire une fiche…");
    ff.title = "Une fiche nouvelle sur ce sujet, qui part des sources trouvées ici";
    ff.onclick = () => ff.replaceWith(formFiche({
      question: d.cible.assertions.map((a) => etat.atelier.assertions[a]?.texte ?? a).join(" ; "),
      chapitres: [etat.slug], depuis: d.id,
      sources_initiales: (R.hypotheses ?? []).flatMap((h) => h.sources ?? []) }));
    t.append(ff);
  }

  // l'essai : le passage proposé, et où
  const E = R.essai ?? {};
  t.append(el("h5", null, "Pour l'essai"));
  let place = null;
  if (E.action === "aucune" || !E.texte) {
    t.append(el("p", "mut", "Rien à ajouter. " + (E.justification ?? "")));
  } else {
    const plan = await api(`/chapitres/${etat.slug}/essai/plan`).catch(() => null);
    const lieux = [];                                    // [valeur, libellé, place]
    const parcourt = (s, ind) => {
      if (s.id) lieux.push([`s:${s.id}`, `${"  ".repeat(ind)}▸ à la fin de « ${s.titre} »`, { type: "section", id: s.id, place: "fin" }]);
      for (const b of s.blocs) lieux.push([`b:${b.id}`, `${"  ".repeat(ind + 1)}après « ${b.debut.slice(0, 50)} »`, { type: "bloc", id: b.id, place: "apres" }]);
      for (const e of s.enfants) parcourt(e, ind + 1);
    };
    if (plan) parcourt(plan.arbre, 0);
    const prop = E.action === "complement" ? null : (E.apres_bloc ? `b:${E.apres_bloc}` : `s:${E.section}`);
    const pl = el("div", "verif-place");
    if (E.action === "complement") {
      pl.append(el("span", "appui-lieu", `complète le paragraphe ^${E.bloc}`));
      const doc = etat.docs.essai;
      const src = doc?.querySelector(`[data-block="${E.bloc}"]`);
      if (src) pl.append(diff(texteSans(src), E.texte.replace(/\[\^[^\]]+\]/g, "")));
    } else {
      pl.append(el("span", "appui-lieu", "nouveau paragraphe — emplacement"));
      const sel = el("select", "livre-select verif-select");
      for (const [v, lib, pla] of lieux) {
        const o = el("option", null, lib + (v === prop ? "  (proposé)" : ""));
        o.value = v;
        if (v === prop) { o.selected = true; place = pla; }
        sel.append(o);
      }
      sel.onchange = () => { place = lieux.find((l) => l[0] === sel.value)?.[2]; };
      pl.append(sel);
      const p = el("p", "verif-texte");
      p.innerHTML = mdLigne(E.texte);
      pl.append(p);
    }
    for (const n of E.notes ?? []) {
      const nn = el("p", "pan-note");
      nn.innerHTML = `<span class="appui-lieu">note ${n.cle} · </span>` + mdLigne(n.texte);
      pl.append(nn);
    }
    pl.append(el("p", "dem-note", E.justification ?? ""));
    t.append(pl);
  }
  if (R.bibliographie?.length) {
    t.append(el("h5", null, "Bibliographie du chapitre — à ajouter"));
    const ul = el("ul", "appui-biblio");
    for (const b of R.bibliographie) { const li = el("li"); li.innerHTML = `<code>${b.cle}</code> ` + mdLigne(b.ref); ul.append(li); }
    t.append(ul);
  }
  t.append(el("h5", null, "Verrou"));
  for (const v of R.verrou ?? []) {
    const x = etat.atelier.assertions[v.assertion];
    const l = el("div", "verif-v");
    l.append(el("strong", null, `${v.assertion} · ${v.action}`));
    if (v.texte && v.texte !== x?.texte) l.append(diff(x?.texte ?? "", v.texte));
    if (v.motif) l.append(el("p", "dem-note", v.motif));
    t.append(l);
  }
  if (R.recit) {
    t.append(el("h5", null, "Récit"));
    t.append(el("p", "annot-corps", (R.recit.a_reecrire ? "À réécrire : " : "Rien à changer. ") + (R.recit.raison ?? "")));
  }

  // ce qu'il faut faire, dans l'ordre
  const blocsRecit = Object.entries(etat.atelier.links.recit)
    .filter(([, l]) => (l.assertions ?? []).some((z) => d.cible.assertions.includes(z))).map(([b]) => b);
  const faire = el("div", "que-faire");
  faire.append(el("h5", null, "Que faire ?"));
  const change = [];
  if (E.action === "complement") change.push(`compléter le paragraphe ^${E.bloc} de l'essai`);
  if (E.action === "ajout") change.push("ajouter un paragraphe à l'essai (à l'emplacement choisi ci-dessus)");
  if ((E.notes ?? []).length) change.push(`${E.notes.length} note(s)`);
  if ((R.bibliographie ?? []).length) change.push(`${R.bibliographie.length} œuvre(s) à la bibliographie du chapitre`);
  const verr = (R.verrou ?? []).filter((v) => v.action !== "rien");
  if (verr.length) change.push("verrou : " + verr.map((v) => `${v.assertion} ${v.action === "lier" ? "reliée" : v.action === "nuancer" ? "nuancée" : "corrigée"}`).join(", "));
  if (d.cible.annotation) change.push("ta question marquée résolue");
  const etape1 = el("div", "etape" + (d.decision ? " faite" : ""));
  etape1.append(el("span", "etape-n", "1"));
  const c1 = el("div");
  c1.append(el("strong", null, "Appliquer l'analyse à l'essai et au verrou"),
    el("p", "mut petit", change.length ? "Ce qui sera écrit : " + change.join(" ; ") + ". Le récit n'est pas modifié. Tout est noté au journal."
      : "Rien à écrire : l'analyse ne propose aucun changement."));
  if (d.etat === "prete") {
    const act = el("div", "annot-actions");
    const motif = el("input", "dem-motif");
    motif.placeholder = "motif (facultatif)";
    const ok = el("button", "bouton", "Appliquer");
    ok.onclick = () => decideVerif(d, true, motif.value, place);
    const non = el("button", "pan-lien", "rejeter l'analyse");
    non.title = "ne rien écrire ; le motif est gardé";
    non.onclick = () => decideVerif(d, false, motif.value);
    act.append(ok, motif, non);
    c1.append(act);
  } else if (d.decision) {
    c1.append(el("p", "etape-fait", d.decision.proposition ? `✓ appliquée le ${d.decision.date.slice(0, 10)}` : "✗ rejetée"));
  }
  etape1.append(c1);
  faire.append(etape1);
  if (R.recit?.a_reecrire && blocsRecit.length) {
    const etape2 = el("div", "etape");
    etape2.append(el("span", "etape-n", "2"));
    const c2 = el("div");
    c2.append(el("strong", null, `Puis réécrire le récit (${blocsRecit.map((b) => "^" + b).join(", ")})`),
      el("p", "mut petit", "Le récit dit encore l'ancienne version. À faire après l'étape 1 : la réécriture lira le verrou " +
        "corrigé et le nouvel appui de l'essai. Elle rendra des propositions, rien n'est remplacé sans ton choix."));
    const re = el("button", d.decision?.proposition ? "bouton" : "pan-lien", "↻ réécrire le récit…");
    re.onclick = () => re.replaceWith(formDemande({ portee: "paragraphe", blocs: blocsRecit }));
    c2.append(re);
    etape2.append(c2);
    faire.append(etape2);
  }
  t.append(faire);
  if (d.decision) {
    const dec = el("div", "dem-decision");
    dec.append(el("strong", null, d.decision.proposition ? "Appliquée" : "Rejetée"),
      document.createTextNode(d.decision.motif ? " — " + d.decision.motif : ""),
      el("span", "annot-date", " " + d.decision.date.slice(0, 16).replace("T", " ")));
    if (d.decision.bloc_essai) {
      const va = el("button", "pan-lien", `→ voir le passage dans l'essai (^${d.decision.bloc_essai})`);
      va.onclick = () => vaVers("essai", d.decision.bloc_essai);
      dec.append(va);
    }
    t.append(dec);
  }
  piedTiroir(t, d);
}

// Ce que Claude fait, pendant qu'il le fait : le temps écoulé et les dernières étapes.
// Seule cette zone se met à jour ; le reste du tiroir (dont « ce que Claude a reçu ») ne bouge pas.
function enDirect(d) {
  const z = el("div", "dem-direct");
  z.id = "dem-direct";
  remplitDirect(z, d);
  return z;
}

function remplitDirect(z, d) {
  const depuis = Math.round((Date.now() - new Date(d.cree).getTime()) / 1000);
  const verbe = d.type === "verification" || d.type === "fiche" ? "Claude cherche" : "Claude travaille";
  const je = d.jetons_en_cours;
  z.replaceChildren(el("p", "dem-attente", `${verbe}… ${Math.floor(depuis / 60)} min ${String(depuis % 60).padStart(2, "0")} s`
    + ` · ${(d.deroule ?? []).filter((x) => x.type === "outil").length} étapes`
    + ` · ${nomModele(d.modele_en_cours ?? d.modele_choisi ?? etat.modeles?.defaut?.[d.type === "verification" || d.type === "fiche" ? d.type : "reecriture"])}`
    + (je ? ` · ↑ ${k((je.entree ?? 0) + (je.cache_cree ?? 0) + (je.cache_lu ?? 0))} (${partCache(je)} % du cache) ↓ ${k(je.sortie ?? 0)} jetons` : "")
    + (d.budget?.limites?.recherches ? ` · ${d.budget.recherches}/${d.budget.limites.recherches} recherches, ${d.budget.pages}/${d.budget.limites.pages} pages` : "")));
  const ol = el("ol", "deroule");
  // la dernière réflexion (ou le dernier commentaire), en tête : où Claude en est
  const derniere = [...(d.deroule ?? [])].reverse().find((e) => e.type === "pensee" || e.type === "texte");
  if (derniere) {
    const b = el("div", "der-derniere");
    b.append(el("span", "mut petit", (derniere.type === "pensee" ? "💭 réflexion" : "✎ Claude") + ` · ${derniere.t}`),
      el("p", null, derniere.texte));
    z.append(b);
  }
  for (const e of (d.deroule ?? []).slice(-14)) ol.append(ligneDeroule(e));
  z.append(ol, el("p", "mut petit", "Tu peux fermer ce tiroir ou changer de vue : le travail continue sur le serveur. " +
    "« ↻ Demandes » s'allume quand c'est prêt."));
}

const ICONES = { WebSearch: "🔎", WebFetch: "🌐", Read: "📄", Grep: "⌕", Glob: "⌕" };
function ligneDeroule(e) {
  const li = el("li", "der-" + e.type);
  li.append(el("span", "der-t", e.t));
  if (e.type === "outil") {
    li.append(el("span", "der-icone", ICONES[e.nom] ?? "⚙"), el("span", "der-nom", e.nom + " "));
    const x = el("span", "der-detail", e.detail);
    if (/^https?:/.test(e.detail)) { const a = el("a", "lien-ext", e.detail); a.href = e.detail; a.target = "_blank"; x.replaceChildren(a); }
    li.append(x);
  } else {
    li.append(el("span", "der-icone", { echec: "⚠", pensee: "💭", limite: "⛔", reprise: "⏵", resultat: "↳" }[e.type] ?? "✎"));
    const x = el("span", "der-detail", e.texte);
    if (e.type === "resultat" && e.nom) x.prepend(el("span", "der-nom", e.nom + " → "));
    // réflexions et résultats : repliés à quelques lignes, un clic les déplie
    if (["pensee", "texte", "resultat"].includes(e.type)) {
      li.classList.add("pliable");
      li.onclick = () => li.classList.toggle("deplie");
      li.title = "clic : déplier / replier";
    }
    li.append(x);
  }
  return li;
}

async function rafraichitDirect(ident) {
  const t = document.getElementById("tiroir");
  if (t.hidden) return;
  const d = await api(`/chapitres/${slugDe(ident)}/demandes/${ident}`).catch(() => null);
  const z = document.getElementById("dem-direct");
  if (etat.tiroirMontre !== ident) return;                           // le tiroir montre autre chose : on arrête
  if (!d || d.etat !== "en_cours" || !z) return tiroir(ident);       // fini : tout redessiner
  remplitDirect(z, d);
  suivi = setTimeout(() => rafraichitDirect(ident), 2000);
}

// Le déroulé complet d'une demande finie : les recherches, les pages lues, ce que Claude
// a écrit en chemin — de quoi suivre son raisonnement.
function derouleComplet(d) {
  d.deroule = (d.deroule ?? []).filter((e) => e.nom !== "StructuredOutput");   // la réponse, pas une étape
  const n = d.deroule.length;
  if (!n) return null;
  const det = el("details", "replie");
  const compte = (f) => d.deroule.filter(f).length;
  const SORTES = [["tout", "tout", () => true], ["actions", "actions", (e) => e.type === "outil" || e.type === "echec" || e.type === "limite"],
    ["pensees", "réflexions", (e) => e.type === "pensee" || e.type === "texte"], ["resultats", "résultats", (e) => e.type === "resultat"]];
  det.append(el("summary", null, `le déroulé de Claude (${n} étapes : ${compte(SORTES[1][2])} actions, ` +
    `${compte(SORTES[2][2])} réflexions, ${compte(SORTES[3][2])} résultats)`));
  const barre = el("div", "dem-filtres");
  const g = el("span", "groupe filtres");
  const ol = el("ol", "deroule complet");
  const montre = (cle) => {
    etat.filtreDeroule = cle;
    const fn = SORTES.find((s) => s[0] === cle)[2];
    ol.replaceChildren(...d.deroule.filter(fn).map(ligneDeroule));
    g.querySelectorAll("button").forEach((b) => b.classList.toggle("actif", b.dataset.k === cle));
  };
  for (const [k, lib, fn] of SORTES) {
    const b = el("button", null, `${lib} · ${compte(fn)}`);
    b.dataset.k = k;
    b.onclick = () => montre(k);
    g.append(b);
  }
  barre.append(g);
  det.append(barre, ol);
  montre(etat.filtreDeroule ?? "tout");
  return det;
}

// Les jetons, lisibles : « 12,3 k ».
function k(n) {
  if (n == null) return "?";
  return n >= 1000 ? (n / 1000).toLocaleString("fr-FR", { maximumFractionDigits: 1 }) + " k" : String(n);
}

// La part de l'entrée relue du cache (facturée un dixième) : ce qui est vraiment « neuf » à chaque tour.
function partCache(j) {
  const entree = (j.entree ?? 0) + (j.cache_cree ?? 0) + (j.cache_lu ?? 0);
  return entree ? Math.round((100 * (j.cache_lu ?? 0)) / entree) : 0;
}

function ligneJetons(j) {
  if (!j) return null;
  const entree = (j.entree ?? 0) + (j.cache_cree ?? 0) + (j.cache_lu ?? 0);
  const s = el("span", "jetons");
  s.textContent = `jetons : ↑ ${k(entree)} en entrée` + (j.cache_lu ? ` (${partCache(j)} % relus du cache, ${k(entree - j.cache_lu)} neufs)` : "")
    + ` · ↓ ${k(j.sortie ?? 0)} en sortie`;
  const detail = Object.entries(j.par_modele ?? {}).map(([m, u]) =>
    `${m} : entrée ${u.inputTokens ?? u.input_tokens ?? "?"}, sortie ${u.outputTokens ?? u.output_tokens ?? "?"}, ` +
    `cache lu ${u.cacheReadInputTokens ?? u.cache_read_input_tokens ?? 0}, cache créé ${u.cacheCreationInputTokens ?? u.cache_creation_input_tokens ?? 0}`);
  s.title = (detail.length ? detail.join("\n") + "\n\n" : "") + "entrée = nouvelle + cache créé + cache relu. " +
    "Le contexte entier est renvoyé à chaque tour : l'entrée se cumule sur tous les tours (surtout relue du cache, facturée un dixième).";
  return s;
}

// Le budget de recherche d'une demande : consommé / permis.
function ligneBudget(b) {
  if (!b) return null;
  const av = b.avant ?? {};
  const R = (b.recherches ?? 0) + (av.recherches ?? 0), P = (b.pages ?? 0) + (av.pages ?? 0), X = (b.refus ?? 0) + (av.refus ?? 0);
  if (!R && !P && !X) return null;
  const L = b.limites ?? {};
  const n = 1 + (b.encore ?? 0);
  const plafond = (x) => (x != null ? "/" + x * n : "");
  return el("span", "jetons", `recherche : ${R}${plafond(L.recherches)} recherches web · ${P}${plafond(L.pages)} pages lues` +
    (X ? ` · ${X} refus (budget atteint)` : "") + (b.encore ? ` · poursuivie ${b.encore} fois` : ""));
}

function piedTiroir(t, d) {
  setTimeout(() => lieRefs(t.querySelector(".dem-cible")), 0);
  const dc = d.etat !== "en_cours" && derouleComplet(d);
  if (dc) t.append(dc);
  // reprendre : la session est gardée ; Claude y retrouve ce qu'il a lu et rend sa réponse
  const finir = d.etat === "erreur";
  const chercher = (d.type === "verification" || d.type === "fiche") && (d.etat === "erreur" || d.etat === "prete");
  if (d.session_id && !d.remplacee_par && (finir || chercher)) {
    const bloc = el("div", "relance reprise");
    const act = el("div", "annot-actions");
    const envoie = async (b, quoi, corps) => {
      b.disabled = true;
      const r = await fetch(`/api/chapitres/${slugDe(d.id)}/demandes/${d.id}/${quoi}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps ?? {}) });
      if (!r.ok) { b.disabled = false; alert((await r.json().catch(() => ({}))).detail ?? r.status); return; }
      if (etat.atelier) await chargeDemandes();
      tiroir(d.id);
    };
    if (finir) {
      const b = el("button", "bouton", "⏵ reprendre et finir");
      b.title = "sans nouvelle recherche : Claude rend sa réponse avec ce qu'il a déjà lu";
      b.onclick = () => envoie(b, "reprise");
      act.append(b);
    }
    if (chercher) {
      const lim = etat.modeles?.limites?.verification;
      const b = el("button", finir ? "pan-lien" : "bouton", "🔎 poursuivre la recherche…");
      b.onclick = () => {
        const z = el("textarea", "annot-texte");
        z.placeholder = "ce qu'il faut chercher de plus (facultatif) : une valeur, une source précise…";
        const go = el("button", "bouton", "🔎 poursuivre");
        go.onclick = () => envoie(go, "encore", { consigne: z.value });
        const a2 = el("div", "annot-actions");
        a2.append(go);
        bloc.replaceChildren(el("p", "mut petit", "Claude reprend sa session là où il en est : tout ce qu'il a cherché, lu et " +
          "conclu reste dans son contexte. Il reçoit seulement une rallonge" +
          (lim ? ` (${lim.tours} tours, ${lim.recherches} recherches, ${lim.pages} pages de plus)` : "") +
          ". Sa réponse mise à jour remplace " + (d.etat === "prete" ? "celle-ci, qui reste lisible pour comparer." : "l'échec.")), z, a2);
        z.focus();
      };
      act.append(b);
    }
    bloc.append(act, el("p", "mut petit", "La session de cette demande est conservée : tout ce qui a été cherché et lu y est. " +
      (finir ? "« Reprendre et finir » : quelques tours, sans rechercher davantage. " : "") +
      (chercher ? "« Poursuivre la recherche » : la même session continue, avec une rallonge de tours et de recherches — une nouvelle demande, elle, repartirait de zéro." : "")));
    t.append(bloc);
  }
  if (d.etat === "erreur" && !d.remplacee_par) {
    const c = el("button", "pan-lien", "classer (clore sans relancer)");
    c.onclick = async () => {
      const r = await fetch(`/api/chapitres/${slugDe(d.id)}/demandes/${d.id}/classer`, { method: "POST" });
      if (!r.ok) { alert((await r.json().catch(() => ({}))).detail ?? r.status); return; }
      tiroir(d.id);
    };
    t.append(c);
  }
  // relancer : même cible, consigne revue si besoin, sur l'état présent du livre
  if (d.relance_de) {
    const r = el("button", "pan-lien", `↩ relance de la demande du ${d.relance_de.slice(2, 10).replace(/(\d{4})(\d{2})(\d{2})/, "$3/$2")}`);
    r.onclick = () => tiroir(d.relance_de);
    t.append(r);
  }
  if (d.remplacee_par) {
    const r = el("button", "pan-lien", "→ remplacée par une relance : l'ouvrir");
    r.onclick = () => tiroir(d.remplacee_par);
    t.append(r);
  } else if (d.etat !== "en_cours") {
    const bloc = el("div", "relance");
    const b = el("button", "pan-lien", "↻ relancer cette demande avec l'état actuel du livre…");
    b.onclick = () => {
      const z = el("textarea", "annot-texte");
      z.value = d.consigne ?? "";
      z.placeholder = "consigne (facultatif)";
      const mod = choixModele(d.type === "verification" || d.type === "fiche" ? d.type : "reecriture", d.modele_choisi ?? "");
      const go = el("button", "bouton", "↻ relancer");
      go.onclick = async () => {
        go.disabled = true;
        const r = await fetch(`/api/chapitres/${slugDe(d.id)}/demandes/${d.id}/relance`, {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ consigne: z.value, modele: mod.valeur() }) });
        if (!r.ok) { go.disabled = false; alert((await r.json().catch(() => ({}))).detail ?? r.status); return; }
        const n = await r.json();
        await chargeDemandes();
        marquesDemandes();
        tiroir(n.id);
      };
      const act = el("div", "annot-actions");
      act.append(go);
      bloc.replaceChildren(el("p", "mut petit", "Même cible, sur l'état présent du livre : le contexte est recompilé " +
        "(verrou, essai, storyboard, annotations du moment). " + (d.etat === "prete" ? "Cette demande-ci passera à « remplacée »." : "")),
        z, mod.noeud, act);
      z.focus();
    };
    bloc.append(b);
    t.append(bloc);
  }
  if (d.execution) {
    const ex = el("p", "mut petit");
    ex.append(`${d.execution.modele ?? ""} · ${d.execution.duree_s} s` +
      (d.execution.tours ? ` · ${d.execution.tours} tours` : "") +
      (d.execution.reprises ? ` (dont ${d.execution.reprises} reprise${d.execution.reprises > 1 ? "s" : ""})` : "") +
      (d.execution.cout_usd ? ` · ≈ ${d.execution.cout_usd.toFixed(2)} $ (tarif API)` : ""));
    const lj = ligneJetons(d.execution.jetons);
    if (lj) ex.append(el("br"), lj);
    const bu = ligneBudget(d.budget);
    if (bu) ex.append(el("br"), bu);
    t.append(ex);
  }
  const ctx = el("details", "replie");
  ctx.append(el("summary", null, "ce que Claude a reçu"),
    el("pre", "dem-contexte", d.contexte.message), el("pre", "dem-contexte", d.contexte.systeme));
  t.append(ctx);
  const h = el("button", "pan-lien", "← toutes les demandes du chapitre");
  h.onclick = () => tiroir(null);
  t.append(h);
}

async function decideVerif(d, retenir, motif, place) {
  const r = await fetch(`/api/chapitres/${etat.slug}/demandes/${d.id}/decision`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ retenir, motif, place }) });
  if (!r.ok) { alert("échec : " + ((await r.json().catch(() => ({}))).detail ?? r.status)); return; }
  if (retenir) {
    etat.docs = {};
    etat.garde = null;
    await rechargeAnnotations();
    await ouvre(etat.slug);
  } else {
    await chargeDemandes();
  }
  tiroir(d.id);
}

function teteTiroir(titre, retour = null) {
  const h = el("div", "pan-tete");
  if (retour) {
    const r = el("button", "retour", "← demandes");
    r.title = "revenir à la liste des demandes";
    r.onclick = () => { clearTimeout(suivi); retiensTiroir(null); retour(); };
    h.append(r);
  }
  const x = el("button", "fermer", "×");
  x.onclick = () => { clearTimeout(suivi); retiensTiroir(null); document.getElementById("tiroir").hidden = true; delete document.body.dataset.tiroir; };
  h.append(el("h4", null, titre), x);
  return h;
}

const OUVERTES = new Set(["en_cours", "prete", "en_attente", "a_confirmer"]);

const LIB_TYPES = { reecriture: "↻ réécriture", verification: "🔎 vérification", naive: "👁 lecture naïve", fiche: "◇ fiche",
  pistes: "◇ creuser", renvois: "⇄ renvois", reference: "🔎 référence", document: "⤓ original", plan: "✦ plan", redaction: "✎ rédaction" };
const STATUTS_DEM = [["tout", "tous les statuts"], ["ouvertes", "ouvertes"], ["actives", "en cours + en attente"], ["en_cours", "en cours"], ["a_decider", "à décider"],
  ["en_attente", "en attente"], ["erreur", "en erreur"], ["retenues", "retenues"], ["rejetees", "rejetées"], ["closes", "closes"]];
const PERIODES = [["tout", "toutes dates"], ["1", "aujourd'hui"], ["2", "depuis hier"], ["7", "7 jours"], ["30", "30 jours"], ["date", "depuis le…"]];

function statutDe(d, s) {
  switch (s) {
    case "tout": return true;
    case "ouvertes": return OUVERTES.has(d.etat);
    case "closes": return !OUVERTES.has(d.etat);
    case "actives": return d.etat === "en_cours" || d.etat === "en_attente";
    case "a_decider": return d.etat === "prete" || d.etat === "a_confirmer";
    case "retenues": return d.etat === "decidee" && !!d.decision?.proposition;
    case "rejetees": return d.etat === "decidee" && !d.decision?.proposition;
    default: return d.etat === s;
  }
}

function periodeDe(d, F) {
  if (F.periode === "tout") return true;
  const c = (d.cree ?? "").slice(0, 10);
  if (F.periode === "date") return !F.depuis || c >= F.depuis;
  const j = new Date();
  j.setDate(j.getDate() - (Number(F.periode) - 1));
  return c >= j.toLocaleDateString("sv");                 // AAAA-MM-JJ, heure locale
}

// La liste des demandes : ce chapitre, tout le livre, ou les fiches (la base) ; filtres par type,
// statut, période et texte. Les filtres sont retenus pour la session.
async function historique(t, portee = null) {
  clearTimeout(suivi);
  etat.tiroirMontre = null;
  const F = etat.filtresDem ??= { portee: "chapitre", type: "tout", statut: "tout", periode: "tout", depuis: "", texte: "" };
  if (portee) F.portee = portee;
  const sansChapitre = !etat.slug || !etat.atelier || etat.wiki || etat.accueil;
  if (F.portee === "chapitre" && sansChapitre) F.portee = "livre";
  const ds = F.portee === "livre" ? await api("/demandes").catch(() => [])
    : F.portee === "fiches" ? (await api("/fiches/demandes").catch(() => [])).map((d) => ({ ...d, chapitre: "_kb" }))
    : (await api(`/chapitres/${etat.slug}/demandes`).catch(() => [])).map((d) => ({ ...d, chapitre: etat.slug }));
  t.replaceChildren(teteTiroir({ livre: "Demandes du livre", fiches: "Demandes des fiches", chapitre: "Demandes du chapitre" }[F.portee]));
  const redessine = () => historique(t);
  const boutons = (cle, options) => {
    const g = el("span", "groupe filtres");
    for (const [v, lib] of options) {
      const b = el("button", F[cle] === v ? "actif" : null, lib);
      b.onclick = () => { F[cle] = v; redessine(); };
      g.append(b);
    }
    return g;
  };
  const choix = (cle, options, compte) => {
    const s = el("select", "dem-choix");
    for (const [v, lib] of options) {
      const n = compte ? compte(v) : null;
      s.append(new Option(n == null || v === "tout" ? lib : `${lib} (${n})`, v, false, F[cle] === v));
    }
    s.onchange = () => { F[cle] = s.value; redessine(); };
    return s;
  };
  const barre = el("div", "dem-filtres");
  barre.append(boutons("portee", [...(sansChapitre ? [] : [["chapitre", "ce chapitre"]]), ["livre", "tout le livre"], ["fiches", "fiches"]]));
  const types = [["tout", "tous les types"], ...Object.entries(LIB_TYPES).filter(([v]) => ds.some((d) => (d.type ?? "reecriture") === v))];
  const sel = el("div", "dem-filtres");
  sel.append(choix("type", types, (v) => ds.filter((d) => (d.type ?? "reecriture") === v).length),
    choix("statut", STATUTS_DEM, (v) => ds.filter((d) => statutDe(d, v)).length),
    choix("periode", PERIODES));
  if (F.periode === "date") {
    const dt = el("input", "dem-date");
    dt.type = "date";
    dt.value = F.depuis;
    dt.onchange = () => { F.depuis = dt.value; redessine(); };
    sel.append(dt);
  }
  const q = el("input", "dem-texte");
  q.type = "search";
  q.placeholder = "chercher (titre, consigne)…";
  q.value = F.texte;
  let minuteur = null;
  q.oninput = () => { clearTimeout(minuteur); minuteur = setTimeout(() => { F.texte = q.value; redessine(); }, 300); };
  sel.append(q);
  const efface = el("button", "pan-lien", "effacer les filtres");
  efface.onclick = () => { Object.assign(F, { type: "tout", statut: "tout", periode: "tout", depuis: "", texte: "" }); redessine(); };
  if (F.type !== "tout" || F.statut !== "tout" || F.periode !== "tout" || F.texte) sel.append(efface);
  t.append(barre, sel);
  const mots = F.texte.trim().toLowerCase();
  const garde = ds.filter((d) => (F.type === "tout" || (d.type ?? "reecriture") === F.type) && statutDe(d, F.statut) && periodeDe(d, F)
    && (!mots || `${d.titre ?? ""} ${d.consigne ?? ""} ${d.question ?? ""}`.toLowerCase().includes(mots)));
  if (F.texte) setTimeout(() => { q.focus(); q.setSelectionRange(q.value.length, q.value.length); }, 0);
  if (!garde.length) {
    t.append(el("p", "mut", ds.length ? `Aucune demande pour ces filtres (${ds.length} en tout).` :
      "Aucune demande. ↻ réécrire depuis une annotation, un paragraphe ou un plan ; 🔎 vérifier depuis une assertion ou une annotation."));
    return;
  }
  // le total de ce qui est affiché
  const tot = garde.reduce((s, d) => {
    const j = d.jetons ?? {};
    s.e += (j.entree ?? 0) + (j.cache_cree ?? 0) + (j.cache_lu ?? 0);
    s.s += j.sortie ?? 0;
    s.c += d.cout_usd ?? 0;
    s.nc += d.cout_usd != null ? 1 : 0;
    s.n += d.jetons ? 1 : 0;
    return s;
  }, { e: 0, s: 0, c: 0, n: 0, nc: 0 });
  // les demandes anciennes n'ont que leur coût : chaque total dit sur combien de demandes il porte
  const totaux = [`${garde.length} demande${garde.length > 1 ? "s" : ""}${garde.length < ds.length ? ` sur ${ds.length}` : ""}`];
  if (tot.n) totaux.push(`jetons (${tot.n}) : ↑ ${k(tot.e)} en entrée · ↓ ${k(tot.s)} en sortie`);
  if (tot.nc) totaux.push(`≈ ${tot.c.toFixed(2)} $ au tarif API (${tot.nc})`);
  t.append(el("p", "mut petit", totaux.join(" ; ")));
  // classement par chapitre, dans l'ordre du livre ; dans un chapitre, les plus récentes d'abord
  const parChap = new Map();
  for (const d of garde) {
    if (!parChap.has(d.chapitre)) parChap.set(d.chapitre, []);
    parChap.get(d.chapitre).push(d);
  }
  const ordre = etat.chapitres.map((c) => c.slug);
  for (const slug of [...parChap.keys()].sort((a, b) => ordre.indexOf(a) - ordre.indexOf(b))) {
    const c = slug === "_kb" ? { numero: "◇", title: "Fiches et livre" } : etat.chapitres.find((x) => x.slug === slug);
    const liste = parChap.get(slug).sort((a, b) => (a.cree < b.cree ? 1 : -1));
    const ouvertes = liste.filter((d) => OUVERTES.has(d.etat)).length;
    if (F.portee !== "chapitre") t.append(el("h5", "dem-chapitre", `${c?.numero ?? ""} · ${c?.title ?? slug} — ${liste.length} demande(s)${ouvertes ? `, ${ouvertes} ouverte(s)` : ""}`));
    for (const d of liste) {
      const l = el("button", "dem-ligne " + (OUVERTES.has(d.etat) ? "ouverte" : "close"));
      const haut = el("span", "dem-haut");
      haut.append(el("span", "annot-type", LIB_TYPES[d.type ?? "reecriture"] ?? d.type),
        el("span", "dem-etat " + d.etat, etiquetteDemande(d)), el("span", "annot-date", d.cree.slice(0, 16).replace("T", " ")));
      l.append(haut, el("span", "dem-titre-ligne", d.titre ?? d.question ?? ""));
      if (d.consigne) l.append(el("span", "dem-consigne", "« " + d.consigne + " »"));
      if (d.jetons) {
        const j = d.jetons;
        haut.append(el("span", "jetons", `↑${k((j.entree ?? 0) + (j.cache_cree ?? 0) + (j.cache_lu ?? 0))} ↓${k(j.sortie ?? 0)}`));
      }
      l.onclick = () => ouvreDemande(slug, d.id);
      t.append(l);
    }
  }
}

// Ouvrir une demande, y compris d'un autre chapitre : on y va d'abord.
function ouvreDemande(slug, id) {
  if (slug === etat.slug || slug === "_kb") return tiroir(id);
  etat.tiroirApres = id;
  location.hash = `${slug}/recit`;
}

function carteProposition(d, p) {
  const c = el("div", "dem-prop" + (d.decision?.proposition === p.id ? " retenue" : ""));
  const tete = el("div", "annot-tete");
  tete.append(el("strong", null, "Proposition " + p.id.slice(1)));
  if (!p.complete) tete.append(el("span", "annot-orph", "incomplète"));
  if (p.annotations_traitees.length) tete.append(el("span", "annot-date", "traite " + p.annotations_traitees.join(", ")));
  c.append(tete);
  for (const b of d.cible.blocs) {
    if (!p.paragraphes[b]) continue;
    if (d.cible.blocs.length > 1) c.append(el("span", "appui-lieu", "^" + b));
    c.append(diff(d.cible.textes[b], p.paragraphes[b]));
  }
  c.append(el("p", "dem-note", p.note));
  if (d.etat === "prete" && p.complete) {
    const act = el("div", "annot-actions");
    const motif = el("input", "dem-motif");
    motif.placeholder = "pourquoi celle-ci (facultatif)";
    const ok = el("button", "bouton", "Garder celle-ci");
    ok.title = "remplace le texte du récit par cette proposition";
    ok.onclick = () => decide(d, p.id, motif.value);
    act.append(ok, motif);
    c.append(act);
  }
  return c;
}

function rejetTout(d) {
  const f = el("div", "annot-actions dem-rejet");
  const motif = el("input", "dem-motif");
  motif.placeholder = "pourquoi aucune ne convient — c'est ce qui apprend à l'atelier";
  const non = el("button", "pan-lien", "aucune ne convient");
  non.onclick = () => decide(d, null, motif.value);
  f.append(non, motif);
  return f;
}

async function decide(d, proposition, motif) {
  const r = await fetch(`/api/chapitres/${etat.slug}/demandes/${d.id}/decision`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ proposition, motif }) });
  if (!r.ok) { alert("échec : " + ((await r.json().catch(() => ({}))).detail ?? r.status)); return; }
  if (proposition) {
    etat.bloc = d.cible.blocs[0];
    etat.docs = {};                                  // le texte a changé : relire récit et essai
    etat.garde = null;
    await rechargeAnnotations();
    await ouvre(etat.slug);
  } else {
    await chargeDemandes();
    marquesDemandes();
  }
  tiroir(d.id);
}

// Ce qui change, mot à mot (plus longue sous-suite commune).
function diff(a, b) {
  const x = a.split(/\s+/), y = b.split(/\s+/);
  const n = x.length, m = y.length;
  const L = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) {
    L[i][j] = x[i] === y[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  }
  const out = el("p", "dem-diff");
  let i = 0, j = 0;
  const pousse = (cls, mot) => { out.append(cls ? el("span", cls, mot) : document.createTextNode(mot), " "); };
  while (i < n && j < m) {
    if (x[i] === y[j]) { pousse(null, x[i]); i++; j++; }
    else if (L[i + 1][j] >= L[i][j + 1]) pousse("del", x[i++]);
    else pousse("ins", y[j++]);
  }
  while (i < n) pousse("del", x[i++]);
  while (j < m) pousse("ins", y[j++]);
  return out;
}

// ------------------------------------------------------------------ corriger

// Corriger un paragraphe sur place : son Markdown dans une zone de saisie, à la place du
// texte. Enregistrer écrit le fichier (le ^id reste), note la correction au journal (avant,
// après, motif). L'essai accepte aussi un paragraphe nouveau et la suppression.
async function editeBloc(bloc) {
  document.querySelectorAll("#page .editeur").forEach((x) => x.fermer?.());
  const version = versionVue();
  const cible = blocEl(bloc);
  if (!cible) return;
  const src = await api(`/chapitres/${etat.slug}/${version}/blocs/${bloc}`).catch(() => null);
  if (!src) { alert("paragraphe introuvable"); return; }
  const para = etat.version === "storyboard" ? cible.querySelector("p") : cible;
  const ed = el("div", "editeur");
  const z = el("textarea", "editeur-texte");
  z.value = src.texte;
  z.lang = etat.livre.langue ?? "fr";
  z.spellcheck = true;
  const l = etat.atelier?.links?.[version]?.[bloc];
  const info = el("p", "mut petit");
  info.textContent = l?.assertions?.length
    ? `Ce paragraphe porte ${l.assertions.join(", ")} : une correction de fond se reporte au verrou.`
    : (l?.ajout ? "Paragraphe hors verrou (ajout)." : "");
  const motif = el("input", "dem-motif");
  motif.placeholder = "motif (facultatif) : coquille, précision, rythme…";
  const act = el("div", "annot-actions");
  const ok = el("button", "bouton", "Enregistrer");
  const non = el("button", "pan-lien", "annuler");
  act.append(ok, non);
  if (version === "essai") {
    const plus = el("button", "pan-lien", "＋ paragraphe après");
    plus.onclick = async () => {
      const r = await fetch(`/api/chapitres/${etat.slug}/essai/blocs/${bloc}/apres`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ texte: "…", motif: motif.value }) });
      if (!r.ok) { alert("échec : " + ((await r.json().catch(() => ({}))).detail ?? r.status)); return; }
      const n = await r.json();
      await apresCorrection(n.bloc);
      editeBloc(n.bloc);
    };
    const sup = el("button", "pan-lien danger", "supprimer ce paragraphe");
    sup.onclick = async () => {
      if (!confirm("Supprimer ce paragraphe de l'essai ? Il reste dans le journal (texte complet).")) return;
      const r = await fetch(`/api/chapitres/${etat.slug}/essai/blocs/${bloc}`, {
        method: "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ avant: src.texte, motif: motif.value }) });
      if (!r.ok) { alert((await r.json().catch(() => ({}))).detail ?? r.status); return; }
      await apresCorrection(null);
    };
    act.append(plus, sup);
  }
  act.append(el("span", "mut petit", "⌘↵ · Échap"));
  ed.append(z, info, motif, act);
  para.hidden = true;
  para.after(ed);
  ed.fermer = () => { ed.remove(); para.hidden = false; };
  ajuste(z);
  z.focus();
  z.addEventListener("input", () => ajuste(z));
  non.onclick = () => ed.fermer();
  const enregistre = async () => {
    ok.disabled = true;
    const r = await fetch(`/api/chapitres/${etat.slug}/${version}/blocs/${bloc}`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ texte: z.value, avant: src.texte, motif: motif.value }) });
    if (!r.ok) {
      ok.disabled = false;
      alert(r.status === 409 ? "Ce paragraphe a changé ailleurs : rechargement." : "Refusé : " + ((await r.json().catch(() => ({}))).detail ?? r.status));
      if (r.status === 409) await apresCorrection(bloc);
      return;
    }
    await apresCorrection(bloc);
  };
  ok.onclick = enregistre;
  for (const x of [z, motif]) {
    x.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) enregistre();
      if (e.key === "Escape") { e.stopPropagation(); ed.fermer(); }
    });
  }
}

// Après une correction : le texte est relu partout (vue, appuis, annotations), à la même place.
async function apresCorrection(bloc) {
  const y = zone().scrollTop;
  etat.docs = {};
  etat.garde = null;
  if (bloc) { if (versionVue() === "essai") etat.blocEssai = bloc; else etat.bloc = bloc; }
  await ouvre(etat.slug);
  zone().scrollTo(0, y);
  majVersions();
}

// ------------------------------------------------------------------ état de validation

// Ce qui a changé depuis la dernière validation (la migration, puis la boucle ou l'auteur) :
// un paragraphe modifié, nouveau, ou dont le cadre (plan, verrou) a changé porte une marque
// dans sa marge gauche. C'est la liste de ce que la boucle de validation devra reprendre.
const LIB_VALID = { modifie: "modifié", nouveau: "nouveau", cadre: "cadre modifié" };

function marquesValidation() {
  document.querySelectorAll("#page [data-valid]").forEach((x) => { delete x.dataset.valid; x.removeAttribute("title"); });
  const EV = etat.validation?.versions?.[versionVue()];
  if (!EV) return;
  for (const [b, x] of Object.entries(EV)) {
    if (x.etat === "valide") continue;
    const e = blocEl(b);
    if (!e) continue;
    e.dataset.valid = x.etat;
    e.title = `${LIB_VALID[x.etat]}${x.raisons?.length ? " : " + x.raisons.join(", ") : ""} — à revalider`;
  }
  // le plan de l'essai : ses paragraphes et ses sections, marqués aussi
  if (versionVue() === "essai") {
    document.querySelectorAll("#plan-col .pl-bloc").forEach((r) => {
      const x = EV[r.dataset.id];
      if (x && x.etat !== "valide") r.dataset.valid = x.etat;
    });
  }
}

async function panneauValidation(ancre) {
  document.querySelector(".versions-pop")?.remove();
  const v = versionVue();
  const E = etat.validation;
  const EV = E?.versions?.[v] ?? {};
  const pop = el("div", "versions-pop");
  const tete = el("div", "pan-tete");
  const x = el("button", "fermer", "×");
  x.onclick = () => pop.remove();
  tete.append(el("h4", null, `État de validation · ${v === "essai" ? "essai" : "récit"}`), x);
  pop.append(tete);
  const base = E?.base ?? {};
  pop.append(el("p", "mut petit", `Référence : ${base.par === "migration" ? "la migration (dernier état validé par le cycle de l'ancien dépôt)" : base.par ?? "?"}` +
    `${base.date ? ", le " + base.date.slice(0, 10) : ""}. Un paragraphe modifié, nouveau, ou dont le plan ou une assertion ` +
    "a changé depuis, est à revalider."));
  const ordre = [...document.querySelectorAll("#page [data-block]")].map((e) => e.dataset.block);
  const aRevalider = Object.entries(EV).filter(([, y]) => y.etat !== "valide")
    .sort((a, b) => ordre.indexOf(a[0]) - ordre.indexOf(b[0]));
  if (!aRevalider.length) pop.append(el("p", null, "Tout est validé."));
  for (const [b, y] of aRevalider) {
    const l = el("button", "valid-ligne");
    const src = etat.docs?.[v]?.querySelector(`[data-block="${b}"]`);
    l.append(el("span", "valid-etat " + y.etat, LIB_VALID[y.etat]),
      el("span", "valid-texte", (src ? texteSans(src) : "^" + b).replace(/\s+/g, " ").slice(0, 90) + "…"));
    if (y.raisons?.length) l.append(el("span", "mut petit", y.raisons.join(", ")));
    l.onclick = () => { pop.remove(); vaVers(v === "essai" ? "essai" : "recit", b); };
    pop.append(l);
  }
  if (E?.resume?.[v]?.brief_modifie) pop.append(el("p", "valid-etat cadre", "L'en-tête du storyboard a changé depuis la validation."));
  const act = el("div", "annot-actions");
  const ok = el("button", "pan-lien", `Considérer ${v === "essai" ? "l'essai" : "le récit"} comme relu (sans vérification)`);
  ok.title = "ne lance aucune vérification : prend l'état présent comme nouvelle référence";
  ok.onclick = async () => {
    if (!confirm("Aucune vérification n'est lancée : l'état présent devient la référence, et les marques « à revalider » " +
      "disparaissent pour cette version. À faire seulement après l'avoir relue soi-même.")) return;
    etat.validation = await (await fetch(`/api/chapitres/${etat.slug}/validation`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ version: v }) })).json();
    pop.remove();
    marquesValidation();
    barreOutils();
    etat.chapitres = await api("/chapitres");
    sommaire();
  };
  act.append(ok);
  if (aRevalider.length) pop.append(act);
  pop.append(el("p", "mut petit", "La boucle de validation (propositions à retenir ou non, comme la réécriture) viendra reprendre cette liste."));
  document.body.append(pop);
  const r = ancre.getBoundingClientRect();
  pop.style.top = r.bottom + 6 + "px";
  pop.style.right = Math.max(12, window.innerWidth - r.right) + "px";
}

// Dans la fiche d'un paragraphe : son état, et le marquer validé seul.
function etatDuBloc(id) {
  const x = etat.validation?.versions?.[versionVue()]?.[id];
  if (!x || x.etat === "valide") return null;
  const d = el("div", "valid-fiche");
  d.append(el("span", "valid-etat " + x.etat, LIB_VALID[x.etat]),
    el("span", "mut petit", x.raisons?.length ? " " + x.raisons.join(", ") : " depuis la dernière validation"));
  const b = el("button", "pan-lien", "considérer ce paragraphe comme relu (sans vérification)");
  b.onclick = async () => {
    etat.validation = await (await fetch(`/api/chapitres/${etat.slug}/validation`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ version: versionVue(), blocs: [id] }) })).json();
    marquesValidation();
    barreOutils();
    fiche(id);
  };
  d.append(b);
  return d;
}

// ------------------------------------------------------------------ versions (git)

async function majVersions(b = document.querySelector("#outils .b-versions")) {
  if (!b) return;
  const v = await api("/versions").catch(() => null);
  if (!v?.git) { b.hidden = true; return; }
  const n = v.changements.length;
  b.textContent = n ? `⎇ ${n} modif. non versionnée${n > 1 ? "s" : ""}` : "⎇ versionné";
  b.classList.toggle("a-versionner", n > 0);
}

async function panneauVersions(ancre) {
  document.querySelector(".versions-pop")?.remove();
  const v = await api("/versions").catch(() => null);
  if (!v?.git) return;
  const pop = el("div", "versions-pop");
  const tete = el("div", "pan-tete");
  const x = el("button", "fermer", "×");
  x.onclick = () => pop.remove();
  tete.append(el("h4", null, `Versions du livre · git, branche ${v.branche}`), x);
  pop.append(tete);
  pop.append(el("p", "mut petit", "Enregistrer une version fait un commit des seuls fichiers du livre " +
    "(le reste du dépôt n'est pas touché). La trace fine de chaque correction est dans le journal du chapitre."));
  if (v.changements.length) {
    const ul = el("ul", "versions-liste");
    for (const c of v.changements) ul.append(el("li", null, `${c.etat}  ${c.fichier.replace(/^.*?book-atelier\//, "")}`));
    pop.append(el("h5", null, `${v.changements.length} fichier(s) modifié(s) depuis la dernière version`), ul);
    const msg = el("input", "dem-motif");
    msg.value = `${etat.livre.titre} — ${new Date().toISOString().slice(0, 10)} : corrections et annotations`;
    const ok = el("button", "bouton", "Enregistrer la version");
    ok.onclick = async () => {
      ok.disabled = true;
      const r = await fetch("/api/versions", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg.value }) });
      if (!r.ok) { ok.disabled = false; alert((await r.json().catch(() => ({}))).detail ?? r.status); return; }
      pop.remove();
      majVersions();
    };
    const act = el("div", "annot-actions");
    act.append(ok);
    pop.append(msg, act);
  } else {
    pop.append(el("p", null, "Tout est versionné."));
  }
  pop.append(el("h5", null, "Dernières versions"));
  for (const h of v.historique) {
    pop.append(el("p", "versions-h", `${h.date} · ${h.message}`));
  }
  document.body.append(pop);
  const r = ancre.getBoundingClientRect();
  pop.style.top = r.bottom + 6 + "px";
  pop.style.right = Math.max(12, window.innerWidth - r.right) + "px";
}

// ------------------------------------------------------------------ page du livre

// La page de présentation : ce que dit livre.yaml, modifiable sur place. Chaque champ
// s'enregistre seul (après une courte pause de frappe) dans livre.yaml, commentaires
// du fichier conservés. Si le fichier a changé ailleurs entre-temps, on ne l'écrase pas.

const CHAMPS_LIVRE = [
  { k: "titre", nom: "Titre", classe: "ed-titre" },
  { k: "sous_titre", nom: "Sous-titre", classe: "ed-sous-titre" },
  { k: "auteur", nom: "Auteur", classe: "ed-court" },
  { k: "langue", nom: "Langue", classe: "ed-court" },
  { k: "synopsis", nom: "Synopsis", long: true },
  { k: "quatrieme", nom: "Quatrième de couverture", long: true },
];

function afficheTitre() {
  const t = document.getElementById("titre-livre");
  t.textContent = "— " + (etat.livre.titre ?? "");
  t.title = "Page du livre · " + (etat.livre.dossier ?? "");
  document.title = `Atelier — ${etat.livre.titre ?? ""}`;
}

// Les onglets de la page du livre : la présentation, puis les garde-fous de chaque version.
// La barre de vue de la page du livre, comme celles des chapitres et des fiches :
// présentation · garde-fous de chaque version · Claude (modèles, budgets, file d'attente).
function barreLivre() {
  const o = document.getElementById("outils");
  o.replaceChildren();
  o.hidden = false;
  const g = el("span", "groupe");
  const b = (lib, actif, h, titre = "") => {
    const x = el("button", actif ? "actif" : null, lib);
    x.onclick = () => { location.hash = h; };
    if (titre) x.title = titre;
    g.append(x);
  };
  b("présentation", etat.ongletLivre === "presentation" || !etat.ongletLivre, "livre", "titre, auteur, synopsis, couverture, versions, structure");
  for (const v of Object.keys(etat.regles ?? {})) {
    const n = etat.regles[v].elements.filter((e) => e.type === "regle").length;
    b(`garde-fous · ${(etat.livre.versions?.[v]?.titre ?? v).toLowerCase()} (${n})`, etat.ongletLivre === "regles" && etat.reglesVue === v,
      `livre/regles/${v}`, "les règles d'écriture de cette version, et leurs contrôles");
  }
  b("claude", etat.ongletLivre === "claude", "livre/claude", "le modèle et le budget de chaque demande, la file d'attente");
  b("consommation", etat.ongletLivre === "consommation", "livre/consommation", "ce que Claude a consommé : jetons, cache, coût, par type, modèle, chapitre, jour");
  o.append(el("span", "etiq", "livre"), g, el("span", "espace"));
  for (const v of ["recit", "essai"].filter((x) => etat.livre.versions?.[x])) {
    const [pdf, imp] = boutonsPdf(v, `⎙ ${(etat.livre.versions[v].titre ?? v).toLowerCase()} PDF`, v + ".pdf", titrePdf(v));
    imp.textContent = "↗";
    o.append(pdf, imp);
  }
  const y = el("a", "lien-ext", "livre.yaml ↗");
  y.href = "vscode://file" + (etat.livre.chemins?.["livre.yaml"] ?? "");
  y.title = "ouvrir livre.yaml dans l'éditeur";
  o.append(y);
}

function ongletsLivre() {
  barreLivre();
  return el("span");
}

async function accueil() {
  document.body.dataset.vue = "livre";
  document.getElementById("volet-chapitre").hidden = true;
  delete document.body.dataset.panneau;
  etat.livre = await api("/livre").catch(() => etat.livre);
  afficheTitre();
  sommaire();
  const L = etat.livre;
  const page = document.getElementById("page");
  if (etat.ongletLivre === "consommation") {
    page.replaceChildren(ongletsLivre(), el("h1", null, "Consommation"), await sectionConsommation());
    colonneLivre();
    zone().scrollTo(0, 0);
    return;
  }
  if (etat.ongletLivre === "claude") {
    page.replaceChildren(ongletsLivre(), el("h1", null, "Claude"),
      el("p", "mut", "Ce que Claude peut faire pour chaque sorte de demande : le modèle, le nombre de tours, de recherches web et de " +
        "pages lues. Au-delà du budget, l'outil est refusé et Claude rend sa réponse avec ce qu'il a. Chaque demande peut aussi " +
        "choisir son modèle, pour elle seule."), sectionClaude(L));
    colonneLivre();
    zone().scrollTo(0, 0);
    return;
  }
  if (etat.ongletLivre === "regles") {
    page.replaceChildren(ongletsLivre(), sectionRegles());
    colonneLivre();
    const c = etat.regleCible && document.getElementById(`regle-${etat.reglesVue}-${etat.regleCible}`);
    etat.regleCible = null;
    if (c) { c.classList.add("eclair"); c.scrollIntoView({ block: "center" }); } else zone().scrollTo(0, 0);
    return;
  }
  const tete = el("div", "livre-tete");

  // couverture : un clic pour en choisir une
  const couv = el("div", "livre-couv");
  couv.title = "Choisir une image de couverture";
  if (L.couverture) {
    const img = el("img");
    img.src = `/api/livre/fichier?chemin=${encodeURIComponent(L.couverture)}&v=${L._version}`;
    img.alt = "couverture";
    img.onerror = () => img.replaceWith(el("span", "mut", `introuvable : ${L.couverture}`));
    couv.append(img);
  } else {
    couv.append(el("span", null, "＋ couverture"));
  }
  const choix = el("input");
  choix.type = "file";
  choix.accept = "image/*";
  choix.hidden = true;
  choix.onchange = () => choix.files[0] && envoieCouverture(choix.files[0]);
  couv.onclick = () => choix.click();
  couv.append(choix);

  const ident = el("div", "livre-ident");
  for (const ch of CHAMPS_LIVRE.filter((c) => !c.long)) ident.append(champEdit(ch, L[ch.k]));
  tete.append(couv, ident);

  const corps = el("div", "livre-corps");
  for (const ch of CHAMPS_LIVRE.filter((c) => c.long)) corps.append(champEdit(ch, L[ch.k]));

  // ce qui ne s'édite pas ici : les versions (et l'héritage, dans la colonne)
  const versions = el("section", "livre-bloc");
  versions.append(el("h3", null, "Versions"));
  for (const [k, v] of Object.entries(L.versions ?? {})) {
    const d = el("p");
    d.append(el("strong", null, v.titre ?? k), document.createTextNode(v.role ? " — " + v.role : ""));
    versions.append(d);
  }

  // la numérotation de l'essai : calculée à l'affichage, jamais stockée dans le texte
  if (L.versions?.essai) {
    const nd = el("label", "champ-edit ed-court");
    nd.append(el("span", "nom", "Numérotation de l'essai"));
    const sel = el("select", "livre-select");
    for (const [v, lib] of [["aucune", "aucune"], ["sections", "sections (1.2.3)"], ["paragraphes", "sections et paragraphes (§1.23)"]]) {
      const o = el("option", null, lib);
      o.value = v;
      if ((L.numerotation_essai ?? "aucune") === v) o.selected = true;
      sel.append(o);
    }
    sel.onchange = () => enregistre({ numerotation_essai: sel.value });
    nd.append(sel);
    versions.append(nd);
  }

  // Claude : le modèle par défaut et le budget de chaque demande

  // la structure, en un coup d'œil
  const st = el("section", "livre-bloc");
  const nChap = etat.chapitres.filter((c) => c.numero).length;
  const nMig = etat.chapitres.filter((c) => c.atelier).length;
  const parties = [...new Set(etat.chapitres.filter((c) => c.partie).map((c) => c.partie))];
  st.append(el("h3", null, "Structure"),
    el("p", "mut", `${parties.length} parties · ${nChap} chapitres · ${nMig} dans l'atelier`));
  const grille = el("div", "livre-parties");
  for (const pid of parties) {
    const chs = etat.chapitres.filter((c) => c.partie === pid);
    const col = el("div");
    col.append(el("h4", null, chs[0].partie_titre));
    const ol = el("ol");
    ol.start = chs[0].numero;
    for (const c of chs) {
      const a = el("a", c.atelier ? "migre" : null, c.title);
      a.href = `#${c.slug}/recit`;          // le récit, dans son mode retenu
      const li = el("li");
      li.append(a);
      ol.append(li);
    }
    col.append(ol);
    grille.append(col);
  }
  if (!parties.length) grille.append(el("p", "mut", "Aucun chapitre : structure.yaml est vide."));
  st.append(grille);

  page.replaceChildren(ongletsLivre(), tete, corps, versions, st);
  page.querySelectorAll("textarea").forEach(ajuste);
  colonneLivre();
  zone().scrollTo(0, 0);
}

function champEdit(ch, valeur) {
  const d = el("label", "champ-edit " + (ch.classe ?? ""));
  d.append(el("span", "nom", ch.nom));
  const x = el(ch.long ? "textarea" : "input");
  x.value = valeur ?? "";
  x.placeholder = ch.long ? "à écrire" : "—";
  x.dataset.champ = ch.k;
  x.spellcheck = true;
  x.lang = etat.livre.langue ?? "fr";
  let minuterie = null;
  x.addEventListener("input", () => {
    if (ch.long) ajuste(x);
    statut("modifié…", "attente");
    clearTimeout(minuterie);
    minuterie = setTimeout(() => enregistre({ [ch.k]: x.value }), 700);
  });
  x.addEventListener("blur", () => {
    if (minuterie) { clearTimeout(minuterie); minuterie = null; enregistre({ [ch.k]: x.value }); }
  });
  d.append(x);
  return d;
}

function ajuste(t) {
  t.style.height = "auto";
  t.style.height = t.scrollHeight + 2 + "px";
}

function sectionClaude(L) {
  const C = L.claude ?? {};
  const s = el("section", "livre-bloc");
  s.append(el("p", "mut petit",
    "Écrit dans livre.yaml, section « claude ». Un modèle moins cher convient souvent à une retouche, à la vérification " +
    "d'une référence ou à une lecture naïve ; la vérification d'un fait et la création d'une fiche demandent du jugement sur les sources."));
  const selModele = (valeur, vide, surChange) => {
    const sel = el("select", "livre-select");
    const o0 = el("option", null, vide);
    o0.value = "";
    sel.append(o0);
    for (const [m, nom] of Object.entries(etat.modeles?.modeles ?? {})) {
      const o = el("option", null, nom);
      o.value = m;
      if (m === valeur) o.selected = true;
      sel.append(o);
    }
    sel.onchange = () => surChange(sel.value);
    return sel;
  };
  const apres = async (champs) => { await enregistre({ claude: champs }); await chargeModeles(); };
  const ligne = (nom, noeud) => { const l = el("label", "champ-edit ed-court"); l.append(el("span", "nom", nom), noeud); return l; };
  s.append(ligne("Modèle du livre", selModele(C.modele, "défaut de Claude Code", (v) => apres({ modele: v }))));
  const fileBox = el("div", "claude-genre");
  fileBox.append(el("strong", null, "File d'attente"));
  api("/file").then((F) => fileBox.append(reglageFile(F, () => accueil()),
    el("span", "mut petit", `${F.en_attente.length} en attente · désactivé : chaque demande se lance à la main`))).catch(() => {});
  s.append(fileBox);
  const LIB = { verification: "Vérification", reecriture: "Réécriture", fiche: "Fiche nouvelle", pistes: "Creuser", reference: "Référence",
    naive: "Lecture naïve", document: "Texte original", plan: "Plan", conversation: "Conversation", redaction: "Rédaction de l'essai" };
  const CH = { tours: "tours", recherches: "recherches web", pages: "pages lues" };
  for (const g of ["conversation", "redaction", "verification", "reecriture", "fiche", "pistes", "reference", "naive", "document", "plan"]) {
    const G = C[g] ?? {};
    const lim = etat.modeles?.limites?.[g] ?? {};
    const box = el("div", "claude-genre");
    box.append(el("strong", null, LIB[g]),
      selModele(G.modele, "comme le livre", (v) => apres({ [g]: { modele: v } })));
    for (const cle of ["verification", "fiche", "reference", "document", "conversation"].includes(g) ? ["tours", "recherches", "pages"] : g === "naive" ? [] : ["tours"]) {
      const n = el("input", "claude-nombre");
      n.type = "number";
      n.min = 0;
      n.value = G[cle] ?? lim[cle] ?? "";
      n.title = G[cle] == null ? "valeur par défaut" : "";
      n.onchange = () => apres({ [g]: { [cle]: n.value } });
      const l = el("label", "claude-lim");
      l.append(n, document.createTextNode(" " + CH[cle]));
      box.append(l);
    }
    s.append(box);
  }
  return s;
}

async function enregistre(champs) {
  statut("enregistrement…", "attente");
  const r = await fetch("/api/livre", {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ champs, version: etat.livre._version }),
  });
  if (r.ok) {
    etat.livre = await r.json();
    afficheTitre();
    statut("enregistré dans livre.yaml", "ok");
  } else if (r.status === 409) {
    statut("livre.yaml a changé ailleurs : page rechargée, ta dernière saisie n'est pas enregistrée", "erreur");
    setTimeout(accueil, 1500);
  } else {
    statut("erreur : " + ((await r.json().catch(() => ({}))).detail ?? r.status), "erreur");
  }
}

async function envoieCouverture(f) {
  statut("envoi de la couverture…", "attente");
  const r = await fetch(`/api/livre/couverture?nom=${encodeURIComponent(f.name)}&version=${etat.livre._version}`,
    { method: "POST", body: f });
  if (r.ok) { etat.livre = await r.json(); statut("couverture enregistrée", "ok"); accueil(); }
  else statut("erreur : " + ((await r.json().catch(() => ({}))).detail ?? r.status), "erreur");
}

function statut(texte, cls) {
  const s = document.getElementById("statut-livre");
  if (!s) return;
  s.textContent = texte;
  s.className = "statut " + cls;
}

// La colonne de droite : les fichiers (à ouvrir dans un éditeur), l'héritage, l'état.
function colonneLivre() {
  const f = document.getElementById("fiche");
  f.replaceChildren(el("h4", null, "Fichiers"));
  for (const nom of ["livre.yaml", "structure.yaml",
    ...Object.keys(etat.regles ?? {}).filter((v) => etat.regles[v].fichier).map((v) => `regles/${v}.md`)]) {
    const d = el("div", "fichier-ligne");
    d.append(el("code", null, nom));
    const ouvrir = el("button", "pan-lien", "ouvrir");
    ouvrir.title = "Ouvrir dans l'application par défaut du poste";
    ouvrir.onclick = () => fetch(`/api/ouvrir?chemin=${encodeURIComponent(nom)}`, { method: "POST" });
    const vs = el("a", "lien-ext", "VS Code ↗");
    vs.href = "vscode://file" + (etat.livre.chemins?.[nom] ?? etat.regles?.[nom.slice(7, -3)]?.fichier ?? "");
    d.append(ouvrir, vs);
    f.append(d);
  }
  f.append(el("p", "mut petit", etat.livre.dossier ?? ""));
  const s = el("p", "statut");
  s.id = "statut-livre";
  f.append(s);
  const h = etat.livre.heritage;
  if (h?.depot) {
    f.append(el("h4", null, "Héritage"));
    f.append(el("p", "mut petit", "Lu en lecture seule, tant que la migration n'est pas finie :"));
    f.append(champLecture("dépôt", h.depot));
    if (h.bibliographie) f.append(champLecture("bibliographie", h.bibliographie));
    if (h.resume) f.append(champLecture("résumé", h.resume));
  }
  f.append(el("p", "mut petit", "Versions et héritage se modifient dans livre.yaml."));
}

function champLecture(nom, valeur) {
  const d = el("div", "champ");
  d.append(el("span", "nom", nom), el("code", null, valeur));
  return d;
}

// ------------------------------------------------------------------ garde-fous d'écriture

// regles/<version>.md, une section par règle (« ## R14 — titre ») ou par contexte (la voix,
// les interdits). Modifiables sur place ; le fichier reste la source, lisible et diffable.

function sectionRegles() {
  const s = el("section", "livre-bloc garde-fous");
  s.id = "garde-fous";
  const versions = Object.keys(etat.regles ?? {});
  if (!versions.length) return s;
  etat.reglesVue = versions.includes(etat.reglesVue) ? etat.reglesVue : versions[0];
  s.append(el("h2", null, `Garde-fous d'écriture — ${etat.livre.versions?.[etat.reglesVue]?.titre ?? etat.reglesVue}`));
  const R = etat.regles[etat.reglesVue];
  if (!R.fichier) {
    s.append(el("p", "mut", `Pas de fichier regles/${etat.reglesVue}.md.`));
    return s;
  }
  s.append(el("p", "mut petit", "Données telles quelles à Claude pour toute réécriture de cette version ; " +
    "une règle peut être citée par une annotation. Fichier : regles/" + etat.reglesVue + ".md"));
  const liste = el("div", "gf-liste");
  for (const e of R.elements) liste.append(e.type === "regle" ? carteRegle(e) : carteSection(e));
  s.append(liste);
  const plus = el("button", "pan-lien", "＋ ajouter une règle");
  plus.onclick = () => plus.replaceWith(formRegle(null));
  s.append(plus);
  return s;
}

function carteRegle(e) {
  const c = el("div", "regle");
  c.id = `regle-${etat.reglesVue}-${e.id}`;
  const h = el("div", "regle-tete");
  h.append(el("span", "regle-id", e.id), el("span", "regle-titre", e.titre), boutonRef(`@regle/${etat.reglesVue}/${e.id}`));
  const act = el("span", "regle-actions");
  const mod = el("button", "pan-lien", "modifier");
  mod.onclick = () => c.replaceWith(formRegle(e));
  const sup = el("button", "pan-lien", "supprimer");
  sup.onclick = () => supprimeRegle(e);
  act.append(mod, sup);
  h.append(act);
  const corps = el("div", "regle-corps");
  corps.append(...mdBloc(e.texte));
  corps.onclick = () => corps.classList.toggle("ouvert");
  c.append(h, corps);
  return c;
}

function carteSection(e) {
  const d = el("details", "regle section");
  d.id = `regle-${etat.reglesVue}-${e.id}`;
  const sm = el("summary");
  sm.append(el("span", "regle-titre", e.titre));
  d.append(sm);
  const corps = el("div", "regle-corps ouvert");
  corps.append(...mdBloc(e.texte));
  const mod = el("button", "pan-lien", "modifier cette section");
  mod.onclick = () => d.replaceWith(formRegle(e));
  d.append(corps, mod);
  return d;
}

function formRegle(e) {
  const f = el("div", "regle form-regle");
  const titre = el("input", "dem-motif");
  titre.value = e?.titre ?? "";
  titre.placeholder = "titre de la règle (ex. Limiter les répétitions, sauf pour un effet)";
  const texte = el("textarea", "annot-texte");
  texte.value = e?.texte ?? "";
  texte.placeholder = "ce que la règle demande, et pourquoi ; un exemple si possible";
  const act = el("div", "annot-actions");
  const ok = el("button", "bouton", e ? "Enregistrer" : "Ajouter");
  const non = el("button", "pan-lien", "annuler");
  act.append(ok, non);
  f.append(el("span", "appui-lieu", e ? (e.type === "regle" ? e.id : "section") : "nouvelle règle"), titre, texte, act);
  setTimeout(() => { ajuste(texte); (e ? texte : titre).focus(); }, 0);
  texte.addEventListener("input", () => ajuste(texte));
  non.onclick = () => rafraichitRegles();
  ok.onclick = async () => {
    const v = etat.reglesVue;
    const r = await fetch(e ? `/api/regles/${v}/${encodeURIComponent(e.id)}` : `/api/regles/${v}`, {
      method: e ? "PUT" : "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ titre: titre.value, texte: texte.value, empreinte: etat.regles[v].empreinte }) });
    await finRegles(r);
  };
  return f;
}

async function supprimeRegle(e) {
  if (!confirm(`Supprimer ${e.id} — ${e.titre} ? Son identifiant ne sera pas réattribué.`)) return;
  const v = etat.reglesVue;
  const r = await fetch(`/api/regles/${v}/${encodeURIComponent(e.id)}?empreinte=${etat.regles[v].empreinte}`,
    { method: "DELETE" });
  await finRegles(r);
}

async function finRegles(r) {
  if (r.status === 409) statut("les règles ont changé ailleurs : rechargées, ta modification n'est pas enregistrée", "erreur");
  else if (!r.ok) statut("erreur : " + ((await r.json().catch(() => ({}))).detail ?? r.status), "erreur");
  else statut("enregistré dans regles/" + etat.reglesVue + ".md", "ok");
  await rafraichitRegles();
}

async function rafraichitRegles() {
  etat.regles = await api("/regles").catch(() => etat.regles);
  document.getElementById("garde-fous")?.replaceWith(sectionRegles());
  if (etat.accueil) barreLivre();
}

// Markdown d'un bloc de règle : paragraphes, listes, tableaux (tels quels), *italique*, **gras**.
function mdBloc(texte) {
  const out = [];
  for (const para of (texte ?? "").split(/\n\s*\n/)) {
    const l = para.trim();
    if (!l) continue;
    if (l.startsWith("|")) { out.push(el("pre", "regle-table", l)); continue; }
    if (/^#{3,}\s/.test(l)) { out.push(el("h5", null, l.replace(/^#+\s*/, ""))); continue; }
    if (/^[-*] /.test(l)) {
      const ul = el("ul");
      for (const it of l.split(/\n(?=[-*] )/)) { const li = el("li"); li.innerHTML = mdLigne(it.replace(/^[-*] /, "").replace(/\s+/g, " ")); ul.append(li); }
      out.push(ul);
      continue;
    }
    const p = el("p");
    p.innerHTML = mdLigne(l.replace(/\s+/g, " "));
    out.push(p);
  }
  return out;
}

// Les règles d'une version, pour les annotations : [{id, titre}].
function reglesDe(version) {
  return (etat.regles?.[version]?.elements ?? []).filter((e) => e.type === "regle");
}

function puceRegle(version, id) {
  const r = reglesDe(version).find((x) => x.id === id);
  const b = el("button", "puce regle-puce", id);
  b.title = r ? r.titre : "règle inconnue";
  b.onclick = (e) => { e.stopPropagation(); location.hash = `livre/regles/${version}/${id}`; };
  return b;
}

// ------------------------------------------------------------------ bascules

document.getElementById("versions").addEventListener("click", (e) => {
  if (e.target.dataset.v) bascule(e.target.dataset.v);
});

// L'adresse porte le chapitre et la vue : #la-mer/storyboard. Recharger garde la vue.
const VUES = ["recit", "essai", "storyboard"];

const MODES_ESSAI = ["texte", "notes", "biblio"];

// L'adresse d'une vue : #slug/recit/<storyboard|texte> ou #slug/essai/<texte|notes|biblio>.
// En interne, le récit avec storyboard reste la vue « storyboard », le récit seul la vue « recit ».
function adresse(slug, v = etat.version) {
  if (v === "essai") return `${slug}/essai/${etat.essaiMode}`;
  if (v === "storyboard") return `${slug}/recit/storyboard`;
  if (v === "recit") return `${slug}/recit/${etat.recitMode}`;
  return `${slug}/${v}`;
}

// « Récit » ouvre le récit dans son mode retenu (storyboard par défaut) ; déjà dans le
// récit, on y reste. « storyboard » et « recit » (texte seul) désignent les deux modes.
function bascule(v) {
  if (v === "recit") {
    const dedans = etat.version === "recit" || etat.version === "storyboard";
    v = dedans ? etat.version : (etat.recitMode === "texte" ? "recit" : "storyboard");
  }
  if (v === "storyboard") etat.recitMode = "storyboard";
  else if (v === "recit") etat.recitMode = "texte";
  if (etat.slug) location.hash = adresse(etat.slug, v);   // -> hashchange -> depuisAdresse
  else { etat.version = v; boutons(); sommaire(); }
}

function boutons() {
  const recit = etat.version === "recit" || etat.version === "storyboard";
  document.querySelectorAll("#versions button[data-v]").forEach((b) =>
    b.classList.toggle("actif", b.dataset.v === "recit" ? recit : b.dataset.v === etat.version));
  document.body.dataset.recit = recit ? "1" : "";
  if (etat.wiki) document.querySelectorAll("#versions button[data-v]").forEach((b) => b.classList.remove("actif"));
  document.getElementById("b-fiches").classList.toggle("actif", !!etat.wiki && !etat.enPlan);
  document.getElementById("b-plan").classList.toggle("actif", !!etat.enPlan);
}

function depuisAdresse() {
  quitte();
  const [slug, vue, mode] = decodeURIComponent(location.hash.slice(1)).split("/");
  if (slug.startsWith("fn")) return;
  etat.enPlan = slug === "plan";
  etat.wiki = slug === "fiches" || slug === "biblio" || etat.enPlan;
  boutons();
  if (etat.enPlan) { etat.accueil = false; return vuePlan(vue, mode); }
  if (slug === "biblio") { etat.accueil = false; return vue ? pageOeuvre(vue) : vueBiblioLivre(); }
  if (etat.wiki) { etat.accueil = false; return vueFiches(vue, mode); }
  if (!slug || slug === "livre") {
    etat.accueil = true;
    etat.ongletLivre = ["regles", "claude", "consommation"].includes(vue) ? vue : "presentation";
    if (vue === "regles") { etat.reglesVue = mode ?? etat.reglesVue; etat.regleCible = decodeURIComponent(location.hash).split("/")[3]; }
    return accueil();
  }
  etat.accueil = false;
  if (vue === "recit") {
    // #slug/recit (mode retenu), #slug/recit/texte, #slug/recit/storyboard
    if (mode === "texte" || mode === "storyboard") etat.recitMode = mode;
    etat.version = etat.recitMode === "texte" ? "recit" : "storyboard";
  } else if (VUES.includes(vue)) {
    etat.version = vue;
    if (vue === "storyboard") etat.recitMode = "storyboard";
  }
  if (vue === "essai" && MODES_ESSAI.includes(mode)) etat.essaiMode = mode;
  if (vue === "essai" && mode === "plan") { etat.essaiMode = "texte"; etat.planOn = true; }   // ancienne adresse
  boutons();
  ouvre(slug);
}

// ------------------------------------------------------------------ les fiches dans le texte
//
// Une pastille « fiche » ouvre la fiche en aperçu dans la colonne de droite, sans quitter le
// chapitre : son texte, sa confiance, ses liens (qui s'ouvrent dans l'aperçu). « ← » revient
// à ce que la colonne montrait ; « pleine page » va au wiki.

function titreFiche(slug) {
  return (etat.fichesIndex ?? []).find((x) => x.slug === slug)?.titre ?? slug;
}

function puceFiche(slug, section = null) {
  const b = el("button", "puce-fiche", "◇ " + slug);
  b.title = titreFiche(slug) + " — ouvrir la fiche ici";
  b.onclick = (e) => { e.stopPropagation(); apercuFiche(slug, section); };
  return b;
}

function blocFiches(titre, slugs, vide = null, comment = null) {
  const d = el("div", "bloc-fiches");
  d.append(el("h5", null, titre));
  if (comment) d.append(el("p", "mut petit", comment));
  if (!slugs.length && vide) d.append(el("p", "mut petit", vide));
  const p = el("div", "pastilles");
  p.append(...slugs.map((x) => puceFiche(x)));
  d.append(p);
  return d;
}

// Les fiches d'une note : celles des œuvres de la bibliographie du chapitre qui la citent.
function fichesDeNote(cle) {
  const out = new Set();
  for (const s of etat.atelier?.bibliographie ?? []) {
    if ((s.notes ?? []).includes(cle)) for (const f of s.fiches ?? []) out.add(f);
  }
  return [...out];
}

// Les fiches d'un paragraphe de l'essai : celles des notes qu'il appelle.
function fichesDuBloc(id) {
  const p = blocEl(id);
  if (!p) return [];
  const out = new Set();
  for (const a of p.querySelectorAll('a[href^="#fn:"]')) {
    for (const f of fichesDeNote(decodeURIComponent(a.getAttribute("href").slice(4)))) out.add(f);
  }
  return [...out];
}

async function apercuFiche(slug, section = null) {
  const d = document.getElementById("fiche");
  const dejaApercu = d.querySelector(":scope > .apercu-fiche");
  if (!dejaApercu) { etat.apercuRetour = [...d.childNodes]; etat.apercuPile = []; }
  else etat.apercuPile.push(dejaApercu.dataset.slug);
  let f;
  try { f = await api(`/fiches/${encodeURIComponent(slug)}`); }
  catch { alert("Fiche introuvable : " + slug); return; }
  indexFiches();
  const box = el("div", "apercu-fiche");
  box.dataset.slug = slug;
  const tete = el("div", "apercu-tete");
  const retour = el("button", "pan-lien", "←");
  retour.title = etat.apercuPile.length ? "fiche précédente" : "revenir à ce que montrait la colonne";
  retour.onclick = () => {
    const prec = etat.apercuPile.pop();
    if (prec) return rouvreApercu(prec);
    d.replaceChildren(...(etat.apercuRetour ?? []));
    etat.apercuRetour = null;
  };
  const plein = el("a", "pan-lien", "pleine page ↗");
  plein.href = `#fiches/${slug}${section ? "/" + section : ""}`;
  tete.append(retour, el("span", "mut petit", "fiche · " + slug), boutonRef("@fiche/" + slug), plein);
  const corps = el("div", "fiche-corps apercu");
  corps.innerHTML = f.html;
  corps.querySelectorAll("a.wiki").forEach((a) => {
    const [, cible, sec] = a.getAttribute("href").split("/");
    a.title = titreFiche(cible);
    a.onclick = (e) => { e.preventDefault(); apercuFiche(cible, sec ?? null); };
  });
  enrichit(corps);
  marqueConfiance(corps, f.confiance_par);
  const ch = el("p", "mut petit");
  ch.append(f.chapitres.length ? "Chapitres : " + f.chapitres.map((c) => `${c.numero ?? ""} ${c.title}`).join(" · ") : "Aucun chapitre ne la liste.");
  box.append(tete, el("h3", "apercu-titre", f.titre), pastilles(f.confiance, true), ch, corps);
  d.replaceChildren(box);
  if (section) document.getElementById("fs-" + section)?.scrollIntoView({ block: "start" });
  else document.getElementById("droite").scrollTop = 0;
}

// ------------------------------------------------------------------ la confiance par paragraphe

const CLASSE_DEGRE = { "établi": "etabli", "débattu": "debattu", "récent": "recent", "hypothèse": "hypo",
  "projeté": "projete", "raisonnement": "raison" };

function marqueConfiance(corps, C) {
  const par = C?.paragraphes ?? {};
  corps.querySelectorAll("[data-empreinte]").forEach((b) => {
    const x = par[b.dataset.empreinte];
    if (!x) return;
    b.classList.add("conf", "conf-" + (CLASSE_DEGRE[x.degre] ?? "raison"));
    b.dataset.degre = x.degre;
    b.title = `${x.degre} — ${x.raison}`;
  });
}

// Sous la confiance de la fiche : l'état de la lecture par paragraphe, et de quoi la (re)lancer.
function barreConfiance(f, corps) {
  const b = el("div", "barre-confiance");
  const C = f.confiance_par;
  const n = corps.querySelectorAll("[data-empreinte]").length;
  const marques = corps.querySelectorAll(".conf").length;
  const bouton = el("button", "pan-lien", C?.paragraphes ? "↻ relire" : "◐ lire la confiance par paragraphe…");
  bouton.title = "Claude lit chaque paragraphe et lui donne un degré (sans recherche) — quelques centimes";
  bouton.onclick = async () => {
    bouton.disabled = true;
    const r = await fetch(`/api/fiches/${f.slug}/confiance`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    if (!r.ok) { bouton.disabled = false; alert((await r.json().catch(() => ({}))).detail ?? r.status); return; }
    const attend = async () => {
      const e = await api(`/fiches/${f.slug}/confiance`).catch(() => null);
      if (!b.isConnected) return;
      if (e?.en_cours) { bouton.textContent = `lecture en cours… ${e.depuis_s} s`; return setTimeout(attend, 2000); }
      pageFiche(f.slug, null, etat.fichesIndex ?? []);
    };
    attend();
  };
  if (C?.paragraphes) {
    const leg = el("span", "legende-conf");
    for (const [deg, cl] of Object.entries(CLASSE_DEGRE)) {
      const k = corps.querySelectorAll(".conf-" + cl).length;
      if (k) leg.append(el("span", "pastille degre-" + (cl === "raison" ? "autre" : cl), `${deg} ${k}`));
    }
    const voir = el("label", "graphe-coche");
    const c = el("input");
    c.type = "checkbox"; c.checked = etat.voirConfiance ?? true;
    c.onchange = () => { etat.voirConfiance = c.checked; corps.classList.toggle("sans-conf", !c.checked); };
    corps.classList.toggle("sans-conf", !(etat.voirConfiance ?? true));
    voir.append(c, " en marge");
    b.append(el("span", "mut petit", `par paragraphe : ${marques}/${n} marqués · ${C.par === "creation" ? "à la création" : "lu par " + nomModele(C.modele)}` +
      ` le ${(C.date ?? "").slice(0, 10)}` + (marques < n ? " (les autres ont changé depuis, ou sont trop courts)" : "")), leg, voir);
  } else b.append(el("span", "mut petit", "Pas encore de confiance par paragraphe."));
  if (C?.erreur) b.append(el("span", "fiche-alerte petit", " dernière lecture en échec : " + C.erreur));
  b.append(bouton);
  return b;
}

// ------------------------------------------------------------------ les œuvres

async function chargeOeuvres(force = false) {
  if (!etat.oeuvres || force) {
    const O = await api("/oeuvres").catch(() => []);
    etat.oeuvres = Object.fromEntries(O.map((o) => [o.cle, o]));
  }
  return etat.oeuvres;
}

const STATUT_OEUVRE = {
  importee: ["importée", "", "venue de la base centrale, jamais vérifiée une à une"],
  a_verifier: ["à vérifier", "doute", "hors base, douteuse, ou relevée par Claude"],
  verifiee: ["vérifiée", "ok", "l'œuvre existe, la référence est juste"],
  corrigee: ["corrigée", "ok", "l'œuvre existe, la référence a été rectifiée"],
  introuvable: ["introuvable", "hors", "aucune trace fiable de l'œuvre"],
  mal_attribuee: ["mal attribuée", "hors", "l'œuvre existe, mais ne dit pas ce qu'on lui fait dire"],
  doublon: ["doublon", "hors", "la même œuvre qu'une autre clé"],
  hors_base: ["hors base", "hors", "citée, mais absente de kb/sources"],
};

function badgeStatut(o) {
  const s = STATUT_OEUVRE[o.statut ?? (o.centrale ? "importee" : "hors_base")] ?? [o.statut, "", ""];
  const b = el("span", "badge statut-" + (s[1] || "neutre"), s[0]);
  b.title = s[2];
  return b;
}

// Une œuvre dans la colonne de droite : sa référence, ses liens, et tout ce qui la cite.
async function apercuOeuvre(cle) {
  const d = document.getElementById("fiche");
  const dejaApercu = d.querySelector(":scope > .apercu-fiche");
  if (!dejaApercu) { etat.apercuRetour = [...d.childNodes]; etat.apercuPile = []; }
  else etat.apercuPile.push(dejaApercu.dataset.slug);
  const O = await chargeOeuvres();
  const o = O[cle];
  const box = el("div", "apercu-fiche apercu-oeuvre");
  box.dataset.slug = "œ:" + cle;
  const tete = el("div", "apercu-tete");
  const retour = el("button", "pan-lien", "←");
  retour.onclick = () => {
    const prec = etat.apercuPile.pop();
    if (prec) return rouvreApercu(prec);
    d.replaceChildren(...(etat.apercuRetour ?? []));
    etat.apercuRetour = null;
  };
  const plein = el("a", "pan-lien", "page de l'œuvre ↗");
  plein.href = `#biblio/${cle}`;
  tete.append(retour, el("span", "mut petit", "œuvre · " + cle), boutonRef("@oeuvre/" + cle), plein);
  box.append(tete);
  if (!o) {
    box.append(el("p", "fiche-alerte", `Clé « ${cle} » introuvable : ni dans la base centrale, ni dans une bibliographie de chapitre, ni dans les sources d'une fiche.`));
    d.replaceChildren(box);
    return;
  }
  const ref = el("p", "oeuvre-ref");
  ref.innerHTML = mdLigne(o.ref || cle);
  box.append(ref);
  const meta = el("div", "biblio-ou");
  meta.append(badgeStatut(o));
  if (o.doublon_de) { const x = el("button", "pan-lien", "même œuvre que " + o.doublon_de); x.onclick = () => apercuOeuvre(o.doublon_de); meta.append(x); }
  if (o.doute) { const x = el("span", "badge doute", "doute"); x.title = o.doute; meta.append(x); }
  meta.append(liensSource(o.doi, o.ref));
  if (o.url) { const a = el("a", "lien-ext", "page ↗"); a.href = o.url; a.target = "_blank"; meta.append(a); }
  box.append(meta);
  if (o.doute) box.append(el("p", "mut petit", "doute : " + o.doute));
  if (o.notes) box.append(el("p", "mut petit", o.notes));
  // la dernière vérification retenue
  const V = o.verification;
  if (V) {
    const v = el("div", "oeuvre-verif");
    v.append(el("span", "appui-lieu", `vérifiée le ${V.date} (${V.verdict})`), el("p", "petit", V.resume ?? ""));
    for (const c of V.citations ?? []) {
      const l = el("p", "petit");
      l.append(el("span", "badge " + (c.appui === "oui" ? "statut-ok" : c.appui === "non" ? "hors" : "doute"), c.appui), ` ${c.ou} — ${c.commentaire ?? ""}`);
      v.append(l);
    }
    const a = el("button", "pan-lien", "la demande →");
    a.onclick = () => tiroir(V.demande);
    v.append(a);
    box.append(v);
  }
  // les actions : vérifier, modifier, ajouter à la base
  const act = el("div", "annot-actions oeuvre-actions");
  if (o.centrale) {
    const ver = el("button", "bouton", "🔎 vérifier la référence…");
    ver.title = "Claude la retrouve (éditeur, PubMed, arXiv…), cherche un doublon, et contrôle ce que chaque endroit lui fait dire";
    ver.onclick = () => ver.replaceWith(formVerifReference(cle));
    const mod = el("button", "pan-lien", "✎ modifier");
    mod.onclick = () => { box.querySelector(".form-oeuvre")?.remove(); act.after(formOeuvre(o)); };
    act.append(ver, mod);
  } else {
    const aj = el("button", "bouton", "＋ ajouter à la base");
    aj.title = "l'écrire dans kb/sources (statut « à vérifier »), pour pouvoir la vérifier";
    aj.onclick = async () => {
      const r = await fetch("/api/oeuvres", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cle, ref: o.ref, doi: o.doi, url: o.url, doute: o.doute, fiches: o.fiches,
          origine: "ajoutée depuis la bibliographie de l'atelier (citée " + (o.chapitres.length ? "par l'essai" : "par une fiche") + ")" }) });
      if (!r.ok) { alert((await r.json().catch(() => ({}))).detail ?? r.status); return; }
      await chargeOeuvres(true);
      d.querySelector(":scope > .apercu-fiche")?.remove();
      apercuOeuvre(cle);
    };
    act.append(aj);
  }
  box.append(act);
  api("/fiches/demandes").then((ds) => {
    const V2 = ds.filter((x) => x.type === "reference" && x.cle === cle && x.etat !== "decidee");
    for (const x of V2) {
      const b = el("button", "pan-lien", `🔎 vérification ${etiquetteDemande(x)} →`);
      b.onclick = () => tiroir(x.id);
      act.append(b);
    }
  }).catch(() => {});
  box.append(el("h5", null, `Dans l'essai · ${o.chapitres.length} chapitre(s)`));
  if (!o.chapitres.length) box.append(el("p", "mut petit", "Aucune note d'un chapitre de l'atelier ne la cite."));
  for (const c of o.chapitres) {
    const l = el("div", "petit");
    l.append(`${c.numero ?? ""} ${c.title} : `);
    (c.notes.length ? c.notes : [null]).forEach((n, i) => {
      const a = el("a", "lien-fiche-inline", n ? "note " + n.replace(c.slug + "-", "") : "bibliographie");
      a.href = `#${c.slug}/essai/${n ? "notes" : "biblio"}`;
      a.onclick = () => { etat.noteApres = n; etat.sourceChoisie = n ? null : cle; };
      l.append(i ? " · " : "", a);
    });
    if (c.citation === "clair") l.append(el("span", "mut", " (citée en clair)"));
    box.append(l);
  }
  box.append(el("h5", null, `Dans les fiches · ${o.fiches.length}`));
  const p = el("div", "pastilles");
  p.append(...o.fiches.map((f) => puceFiche(f)));
  box.append(p);
  if (o.extraits.length) {
    box.append(el("h5", null, "Extraits relevés"));
    for (const x of o.extraits) {
      const q = el("blockquote", "verif-extrait", x.extrait ?? "");
      const s = el("p", "petit");
      s.append(puceFiche(x.fiche), el("span", x.verifie ? "verif-ok" : "verif-non", x.verifie ? " lu" : " non vérifié"));
      box.append(s, q);
    }
  }
  d.replaceChildren(box);
  document.getElementById("droite").scrollTop = 0;
}

function formVerifReference(cle) {
  const f = el("div", "form-demande");
  const z = el("textarea", "annot-texte petit-texte");
  z.placeholder = "Précision (facultatif) : ce qui fait douter…";
  const mod = choixModele("reference");
  const lim = etat.modeles?.limites?.reference;
  const go = el("button", "bouton", "🔎 vérifier");
  go.onclick = async () => {
    go.disabled = true;
    const r = await fetch(`/api/oeuvres/${cle}/verification`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ consigne: z.value, modele: mod.valeur() }) });
    if (!r.ok) { go.disabled = false; alert((await r.json().catch(() => ({}))).detail ?? r.status); return; }
    tiroir((await r.json()).id);
  };
  const non = el("button", "pan-lien", "annuler");
  non.onclick = () => f.remove();
  const act = el("div", "annot-actions");
  act.append(go, non);
  f.append(el("span", "appui-lieu", "vérifier la référence " + cle), z, mod.noeud,
    el("p", "mut petit", `Budget : ${lim ? `${lim.recherches} recherches, ${lim.pages} pages, ${lim.tours} tours` : "livre.yaml"}. ` +
      "Rien n'est modifié sans toi."), act);
  return f;
}

function formOeuvre(o) {
  const f = el("div", "form-demande form-oeuvre");
  const champ = (nom, v, long = false) => {
    const x = el(long ? "textarea" : "input", long ? "annot-texte petit-texte" : "dem-motif");
    x.value = v ?? "";
    f.append(el("span", "appui-lieu", nom), x);
    return x;
  };
  const ref = champ("référence (Markdown : *revue*)", o.ref, true);
  const doi = champ("DOI (lu sur une page, jamais de mémoire)", o.doi);
  const url = champ("page", o.url);
  const st = el("select", "livre-select");
  for (const [k, [lib]] of Object.entries(STATUT_OEUVRE)) {
    if (k === "hors_base") continue;
    const op = el("option", null, lib); op.value = k; if (k === o.statut) op.selected = true; st.append(op);
  }
  f.append(el("span", "appui-lieu", "statut"), st);
  const doute = champ("doute", o.doute, true);
  const notes = champ("notes", o.notes, true);
  const motif = el("input", "dem-motif");
  motif.placeholder = "motif (va au journal)";
  const ok = el("button", "bouton", "enregistrer");
  ok.onclick = async () => {
    const r = await fetch(`/api/oeuvres/${o.cle}`, { method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ champs: { ref: ref.value, doi: doi.value, url: url.value, statut: st.value, doute: doute.value, notes: notes.value },
        motif: motif.value }) });
    if (!r.ok) { alert((await r.json().catch(() => ({}))).detail ?? r.status); return; }
    await chargeOeuvres(true);
    document.querySelector("#fiche > .apercu-fiche")?.remove();
    apercuOeuvre(o.cle);
  };
  const non = el("button", "pan-lien", "annuler");
  non.onclick = () => f.remove();
  const act = el("div", "annot-actions");
  act.append(ok, non);
  f.append(motif, act);
  return f;
}

const VERDICT_REF = { confirmee: "confirmée", corrigee: "corrigée", introuvable: "introuvable", mal_attribuee: "mal attribuée", doublon: "doublon" };

async function tiroirReference(t, d) {
  t.replaceChildren(teteTiroir("Vérifier une référence", () => historiqueFiches(t)));
  const cible = el("div", "dem-cible");
  const c = el("p", "annot-corps");
  const lien = el("a", "pan-lien", d.cible.cle + " ↗");
  lien.href = `#biblio/${d.cible.cle}`;
  lien.title = "la page de l'œuvre : ses documents, ses citations, ses vérifications";
  lien.onclick = () => { t.hidden = true; delete document.body.dataset.tiroir; };
  c.append(lien, " — ");
  const ref = el("span");
  ref.innerHTML = mdLigne(d.cible.ref ?? "");
  c.append(ref);
  cible.append(c);
  if (d.cible.usages?.length) cible.append(el("p", "mut petit", "citée : " + d.cible.usages.join(" · ")));
  t.append(cible);
  if (d.etat === "en_attente" || d.etat === "retiree") return t.append(blocAttente(d));
  if (d.etat === "en_cours") {
    t.append(enDirect(d));
    suivi = setTimeout(() => rafraichitDirect(d.id), 2000);
    return piedTiroir(t, d);
  }
  if (d.etat === "erreur") { t.append(el("p", "annot-orph-titre", "Échec : " + d.erreur)); return piedTiroir(t, d); }
  const R = d.resultat ?? {};
  const tete = el("div", "annot-tete");
  tete.append(el("strong", null, "Verdict : "), el("span", "verdict " + (R.verdict === "confirmee" ? "etabli" : R.verdict === "corrigee" ? "nuance" : "contredit"),
    VERDICT_REF[R.verdict] ?? R.verdict));
  t.append(tete, el("p", "annot-corps", R.resume ?? ""));
  const I = R.identite ?? {};
  if (Object.keys(I).length) {
    const id = el("div", "verif-source");
    id.append(el("span", "verif-ref", [I.auteurs, I.titre && `« ${I.titre} »`, I.revue, I.volume, I.pages, I.annee].filter(Boolean).join(" · ")));
    if (I.doi) { const a = el("a", "lien-ext", "doi ↗"); a.href = "https://doi.org/" + I.doi; a.target = "_blank"; id.append(" ", a); }
    if (I.url) { const a = el("a", "lien-ext", "page ↗"); a.href = I.url; a.target = "_blank"; id.append(" ", a); }
    if (I.lu_sur) id.append(el("span", "mut petit", " · lu sur " + I.lu_sur));
    t.append(el("h5", null, "L'œuvre trouvée"), id);
  }
  if (R.ref) {
    const p = el("p", "annot-corps");
    p.innerHTML = "référence proposée : " + mdLigne(R.ref);
    t.append(p);
  }
  if (R.doublon_de) {
    const p = el("p", "fiche-alerte petit");
    const b = el("button", "pan-lien", R.doublon_de);
    b.onclick = () => apercuOeuvre(R.doublon_de);
    p.append("même œuvre que ", b, " : la clé n'est pas fusionnée, le doublon est signalé.");
    t.append(p);
  }
  if ((R.citations ?? []).length) {
    t.append(el("h5", null, "Ce qu'on lui fait dire"));
    for (const x of R.citations) {
      const b = el("div", "verif-source");
      b.append(el("span", "badge " + (x.appui === "oui" ? "statut-ok" : x.appui === "non" ? "hors" : "doute"), x.appui), ` ${x.ou}`);
      b.append(el("p", "petit", x.commentaire ?? ""));
      if (x.extrait) b.append(el("blockquote", "verif-extrait", x.extrait));
      t.append(b);
    }
  }
  if (d.decision) t.append(el("div", "dem-decision", d.decision.proposition ? `Retenue — statut : ${d.decision.statut}` +
    (d.decision.chapitres?.length ? ` · bibliographie de ${d.decision.chapitres.join(", ")} mise à jour` : "") : "Non retenue"));
  if (d.etat === "prete") {
    const faire = el("div", "que-faire");
    faire.append(el("h5", null, "Que faire ?"), el("p", "mut petit",
      "Retenir écrit l'œuvre dans kb/sources (référence, DOI, statut, cette vérification) et met à jour la bibliographie " +
      "des chapitres qui la citent. Un « mal attribuée » ne corrige pas l'essai : la note est à reprendre à part."));
    const z = el("textarea", "annot-texte petit-texte");
    z.value = R.ref ?? "";
    z.placeholder = "référence à écrire (vide : garder l'actuelle)";
    const oui = el("button", "bouton", "retenir");
    const non = el("button", "pan-lien", "ne pas retenir");
    const envoie = async (corps) => {
      const r = await fetch(`/api/chapitres/_kb/demandes/${d.id}/decision`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps) });
      if (!r.ok) { alert("échec : " + ((await r.json().catch(() => ({}))).detail ?? r.status)); return; }
      await chargeOeuvres(true);
      etat.sources = await api("/sources").catch(() => etat.sources);
      tiroir(d.id);
    };
    oui.onclick = () => envoie({ action: "retenir", ref: z.value });
    non.onclick = () => envoie({ action: "rejeter" });
    const act = el("div", "annot-actions");
    act.append(oui, non);
    faire.append(z, act);
    t.append(faire);
  }
  piedTiroir(t, d);
}

// ------------------------------------------------------------------ les références
//
// @fiche/luca#section · @oeuvre/cle · @chapitre/slug[/essai#sec|/essai^bloc|/recit^bloc|/plan/A|
// /assertion/1.9|/note/cle|/annotation/id] · @partie/p1 · @regle/recit/R11
// ⧉ copie une référence ; collée dans une consigne ou une annotation, Claude reçoit la partie visée.

const MOTIF_REF = /(?<![\w[])@(fiche|oeuvre|chapitre|partie|regle)\/[\w./#^:-]*[\w-]/g;

function copieRef(ref) {
  const fin = () => {
    const a = el("div", "avis", "copié : " + ref);
    document.body.append(a);
    setTimeout(() => a.remove(), 2200);
  };
  if (navigator.clipboard?.writeText) navigator.clipboard.writeText(ref).then(fin, () => prompt("La référence :", ref));
  else prompt("La référence :", ref);
}

function boutonRef(ref, classe = "pan-lien ref-copie") {
  const b = el("button", classe, "⧉");
  b.title = "copier la référence " + ref + " — à coller dans une consigne : Claude lira cette partie";
  b.onclick = (e) => { e.stopPropagation(); e.preventDefault(); copieRef(ref); };
  return b;
}

// Aller à ce qu'une référence désigne.
function allerRef(ref) {
  const m = ref.match(/^@(\w+)\/(.+)$/);
  if (!m) return;
  const [, genre, chemin] = m;
  if (genre === "fiche") { const [s, sec] = chemin.split("#"); location.hash = `fiches/${s}${sec ? "/" + sec : ""}`; return; }
  if (genre === "oeuvre") { location.hash = `biblio/${chemin}`; return; }
  if (genre === "partie") { location.hash = `plan/p/${chemin}`; return; }
  if (genre === "regle") { location.hash = `livre/regles/${chemin}`; return; }
  const c = chemin.match(/^([\w-]+)(?:\/(.*))?$/);
  const slug = c[1], reste = c[2] ?? "";
  let x;
  if ((x = reste.match(/^(essai|recit)\^([\w-]+)$/))) {
    if (etat.slug === slug && !etat.wiki && !etat.accueil) return vaVers(x[1], x[2]);
    etat.blocApres = { version: x[1], bloc: x[2] };
    location.hash = `${slug}/${x[1] === "essai" ? "essai/texte" : "recit/texte"}`;
  } else if ((x = reste.match(/^(essai|recit)#([\w-]+)$/))) {
    etat.cibleSection = x[2];
    location.hash = `${slug}/${x[1] === "essai" ? "essai/texte" : "recit/texte"}`;
  } else if ((x = reste.match(/^note\/(.+)$/))) {
    etat.noteApres = x[1];
    location.hash = `${slug}/essai/notes`;
  } else if ((x = reste.match(/^annotation\/(.+)$/))) {
    etat.annotApres = x[1];
    location.hash = `${slug}/recit/texte`;
  } else if (/^(plan|assertion)\//.test(reste)) location.hash = `${slug}/recit/storyboard`;
  else if (/^(essai|recit)$/.test(reste)) location.hash = `${slug}/${reste === "essai" ? "essai/texte" : "recit/texte"}`;
  else location.hash = `plan/c/${slug}`;
}

// Les références d'un nœud déjà écrit deviennent des liens (le texte ne change pas).
function lieRefs(racine) {
  if (!racine) return;
  const w = document.createTreeWalker(racine, NodeFilter.SHOW_TEXT);
  const aTraiter = [];
  while (w.nextNode()) {
    MOTIF_REF.lastIndex = 0;
    if (MOTIF_REF.test(w.currentNode.data) && !w.currentNode.parentElement.closest("a, textarea, input, .ref-lien")) aTraiter.push(w.currentNode);
  }
  for (const n of aTraiter) {
    const frag = document.createDocumentFragment();
    let i = 0;
    for (const m of n.data.matchAll(new RegExp(MOTIF_REF.source, "g"))) {
      frag.append(n.data.slice(i, m.index));
      const a = el("a", "ref-lien", m[0]);
      a.href = "#";
      a.onclick = (e) => { e.preventDefault(); e.stopPropagation(); allerRef(m[0]); };
      frag.append(a);
      i = m.index + m[0].length;
    }
    frag.append(n.data.slice(i));
    n.replaceWith(frag);
  }
}

// Sous un champ de consigne : ce que Claude lira, pour chaque référence collée.
let refsMinuteur = null;
document.addEventListener("input", (e) => {
  const x = e.target;
  if (!(x instanceof HTMLTextAreaElement || x instanceof HTMLInputElement) || !x.closest("#tiroir, #page, #fiche, #dialogue")) return;
  clearTimeout(refsMinuteur);
  refsMinuteur = setTimeout(async () => {
    let aide = x.nextElementSibling?.classList.contains("aide-refs") ? x.nextElementSibling : null;
    MOTIF_REF.lastIndex = 0;
    if (!MOTIF_REF.test(x.value)) { aide?.remove(); return; }
    const R = await api("/refs?texte=" + encodeURIComponent(x.value)).catch(() => []);
    if (!aide) { aide = el("div", "aide-refs"); x.after(aide); }
    aide.replaceChildren(el("span", "mut petit", "Claude lira : "));
    for (const r of R) {
      const s = el("span", "ref-resolue " + (r.ok ? "ok" : "ko"), (r.ok ? "✓ " + r.titre : "✗ " + r.ref + " — " + (r.erreur ?? "introuvable")));
      if (r.ok) s.title = (r.extrait ?? "").slice(0, 600);
      aide.append(s);
    }
  }, 350);
});

// ------------------------------------------------------------------ le plan et le synopsis
//
// #plan              le livre : synopsis, idée, arc, et la structure (parties, chapitres)
// #plan/p/<id>       une partie : son sens, son arc, sa question, ses chapitres
// #plan/c/<slug>     un chapitre : son synopsis, sa question, ses fiches
// À chaque niveau, on édite à la main, ou on demande une proposition à Claude (✦).

async function opSynopsis(corps) {
  const r = await fetch("/api/plan", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps) });
  if (!r.ok) { alert((await r.json().catch(() => ({}))).detail ?? r.status); return null; }
  etat.plan = await r.json();
  etat.chapitres = await api("/chapitres").catch(() => etat.chapitres);
  sommaire();
  return etat.plan;
}

// Un champ du plan : il s'enregistre quand on le quitte.
function champPlanSyn(lib, valeur, enregistre, { long = false, aide = "" } = {}) {
  const l = el("label", "champ-edit champ-plan-syn");
  l.append(el("span", "nom", lib));
  const x = el(long ? "textarea" : "input", long ? "annot-texte" : "dem-motif");
  x.value = valeur ?? "";
  if (aide) x.placeholder = aide;
  if (long) { x.rows = 2; setTimeout(() => ajuste(x), 0); x.addEventListener("input", () => ajuste(x)); }
  x.addEventListener("change", async () => {
    x.classList.add("enregistre");
    await enregistre(x.value);
    x.classList.remove("enregistre");
  });
  l.append(x);
  return l;
}

function barrePlan(niveau, cible, actions) {
  const o = document.getElementById("outils");
  o.replaceChildren();
  o.hidden = false;
  o.append(el("span", "etiq", "plan"));
  const g = el("span", "groupe");
  const P = etat.plan;
  const b = (lib, h, actif) => { const x = el("button", actif ? "actif" : null, lib); x.onclick = () => { location.hash = h; }; g.append(x); };
  b("le livre", "plan", niveau === "livre");
  if (niveau !== "livre") {
    const pid = niveau === "partie" ? cible : P.parties.find((p) => p.chapitres.some((c) => c.slug === cible))?.id;
    const p = P.parties.find((x) => x.id === pid);
    if (p) b(p.title.slice(0, 32), `plan/p/${p.id}`, niveau === "partie");
    if (niveau === "chapitre") b(P.parties.flatMap((x) => x.chapitres).find((c) => c.slug === cible)?.title?.slice(0, 32) ?? cible, `plan/c/${cible}`, true);
  }
  o.append(g, el("span", "espace"));
  if (actions) o.append(actions);
}

function boutonPropose(niveau, cible, lib) {
  const b = el("button", "b-versions", lib);
  b.title = "Claude lit le plan et la base de fiches, et propose ; tu retiens élément par élément";
  b.onclick = () => {
    const z = document.querySelector("#page > .actions-fiche");
    const f = el("div", "form-demande");
    const cons = el("textarea", "annot-texte petit-texte");
    cons.placeholder = "Précision (facultatif) : ce qui compte, ce qu'il faut garder, l'angle…";
    const mod = choixModele("plan");
    const go = el("button", "bouton", "✦ proposer");
    go.onclick = async () => {
      go.disabled = true;
      const r = await fetch("/api/plan/propose", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ niveau, partie: niveau === "partie" ? cible : null, chapitre: niveau === "chapitre" ? cible : null,
          consigne: cons.value, modele: mod.valeur() }) });
      if (!r.ok) { go.disabled = false; alert((await r.json().catch(() => ({}))).detail ?? r.status); return; }
      tiroir((await r.json()).id);
    };
    const non = el("button", "pan-lien", "annuler");
    non.onclick = () => f.remove();
    const act = el("div", "annot-actions");
    act.append(go, non);
    f.append(el("span", "appui-lieu", lib.replace("…", "") + " — une lecture du plan et des fiches, sans web ; rien n'est écrit sans toi"), cons, mod.noeud, act);
    z.replaceChildren(f);
    f.scrollIntoView({ block: "center" });
  };
  return b;
}

// Les demandes de plan en cours ou à décider, pour ce niveau.
async function demandesPlan(niveau, cible) {
  const ds = await api("/fiches/demandes").catch(() => []);
  const d = el("div");
  const ici = ds.filter((y) => y.type === "plan" && y.niveau === niveau && (niveau === "livre" || y.partie === cible || y.chapitre === cible));
  for (const x of ici.filter((y) => ["en_cours", "prete", "erreur"].includes(y.etat))) {
    const b = el("button", "banniere-pistes", `✦ ${x.titre} — ${etiquetteDemande(x)} → ouvrir`);
    b.onclick = () => tiroir(x.id);
    d.append(b);
  }
  // les propositions passées restent attachées à leur niveau : ce qui a été retenu, rejeté, et leurs manques
  const passees = ici.filter((y) => !["en_cours", "prete", "erreur"].includes(y.etat));
  if (passees.length) {
    const h = el("details", "plan-historique");
    h.append(el("summary", "mut petit", `propositions passées de Claude (${passees.length})`));
    const ul = el("ul");
    for (const x of passees) {
      const li = el("li");
      const a = el("a", null, `${(x.cree ?? "").slice(0, 10)} · ${x.decision?.proposition === "retenue" ? `retenue (${x.decision.faits?.length ?? 0} changements)` : etiquetteDemande(x)}`);
      a.href = "#";
      a.onclick = (e) => { e.preventDefault(); tiroir(x.id); };
      li.append(a);
      if (x.consigne) li.append(el("span", "mut petit", " — " + x.consigne.slice(0, 90)));
      ul.append(li);
    }
    h.append(ul);
    d.append(h);
  }
  return d;
}

function colonnePlanSyn(niveau, cible) {
  const volet = document.getElementById("volet-chapitre");
  volet.hidden = false;
  volet.querySelector(".volet-titre").textContent = "Plan";
  const col = document.getElementById("plan-col");
  const r = el("div", "plan-fiche");
  const lien = (lib, h, actif, niv) => {
    const a = el("a", "pf-ligne" + (actif ? " actif" : ""), lib);
    a.href = "#" + h;
    a.style.paddingLeft = (niv * .9 + .6) + "rem";
    r.append(a);
  };
  lien(etat.plan.livre.titre || "Le livre", "plan", niveau === "livre", 0);
  let n = 0;
  for (const p of etat.plan.parties) {
    lien(p.title, `plan/p/${p.id}`, niveau === "partie" && cible === p.id, 1);
    for (const c of p.chapitres) lien(`${++n}. ${c.title}`, `plan/c/${c.slug}`, niveau === "chapitre" && cible === c.slug, 2);
  }
  col.replaceChildren(r);
}

async function vuePlan(vue, id) {
  document.body.dataset.vue = "plan";
  delete document.body.dataset.panneau;
  sommaire();
  etat.plan = await api("/plan");
  if (vue === "p") return pagePartie(id);
  if (vue === "c") return pageChapitrePlan(id);
  return pageLivrePlan();
}

// Une liste de chapitres (d'une partie), avec de quoi les ranger.
function listeChapitres(p) {
  const d = el("div", "plan-chapitres");
  const tous = etat.plan.parties.flatMap((x) => x.chapitres.map((c) => c.slug));
  p.chapitres.forEach((c) => {
    const l = el("div", "plan-chapitre");
    const a = el("a", "plan-chapitre-titre", `${tous.indexOf(c.slug) + 1}. ${c.title}`);
    a.href = `#plan/c/${c.slug}`;
    l.append(a);
    if (c.periode) l.append(el("span", "mut petit", " · " + c.periode));
    l.append(badgesAvancement(c));
    const outils = el("span", "plan-outils");
    const bt = (lib, titre, f) => { const x = el("button", "pan-lien", lib); x.title = titre; x.onclick = f; outils.append(x); };
    bt("↑", "monter (au bord : partie précédente)", () => opSynopsis({ op: "chapitre_deplace", slug: c.slug, sens: -1 }).then((P) => P && vuePlanCourant()));
    bt("↓", "descendre (au bord : partie suivante)", () => opSynopsis({ op: "chapitre_deplace", slug: c.slug, sens: 1 }).then((P) => P && vuePlanCourant()));
    if (!c.a_texte) bt("✕", "supprimer (le chapitre n'a pas de texte)", () => confirm(`Supprimer « ${c.title} » du plan ?`) &&
      opSynopsis({ op: "chapitre_supprime", slug: c.slug }).then((P) => P && vuePlanCourant()));
    l.append(outils);
    if (c.synopsis) l.append(el("p", "plan-synopsis", c.synopsis.length > 320 ? c.synopsis.slice(0, 320) + "…" : c.synopsis));
    else l.append(el("p", "mut petit", "pas encore de synopsis"));
    if (c.fiches.length) { const f = el("div", "pastilles"); f.append(...c.fiches.map((x) => puceFiche(x))); l.append(f); }
    d.append(l);
  });
  const ajout = el("div", "annot-actions");
  const titre = el("input", "dem-motif");
  titre.placeholder = "＋ un chapitre (son titre)";
  titre.onkeydown = async (e) => {
    if (e.key !== "Enter" || !titre.value.trim()) return;
    if (await opSynopsis({ op: "chapitre_ajoute", partie: p.id, titre: titre.value })) vuePlanCourant();
  };
  ajout.append(titre);
  d.append(ajout);
  return d;
}

function vuePlanCourant() {
  const [, vue, id] = decodeURIComponent(location.hash.slice(1)).split("/");
  if (vue === "p") return pagePartie(id);
  if (vue === "c") return pageChapitrePlan(id);
  return pageLivrePlan();
}

async function pageLivrePlan() {
  const P = etat.plan, L = P.livre;
  const page = document.getElementById("page");
  const actions = el("span", "actions-barre");
  actions.append(boutonPropose("livre", null, "✦ proposer la structure…"), boutonSerie(null));
  barrePlan("livre", null, actions);
  colonnePlanSyn("livre");
  const zone_ = el("div", "actions-fiche");
  page.replaceChildren(el("h1", null, L.titre || "Le livre"), await demandesPlan("livre"), zone_,
    champPlanSyn("synopsis court", L.synopsis, (v) => opSynopsis({ op: "livre", champs: { synopsis: v } }), { long: true, aide: "le livre en un paragraphe (celui de la couverture)" }),
    champPlanSyn("idée maîtresse", L.idee, (v) => opSynopsis({ op: "livre", champs: { idee: v } }), { long: true, aide: "une phrase : ce que le livre démontre" }),
    champPlanSyn("arc", L.arc, (v) => opSynopsis({ op: "livre", champs: { arc: v } }), { long: true, aide: "le mouvement d'ensemble, du début à la fin" }),
    champPlanSyn("synopsis développé", L.developpe, (v) => opSynopsis({ op: "livre", champs: { developpe: v } }), { long: true, aide: "quelques paragraphes" }));
  page.append(el("h2", "oeuvre-section", `Structure · ${P.parties.length} partie(s) · ${P.parties.reduce((s, p) => s + p.chapitres.length, 0)} chapitre(s)`));
  P.parties.forEach((p, i) => {
    const c = el("div", "plan-partie");
    const tete = el("div", "plan-partie-tete");
    const a = el("a", "plan-partie-titre", `${i + 1}. ${p.title}`);
    a.href = `#plan/p/${p.id}`;
    tete.append(a);
    const outils = el("span", "plan-outils");
    const bt = (lib, titre, f) => { const x = el("button", "pan-lien", lib); x.title = titre; x.onclick = f; outils.append(x); };
    bt("↑", "monter", () => opSynopsis({ op: "partie_deplace", id: p.id, sens: -1 }).then((X) => X && pageLivrePlan()));
    bt("↓", "descendre", () => opSynopsis({ op: "partie_deplace", id: p.id, sens: 1 }).then((X) => X && pageLivrePlan()));
    if (!p.chapitres.length) bt("✕", "supprimer la partie (vide)", () => opSynopsis({ op: "partie_supprime", id: p.id }).then((X) => X && pageLivrePlan()));
    tete.append(outils);
    c.append(tete);
    if (p.sens) c.append(el("p", "plan-synopsis", p.sens));
    if (p.question) c.append(el("p", "mut petit", "question : " + p.question));
    c.append(listeChapitres(p));
    page.append(c);
  });
  const np = el("input", "dem-motif");
  np.placeholder = "＋ une partie (son titre)";
  np.onkeydown = async (e) => {
    if (e.key !== "Enter" || !np.value.trim()) return;
    if (await opSynopsis({ op: "partie_ajoute", titre: np.value })) pageLivrePlan();
  };
  page.append(np);
  document.getElementById("fiche").replaceChildren(el("h4", null, "Plan"), el("p", "mut petit",
    "Le livre s'écrit de haut en bas : l'idée et l'arc du livre, le sens de chaque partie, le synopsis de chaque chapitre, puis le texte. " +
    "Chaque niveau s'édite à la main, ou avec une proposition de Claude (✦) qu'on retient élément par élément."),
    el("p", "mut petit", "Les champs s'enregistrent quand on les quitte."));
  zone().scrollTo(0, 0);
}

async function pagePartie(pid) {
  const P = etat.plan;
  const i = P.parties.findIndex((x) => x.id === pid);
  const p = P.parties[i];
  const page = document.getElementById("page");
  if (!p) { page.replaceChildren(el("p", "mut", "Partie inconnue.")); return; }
  const actions = el("span", "actions-barre");
  actions.append(boutonRef("@partie/" + pid, "b-versions"), boutonPropose("partie", pid, "✦ développer la partie…"), boutonSerie(pid));
  barrePlan("partie", pid, actions);
  colonnePlanSyn("partie", pid);
  const zone_ = el("div", "actions-fiche");
  const voisins = el("p", "fil");
  if (i > 0) { const a = el("a", null, "← " + P.parties[i - 1].title); a.href = `#plan/p/${P.parties[i - 1].id}`; voisins.append(a, "   "); }
  if (i < P.parties.length - 1) { const a = el("a", null, P.parties[i + 1].title + " →"); a.href = `#plan/p/${P.parties[i + 1].id}`; voisins.append(a); }
  page.replaceChildren(voisins, el("h1", null, `Partie ${i + 1} — ${p.title}`), await demandesPlan("partie", pid), zone_,
    champPlanSyn("titre", p.title, (v) => opSynopsis({ op: "partie", id: pid, champs: { title: v } })),
    champPlanSyn("sens", p.sens, (v) => opSynopsis({ op: "partie", id: pid, champs: { sens: v } }), { long: true, aide: "ce que la partie accomplit dans le livre, et pourquoi elle vient là" }),
    champPlanSyn("arc", p.arc, (v) => opSynopsis({ op: "partie", id: pid, champs: { arc: v } }), { long: true, aide: "son mouvement, du premier chapitre au dernier" }),
    champPlanSyn("question", p.question, (v) => opSynopsis({ op: "partie", id: pid, champs: { question: v } }), { aide: "la question à laquelle elle répond" }),
    el("h2", "oeuvre-section", `Chapitres · ${p.chapitres.length}`), listeChapitres(p));
  document.getElementById("fiche").replaceChildren(el("h4", null, "Partie"), el("p", "mut petit",
    "Son sens et ses chapitres. « Développer la partie » : Claude propose son sens, son arc, sa question, et la liste de ses chapitres — ajouter, retirer, réordonner."));
  zone().scrollTo(0, 0);
}

async function pageChapitrePlan(slug) {
  const P = etat.plan;
  const tous = P.parties.flatMap((p) => p.chapitres.map((c) => ({ ...c, partie: p })));
  const i = tous.findIndex((c) => c.slug === slug);
  const c = tous[i];
  const page = document.getElementById("page");
  if (!c) { page.replaceChildren(el("p", "mut", "Chapitre inconnu.")); return; }
  const actions = el("span", "actions-barre");
  actions.append(boutonRef("@chapitre/" + slug, "b-versions"), boutonPropose("chapitre", slug, "✦ développer le chapitre…"));
  if (["synopsis", "brief"].includes(c.avancement?.essai)) actions.append(boutonEcrire(slug));
  for (const v of c.versions.filter((v) => c.a_texte || v === "essai")) {
    const a = el("a", "b-versions lien-barre", `${v === "essai" ? "essai" : "récit"} ↗`);
    a.href = `#${slug}/${v === "essai" ? "essai/texte" : "recit"}`;
    actions.append(a);
  }
  barrePlan("chapitre", slug, actions);
  colonnePlanSyn("chapitre", slug);
  const zone_ = el("div", "actions-fiche");
  const voisins = el("p", "fil");
  if (i > 0) { const a = el("a", null, "← " + tous[i - 1].title); a.href = `#plan/c/${tous[i - 1].slug}`; voisins.append(a, "   "); }
  if (i < tous.length - 1) { const a = el("a", null, tous[i + 1].title + " →"); a.href = `#plan/c/${tous[i + 1].slug}`; voisins.append(a); }
  const statut = el("select", "livre-select");
  for (const s of ["outline", "draft", "revised", "locked"]) { const o = el("option", null, s); o.value = s; if (s === (c.status ?? "outline")) o.selected = true; statut.append(o); }
  statut.onchange = () => opSynopsis({ op: "chapitre", slug, champs: { status: statut.value } });
  const partie = el("select", "livre-select");
  for (const p of P.parties) { const o = el("option", null, p.title); o.value = p.id; if (p.id === c.partie.id) o.selected = true; partie.append(o); }
  partie.onchange = () => opSynopsis({ op: "chapitre_deplace", slug, partie: partie.value }).then((X) => X && pageChapitrePlan(slug));
  const ligne = el("div", "annot-actions");
  ligne.append(el("span", "mut petit", "partie"), partie, el("span", "mut petit", "statut"), statut);
  const fiches = el("div", "pastilles");
  fiches.append(...c.fiches.map((x) => puceFiche(x)));
  page.replaceChildren(voisins, el("h1", null, `${i + 1}. ${c.title}`), await demandesPlan("chapitre", slug), zone_, ligne,
    champPlanSyn("titre", c.title, (v) => opSynopsis({ op: "chapitre", slug, champs: { title: v } })),
    champPlanSyn("période", c.periode, (v) => opSynopsis({ op: "chapitre", slug, champs: { periode: v } }), { aide: "facultatif : 13,8 Ga → 380 000 ans…" }),
    champPlanSyn("question", c.question, (v) => opSynopsis({ op: "chapitre", slug, champs: { question: v } }), { aide: "la question à laquelle il répond, et qui ouvre la suivante" }),
    champPlanSyn("synopsis", c.synopsis, (v) => opSynopsis({ op: "chapitre", slug, champs: { synopsis: v } }), { long: true, aide: "ce qui arrive, dans l'ordre" }),
    el("h2", "oeuvre-section", `Fiches · ${c.fiches.length}`), fiches,
    champPlanSyn("fiches (slugs, séparés par des virgules)", c.fiches.join(", "), (v) => opSynopsis({ op: "chapitre", slug, champs: { fiches: v } }).then((X) => X && pageChapitrePlan(slug))));
  if (!c.a_texte) page.append(el("p", "mut petit", "Pas encore de texte. « Développer le chapitre » propose, en plus du synopsis, le déroulé de l'essai et ses assertions — " +
    "et, si tu le retiens, amorce l'essai (un squelette, une section par étape) et son verrou."));
  document.getElementById("fiche").replaceChildren(el("h4", null, "Chapitre"), el("p", "mut petit",
    "Son synopsis, sa question, ses fiches. Il existe dès cette étape (chapters/" + slug + "/brief.yaml), avant tout texte."));
  zone().scrollTo(0, 0);
}

// Le tiroir d'une proposition de plan : on retient élément par élément.
async function tiroirPlan(t, d) {
  const niv = d.cible.niveau;
  t.replaceChildren(teteTiroir(d.titre ?? "Plan", () => historiqueFiches(t)));
  if (d.etat === "en_cours") {
    t.append(enDirect(d));
    suivi = setTimeout(() => rafraichitDirect(d.id), 2000);
    return piedTiroir(t, d);
  }
  if (d.etat === "erreur") { t.append(el("p", "annot-orph-titre", "Échec : " + d.erreur)); return piedTiroir(t, d); }
  const R = d.resultat ?? {};
  const P = await api("/plan").catch(() => etat.plan);
  if (R.remarques) t.append(el("p", "annot-corps", R.remarques));
  const prete = d.etat === "prete";
  const coche = (lib, val = true) => {
    const l = el("label", "dem-consulter");
    const x = el("input");
    x.type = "checkbox"; x.checked = val; x.disabled = !prete;
    l.append(x, " " + lib);
    return [l, x];
  };
  const sel = { livre: [], parties: {}, chapitres: {}, chapitre: [], amorce: false };
  const lecteurs = [];
  if (R.livre && niv === "livre") {
    t.append(el("h5", null, "Le livre"));
    for (const [k, lib] of [["idee", "idée maîtresse"], ["arc", "arc"], ["developpe", "synopsis développé"]]) {
      if (!R.livre[k]) continue;
      const [l, x] = coche(lib, !P.livre[k]);
      const b = el("div", "piste piste-nouvelle");
      b.append(l, el("p", "annot-corps", R.livre[k]));
      if (P.livre[k]) b.append(el("p", "mut petit", "actuel : " + P.livre[k].slice(0, 300)));
      t.append(b);
      lecteurs.push(() => { if (x.checked) sel.livre.push(k); });
    }
  }
  const tous = new Map(P.parties.flatMap((p) => p.chapitres.map((c) => [c.slug, c])));
  (R.parties ?? []).forEach((p, i) => {
    const b = el("div", "plan-partie proposee");
    const [l, x] = coche(`${p.id ? "partie " + p.id + " (existante)" : "partie nouvelle"} — ${p.titre}`);
    b.append(l, el("p", "plan-synopsis", p.sens ?? ""));
    if (p.arc) b.append(el("p", "mut petit", "arc : " + p.arc));
    if (p.question) b.append(el("p", "mut petit", "question : " + p.question));
    lecteurs.push(() => { if (x.checked) sel.parties[String(i)] = ["titre", "sens", "arc", "question"]; });
    (p.chapitres ?? []).forEach((c, j) => {
      const exist = c.slug && tous.get(c.slug);
      const [lc, xc] = coche(`${exist ? "existant" : "nouveau"} — ${c.titre}${c.periode ? " (" + c.periode + ")" : ""}`);
      const cc = el("div", "plan-chapitre");
      cc.append(lc, el("p", "plan-synopsis", c.synopsis ?? ""));
      if (c.question) cc.append(el("p", "mut petit", "question : " + c.question));
      if (c.fiches?.length) { const f = el("div", "pastilles"); f.append(...c.fiches.map((y) => puceFiche(y))); cc.append(f); }
      if (exist?.synopsis) cc.append(el("p", "mut petit", "synopsis actuel : " + exist.synopsis.slice(0, 200)));
      b.append(cc);
      lecteurs.push(() => { if (xc.checked) sel.chapitres[`${i}.${j}`] = true; });
    });
    t.append(b);
  });
  const C = R.chapitre;
  if (C && niv === "chapitre") {
    const cur = tous.get(d.cible.chapitre) ?? {};
    for (const [k, lib] of [["synopsis", "synopsis"], ["question", "question"]]) {
      if (!C[k]) continue;
      const [l, x] = coche(lib);
      const b = el("div", "piste piste-nouvelle");
      b.append(l, el("p", "annot-corps", C[k]));
      if (cur[k]) b.append(el("p", "mut petit", "actuel : " + cur[k].slice(0, 300)));
      t.append(b);
      lecteurs.push(() => { if (x.checked) sel.chapitre.push(k); });
    }
    if (C.fiches?.length) {
      const [l, x] = coche("fiches du chapitre");
      const b = el("div", "piste piste-nouvelle");
      b.append(l);
      for (const f of C.fiches) { const p = el("p", "petit"); p.append(puceFiche(f.fiche), " " + f.raison); b.append(p); }
      t.append(b);
      lecteurs.push(() => { if (x.checked) sel.chapitre.push("fiches"); });
    }
    if (C.deroule?.length) {
      t.append(el("h5", null, `Déroulé de l'essai · ${C.deroule.length} section(s)`));
      const ol = el("ol", "petit");
      for (const s of C.deroule) { const li = el("li"); li.append(el("strong", null, s.titre), " — " + s.contenu); ol.append(li); }
      t.append(ol);
    }
    if (C.assertions?.length) {
      t.append(el("h5", null, `Assertions · ${C.assertions.length}`));
      const ol = el("ol", "petit");
      for (const a of C.assertions) { const li = el("li", null, a.texte); if (a.fiche) li.append(" ", puceFiche(a.fiche)); ol.append(li); }
      t.append(ol);
    }
    if (C.deroule?.length || C.assertions?.length) {
      const [l, x] = coche("amorcer l'essai : le squelette (une section par étape du déroulé) et un premier verrou (les assertions)", !cur.a_texte);
      if (cur.a_texte) { x.checked = false; x.disabled = true; l.append(el("span", "mut petit", " — le chapitre a déjà du texte")); }
      t.append(l);
      lecteurs.push(() => { sel.amorce = x.checked; });
    }
  }
  if ((R.manques ?? []).length) {
    t.append(el("h5", null, "Sujets sans fiche"));
    for (const m of R.manques) {
      const p = el("p", "petit");
      const b = el("button", "pan-lien", "◇ créer une fiche…");
      b.onclick = () => b.replaceWith(formFiche({ question: m }));
      p.append(m + " ", b);
      t.append(p);
    }
  }
  if (d.decision) t.append(el("div", "dem-decision", d.decision.proposition ? "Retenue : " + (d.decision.faits ?? []).join(" · ") : "Rien retenu"));
  if (prete) {
    const faire = el("div", "que-faire");
    faire.append(el("h5", null, "Que faire ?"), el("p", "mut petit",
      "Décocher ce qu'on ne garde pas. Retenir écrit le plan (structure.yaml, synopsis.yaml, les briefs) — une partie ou un chapitre existant est mis à jour, un nouveau est créé ; les chapitres retenus prennent l'ordre proposé."));
    const oui = el("button", "bouton", "retenir la sélection");
    const non = el("button", "pan-lien", "ne rien retenir");
    const envoie = async (corps) => {
      const r = await fetch(`/api/chapitres/_kb/demandes/${d.id}/decision`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps) });
      if (!r.ok) { alert((await r.json().catch(() => ({}))).detail ?? r.status); return; }
      etat.chapitres = await api("/chapitres").catch(() => etat.chapitres);
      sommaire();
      if (etat.enPlan) { etat.plan = await api("/plan"); vuePlanCourant(); }
      tiroir(d.id);
    };
    oui.onclick = () => { lecteurs.forEach((f) => f()); oui.disabled = true; envoie({ action: "retenir", ...sel }); };
    non.onclick = () => envoie({ action: "rejeter" });
    const act = el("div", "annot-actions");
    act.append(oui, non);
    faire.append(act);
    t.append(faire);
  }
  piedTiroir(t, d);
}

// ------------------------------------------------------------------ la page d'une œuvre

const CONTROLE_CIT = { trouvee: ["trouvée", "statut-ok"], absente: ["absente du document", "hors"],
  sans_document: ["pas de document", "statut-neutre"], trop_courte: ["trop courte", "statut-neutre"] };

function titreOeuvre(o) {
  const m = (o.ref ?? "").match(/«\s*(.+?)\s*»/);
  return m ? m[1] : o.cle;
}

async function pageOeuvre(cle) {
  document.body.dataset.vue = "fiches";
  delete document.body.dataset.panneau;
  document.getElementById("volet-chapitre").hidden = true;
  sommaire();
  const page = document.getElementById("page");
  let X;
  try { X = await api(`/oeuvres/${encodeURIComponent(cle)}`); }
  catch { page.replaceChildren(el("p", "mut", `Pas d'œuvre « ${cle} ».`)); return; }
  const o = X.oeuvre, B = X.base;
  const rafraichit = async () => { await chargeOeuvres(true); pageOeuvre(cle); };
  // la barre : les actions sur l'œuvre
  const aO = el("span", "actions-barre");
  aO.append(el("span", "etiq", "cette œuvre"), boutonRef("@oeuvre/" + cle, "b-versions"));
  const zoneForm = el("div", "actions-fiche");
  const ouvre = (n) => { zoneForm.replaceChildren(n); n.scrollIntoView({ block: "center" }); };
  if (B) {
    const ver = el("button", "b-versions", "🔎 vérifier…");
    ver.onclick = () => ouvre(formVerifReference(cle));
    const ori = el("button", "b-versions", "⤓ texte original…");
    ori.title = "Claude cherche une version en accès libre ; tu choisis, le serveur la range dans le livre";
    ori.onclick = () => ouvre(formOriginal(cle));
    const mod = el("button", "b-versions", "✎ modifier");
    mod.onclick = () => ouvre(formOeuvre(Object.assign({}, B, { cle })));
    aO.append(ver, ori, mod);
  } else {
    const aj = el("button", "b-versions", "＋ ajouter à la base");
    aj.onclick = async () => {
      const r = await fetch("/api/oeuvres", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cle, ref: o.ref, doi: o.doi, url: o.url, doute: o.doute, fiches: o.fiches, origine: "ajoutée depuis sa page" }) });
      if (!r.ok) { alert((await r.json().catch(() => ({}))).detail ?? r.status); return; }
      rafraichit();
    };
    aO.append(aj);
  }
  barreFiches("biblio", aO);

  const fil = el("p", "fil");
  const retour = el("a", null, "Bibliographie");
  retour.href = "#biblio";
  fil.append(retour, ` › ${cle}`);
  const ref = el("p", "oeuvre-ref grande");
  ref.innerHTML = mdLigne(o.ref || cle);
  const meta = el("div", "biblio-ou");
  meta.append(badgeStatut(o));
  if (o.doublon_de) { const a = el("a", "pan-lien", "même œuvre que " + o.doublon_de); a.href = `#biblio/${o.doublon_de}`; meta.append(a); }
  if (o.doute) { const x = el("span", "badge doute", "doute"); x.title = o.doute; meta.append(x); }
  meta.append(liensSource(o.doi, o.ref));
  if (o.url) { const a = el("a", "lien-ext", "page ↗"); a.href = o.url; a.target = "_blank"; meta.append(a); }
  page.replaceChildren(fil, el("h1", null, titreOeuvre(o)), ref, meta, zoneForm);
  if (o.origine) page.append(el("p", "mut petit", "origine : " + o.origine));
  if (o.doute) page.append(el("p", "mut petit", "doute : " + o.doute));
  if (o.notes) page.append(el("p", "mut petit", o.notes));
  if (!B) page.append(el("p", "fiche-alerte petit", "Cette œuvre est citée, mais n'est pas dans la bibliographie du livre (kb/sources) : l'y ajouter pour la vérifier, ranger ses documents et ses citations."));
  const section = (titre, n) => { const h = el("h2", "oeuvre-section", n != null ? `${titre} · ${n}` : titre); page.append(h); return h; };

  // les documents
  if (B) {
    const docs = B.documents ?? [];
    section("Documents", docs.length);
    if (!docs.length) page.append(el("p", "mut petit", "Aucun document : le texte original n'est pas encore dans le livre."));
    for (const x of docs) {
      const l = el("div", "doc-ligne");
      const a = el("a", "pan-lien", "📄 " + x.fichier);
      a.href = `/api/oeuvres/${encodeURIComponent(cle)}/documents/${encodeURIComponent(x.fichier)}`;
      a.target = "_blank";
      l.append(a, el("span", "mut petit", ` ${x.pages ? x.pages + " pages · " : ""}${Math.round((x.taille ?? 0) / 1024)} Ko · ${x.date} · ${x.par ?? ""}` +
        (x.texte ? "" : " · texte non extrait")));
      if (x.source && /^https?:/.test(x.source)) { const s = el("a", "lien-ext", "source ↗"); s.href = x.source; s.target = "_blank"; l.append(" ", s); }
      else if (x.source) l.append(el("span", "mut petit", " · " + x.source));
      const rm = el("button", "pan-lien danger", "retirer");
      rm.onclick = async () => {
        if (!confirm(`Retirer ${x.fichier} du livre ?`)) return;
        await fetch(`/api/oeuvres/${encodeURIComponent(cle)}/documents/${encodeURIComponent(x.fichier)}`, { method: "DELETE" });
        rafraichit();
      };
      l.append(" ", rm);
      page.append(l);
    }
    const ajout = el("div", "annot-actions doc-ajout");
    const fichier = el("input");
    fichier.type = "file";
    fichier.accept = ".pdf,.html,.htm,.txt,.xml,.epub";
    fichier.hidden = true;
    const tel = el("button", "bouton", "⇪ téléverser un document…");
    tel.onclick = () => fichier.click();
    fichier.onchange = async () => {
      const f = fichier.files[0];
      if (!f) return;
      tel.disabled = true; tel.textContent = "envoi…";
      const r = await fetch(`/api/oeuvres/${encodeURIComponent(cle)}/documents?nom=${encodeURIComponent(f.name)}`, { method: "POST", body: f });
      if (!r.ok) { alert((await r.json().catch(() => ({}))).detail ?? r.status); tel.disabled = false; tel.textContent = "⇪ téléverser un document…"; return; }
      rafraichit();
    };
    const url = el("input", "dem-motif");
    url.placeholder = "ou l'adresse d'un PDF en accès libre…";
    const dl = el("button", "pan-lien", "⤓ télécharger");
    dl.onclick = async () => {
      if (!url.value.trim()) return;
      dl.disabled = true; dl.textContent = "téléchargement…";
      const r = await fetch(`/api/oeuvres/${encodeURIComponent(cle)}/documents/url`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.value }) });
      if (!r.ok) { alert((await r.json().catch(() => ({}))).detail ?? r.status); dl.disabled = false; dl.textContent = "⤓ télécharger"; return; }
      rafraichit();
    };
    ajout.append(tel, fichier, url, dl);
    page.append(ajout);
    for (const x of X.demandes.filter((y) => y.type === "document" && y.etat !== "decidee")) {
      const b = el("button", "pan-lien", `⤓ recherche du texte original : ${etiquetteDemande(x)} →`);
      b.onclick = () => tiroir(x.id);
      page.append(b);
    }
  }

  // les citations
  if (B) {
    const C = B.citations ?? [];
    section("Citations", C.length);
    page.append(el("p", "mut petit", "Les passages cités mot pour mot, chacun contrôlé contre les documents de l'œuvre " +
      "(ponctuation, casse et accents ignorés)."));
    C.forEach((c, i) => {
      const b = el("div", "citation-oeuvre");
      b.append(el("blockquote", "verif-extrait", c.texte));
      const m = el("div", "biblio-ou");
      const k = CONTROLE_CIT[c.controle?.etat] ?? [c.controle?.etat ?? "?", "statut-neutre"];
      m.append(el("span", "badge " + k[1], k[0] + (c.controle?.page ? ` · p. ${c.controle.page}` : "")));
      if (c.page) m.append(el("span", "mut petit", `page indiquée : ${c.page}`));
      if (c.usage) m.append(el("span", "mut petit", "· " + c.usage));
      m.append(el("span", "mut petit", `· ${c.origine ?? ""} · ${c.date ?? ""}`));
      const rm = el("button", "pan-lien danger", "retirer");
      rm.onclick = async () => { await fetch(`/api/oeuvres/${encodeURIComponent(cle)}/citations/${i}`, { method: "DELETE" }); rafraichit(); };
      m.append(rm);
      b.append(m);
      page.append(b);
    });
    const f = el("div", "form-demande");
    const tx = el("textarea", "annot-texte petit-texte");
    tx.placeholder = "le passage, mot pour mot (dans la langue de l'œuvre)";
    const pgx = el("input", "dem-motif");
    pgx.placeholder = "page (facultatif)";
    const us = el("input", "dem-motif");
    us.placeholder = "où il sert (note, fiche…) — facultatif";
    const ok = el("button", "bouton", "＋ ajouter la citation");
    ok.onclick = async () => {
      const r = await fetch(`/api/oeuvres/${encodeURIComponent(cle)}/citations`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ texte: tx.value, page: pgx.value || null, usage: us.value || null }) });
      if (!r.ok) { alert((await r.json().catch(() => ({}))).detail ?? r.status); return; }
      rafraichit();
    };
    f.append(tx, pgx, us, ok);
    page.append(f);
  }

  // les vérifications : la dernière, l'historique, celles en cours
  section("Vérifications", (B?.verifications ?? []).length || null);
  const V = B?.verification;
  if (V) {
    const v = el("div", "oeuvre-verif");
    v.append(el("span", "appui-lieu", `dernière : ${V.date} — ${VERDICT_REF[V.verdict] ?? V.verdict}`), el("p", "petit", V.resume ?? ""));
    for (const c of V.citations ?? []) {
      const l = el("p", "petit");
      l.append(el("span", "badge " + (c.appui === "oui" ? "statut-ok" : c.appui === "non" ? "hors" : "doute"), c.appui), ` ${c.ou} — ${c.commentaire ?? ""}`);
      v.append(l);
    }
    page.append(v);
  } else page.append(el("p", "mut petit", "Jamais vérifiée."));
  const H = [...(B?.verifications ?? [])].reverse();
  for (const h of H) {
    const b = el("button", "pan-lien", `${h.date} · ${VERDICT_REF[h.verdict] ?? h.verdict} · ${h.demande} →`);
    b.onclick = () => tiroir(h.demande);
    page.append(b, el("br"));
  }
  for (const x of X.demandes.filter((y) => y.type === "reference" && y.etat !== "decidee")) {
    const b = el("button", "pan-lien", `🔎 vérification ${etiquetteDemande(x)} →`);
    b.onclick = () => tiroir(x.id);
    page.append(b, el("br"));
  }

  // où elle est citée
  section("Où elle est citée", X.usages.length + (o.fiches ?? []).length);
  for (const u of X.usages) {
    const b = el("div", "usage-oeuvre");
    const m = u.ou.match(/^note (\S+) \(chapitre (\S+)\)$/), f = u.ou.match(/^fiche (\S+), section \{#(\S*)\}$/);
    const a = el("a", "pan-lien", u.ou);
    if (m) { a.href = `#${m[2]}/essai/notes`; a.onclick = () => { etat.noteApres = m[1]; }; }
    else if (f) a.href = `#fiches/${f[1]}${f[2] ? "/" + f[2] : ""}`;
    b.append(a, el("p", "petit", u.texte));
    page.append(b);
  }
  if ((o.fiches ?? []).length) {
    const p = el("div", "pastilles");
    p.append(el("span", "mut petit", "exploitée dans les fiches : "), ...o.fiches.map((x) => puceFiche(x)));
    page.append(p);
  }
  for (const c of o.chapitres ?? []) {
    const l = el("p", "petit");
    const a = el("a", "pan-lien", `${c.numero ?? ""} ${c.title} — bibliographie du chapitre`);
    a.href = `#${c.slug}/essai/biblio`;
    a.onclick = () => { etat.sourceChoisie = cle; };
    l.append(a);
    page.append(l);
  }

  // doublons possibles, historique
  if (X.candidats.length) {
    section("Doublons possibles", X.candidats.length);
    for (const c of X.candidats) {
      const l = el("p", "petit");
      const a = el("a", "pan-lien", c.cle);
      a.href = `#biblio/${c.cle}`;
      const r = el("span");
      r.innerHTML = " (" + c.pourquoi + ") — " + mdLigne(c.ref ?? "");
      l.append(a, r);
      page.append(l);
    }
  }
  if (X.journal.length) {
    section("Historique", X.journal.length);
    const ul = el("ul", "petit historique-oeuvre");
    for (const e of [...X.journal].reverse()) {
      const li = el("li");
      li.append(el("span", "mut", (e.date ?? "").slice(0, 16).replace("T", " ") + " "), e.type.replace(/_/g, " "),
        e.verdict ? ` — ${e.verdict}` : "", e.fichier ? ` — ${e.fichier}` : "", e.motif ? ` — ${e.motif}` : "",
        e.texte ? ` — « ${e.texte.slice(0, 80)} »` : "");
      ul.append(li);
    }
    page.append(ul);
  }
  document.getElementById("fiche").replaceChildren(el("h4", null, "Œuvre"),
    el("p", "mut petit", "Tout ce qui la concerne : ses documents (le texte original, rangé dans le livre), les passages cités mot pour mot, " +
      "ses vérifications, et chaque endroit du livre qui la cite."));
  zone().scrollTo(0, 0);
}

function formOriginal(cle) {
  const f = el("div", "form-demande");
  const z = el("textarea", "annot-texte petit-texte");
  z.placeholder = "Précision (facultatif) : une édition, une version…";
  const mod = choixModele("document");
  const go = el("button", "bouton", "⤓ chercher le texte original");
  go.onclick = async () => {
    go.disabled = true;
    const r = await fetch(`/api/oeuvres/${encodeURIComponent(cle)}/original`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ consigne: z.value, modele: mod.valeur() }) });
    if (!r.ok) { go.disabled = false; alert((await r.json().catch(() => ({}))).detail ?? r.status); return; }
    tiroir((await r.json()).id);
  };
  const non = el("button", "pan-lien", "annuler");
  non.onclick = () => f.remove();
  const act = el("div", "annot-actions");
  act.append(go, non);
  f.append(el("span", "appui-lieu", "texte original — une version en accès libre (PMC, arXiv, dépôts, éditeur en libre accès), jamais une bibliothèque pirate"),
    z, mod.noeud, el("p", "mut petit", "Claude propose des candidats ; tu choisis ; le serveur télécharge et range le document. " +
      "Si le texte n'est lisible que derrière un mur, téléverse ton exemplaire."), act);
  return f;
}

async function tiroirDocument(t, d) {
  t.replaceChildren(teteTiroir("Texte original", () => historiqueFiches(t)));
  const cible = el("div", "dem-cible");
  const a = el("a", "pan-lien", d.cible.cle + " ↗");
  a.href = `#biblio/${d.cible.cle}`;
  a.onclick = () => { t.hidden = true; delete document.body.dataset.tiroir; };
  const r0 = el("span");
  r0.innerHTML = " — " + mdLigne(d.cible.ref ?? "");
  cible.append(a, r0);
  t.append(cible);
  if (d.etat === "en_attente" || d.etat === "retiree") return t.append(blocAttente(d));
  if (d.etat === "en_cours") {
    t.append(enDirect(d));
    suivi = setTimeout(() => rafraichitDirect(d.id), 2000);
    return piedTiroir(t, d);
  }
  if (d.etat === "erreur") { t.append(el("p", "annot-orph-titre", "Échec : " + d.erreur)); return piedTiroir(t, d); }
  const R = d.resultat ?? { candidats: [] };
  t.append(el("p", "annot-corps", R.resume ?? ""));
  if (!R.libre) t.append(el("p", "fiche-alerte petit", "Pas de version en accès libre trouvée : téléverser ton exemplaire depuis la page de l'œuvre."));
  R.candidats.forEach((c, i) => {
    const b = el("div", "piste piste-nouvelle");
    const tete = el("div", "annot-tete");
    tete.append(el("span", "badge", c.type), el("span", "badge", c.version), el("span", "badge " + (c.confiance === "haute" ? "statut-ok" : "doute"), c.confiance));
    b.append(tete);
    const u = el("a", "lien-ext", c.url);
    u.href = c.url; u.target = "_blank";
    b.append(u, el("p", "petit", `${c.source}${c.licence ? " · " + c.licence : ""}`));
    if (c.note) b.append(el("p", "mut petit", c.note));
    if (c.echec) b.append(el("p", "fiche-alerte petit", "échec : " + c.echec));
    if (d.etat === "prete") {
      const go = el("button", "bouton", "⤓ télécharger celui-ci");
      go.onclick = async () => {
        go.disabled = true; go.textContent = "téléchargement…";
        const r = await fetch(`/api/chapitres/_kb/demandes/${d.id}/decision`, { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "telecharger", i }) });
        if (!r.ok) { alert((await r.json().catch(() => ({}))).detail ?? r.status); tiroir(d.id); return; }
        await chargeOeuvres(true);
        tiroir(d.id);
      };
      b.append(go);
    }
    t.append(b);
  });
  if (d.decision?.proposition === "telecharge") {
    const p = el("p", "verif-ok petit", "document rangé dans le livre — ");
    const l = el("a", "pan-lien", "la page de l'œuvre ↗");
    l.href = `#biblio/${d.cible.cle}`;
    l.onclick = () => { t.hidden = true; delete document.body.dataset.tiroir; };
    p.append(l);
    t.append(p);
  }
  if (d.etat === "prete") {
    const non = el("button", "pan-lien", "n'en garder aucun");
    non.onclick = async () => {
      await fetch(`/api/chapitres/_kb/demandes/${d.id}/decision`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: "rejeter" }) });
      tiroir(d.id);
    };
    t.append(non);
  }
  piedTiroir(t, d);
}

// Un clic sur une citation, où qu'elle soit (essai, notes, fiche, aperçu) : l'œuvre à droite.
document.addEventListener("click", (e) => {
  const c = e.target.closest?.("cite[data-cle]");
  if (!c || e.target.closest(".editeur")) return;
  e.preventDefault();
  e.stopPropagation();
  apercuOeuvre(c.dataset.cle);
}, true);

// La bibliographie du livre : toutes les œuvres, d'où qu'elles viennent.
async function vueBiblioLivre(cle) {
  document.body.dataset.vue = "fiches";
  delete document.body.dataset.panneau;
  document.getElementById("outils").hidden = true;
  document.getElementById("volet-chapitre").hidden = true;
  sommaire();
  const O = Object.values(await chargeOeuvres(true));
  const page = document.getElementById("page");
  const F = etat.filtreBiblio ??= { q: "", sorte: "essai" };
  const q = el("input", "fiches-recherche");
  q.type = "search";
  q.placeholder = "chercher (auteur, titre, revue, année, clé)…";
  q.value = F.q;
  const sortes = [["toutes", "toutes", () => true], ["essai", "citées par l'essai", (o) => o.chapitres.length],
    ["fiches", "sources des fiches écrites ici", (o) => o.extraits.length],
    ["a_verifier", "à vérifier", (o) => o.statut === "a_verifier"], ["importee", "importées", (o) => o.statut === "importee"],
    ["verifiees", "vérifiées", (o) => o.statut === "verifiee" || o.statut === "corrigee"],
    ["problemes", "introuvables, mal attribuées, doublons", (o) => ["introuvable", "mal_attribuee", "doublon"].includes(o.statut)],
    ["hors", "hors base", (o) => !o.centrale], ["sansdoi", "sans DOI", (o) => !o.doi]];
  const barre = el("div", "dem-filtres");
  const g = el("span", "groupe filtres");
  for (const [v, lib, fn] of sortes) {
    const b = el("button", F.sorte === v ? "actif" : null, `${lib} · ${O.filter(fn).length}`);
    b.onclick = () => { F.sorte = v; vueBiblioLivre(); };
    g.append(b);
  }
  barre.append(g);
  const liste = el("ul", "biblio-liste");
  const plat = (s) => (s ?? "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  const remplit = () => {
    const mots = plat(F.q).split(/\s+/).filter(Boolean);
    const fn = sortes.find((s) => s[0] === F.sorte)[2];
    const garde = O.filter(fn).filter((o) => mots.every((m) => plat(o.cle + " " + o.ref).includes(m)));
    liste.replaceChildren(el("p", "mut petit", `${garde.length} œuvre(s)`));
    etat.biblioSelection = garde.filter((o) => o.centrale && !["verifiee", "corrigee"].includes(o.statut)).map((o) => o.cle);
    majVerifSelection?.();
    for (const o of garde.slice(0, 400)) {
      const li = el("li", "source");
      li.dataset.source = o.cle;
      const ref = el("div", "biblio-ref");
      ref.innerHTML = mdLigne(o.ref || o.cle);
      const meta = el("div", "biblio-ou");
      meta.append(el("span", "appui-lieu", o.cle));
      meta.append(badgeStatut(o));
      if (o.doute) meta.append(el("span", "badge doute", "doute"));
      if (o.extraits.some((x) => !x.verifie)) meta.append(el("span", "badge doute", "non vérifiée"));
      if (o.chapitres.length) meta.append(el("span", "puce", "essai : ch. " + o.chapitres.map((c) => c.numero ?? c.slug).join(", ")));
      if (o.fiches.length) meta.append(el("span", "puce", `${o.fiches.length} fiche(s)`));
      meta.append(liensSource(o.doi, o.ref));
      const pg = el("a", "pan-lien", "page ↗");
      pg.href = `#biblio/${o.cle}`;
      pg.title = "la page de l'œuvre : documents, citations, vérifications, où elle est citée";
      meta.append(pg);
      if ((o.documents ?? []).length) meta.append(el("span", "puce", `📄 ${o.documents.length}`));
      if ((o.citations ?? []).length) meta.append(el("span", "puce", `❝ ${o.citations.length}`));
      li.append(ref, meta);
      li.onclick = (e) => {
        if (e.target.closest("a")) return;
        liste.querySelectorAll(".source").forEach((x) => x.classList.toggle("choisi", x === li));
        history.replaceState(null, "", `#biblio/${o.cle}`);
        apercuOeuvre(o.cle);
      };
      liste.append(li);
    }
    if (garde.length > 400) liste.append(el("p", "mut petit", `… et ${garde.length - 400} autres : préciser la recherche.`));
  };
  // la barre : vérifier la sélection (ce que montrent la recherche et le filtre, hors œuvres déjà vérifiées)
  const verSel = el("button", "b-versions", "🔎 vérifier la sélection…");
  let majVerifSelection = () => {
    const n = (etat.biblioSelection ?? []).length;
    verSel.textContent = `🔎 vérifier la sélection (${n})…`;
    verSel.disabled = !n;
  };
  verSel.title = "met en file d'attente une vérification par œuvre affichée (hors œuvres déjà vérifiées) — lancées à la main, ou enchaînées si l'option est activée";
  verSel.onclick = async () => {
    const cles = etat.biblioSelection ?? [];
    const lim = etat.modeles?.limites?.reference;
    if (!confirm(`Mettre ${cles.length} vérification(s) en attente ?\n\nChacune : jusqu'à ${lim?.recherches ?? "?"} recherches et ${lim?.pages ?? "?"} pages, ` +
      `de l'ordre de 0,10 à 0,30 $ avec Sonnet (davantage avec Opus). Rien ne part sans ▶, sauf si l'enchaînement est activé (Fiches › en création).`)) return;
    const r = await fetch("/api/oeuvres/verifications", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ cles }) });
    const x = await r.json();
    alert(`${x.en_attente.length} vérification(s) en attente : Fiches › en création.`);
    majCompteFiches();
  };
  const aBib = el("span", "actions-barre");
  aBib.append(el("span", "etiq", "la sélection"), verSel);
  q.oninput = () => { F.q = q.value; remplit(); };
  remplit();
  barreFiches("biblio", aBib);
  majVerifSelection();
  page.replaceChildren(el("span"), el("h1", null, "Bibliographie"),
    el("p", "mut", "Toutes les œuvres du livre : la base centrale (ancien dépôt), les bibliographies des chapitres " +
      "(avec les notes de l'essai qui les citent), les sources des fiches écrites ici. Un clic : l'œuvre, et tout ce qui la cite."),
    q, barre, liste);
  document.getElementById("fiche").replaceChildren(el("h4", null, "Bibliographie"),
    el("p", "mut petit", `${O.length} œuvres · ${O.filter((o) => o.centrale).length} dans la base (kb/sources) · ` +
      `${O.filter((o) => o.statut === "verifiee" || o.statut === "corrigee").length} vérifiées · ` +
      `${O.filter((o) => o.chapitres.length).length} citées par l'essai · ${O.filter((o) => o.extraits.length).length} dans les fiches écrites ici.`),
    el("p", "mut petit", "Partout dans l'atelier, un clic sur une citation ouvre son œuvre ici, à droite."));
  if (cle) {
    if (!O.some((o) => o.cle === cle)) { F.sorte = "toutes"; }
    setTimeout(() => {
      const li = liste.querySelector(`.source[data-source="${CSS.escape(cle)}"]`);
      li?.scrollIntoView({ block: "center" });
      li?.classList.add("choisi");
      apercuOeuvre(cle);
    }, 0);
  } else zone().scrollTo(0, 0);
  setTimeout(() => q.focus(), 0);
}

// Revenir, dans l'aperçu, à une fiche précédente (sans l'empiler de nouveau).
async function rouvreApercu(slug) {
  const pile = etat.apercuPile;
  const d = document.getElementById("fiche");
  d.querySelector(":scope > .apercu-fiche")?.remove();
  const garde = etat.apercuRetour;
  if (slug.startsWith("œ:")) await apercuOeuvre(slug.slice(2));
  else await apercuFiche(slug);
  etat.apercuRetour = garde;
  etat.apercuPile = pile;
}

// Une fiche créée d'office : la confirmer (brouillon, reliée aux chapitres cochés) ou ne pas la garder.
function blocConfirmation(d, R) {
  const faire = el("div", "que-faire");
  const slug = d.decision.fiche;
  const lien = el("a", "pan-lien", `kb/fiches/${slug}.md → l'ouvrir`);
  lien.href = `#fiches/${slug}`;
  faire.append(el("h5", null, "Créée d'office — à confirmer"), el("p", "mut petit",
    "La file l'a écrite dans la base dès la réponse de Claude : elle est visible, citable, et signalée aux autres " +
    "demandes comme non relue. Confirmer la passe en brouillon et l'ajoute aux fiches des chapitres cochés ; " +
    "ne pas la garder la met à la corbeille (kb/corbeille/)."), lien);
  const chs = el("div", "choix-assertions");
  const proposes = new Set([...(d.cible.chapitres ?? []), ...(R.chapitres ?? []).map((c) => c.slug)]);
  const cases = etat.chapitres.filter((c) => c.atelier).map((c) => {
    const l = el("label", "dem-consulter");
    const x = el("input");
    x.type = "checkbox"; x.value = c.slug; x.checked = proposes.has(c.slug);
    l.append(x, ` ${c.numero ?? ""} · ${c.title}`);
    chs.append(l);
    return x;
  });
  const envoie = async (corps) => {
    const r = await fetch(`/api/chapitres/_kb/demandes/${d.id}/decision`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps) });
    if (!r.ok) { alert("échec : " + ((await r.json().catch(() => ({}))).detail ?? r.status)); return; }
    await indexFiches(true);
    tiroir(d.id);
  };
  const oui = el("button", "bouton", "✓ confirmer la fiche");
  oui.onclick = () => envoie({ action: "confirmer", chapitres: cases.filter((x) => x.checked).map((x) => x.value) });
  const non = el("button", "pan-lien danger", "✗ ne pas la garder…");
  non.onclick = async () => {
    const C = await api(`/fiches/${slug}/consequences`).catch(() => ({ citee_par: [] }));
    const n = C.citee_par.reduce((s, x) => s + x.liens, 0);
    if (!confirm(`Mettre « ${slug} » à la corbeille ?` + (n ? ` ${n} lien(s) la citent déjà (${C.citee_par.map((x) => x.fiche).join(", ")}) : ils seront défaits, le texte gardé.` : ""))) return;
    envoie({ action: "rejeter", liens: "retirer" });
  };
  const act = el("div", "annot-actions");
  act.append(oui, non);
  faire.append(el("span", "appui-lieu", "ajouter aux fiches des chapitres"), chs, act);
  return faire;
}

// Supprimer une fiche : ce qui en dépend d'abord, puis le choix pour les liens qui la visent.
async function formSuppression(f) {
  const C = await api(`/fiches/${f.slug}/consequences`);
  const b = el("div", "form-demande form-suppression");
  const n = C.citee_par.reduce((s, x) => s + x.liens, 0);
  b.append(el("span", "appui-lieu", `supprimer « ${f.slug} » — elle va à kb/corbeille/ (récupérable)`));
  const ul = el("ul", "petit");
  const li = (texte, ...noeuds) => { const x = el("li", null, texte); x.append(...noeuds); ul.append(x); };
  if (C.citee_par.length) li(`${n} lien(s) depuis ${C.citee_par.length} fiche(s) : `, ...C.citee_par.flatMap((x, i) => [i ? " " : "", puceFiche(x.fiche)]));
  else li("aucune fiche ne la cite");
  li(C.chapitres.length ? `listée par ${C.chapitres.map((c) => c.title).join(", ")} : elle en sera retirée` : "aucun chapitre ne la liste");
  li(C.oeuvres.length ? `${C.oeuvres.length} œuvre(s) des bibliographies de chapitre y sont rattachées : le rattachement sera retiré` : "aucune œuvre rattachée");
  b.append(ul);
  const choix = el("div", "choix-assertions");
  const radio = (v, lib, coche) => {
    const l = el("label", "dem-consulter");
    const r = el("input");
    r.type = "radio"; r.name = "liens-" + f.slug; r.value = v; r.checked = coche;
    l.append(r, " " + lib);
    choix.append(l);
    return r;
  };
  const r1 = radio("laisser", "laisser les liens (ils deviennent des liens morts, en rouge, qui proposent de recréer la fiche)", true);
  radio("retirer", "défaire les liens (le texte du lien est gardé)", false);
  if (n) b.append(el("span", "appui-lieu", "les liens qui la visent"), choix);
  const motif = el("input", "dem-motif");
  motif.placeholder = "motif (va au journal)";
  const ok = el("button", "bouton danger", "supprimer la fiche");
  const non = el("button", "pan-lien", "annuler");
  non.onclick = () => b.remove();
  ok.onclick = async () => {
    ok.disabled = true;
    const r = await fetch(`/api/fiches/${f.slug}/supprimer`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ liens: r1.checked ? "laisser" : "retirer", motif: motif.value }) });
    if (!r.ok) { ok.disabled = false; alert((await r.json().catch(() => ({}))).detail ?? r.status); return; }
    await indexFiches(true);
    location.hash = "fiches";
  };
  const act = el("div", "annot-actions");
  act.append(ok, non);
  b.append(motif, act);
  return b;
}

// ------------------------------------------------------------------ le harnais

const ICONE_PORTE = (p) => (p.ok ? "✓" : p.niveau === "bloquant" ? "✗" : "⚠");

async function tiroirHarnais(version) {
  clearTimeout(suivi);
  etat.tiroirMontre = null;
  clearTimeout(suivi);
  retiensTiroir(null);
  const t = document.getElementById("tiroir");
  t.hidden = false;
  document.body.dataset.tiroir = "1";
  t.replaceChildren(teteTiroir(`Harnais — ${version === "essai" ? "essai" : "récit"}`), el("p", "mut", "calcul des portes…"));
  const R = await api(`/chapitres/${etat.slug}/harnais/${version}`);
  const c = etat.chapitres.find((x) => x.slug === etat.slug);
  t.replaceChildren(teteTiroir(`Harnais — ${version === "essai" ? "essai" : "récit"} · ${c?.title ?? etat.slug}`));
  const av = R.a_revalider ?? {};
  t.append(el("p", "mut petit", `Depuis la dernière validation : ${av.modifie ?? 0} modifié(s), ${av.nouveau ?? 0} nouveau(x), ` +
    `${av.cadre ?? 0} au cadre changé, ${av.valide ?? 0} validé(s). Le harnais compte et désigne ; il ne corrige rien.`));
  const recalc = el("button", "pan-lien", "↻ recalculer");
  recalc.onclick = () => tiroirHarnais(version);
  t.append(recalc);
  for (const p of R.portes) {
    const d = el("details", "porte porte-" + (p.ok ? "ok" : p.niveau === "bloquant" ? "ko" : "avert"));
    const s = el("summary");
    s.append(el("span", "porte-icone", ICONE_PORTE(p)), el("strong", null, p.titre),
      el("span", "porte-n", p.n ? String(p.n) : ""), el("span", "mut petit", p.resume ? " — " + p.resume : ""));
    d.append(s);
    if (p.id === "naif") d.append(blocNaif(version, p));
    for (const r of p.releves) {
      const l = el("div", "releve");
      if (r.bloc && !String(r.bloc).startsWith("note:")) {
        const a = el("button", "pan-lien", "^" + r.bloc);
        a.title = "aller au paragraphe";
        a.onclick = () => { document.getElementById("tiroir").hidden = true; delete document.body.dataset.tiroir; vaVers(version, r.bloc); };
        l.append(a, " ");
      } else if (r.bloc) l.append(el("span", "appui-lieu", r.bloc + " "));
      if (r.regle) {
        const g = /^R\d/.test(r.regle) ? el("a", "badge", r.regle) : el("span", "badge", r.regle);
        if (g.tagName === "A") g.href = `#livre/regles/${version}/${r.regle}`;
        l.append(g, " ");
      }
      l.append(el("span", "releve-lib", r.libelle ?? ""));
      const x = el("div", "releve-extrait");
      if (r.trouve && r.extrait?.includes(r.trouve)) {
        const [a, ...b] = r.extrait.split(r.trouve);
        x.append(a, el("mark", null, r.trouve), b.join(r.trouve));
      } else x.append(r.extrait ?? "");
      l.append(x);
      d.append(l);
    }
    if (!p.ok || p.id === "naif") d.open = p.niveau === "bloquant" && p.n > 0 && p.n <= 12;
    t.append(d);
  }
  // valider
  const faire = el("div", "que-faire");
  faire.append(el("h5", null, "Valider"), el("p", "mut petit", R.ok
    ? "Toutes les portes bloquantes passent. Valider prend l'état présent comme référence : les marques « à revalider » disparaissent."
    : `Portes à passer : ${R.bloquantes.join(", ")}. On peut valider quand même, en disant pourquoi (le motif va au journal).`));
  const motif = el("textarea", "annot-texte petit-texte");
  motif.placeholder = R.ok ? "motif (facultatif)" : "pourquoi valider malgré les écarts (obligatoire)";
  const ok = el("button", "bouton", R.ok ? `✓ valider le ${version === "essai" ? "l'essai" : "récit"}` : "valider malgré les écarts");
  ok.onclick = async () => {
    if (!R.ok && !motif.value.trim()) { motif.focus(); return; }
    const r = await fetch(`/api/chapitres/${etat.slug}/harnais/${version}/valider`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ motif: motif.value }) });
    if (!r.ok) { alert((await r.json().catch(() => ({}))).detail ?? r.status); return; }
    etat.validation = await api(`/chapitres/${etat.slug}/validation`).catch(() => etat.validation);
    marquesValidation();
    barreOutils();
    tiroirHarnais(version);
  };
  const act = el("div", "annot-actions");
  act.append(ok);
  faire.append(motif, act);
  t.append(faire);
}

// La porte « naïf » : la dernière lecture, ou en lancer une.
function blocNaif(version, p) {
  const b = el("div", "releve");
  const ds = (etat.demandes ?? []).filter((x) => x.type === "naive" && (x.version ?? "recit") === version).sort((a, c) => (a.cree < c.cree ? 1 : -1));
  const derniere = ds[0];
  if (derniere) {
    const a = el("button", "pan-lien", `dernière lecture : ${derniere.cree.slice(0, 16).replace("T", " ")} · ${etiquetteDemande(derniere)} →`);
    a.onclick = () => tiroir(derniere.id);
    b.append(a, el("br"));
  }
  if (!p.ok || !derniere) {
    const mod = choixModele("naive");
    const go = el("button", "bouton", "👁 lancer une lecture naïve");
    go.title = "Claude lit le chapitre sans rien savoir du livre, et relève chaque endroit où il doit deviner";
    go.onclick = async () => {
      go.disabled = true;
      const r = await fetch(`/api/chapitres/${etat.slug}/harnais/${version}/naif`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ modele: mod.valeur() }) });
      if (!r.ok) { go.disabled = false; alert((await r.json().catch(() => ({}))).detail ?? r.status); return; }
      await chargeDemandes();
      tiroir((await r.json()).id);
    };
    b.append(el("p", "mut petit", "Claude lit le texte du chapitre, et rien d'autre (ni cadre, ni storyboard, ni le reste du livre). " +
      "Il relève chaque endroit où il doit deviner. Une lecture : quelques dizaines de centimes."), mod.noeud, go);
  }
  return b;
}

const TYPE_NAIF = { referent: "référent flottant", ellipse: "ellipse non résolue", formule: "formule cassée",
  chiffre: "chiffre ambigu", contradiction: "contradiction ou redite", relire: "à relire deux fois" };

async function tiroirNaif(t, d) {
  const version = d.cible.version;
  t.replaceChildren(teteTiroir(`Lecture naïve — ${version === "essai" ? "essai" : "récit"}`, () => tiroirHarnais(version)));
  if (d.etat === "en_cours") {
    t.append(enDirect(d));
    suivi = setTimeout(() => rafraichitDirect(d.id), 2000);
    return piedTiroir(t, d);
  }
  if (d.etat === "erreur") { t.append(el("p", "annot-orph-titre", "Échec : " + d.erreur)); return piedTiroir(t, d); }
  const R = d.resultat ?? { releves: [] };
  if (R.impression) t.append(el("p", "annot-corps", "« " + R.impression + " »"));
  const faits = Object.fromEntries((d.decision?.faits ?? []).map((x) => [x.i, x.action]));
  t.append(el("p", "mut petit", `${R.releves.length} relevé(s). Pour chacun : appliquer la reformulation (le paragraphe est corrigé, ` +
    "au journal), en faire une annotation, ou l'ignorer. Clore enregistre la lecture sur le texte corrigé : la porte « naïf » passe, " +
    "et se rouvrira dès qu'un mot change."));
  const choix = [];
  R.releves.forEach((r, i) => {
    const b = el("div", "piste releve-naif");
    const tete = el("div", "annot-tete");
    const a = el("button", "pan-lien", "^" + r.bloc);
    a.onclick = () => { t.hidden = true; delete document.body.dataset.tiroir; vaVers(version, r.bloc); };
    tete.append(el("span", "badge", TYPE_NAIF[r.type] ?? r.type), a);
    b.append(tete, el("blockquote", "verif-extrait", r.citation), el("p", "petit", "a dû deviner : " + r.devine));
    if (d.etat === "prete") {
      const q = el("textarea", "annot-texte petit-texte");
      q.value = r.reformulation;
      const g = el("span", "groupe filtres choix-naif");
      let action = r.type === "relire" || r.type === "contradiction" ? "annoter" : "appliquer";
      const boutons = [["appliquer", "appliquer"], ["annoter", "annoter"], ["ignorer", "ignorer"]].map(([k, lib]) => {
        const x = el("button", k === action ? "actif" : null, lib);
        x.onclick = () => { action = k; boutons.forEach((y) => y.classList.toggle("actif", y === x)); };
        g.append(x);
        return x;
      });
      b.append(el("span", "appui-lieu", "reformulation (remplace la citation)"), q, g);
      choix.push({ i, q, get action() { return action; } });
    } else {
      b.append(el("p", "annot-corps", "→ " + r.reformulation));
      if (faits[i]) b.append(el("p", faits[i] === "ignorer" ? "mut petit" : "verif-ok petit", faits[i] === "appliquer" ? "appliquée" : faits[i] === "annoter" ? "annotation créée" : "ignorée"));
    }
    t.append(b);
  });
  if (d.etat === "prete") {
    const faire = el("div", "que-faire");
    const clore = el("button", "bouton", "clore la lecture");
    clore.onclick = async () => {
      clore.disabled = true;
      const r = await fetch(`/api/chapitres/${etat.slug}/demandes/${d.id}/decision`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ actions: choix.map((c) => ({ i: c.i, action: c.action, reformulation: c.q.value })) }) });
      if (!r.ok) { clore.disabled = false; alert((await r.json().catch(() => ({}))).detail ?? r.status); return; }
      etat.docs = {};
      etat.garde = null;
      await rechargeAnnotations();
      await ouvre(etat.slug);
      tiroirHarnais(version);
    };
    faire.append(el("h5", null, "Clore"), clore);
    t.append(faire);
  } else if (d.decision) {
    const h = el("button", "bouton", "→ le harnais");
    h.onclick = () => tiroirHarnais(version);
    t.append(h);
  }
  piedTiroir(t, d);
}

// ------------------------------------------------------------------ la file d'attente

// Une demande en attente : la lancer maintenant, ou la retirer.
function blocAttente(d) {
  const b = el("div", "que-faire");
  if (d.etat === "retiree") {
    b.append(el("p", "mut", `Retirée de la file le ${(d.retiree ?? "").slice(0, 16).replace("T", " ")}. Elle n'a pas été lancée.`));
    return b;
  }
  const lim = etat.modeles?.limites?.fiche;
  b.append(el("h5", null, "En attente"), el("p", "mut petit",
    "Pas encore lancée. Son contexte (les fiches existantes, le carnet) sera compilé au lancement : elle verra les fiches " +
    "créées d'ici là. " + (lim ? `Budget : ${lim.tours} tours, ${lim.recherches} recherches, ${lim.pages} pages.` : "")));
  const act = el("div", "annot-actions");
  act.append(boutonLancer(d.id, () => tiroir(d.id)), boutonRetirer(d.id, () => tiroir(d.id)));
  b.append(act);
  api("/file").then((F) => {
    const rang = F.en_attente.findIndex((x) => x.id === d.id) + 1;
    b.append(el("p", "mut petit", `Position dans la file : ${rang} sur ${F.en_attente.length}. ` +
      (F.reglage.auto ? `Enchaînement automatique activé (${F.reglage.simultanees} à la fois) : elle partira d'elle-même.`
        : "Enchaînement automatique désactivé : elle attend que tu la lances (réglage dans Fiches › En création).")));
  }).catch(() => {});
  return b;
}

function boutonLancer(id, apres) {
  const b = el("button", "bouton", "▶ lancer");
  b.title = "lancer cette demande maintenant";
  b.onclick = async (e) => {
    e.stopPropagation();
    b.disabled = true;
    const r = await fetch(`/api/file/${id}/lance`, { method: "POST" });
    if (!r.ok) { b.disabled = false; alert((await r.json().catch(() => ({}))).detail ?? r.status); return; }
    apres?.();
  };
  return b;
}

function boutonRetirer(id, apres) {
  const b = el("button", "pan-lien danger", "retirer");
  b.title = "retirer de la file (elle ne sera pas lancée)";
  b.onclick = async (e) => {
    e.stopPropagation();
    if (!confirm("Retirer cette demande de la file ?")) return;
    const r = await fetch(`/api/file/${id}/retire`, { method: "POST" });
    if (!r.ok) { alert((await r.json().catch(() => ({}))).detail ?? r.status); return; }
    apres?.();
  };
  return b;
}

// Le réglage de la file : l'enchaînement automatique, à activer explicitement.
function reglageFile(F, apres) {
  const l = el("label", "graphe-coche file-auto");
  const c = el("input");
  c.type = "checkbox";
  c.checked = F.reglage.auto;
  c.onchange = async () => {
    if (c.checked && !confirm(`Activer l'enchaînement : les ${F.en_attente.length} demande(s) en attente partiront l'une après ` +
      "l'autre, sans autre clic (chacune avec son budget). Continuer ?")) { c.checked = false; return; }
    await fetch("/api/file", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ auto: c.checked }) });
    apres?.();
  };
  l.append(c, ` enchaîner automatiquement, ${F.reglage.simultanees} à la fois`);
  l.title = "désactivé : chaque demande en attente se lance à la main (▶)";
  const l2 = el("label", "graphe-coche file-auto");
  const c2 = el("input");
  c2.type = "checkbox";
  c2.checked = F.reglage.creer_d_office;
  c2.onchange = async () => {
    if (c2.checked && !confirm("Créer d'office : chaque fiche lancée depuis la file sera écrite dans la base dès que Claude " +
      "aura fini, à l'état « à confirmer » (visible, citable, signalée aux autres demandes comme non relue). " +
      "Tu la confirmes ensuite, ou elle part à la corbeille. Continuer ?")) { c2.checked = false; return; }
    await fetch("/api/file", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ creer_d_office: c2.checked }) });
    apres?.();
  };
  l2.append(c2, " créer d'office (à confirmer)");
  l2.title = "désactivé : une fiche rendue attend ta décision avant d'être écrite";
  const g = el("span", "reglage-file");
  g.append(l, l2);
  return g;
}

// ------------------------------------------------------------------ creuser une fiche

function formPistes(slug) {
  const f = el("div", "form-demande");
  const consigne = el("textarea", "annot-texte petit-texte");
  consigne.placeholder = "Précision (facultatif) : plutôt les mécanismes, ce qui manque au chapitre 3…";
  const mod = choixModele("pistes");
  const go = el("button", "bouton", "◇ chercher des pistes");
  const non = el("button", "pan-lien", "annuler");
  non.onclick = () => f.remove();
  go.onclick = async () => {
    go.disabled = true;
    const r = await fetch(`/api/fiches/${slug}/pistes`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ consigne: consigne.value, modele: mod.valeur() }) });
    if (!r.ok) { go.disabled = false; alert("échec : " + ((await r.json().catch(() => ({}))).detail ?? r.status)); return; }
    const d = await r.json();
    tiroir(d.id);
  };
  const act = el("div", "annot-actions");
  act.append(go, non);
  f.append(el("span", "appui-lieu", "creuser — Claude lit la fiche, cherche ce qu'elle effleure, et vérifie dans la base que chaque piste n'est pas déjà couverte"),
    consigne, mod.noeud, el("p", "mut petit", "Une lecture de la base, sans recherche web : quelques minutes, quelques dizaines de centimes. " +
      "Rien n'est créé sans toi."), act);
  setTimeout(() => consigne.focus(), 0);
  return f;
}

const STATUT_PISTE = { nouvelle: "nouvelle", a_completer: "à compléter", couverte: "déjà couverte" };

async function tiroirPistes(t, d) {
  t.replaceChildren(teteTiroir("Creuser une fiche", () => historiqueFiches(t)));
  const cible = el("div", "dem-cible");
  const c = el("p", "annot-corps");
  c.append("Fiche lue : ", puceFiche(d.cible.fiche));
  cible.append(c);
  if (d.consigne) cible.append(el("p", "annot-corps", "« " + d.consigne + " »"));
  t.append(cible);
  if (d.etat === "en_cours") {
    t.append(enDirect(d));
    suivi = setTimeout(() => rafraichitDirect(d.id), 2000);
    return piedTiroir(t, d);
  }
  if (d.etat === "erreur") { t.append(el("p", "annot-orph-titre", "Échec : " + d.erreur)); return piedTiroir(t, d); }
  const R = d.resultat ?? { pistes: [] };
  if (R.note) t.append(el("p", "annot-corps", R.note));
  const lancees = Object.fromEntries((d.decision?.lancees ?? []).map((x) => [x.i, x.demande]));
  if (d.decision && !d.decision.lancees) t.append(el("div", "dem-decision", "Aucune piste retenue" + (d.decision.motif ? " — " + d.decision.motif : "")));
  const choix = [];
  for (const statut of ["nouvelle", "a_completer", "couverte"]) {
    const P = R.pistes.map((p, i) => ({ p, i })).filter(({ p }) => p.statut === statut);
    if (!P.length) continue;
    t.append(el("h5", null, `${statut === "nouvelle" ? "Pistes nouvelles" : statut === "a_completer" ? "À compléter dans une fiche existante" : "Déjà couvertes"} · ${P.length}`));
    for (const { p, i } of P) {
      const b = el("div", "piste piste-" + statut);
      const tete = el("div", "annot-tete");
      tete.append(el("span", "badge prio-" + p.priorite, p.priorite), el("span", "appui-lieu", p.slug));
      if (p.appel) {
        const a = el("a", "pan-lien", "§ " + p.appel);
        a.href = `#fiches/${d.cible.fiche}/${p.appel}`;
        a.title = "la section de la fiche qui appelle cette piste";
        tete.append(a);
      }
      b.append(tete);
      if (statut === "nouvelle" && d.etat === "prete") {
        const l = el("label", "dem-consulter");
        const x = el("input");
        x.type = "checkbox";
        x.checked = p.priorite !== "basse";
        const q = el("textarea", "annot-texte petit-texte");
        q.value = p.question;
        l.append(x, " créer une fiche sur :");
        b.append(l, q);
        choix.push({ i, x, q, p });
      } else b.append(el("p", "annot-corps", p.question));
      b.append(el("p", "mut petit", p.pourquoi));
      if (p.fiche_existante) {
        const e = el("p", "petit");
        e.append(statut === "couverte" ? "Traitée par " : "À compléter dans ", puceFiche(p.fiche_existante, p.section_existante ?? null),
          p.section_existante ? ` § ${p.section_existante}` : "");
        b.append(e);
      }
      if (p.chapitres?.length) b.append(el("p", "mut petit", "chapitres : " + p.chapitres.join(", ")));
      if (lancees[i]) {
        const a = el("button", "pan-lien", "◇ fiche demandée (en attente, puis lancée) → ouvrir");
        a.onclick = () => tiroir(lancees[i]);
        b.append(a);
      }
      t.append(b);
    }
  }
  if (!R.pistes.length) t.append(el("p", "mut", "Aucune piste proposée."));
  if (d.etat === "prete") {
    const faire = el("div", "que-faire");
    const lim = etat.modeles?.limites?.fiche;
    faire.append(el("h5", null, "Que faire ?"), el("p", "mut petit",
      "Cocher les pistes à creuser, en retoucher la question au besoin. Chacune devient une création de fiche " +
      "en attente : rien ne part tout seul. Tu les lances une à une (▶, dans Fiches › En création ou dans leur " +
      "tiroir), ou tu actives l'enchaînement automatique. Chacune " +
      (lim ? `(budget : ${lim.tours} tours, ${lim.recherches} recherches, ${lim.pages} pages) ` : "") +
      "revérifie, au lancement, qu'aucune fiche ne couvre déjà le sujet. Les pistes « à compléter » attendent " +
      "la complétion d'une fiche (à venir)."));
    const oui = el("button", "bouton", "◇ mettre en attente");
    const maj = () => { const n = choix.filter((c) => c.x.checked).length; oui.textContent = `◇ mettre ${n} fiche(s) en attente`; oui.disabled = !n; };
    choix.forEach((c) => c.x.addEventListener("change", maj));
    maj();
    const motif = el("input", "dem-motif");
    motif.placeholder = "motif (pour n'en retenir aucune)";
    const non = el("button", "pan-lien", "n'en retenir aucune");
    const envoie = async (corps) => {
      const r = await fetch(`/api/chapitres/_kb/demandes/${d.id}/decision`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps) });
      if (!r.ok) { alert("échec : " + ((await r.json().catch(() => ({}))).detail ?? r.status)); return; }
      tiroir(d.id);
    };
    const enchaine = el("label", "graphe-coche");
    const ce = el("input");
    ce.type = "checkbox";
    enchaine.append(ce, " et les lancer à la suite, automatiquement, une à la fois");
    enchaine.title = "active l'enchaînement de la file d'attente (réglage du livre, désactivable ensuite)";
    oui.onclick = async () => {
      const n = choix.filter((c) => c.x.checked).length;
      if (ce.checked && !confirm(`Les ${n} fiche(s) partiront l'une après l'autre, sans autre clic, chacune avec son budget. ` +
        "L'enchaînement restera activé pour la file (désactivable dans Fiches › En création). Continuer ?")) return;
      oui.disabled = true;
      if (ce.checked) await fetch("/api/file", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ auto: true }) });
      envoie({ action: "creer", pistes: choix.filter((c) => c.x.checked).map((c) => ({ i: c.i, question: c.q.value })) });
    };
    non.onclick = () => envoie({ action: "rejeter", motif: motif.value });
    const act = el("div", "annot-actions");
    act.append(oui, non);
    faire.append(enchaine, act, motif);
    t.append(faire);
  }
  // après la décision : la file de ces fiches, lançable d'ici
  if (d.decision?.lancees?.length) {
    const bloc = el("div", "que-faire");
    bloc.append(el("h5", null, "File d'attente"));
    t.append(bloc);
    const remplit = () => Promise.all([api("/file"), api("/fiches/demandes")]).then(([F, ds]) => {
      bloc.replaceChildren(el("h5", null, "File d'attente"), reglageFile(F, remplit));
      for (const x of d.decision.lancees) {
        const dm = ds.find((y) => y.id === x.demande);
        const l = el("div", "dem-ligne ouverte file-ligne");
        l.append(el("span", "dem-etat " + (dm?.etat ?? ""), dm ? etiquetteDemande(dm) : "?"), " ",
          el("span", "dem-titre-ligne", dm?.question ?? x.demande));
        if (dm?.etat === "en_attente") {
          const a = el("span", "file-actions");
          a.append(boutonLancer(x.demande, remplit), boutonRetirer(x.demande, remplit));
          l.append(a);
        }
        l.onclick = (e) => { if (!e.target.closest("button")) tiroir(x.demande); };
        bloc.append(l);
      }
    }).catch(() => {});
    remplit();
  }
  piedTiroir(t, d);
}

// ------------------------------------------------------------------ les renvois

// Proposer les renvois vers une fiche dans les voisines qu'elle cite (qui ne la citent pas encore).
function boutonRenvois(slug, voisines = null) {
  const b = el("button", "bouton", voisines ? `⇄ renvois (${voisines.length} voisine${voisines.length > 1 ? "s" : ""})…` : "⇄ proposer les renvois dans les voisines…");
  b.title = "Claude propose, dans chaque fiche qu'elle cite, une phrase qui renvoie vers elle, à l'endroit juste — rien n'est écrit sans toi" +
    (voisines ? " : " + voisines.join(", ") : "");
  b.onclick = async (e) => {
    e.stopPropagation();
    b.disabled = true;
    const r = await fetch(`/api/fiches/${slug}/renvois`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    if (!r.ok) { b.disabled = false; alert((await r.json().catch(() => ({}))).detail ?? r.status); return; }
    tiroir((await r.json()).id);
  };
  return b;
}

async function tiroirRenvois(t, d) {
  t.replaceChildren(teteTiroir("Renvois", () => historiqueFiches(t)));
  const cible = el("div", "dem-cible");
  const c = el("p", "annot-corps");
  c.append("Vers ", puceFiche(d.cible.fiche), `, depuis ${d.cible.voisines.length} voisine(s) : `, ...d.cible.voisines.flatMap((v, i) => [i ? " " : "", puceFiche(v)]));
  cible.append(c);
  t.append(cible);
  if (d.etat === "en_cours") {
    t.append(enDirect(d));
    suivi = setTimeout(() => rafraichitDirect(d.id), 2000);
    return piedTiroir(t, d);
  }
  if (d.etat === "erreur") { t.append(el("p", "annot-orph-titre", "Échec : " + d.erreur)); return piedTiroir(t, d); }
  const R = d.resultat ?? { renvois: [] };
  const faits = Object.fromEntries((d.decision?.faits ?? []).map((x) => [x.i, x]));
  const choix = [];
  R.renvois.forEach((r, i) => {
    const b = el("div", "piste piste-nouvelle");
    const tete = el("div", "annot-tete");
    const lien = el("a", "pan-lien", `${r.fiche} § ${r.section}`);
    lien.href = `#fiches/${r.fiche}/${r.section}`;
    tete.append(puceFiche(r.fiche, r.section), el("span", "appui-lieu", `§ ${r.section} · ${r.mode === "phrase" ? "phrase en fin de paragraphe" : "paragraphe après"}`));
    if (!r.section_trouvee) tete.append(el("span", "badge doute", "section introuvable : fin de fiche"));
    else if (!r.paragraphe_trouve) tete.append(el("span", "badge doute", "paragraphe introuvable : fin de section"));
    b.append(tete);
    if (r.paragraphe) b.append(el("blockquote", "verif-extrait", r.paragraphe));
    if (d.etat === "prete") {
      const l = el("label", "dem-consulter");
      const x = el("input");
      x.type = "checkbox"; x.checked = true;
      const q = el("textarea", "annot-texte petit-texte");
      q.value = r.texte;
      l.append(x, " insérer :");
      b.append(l, q);
      choix.push({ i, x, q });
    } else {
      const p = el("p", "annot-corps");
      p.innerHTML = mdLigne(r.texte);
      b.append(p);
    }
    b.append(el("p", "mut petit", r.raison));
    if (faits[i]) b.append(el("p", "verif-ok petit", `inséré — ${faits[i].ou}`), lien);
    t.append(b);
  });
  if ((R.ignorees ?? []).length) {
    t.append(el("h5", null, "Voisines laissées"));
    for (const x of R.ignorees) { const p = el("p", "petit"); p.append(puceFiche(x.fiche), " " + x.raison); t.append(p); }
  }
  if (d.etat === "prete" && choix.length) {
    const faire = el("div", "que-faire");
    faire.append(el("h5", null, "Que faire ?"), el("p", "mut petit",
      "Relire chaque renvoi, le retoucher au besoin. « Insérer » l'écrit dans la fiche voisine, à l'endroit montré " +
      "(le paragraphe cité en gris) ; le reste de la fiche est intact, et l'insertion va au journal de la base."));
    const oui = el("button", "bouton", "⇄ insérer les renvois cochés");
    const non = el("button", "pan-lien", "n'en insérer aucun");
    const envoie = async (corps) => {
      const r = await fetch(`/api/chapitres/_kb/demandes/${d.id}/decision`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps) });
      if (!r.ok) { alert("échec : " + ((await r.json().catch(() => ({}))).detail ?? r.status)); return; }
      await indexFiches(true);
      tiroir(d.id);
    };
    oui.onclick = () => { oui.disabled = true; envoie({ action: "inserer", renvois: choix.filter((c) => c.x.checked).map((c) => ({ i: c.i, texte: c.q.value })) }); };
    non.onclick = () => envoie({ action: "rejeter" });
    const act = el("div", "annot-actions");
    act.append(oui, non);
    faire.append(act);
    t.append(faire);
  }
  piedTiroir(t, d);
}

// ------------------------------------------------------------------ créer une fiche

// Le formulaire : une question, les chapitres qu'elle sert, une longueur, un modèle.
function formFiche(base = {}) {
  const f = el("div", "form-demande form-fiche");
  const q = el("textarea", "annot-texte");
  q.placeholder = "La question à laquelle la fiche répond (ex. : quand le premier océan s'est-il condensé, et qu'en sait-on ?)";
  q.value = base.question ?? "";
  const slug = el("input", "dem-motif");
  slug.placeholder = "slug souhaité (facultatif) : origine-des-oceans";
  slug.value = base.slug ?? "";
  const chs = el("div", "choix-assertions");
  const cases = etat.chapitres.filter((c) => c.atelier).map((c) => {
    const l = el("label", "dem-consulter");
    const x = el("input");
    x.type = "checkbox"; x.value = c.slug;
    x.checked = (base.chapitres ?? []).includes(c.slug);
    l.append(x, ` ${c.numero ?? ""} · ${c.title}`);
    chs.append(l);
    return x;
  });
  const longueur = el("select", "livre-select");
  for (const [v, lib] of [["courte", "courte (600–900 mots)"], ["moyenne", "moyenne (1 200–1 800 mots)"], ["longue", "longue (2 500–3 500 mots)"]]) {
    const o = el("option", null, lib); o.value = v; if (v === "moyenne") o.selected = true; longueur.append(o);
  }
  const consigne = el("textarea", "annot-texte petit-texte");
  consigne.placeholder = "Précision (facultatif) : ce qu'il faut couvrir, les sources à privilégier…";
  const mod = choixModele("fiche");
  const lim = etat.modeles?.limites?.fiche;
  const go = el("button", "bouton", "◇ lancer la recherche");
  const non = el("button", "pan-lien", "annuler");
  non.onclick = () => f.remove();
  go.onclick = async () => {
    go.disabled = true;
    const r = await fetch("/api/fiches/demandes", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q.value, slug: slug.value, chapitres: cases.filter((x) => x.checked).map((x) => x.value),
        longueur: longueur.value, consigne: consigne.value, modele: mod.valeur(), depuis: base.depuis,
        sources_initiales: base.sources_initiales }) });
    if (!r.ok) { go.disabled = false; alert("échec : " + ((await r.json().catch(() => ({}))).detail ?? r.status)); return; }
    const d = await r.json();
    f.remove();
    tiroir(d.id);
  };
  const act = el("div", "annot-actions");
  act.append(go, non);
  f.append(el("span", "appui-lieu", "nouvelle fiche — Claude lit d'abord les fiches voisines, puis cherche ; rien n'est écrit sans toi"),
    q, slug, el("span", "appui-lieu", "chapitres servis"), chs, el("span", "appui-lieu", "longueur"), longueur, consigne, mod.noeud,
    el("p", "mut petit", `Budget : ${lim ? `${lim.recherches} recherches, ${lim.pages} pages, ${lim.tours} tours` : "livre.yaml"} ` +
      "(réglable sur la page du livre). Si une fiche couvre déjà la question, Claude le dira."), act);
  if (base.sources_initiales?.length) f.insertBefore(el("p", "mut petit", `${base.sources_initiales.length} source(s) de la vérification ${base.depuis} lui seront données.`), act);
  setTimeout(() => q.focus(), 0);
  return f;
}

// La liste des demandes de fiche (tiroir ouvert depuis le wiki).
function historiqueFiches(t) {
  return historique(t, "fiches");
}

async function tiroirFiche(t, d) {
  t.replaceChildren(teteTiroir("Fiche nouvelle", () => historiqueFiches(t)));
  const cible = el("div", "dem-cible");
  cible.append(el("p", "annot-corps", d.cible.question));
  if (d.cible.chapitres?.length) cible.append(el("p", "mut petit", "chapitres : " + d.cible.chapitres.join(", ")));
  if (d.consigne) cible.append(el("p", "annot-corps", "« " + d.consigne + " »"));
  if (d.cible.depuis) cible.append(el("p", "mut petit", `depuis ${d.cible.depuis} · ${(d.cible.sources_initiales ?? []).length} source(s) données`));
  t.append(cible);
  if (d.etat === "en_attente" || d.etat === "retiree") return t.append(blocAttente(d));
  if (d.etat === "en_cours") {
    t.append(enDirect(d));
    suivi = setTimeout(() => rafraichitDirect(d.id), 2000);
    return piedTiroir(t, d);
  }
  if (d.etat === "erreur") { t.append(el("p", "annot-orph-titre", "Échec : " + d.erreur)); return piedTiroir(t, d); }
  const R = d.resultat ?? {};
  if (d.decision) {
    const dec = el("div", "dem-decision");
    if (d.decision.fiche) {
      const a = el("a", "pan-lien", `fiche créée : ${d.decision.fiche} →`);
      a.href = `#fiches/${d.decision.fiche}`;
      dec.append(a, document.createTextNode(d.decision.chapitres?.length ? ` · ajoutée à ${d.decision.chapitres.join(", ")}` : ""));
      dec.append(el("br"), boutonRenvois(d.decision.fiche));
    } else dec.append(el("strong", null, "Non créée"), document.createTextNode(d.decision.motif ? " — " + d.decision.motif : ""));
    t.append(dec);
  }
  if (R.doublon) {
    const b = el("div", "fiche-doublon");
    if (R.doublon.proposee) {
      const a = el("button", "pan-lien", `« ${R.doublon.fiche} », proposée par une autre recherche (pas encore créée) → l'ouvrir`);
      a.onclick = () => tiroir(R.doublon.proposee);
      b.append(el("strong", null, "Une fiche proposée couvre déjà la question : "), a, el("p", "petit", R.doublon.raison));
    } else b.append(el("strong", null, "Une fiche couvre déjà la question : "), puceFiche(R.doublon.fiche),
      el("p", "petit", R.doublon.raison));
    if (R.doublon.a_ajouter) b.append(el("p", "petit", "À y ajouter : " + R.doublon.a_ajouter));
    t.append(b);
  }
  // l'aperçu, rendu comme dans le wiki ; les paragraphes sans [@source] sont signalés
  if (R.sections?.length) {
    const prec = reponsesPrecedentes(d);
    if (prec) t.append(prec);
    t.append(el("h5", null, "La fiche proposée"));
    const ap = el("div", "fiche-apercu");
    ap.append(el("h3", "apercu-titre", R.titre), el("p", "mut petit", R.sujet), pastilles(R.confiance, true));
    const corps = el("div", "fiche-corps apercu");
    corps.innerHTML = d.apercu?.html ?? "";
    let sans = 0;
    const retenir = [...corps.querySelectorAll("h2")].find((h) => /en tirer|Voisines|Sources/.test(h.textContent));
    for (const p of corps.querySelectorAll("p")) {
      const apres = retenir && (retenir.compareDocumentPosition(p) & Node.DOCUMENT_POSITION_FOLLOWING);
      if (!p.querySelector("cite") && !apres && p.textContent.trim().length > 80 && !p.closest("li") && !/^Écrite pour/.test(p.textContent)) {
        p.classList.add("sans-source");
        p.title = "aucune source [@…] dans ce paragraphe";
        sans++;
      }
    }
    corps.querySelectorAll("a.wiki").forEach((a) => {
      const [, cible] = a.getAttribute("href").split("/");
      a.onclick = (e) => { e.preventDefault(); apercuFiche(cible); };
    });
    const nv = (R.sources ?? []).filter((s) => !s.verifie).length;
    ap.append(el("p", sans || nv ? "fiche-alerte petit" : "mut petit",
      `${(R.sources ?? []).length} source(s), dont ${nv} non vérifiée(s) · ${sans} paragraphe(s) sans source signalé(s) en marge`));
    const morts = d.apercu?.liens_morts ?? [], inconnues = d.apercu?.cles_inconnues ?? [];
    if (morts.length) ap.append(el("p", "fiche-alerte petit", "liens vers des fiches inexistantes : " + morts.map((x) => `[[${x}]]`).join(", ")));
    if (inconnues.length) ap.append(el("p", "fiche-alerte petit", "clés citées absentes des sources : " + inconnues.join(", ")));
    ap.append(corps);
    t.append(ap);
  }
  if (d.etat === "a_confirmer") t.append(blocConfirmation(d, R));
  if (d.etat === "prete" && R.sections?.length) {
    const faire = el("div", "que-faire");
    faire.append(el("h5", null, "Que faire ?"), el("p", "mut petit",
      "Relire la fiche. « Créer » l'écrit dans kb/fiches/ (origine claude, état brouillon) et l'ajoute aux fiches des " +
      "chapitres cochés. Les liens depuis les fiches voisines sont proposés ci-dessous, pas écrits."));
    const slug = el("input", "dem-motif");
    slug.value = R.slug;
    if (R.slug_propose_par) faire.append(el("p", "fiche-alerte petit",
      `Le slug « ${R.slug} » est aussi celui d'une fiche proposée par ${R.slug_propose_par} : en choisir un autre si les deux sont créées.`));
    const titre = el("input", "dem-motif");
    titre.value = R.titre;
    const chs = el("div", "choix-assertions");
    const proposes = new Set([...(d.cible.chapitres ?? []), ...(R.chapitres ?? []).map((c) => c.slug)]);
    const cases = etat.chapitres.filter((c) => c.atelier).map((c) => {
      const l = el("label", "dem-consulter");
      const x = el("input");
      x.type = "checkbox"; x.value = c.slug; x.checked = proposes.has(c.slug);
      const raison = (R.chapitres ?? []).find((y) => y.slug === c.slug)?.raison;
      l.append(x, ` ${c.numero ?? ""} · ${c.title}` + (raison ? ` — ${raison}` : ""));
      chs.append(l);
      return x;
    });
    const motif = el("input", "dem-motif");
    motif.placeholder = "motif (pour ne pas créer)";
    const oui = el("button", "bouton", "◇ Créer la fiche");
    const non = el("button", "pan-lien", "ne pas créer");
    const envoie = async (corps) => {
      const r = await fetch(`/api/chapitres/_kb/demandes/${d.id}/decision`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps) });
      if (!r.ok) { alert("échec : " + ((await r.json().catch(() => ({}))).detail ?? r.status)); return; }
      etat.fichesIndex = null;
      await indexFiches(true);
      if (etat.atelier) etat.atelier = await api(`/chapitres/${etat.slug}/atelier`).catch(() => etat.atelier);
      tiroir(d.id);
    };
    oui.onclick = () => envoie({ action: "creer", slug: slug.value, titre: titre.value, chapitres: cases.filter((x) => x.checked).map((x) => x.value) });
    non.onclick = () => envoie({ action: "rejeter", motif: motif.value });
    const act = el("div", "annot-actions");
    act.append(oui, non);
    faire.append(el("span", "appui-lieu", "slug"), slug, el("span", "appui-lieu", "titre"), titre,
      el("span", "appui-lieu", "ajouter aux fiches des chapitres"), chs, motif, act);
    t.append(faire);
  }
  if ((R.liens ?? []).length) {
    t.append(el("h5", null, "Liens proposés (depuis les fiches voisines — à écrire à la main)"));
    for (const l of R.liens) {
      const p = el("p", "petit");
      p.append(puceFiche(l.fiche), " " + l.raison);
      t.append(p);
    }
  }
  if ((R.sources ?? []).length) {
    const det = el("details", "replie");
    det.append(el("summary", null, `les sources (${R.sources.length})`));
    for (const s of R.sources) {
      const so = el("div", "verif-source");
      const ref = el("span", "verif-ref");
      ref.innerHTML = mdLigne(`${s.cle} — ${s.ref}`);
      so.append(ref);
      if (s.doi) { const l = el("a", "lien-ext", "doi ↗"); l.href = "https://doi.org/" + s.doi; l.target = "_blank"; so.append(" ", l); }
      if (s.url) { const l = el("a", "lien-ext", "page ↗"); l.href = s.url; l.target = "_blank"; so.append(" ", l); }
      so.append(el("span", s.verifie ? "verif-ok" : "verif-non", s.verifie ? " lu" : " non vérifié"));
      if (s.extrait) so.append(el("blockquote", "verif-extrait", s.extrait));
      det.append(so);
    }
    t.append(det);
  }
  piedTiroir(t, d);
}

// ------------------------------------------------------------------ les fiches (wiki)
//
// #fiches                    l'index : chercher, filtrer, ouvrir
// #fiches/<slug>             une fiche : confiance, texte, plan à gauche, liens à droite
// #fiches/<slug>/<section>   la même, à une section
// Les [[liens]] entre fiches sont des liens ordinaires ; un lien hors fiches (le cadre
// poétique de l'ancien dépôt) est marqué et s'ouvre, en lecture seule, dans l'éditeur.

const DEGRES = [["établi", "etabli"], ["débattu", "debattu"], ["contest", "debattu"], ["récent", "recent"],
  ["très récent", "recent"], ["expériment", "hypo"], ["hypoth", "hypo"], ["spécul", "hypo"], ["projet", "projete"],
  ["modèle", "projete"], ["mesur", "etabli"], ["inconnu", "hypo"], ["ouvert", "debattu"]];

function classeDegre(d) {
  const x = (d ?? "").toLowerCase();
  return "degre-" + (DEGRES.find(([k]) => x.startsWith(k) || x.includes(k))?.[1] ?? "autre");
}

async function indexFiches(force = false) {
  if (!etat.fichesIndex || force) etat.fichesIndex = await api("/fiches").catch(() => []);
  return etat.fichesIndex;
}

async function vueFiches(slug, section) {
  document.body.dataset.vue = "fiches";
  delete document.body.dataset.panneau;
  document.getElementById("outils").hidden = true;
  sommaire();
  const I = await indexFiches();
  if (slug === "graphe") return pageGraphe();
  if (slug === "creation") return pageCreation();
  if (!slug) return indexPage(I);
  return pageFiche(slug, section, I);
}

function pastilles(conf, detail = false) {
  const d = el("div", "pastilles");
  for (const c of conf ?? []) {
    const p = el("span", "pastille " + classeDegre(c.degre), c.degre);
    if (c.sur) p.title = c.sur.replace(/\*\*/g, "");
    d.append(p);
  }
  if (!detail || !(conf ?? []).some((c) => c.sur)) return d;
  const det = el("details", "confiance");
  const s = el("summary");
  s.append(d, el("span", "mut petit", " ce qui est établi, débattu… (détail)"));
  det.append(s);
  const ul = el("ul");
  for (const c of conf) {
    if (!c.sur) continue;
    const li = el("li");
    li.append(el("span", "pastille " + classeDegre(c.degre), c.degre), " ");
    const t = el("span");
    t.innerHTML = mdLigne(c.sur);
    li.append(t);
    ul.append(li);
  }
  det.append(ul);
  return det;
}

function indexPage(I) {
  etat.ficheCourante = null;
  const page = document.getElementById("page");
  const volet = document.getElementById("volet-chapitre");
  volet.hidden = true;
  const F = etat.filtreFiches ??= { q: "", usage: "toutes" };
  const q = el("input", "fiches-recherche");
  q.type = "search";
  q.placeholder = "chercher une fiche (titre, sujet, slug)…";
  q.value = F.q;
  const groupe = el("span", "groupe filtres");
  for (const [v, lib] of [["toutes", "toutes"], ["chapitres", "utilisées par un chapitre de l'atelier"], ["orphelines", "sans lien entrant"],
    ["brouillons", `brouillons · ${I.filter((f) => f.etat === "brouillon").length}`],
    ["a_confirmer", `à confirmer · ${I.filter((f) => f.etat === "a_confirmer").length}`]]) {
    const b = el("button", F.usage === v ? "actif" : null, lib);
    b.onclick = () => { F.usage = v; indexPage(I); };
    groupe.append(b);
  }
  const liste = el("div", "fiches-liste");
  const remplit = () => {
    const mots = F.q.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").split(/\s+/).filter(Boolean);
    const plat = (s) => (s ?? "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
    const garde = I.filter((f) => mots.every((m) => plat(f.titre + " " + f.sujet + " " + f.slug).includes(m)))
      .filter((f) => F.usage === "toutes" || (F.usage === "chapitres" ? f.chapitres.length
        : F.usage === "brouillons" ? f.etat === "brouillon" : F.usage === "a_confirmer" ? f.etat === "a_confirmer" : !f.entrants.length))
      .sort((a, b) => a.titre.localeCompare(b.titre, "fr"));
    liste.replaceChildren(el("p", "mut petit", `${garde.length} fiche(s) sur ${I.length}`));
    for (const f of garde) {
      const c = el("a", "fiche-carte");
      c.href = `#fiches/${f.slug}`;
      const ti = el("span", "fiche-titre", f.titre);
      if (f.origine === "claude") ti.append(" ", el("span", "badge " + (["brouillon", "a_confirmer"].includes(f.etat) ? "doute" : ""),
        f.etat === "a_confirmer" ? "à confirmer · Claude" : f.etat === "brouillon" ? "brouillon · Claude" : `${f.etat ?? ""} · Claude`));
      c.append(ti);
      if (f.sujet && f.sujet !== f.titre) c.append(el("span", "fiche-sujet", f.sujet));
      c.append(pastilles(f.confiance));
      const meta = el("span", "fiche-meta",
        `${f.slug} · ${f.sections} sections · ${Math.round(f.mots / 100) / 10} k mots · citée par ${f.entrants.length} fiche(s)` +
        (f.chapitres.length ? ` · ch. ${f.chapitres.map((x) => x.numero ?? x.slug).join(", ")}` : ""));
      c.append(meta);
      liste.append(c);
    }
  };
  q.oninput = () => { F.q = q.value; remplit(); };
  remplit();
  const barre = el("div", "dem-filtres");
  barre.append(groupe);
  page.replaceChildren(ongletsFiches("liste"), el("h1", null, "Fiches"),
    el("p", "mut", "La base de connaissance du livre : ce qu'on sait, à quel point on y croit, qui le dit. " +
      "Une fiche sert plusieurs chapitres."), q, barre, liste);
  document.getElementById("fiche").replaceChildren(el("h4", null, "Fiches"),
    el("p", "mut petit", `${I.length} fiches dans kb/fiches/. Les liens entre elles, et vers les chapitres et les œuvres, ` +
      "sont calculés : une fiche ne recopie rien."),
    el("p", "mut petit", "Les pastilles disent la confiance : établi, débattu, récent, hypothétique, projeté — survol pour le détail."));
  zone().scrollTo(0, 0);
  setTimeout(() => q.focus(), 0);
}

// La barre de vue des fiches, comme celle du récit et de l'essai : la vue (liste, en création,
// graphe, bibliographie), puis les actions sur la base (nouvelle fiche, PDF, version imprimable).
function barreFiches(actif, actionsPage = null) {
  const o = document.getElementById("outils");
  o.replaceChildren();
  o.hidden = false;
  const g = el("span", "groupe");
  for (const [k, lib, h] of [["liste", "liste", "fiches"], ["creation", "en création", "fiches/creation"],
    ["graphe", "graphe", "fiches/graphe"], ["biblio", "bibliographie", "biblio"]]) {
    const b = el("button", k === actif ? "actif" : null, lib);
    b.onclick = () => { location.hash = h; };
    if (k === "creation") b.id = "onglet-creation";
    g.append(b);
  }
  o.append(el("span", "etiq", "fiches"), g, el("span", "espace"));
  if (actionsPage) o.append(actionsPage, el("span", "sep-barre"));
  const nouvelle = el("button", "b-versions", "◇ nouvelle…");
  nouvelle.title = "nouvelle fiche : une question ; Claude lit les fiches voisines, cherche, et propose une fiche";
  nouvelle.onclick = () => {
    const page = document.getElementById("page");
    page.querySelector(":scope > .form-fiche")?.remove();
    const f = formFiche({});
    (page.querySelector(":scope > h1") ?? page.firstChild)?.after(f);
    f.scrollIntoView({ block: "center" });
  };
  const [pdf, imp] = boutonsPdf("kb", "⎙ PDF", "base-de-connaissance.pdf",
    "toutes les fiches en un PDF : couverture (synopsis, date), sommaire par cluster, liens internes gardés, bibliographie — pour une relecture par un tiers");
  o.append(el("span", "etiq", "la base"), nouvelle, pdf, imp);
  majCompteFiches();
}

function ongletsFiches(actif) {
  barreFiches(actif);
  return el("span");
}

// ------------------------------------------------------------------ « En création »
//
// Les demandes de la base (fiches, pistes, renvois), séparées du stock : en cours, en attente,
// à décider, en erreur, puis les dernières closes. La page se met à jour d'elle-même tant
// qu'elle est ouverte.

const GROUPES_CREATION = [
  ["en_cours", "En cours", "Claude y travaille ; le déroulé est dans le tiroir."],
  ["en_attente", "En attente", "Pas encore lancées : ▶ pour lancer, ou l'enchaînement automatique."],
  ["prete", "À décider", "Claude a rendu sa réponse : l'ouvrir, relire, décider."],
  ["a_confirmer", "À confirmer", "Créées d'office par la file : elles sont déjà dans la base ; les confirmer, ou ne pas les garder."],
  ["erreur", "En erreur", "Arrêtées : reprendre, relancer (dans le tiroir), ou classer."],
];

async function pageCreation() {
  etat.ficheCourante = null;
  document.getElementById("volet-chapitre").hidden = true;
  const page = document.getElementById("page");
  const corps = el("div", "creation-corps");
  page.replaceChildren(ongletsFiches("creation"), el("h1", null, "En création"),
    el("p", "mut", "Les fiches en train de naître, et le travail de Claude sur la base (creuser, renvois). " +
      "Le stock des fiches est dans la vue liste."), corps);
  document.getElementById("fiche").replaceChildren(el("h4", null, "En création"),
    el("p", "mut petit", "La page se met à jour d'elle-même. Une demande relancée, décidée ou classée quitte les groupes " +
      "ouverts pour « Closes récemment »."));
  let signature = "";
  const remplit = async () => {
    if (!corps.isConnected) return;
    const [ds, F] = await Promise.all([api("/fiches/demandes").catch(() => []), api("/file").catch(() => null)]);
    const sig = JSON.stringify(ds.map((x) => [x.id, x.etat])) + JSON.stringify(F?.reglage);
    if (sig !== signature) {
      signature = sig;
      corps.replaceChildren();
      if (F) {
        const tete = el("div", "fiches-demandes-tete");
        tete.append(el("strong", null, "File d'attente"), reglageFile(F, remplit));
        corps.append(tete);
      }
      for (const [etatD, titre, aide] of GROUPES_CREATION) {
        const G = ds.filter((x) => x.etat === etatD).sort((a, b) => (a.cree < b.cree ? (etatD === "en_attente" ? -1 : 1) : (etatD === "en_attente" ? 1 : -1)));
        if (!G.length) continue;
        corps.append(el("h5", null, `${titre} · ${G.length}`), el("p", "mut petit", aide));
        for (const x of G) corps.append(ligneCreation(x, remplit));
      }
      const closes = ds.filter((x) => ["decidee", "remplacee", "abandonnee", "retiree"].includes(x.etat))
        .sort((a, b) => (a.cree < b.cree ? 1 : -1)).slice(0, 12);
      if (closes.length) {
        const det = el("details", "replie");
        det.append(el("summary", null, `Closes récemment · ${closes.length}`));
        for (const x of closes) det.append(ligneCreation(x, remplit));
        corps.append(det);
      }
      if (!ds.length) corps.append(el("p", "mut", "Rien en cours. « ◇ nouvelle fiche… », ou « ◇ creuser… » depuis une fiche."));
    }
    const actif = ds.some((x) => x.etat === "en_cours") || (F?.reglage.auto && F.en_attente.length);
    setTimeout(remplit, actif ? 4000 : 15000);
  };
  remplit();
  zone().scrollTo(0, 0);
}

function ligneCreation(x, apres) {
  const l = el("div", "dem-ligne ouverte file-ligne");
  l.append(el("span", "annot-type", LIB_TYPE_KB[x.type] ?? x.type), el("span", "dem-etat " + x.etat, etiquetteDemande(x)),
    el("span", "dem-titre-ligne", x.question ?? x.titre ?? x.id), el("span", "annot-date", (x.cree ?? "").slice(5, 16).replace("T", " ")));
  const a = el("span", "file-actions");
  if (x.etat === "en_attente") a.append(boutonLancer(x.id, apres), boutonRetirer(x.id, apres));
  if (x.etat === "erreur") {
    const c = el("button", "pan-lien", "classer");
    c.title = "clore cette demande sans la relancer (abandonnée)";
    c.onclick = async (e) => {
      e.stopPropagation();
      const r = await fetch(`/api/chapitres/_kb/demandes/${x.id}/classer`, { method: "POST" });
      if (!r.ok) { alert((await r.json().catch(() => ({}))).detail ?? r.status); return; }
      apres?.();
    };
    a.append(c);
  }
  if ((x.etat === "decidee" || x.etat === "a_confirmer") && x.decision?.fiche && !x.decision?.rejetee) {
    const f = el("a", "pan-lien", "fiche →");
    f.href = `#fiches/${x.decision.fiche}`;
    f.onclick = (e) => e.stopPropagation();
    a.append(f);
  }
  l.append(a);
  l.onclick = (e) => { if (!e.target.closest("button, a")) tiroir(x.id); };
  return l;
}

// ------------------------------------------------------------------ le graphe des fiches
//
// Les fiches (cercles) et, si on le veut, les chapitres (carrés) qui les listent. Trois sortes
// de liens : [[lien]] entre fiches, œuvres partagées, même chapitre. Les couleurs sont les
// clusters thématiques, calculés côté serveur (Louvain) avec ces mêmes liens pondérés ; la
// résolution règle leur nombre. Glisser un nœud, glisser le fond, molette pour zoomer ;
// survol : les voisins ; clic : le détail à droite ; double-clic : ouvrir la fiche.

const COULEURS = ["#c0712f", "#3f7fb5", "#4f9a5a", "#a2559b", "#c4a42c", "#3fa3a0", "#c4525a", "#7a6ad0",
  "#8a8f3a", "#b07a55", "#5f7f99", "#9b6b8a"];

async function pageGraphe() {
  etat.ficheCourante = null;
  document.getElementById("volet-chapitre").hidden = true;
  const P = etat.grapheP ??= { resolution: 1, oeuvres: 0.5, chapitres: 0.5, voirChap: true, voirLiens: true,
    voirOeuvres: true, voirMemeChap: false, regrouper: true, q: "" };
  const page = document.getElementById("page");
  const G = await api(`/fiches-graphe?resolution=${P.resolution}&oeuvres=${P.oeuvres}&chapitres=${P.chapitres}`);
  etat.graphe = G;

  const barre = el("div", "graphe-barre");
  const coche = (cle, lib, titre) => {
    const l = el("label", "graphe-coche");
    const c = el("input");
    c.type = "checkbox";
    c.checked = P[cle];
    c.onchange = () => { P[cle] = c.checked; sim.reprend(); };
    l.title = titre;
    l.append(c, " " + lib);
    return l;
  };
  const curseur = (cle, lib, min, max, pas, titre) => {
    const l = el("label", "graphe-curseur");
    const c = el("input");
    c.type = "range"; c.min = min; c.max = max; c.step = pas; c.value = P[cle];
    const v = el("span", "mut", String(P[cle]));
    c.oninput = () => { v.textContent = c.value; };
    c.onchange = () => { P[cle] = Number(c.value); pageGraphe(); };
    l.title = titre;
    l.append(lib + " ", c, " ", v);
    return l;
  };
  const q = el("input", "graphe-q");
  q.type = "search";
  q.placeholder = "surligner…";
  q.value = P.q;
  q.oninput = () => { P.q = q.value; sim.dessine(); };
  barre.append(
    coche("voirLiens", "[[liens]]", "les liens écrits d'une fiche à l'autre"),
    coche("voirOeuvres", "œuvres partagées", "deux fiches qui exploitent les mêmes œuvres"),
    coche("voirMemeChap", "même chapitre", "deux fiches listées par un même chapitre"),
    coche("voirChap", "chapitres", "les chapitres, reliés à leurs fiches (carrés)"),
    coche("regrouper", "regrouper", "rapprocher les fiches d'un même cluster"),
    Object.assign(el("button", "pan-lien", "⤢ recadrer"), { onclick: () => sim.cadre(), title: "tout le graphe dans la boîte" }),
    curseur("resolution", "clusters", 0.4, 2.4, 0.1, "résolution de Louvain : plus haut, plus de clusters, plus petits"),
    curseur("oeuvres", "poids œuvres", 0, 2, 0.1, "poids d'une œuvre partagée dans le calcul des clusters"),
    curseur("chapitres", "poids chapitres", 0, 2, 0.1, "poids d'un chapitre partagé dans le calcul des clusters"),
    q);
  const boite = el("div", "graphe-boite");
  const canvas = el("canvas", "graphe-canvas");
  boite.append(canvas);
  page.replaceChildren(ongletsFiches("graphe"), el("h1", null, "Graphe des fiches"),
    el("p", "mut petit", `${G.noeuds.filter((n) => n.type === "fiche").length} fiches · ${G.clusters.length} clusters · ` +
      `modularité ${G.modularite} · survol : les voisins ; clic : le détail ; double-clic : ouvrir`), barre, boite);
  const sim = simulation(canvas, G, P);
  legendeGraphe(G, sim);
  zone().scrollTo(0, 0);
}

function legendeGraphe(G, sim) {
  const d = document.getElementById("fiche");
  d.replaceChildren(el("h4", null, `Clusters · ${G.clusters.length}`),
    el("p", "mut petit", "Communautés du graphe (Louvain), nommées par leurs mots propres et leurs fiches les plus liées. " +
      "Un clic isole un cluster."));
  for (const c of G.clusters) {
    const b = el("div", "cluster-ligne");
    b.style.borderLeftColor = COULEURS[c.id % COULEURS.length];
    b.append(el("strong", null, c.mots.slice(0, 3).join(" · ") || "—"), el("span", "mut petit", ` ${c.taille} fiches`));
    const ph = el("div", "petit");
    ph.append(...c.phares.flatMap((s, i) => [i ? " · " : "", Object.assign(el("a", "lien-fiche-inline", s), { href: `#fiches/${s}` })]));
    b.append(ph);
    if (c.chapitres.length) b.append(el("div", "mut petit", "ch. " + c.chapitres.map((x) => x[0]).join(", ")));
    b.onclick = (e) => {
      if (e.target.closest("a")) return;
      sim.cluster = sim.cluster === c.id ? null : c.id;
      d.querySelectorAll(".cluster-ligne").forEach((x) => x.classList.toggle("choisi", x === b && sim.cluster === c.id));
      sim.dessine();
    };
    d.append(b);
  }
  const det = el("div", "graphe-detail");
  det.id = "graphe-detail";
  d.append(det);
}

function detailNoeud(n, G, sim) {
  const d = document.getElementById("graphe-detail");
  if (!d) return;
  if (!n) { d.replaceChildren(); return; }
  const c = G.clusters[n.cluster];
  const voisins = sim.voisins(n.id);
  d.replaceChildren(el("h4", null, n.type === "chapitre" ? `Chapitre ${n.numero ?? ""}` : "Fiche"),
    el("p", null, n.titre));
  if (c) d.append(el("p", "mut petit", `cluster : ${c.mots.slice(0, 3).join(" · ")}`));
  const act = el("div", "annot-actions");
  if (n.type === "fiche") {
    const o = el("a", "pan-lien", "ouvrir la fiche →");
    o.href = `#fiches/${n.id}`;
    act.append(o);
    if (n.confiance) d.append(pastilles(n.confiance));
  } else {
    const o = el("a", "pan-lien", n.atelier ? "ouvrir l'essai →" : "ouvrir le chapitre →");
    o.href = `#${n.id.slice(3)}/essai/texte`;
    act.append(o);
  }
  d.append(act, el("h5", null, `Voisins · ${voisins.length}`));
  for (const v of voisins.sort((a, b) => b.w - a.w).slice(0, 20)) {
    const l = el("div", "voisin");
    const a = el("a", "lien-fiche-inline", v.n.type === "chapitre" ? `ch. ${v.n.numero} ${v.n.titre}` : v.n.titre);
    a.href = v.n.type === "chapitre" ? `#${v.n.id.slice(3)}/essai/texte` : `#fiches/${v.n.id}`;
    l.append(a, el("span", "mut petit", " " + v.sortes.join(", ")));
    d.append(l);
  }
}

function simulation(canvas, G, P) {
  const css = getComputedStyle(document.documentElement);
  const FG = css.getPropertyValue("--fg").trim() || "#222", MUT = css.getPropertyValue("--mut").trim() || "#888",
    BG = css.getPropertyValue("--bg").trim() || "#fff";
  const pos = etat.graphePos ??= {};
  const noeuds = G.noeuds.map((n, i) => {
    const p = pos[n.id] ?? { x: Math.cos(n.cluster * 1.3 + i * 0.07) * (150 + (i % 7) * 12) + (Math.random() - .5) * 40,
      y: Math.sin(n.cluster * 1.3 + i * 0.07) * (150 + (i % 7) * 12) + (Math.random() - .5) * 40 };
    const r = n.type === "chapitre" ? 5 : 3 + Math.sqrt(n.degre) * 1.1;
    return { ...n, x: p.x, y: p.y, vx: 0, vy: 0, r };
  });
  const parId = Object.fromEntries(noeuds.map((n) => [n.id, n]));
  // chaque cluster a son ancre, sur un cercle : « regrouper » y attire ses fiches
  const nc = G.clusters.length || 1;
  const ancre = (c) => ({ x: Math.cos(2 * Math.PI * c / nc) * 260, y: Math.sin(2 * Math.PI * c / nc) * 260 });
  const aretes = G.liens.map((l) => ({ ...l, a: parId[l.source], b: parId[l.target] })).filter((l) => l.a && l.b);
  const S = { cluster: null, survol: null, choisi: null, alpha: 1, k: 1, tx: 0, ty: 0 };
  const ctx = canvas.getContext("2d");
  let W = 0, H = 0;

  const visible = (l) => {
    if (l.sorte === "appartient") return P.voirChap;
    return (P.voirLiens && l.lien) || (P.voirOeuvres && l.oeuvres) || (P.voirMemeChap && l.chapitre);
  };
  const noeudVisible = (n) => n.type !== "chapitre" || P.voirChap;
  const poids = (l) => l.sorte === "appartient" ? 0.4 :
    (P.voirLiens ? l.lien : 0) + (P.voirOeuvres ? l.oeuvres * P.oeuvres : 0) + (P.voirMemeChap ? l.chapitre * P.chapitres : 0);

  function taille() {
    const r = canvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    W = r.width; H = r.height;
    canvas.width = W * dpr; canvas.height = H * dpr;
    canvas.style.width = W + "px"; canvas.style.height = H + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (!S.tx && !S.ty) { S.tx = W / 2; S.ty = H / 2; }
  }

  function pas() {
    const vis = noeuds.filter(noeudVisible);

    for (let i = 0; i < vis.length; i++) {
      const a = vis[i];
      for (let j = i + 1; j < vis.length; j++) {
        const b = vis[j];
        let dx = b.x - a.x, dy = b.y - a.y, d2 = dx * dx + dy * dy || 0.01;
        if (d2 > 160000) continue;
        const f = Math.min(2400 / d2, 8) * S.alpha;
        const d = Math.sqrt(d2);
        dx /= d; dy /= d;
        a.vx -= dx * f; a.vy -= dy * f; b.vx += dx * f; b.vy += dy * f;
      }
    }
    for (const l of aretes) {
      if (!visible(l) || !noeudVisible(l.a) || !noeudVisible(l.b)) continue;
      const w = Math.min(poids(l), 4);
      if (!w) continue;
      const dx = l.b.x - l.a.x, dy = l.b.y - l.a.y, d = Math.sqrt(dx * dx + dy * dy) || 1;
      const f = (d - 55) * 0.006 * Math.sqrt(w) * S.alpha;
      l.a.vx += dx / d * f; l.a.vy += dy / d * f; l.b.vx -= dx / d * f; l.b.vy -= dy / d * f;
    }
    for (const n of vis) {
      n.vx -= n.x * 0.002 * S.alpha; n.vy -= n.y * 0.002 * S.alpha;
      if (P.regrouper && n.type === "fiche") {
        const c = ancre(n.cluster);
        n.vx += (c.x - n.x) * 0.02 * S.alpha; n.vy += (c.y - n.y) * 0.02 * S.alpha;
      }
      if (n === S.tire) continue;
      n.vx *= 0.82; n.vy *= 0.82;
      n.x += Math.max(-20, Math.min(20, n.vx)); n.y += Math.max(-20, Math.min(20, n.vy));
      pos[n.id] = { x: n.x, y: n.y };
    }
    S.alpha = Math.max(0.0, S.alpha * 0.985);
  }

  function voisins(id) {
    const out = new Map();
    for (const l of aretes) {
      if (!visible(l)) continue;
      const o = l.a.id === id ? l.b : l.b.id === id ? l.a : null;
      if (!o || !noeudVisible(o)) continue;
      const v = out.get(o.id) ?? { n: o, w: 0, sortes: [] };
      v.w += poids(l);
      for (const [k, lib] of [["lien", "lien"], ["oeuvres", "œuvres"], ["chapitre", "chapitre"]]) {
        if (l[k] && !v.sortes.includes(lib) && (l.sorte !== "appartient" || k === "chapitre")) v.sortes.push(l.sorte === "appartient" ? "liste la fiche" : lib);
      }
      out.set(o.id, v);
    }
    return [...out.values()];
  }

  function dessine() {
    ctx.clearRect(0, 0, W, H);
    ctx.save();
    ctx.translate(S.tx, S.ty);
    ctx.scale(S.k, S.k);
    const focus = S.survol ?? S.choisi;
    const proches = focus ? new Set([focus.id, ...voisins(focus.id).map((v) => v.n.id)]) : null;
    const plat = (s) => (s ?? "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
    const q = plat(P.q).trim();
    const allume = (n) => (!proches || proches.has(n.id)) && (S.cluster == null || n.cluster === S.cluster)
      && (!q || plat(n.titre + " " + n.id).includes(q));
    for (const l of aretes) {
      if (!visible(l) || !noeudVisible(l.a) || !noeudVisible(l.b)) continue;
      const on = allume(l.a) && allume(l.b) && (!proches || l.a === focus || l.b === focus);
      ctx.globalAlpha = on ? (proches ? 0.8 : 0.28) : 0.05;
      ctx.strokeStyle = l.sorte === "appartient" ? MUT : l.lien ? FG : COULEURS[l.a.cluster % COULEURS.length];
      ctx.lineWidth = (l.lien ? 0.9 : 0.6) / Math.sqrt(S.k);
      ctx.setLineDash(l.sorte === "appartient" ? [3, 3] : l.lien ? [] : [1, 2]);
      ctx.beginPath(); ctx.moveTo(l.a.x, l.a.y); ctx.lineTo(l.b.x, l.b.y); ctx.stroke();
    }
    ctx.setLineDash([]);
    const grands = new Set(noeuds.filter((n) => n.type === "fiche").sort((a, b) => b.degre - a.degre).slice(0, 10).map((n) => n.id));
    for (const n of noeuds) {
      if (!noeudVisible(n)) continue;
      const on = allume(n);
      ctx.globalAlpha = on ? 1 : 0.15;
      ctx.fillStyle = COULEURS[n.cluster % COULEURS.length];
      ctx.beginPath();
      if (n.type === "chapitre") ctx.rect(n.x - n.r, n.y - n.r, n.r * 2, n.r * 2);
      else ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
      ctx.fill();
      if (n.type === "chapitre" || n === S.choisi) { ctx.strokeStyle = n === S.choisi ? FG : BG; ctx.lineWidth = 1.5 / S.k; ctx.stroke(); }
      const etiquette = on && (n === focus || (proches && proches.has(n.id)) || (!proches && grands.has(n.id)) || S.k > 1.6
        || (n.type === "chapitre" && (S.k > 1.1 || proches)) || (q && on) || (S.cluster != null && n.cluster === S.cluster));
      if (etiquette) {
        ctx.globalAlpha = on ? 0.95 : 0.2;
        ctx.fillStyle = FG;
        ctx.font = `${(n === focus ? 12 : 10.5) / S.k}px system-ui, sans-serif`;
        const lib = n.type === "chapitre" ? `${n.numero ?? ""} ${n.titre}` : n.id;
        ctx.strokeStyle = BG; ctx.lineWidth = 3 / S.k; ctx.lineJoin = "round";
        ctx.strokeText(lib, n.x + n.r + 3 / S.k, n.y + 3.5 / S.k);
        ctx.fillText(lib, n.x + n.r + 3 / S.k, n.y + 3.5 / S.k);
      }
    }
    ctx.restore();
  }

  // cadrer : tout le graphe visible dans la boîte
  function cadre() {
    const vis = noeuds.filter(noeudVisible);
    if (!vis.length || !W) return;
    const xs = vis.map((n) => n.x), ys = vis.map((n) => n.y);
    const x0 = Math.min(...xs) - 40, x1 = Math.max(...xs) + 140, y0 = Math.min(...ys) - 30, y1 = Math.max(...ys) + 30;
    S.k = Math.max(0.25, Math.min(2.5, Math.min(W / (x1 - x0), H / (y1 - y0))));
    S.tx = W / 2 - (x0 + x1) / 2 * S.k; S.ty = H / 2 - (y0 + y1) / 2 * S.k;
  }
  let cadre_fait = false;

  let enCours = true;
  function boucle() {
    if (!canvas.isConnected) {                 // la page a changé : on se retire
      enCours = false; window.removeEventListener("mouseup", haut); obs.disconnect(); return;
    }
    if (S.alpha > 0.01) {
      pas();
      if (!cadre_fait && !S.bouge && S.alpha < 0.08) { cadre(); cadre_fait = true; }
      if (!S.bouge && !S.fini && S.alpha < 0.013) { cadre(); S.fini = true; }   // la disposition est posée : cadrer une dernière fois
      dessine();
    }
    requestAnimationFrame(boucle);
  }

  const monde = (e) => {
    const r = canvas.getBoundingClientRect();
    return { x: (e.clientX - r.left - S.tx) / S.k, y: (e.clientY - r.top - S.ty) / S.k };
  };
  const sous = (e) => {
    const m = monde(e);
    let best = null, bd = Infinity;
    for (const n of noeuds) {
      if (!noeudVisible(n)) continue;
      const d = Math.hypot(n.x - m.x, n.y - m.y);
      if (d < n.r + 5 / S.k && d < bd) { best = n; bd = d; }
    }
    return best;
  };
  let glisse = null;
  canvas.onmousedown = (e) => {
    const n = sous(e);
    glisse = { n, x: e.clientX, y: e.clientY, tx: S.tx, ty: S.ty, bouge: false };
    if (n) { S.tire = n; }
  };
  const haut = () => {
    if (glisse && !glisse.bouge) {
      S.choisi = glisse.n;
      detailNoeud(glisse.n, G, api_);
      dessine();
    }
    glisse = null; S.tire = null;
  };
  window.addEventListener("mouseup", haut);
  canvas.onmousemove = (e) => {
    if (glisse) {
      if (Math.hypot(e.clientX - glisse.x, e.clientY - glisse.y) > 3) glisse.bouge = true;
      if (glisse.n) { const m = monde(e); glisse.n.x = m.x; glisse.n.y = m.y; glisse.n.vx = glisse.n.vy = 0; S.alpha = Math.max(S.alpha, 0.3); }
      else { S.tx = glisse.tx + e.clientX - glisse.x; S.ty = glisse.ty + e.clientY - glisse.y; S.bouge = true; dessine(); }
      return;
    }
    const n = sous(e);
    if (n !== S.survol) { S.survol = n; canvas.style.cursor = n ? "pointer" : "grab"; dessine(); }
  };
  canvas.onmouseleave = () => { S.survol = null; dessine(); };
  canvas.ondblclick = (e) => {
    const n = sous(e);
    if (n) location.hash = n.type === "fiche" ? `fiches/${n.id}` : `${n.id.slice(3)}/essai/texte`;
  };
  canvas.onwheel = (e) => {
    e.preventDefault();
    const r = canvas.getBoundingClientRect();
    const mx = e.clientX - r.left, my = e.clientY - r.top;
    const f = Math.exp(-e.deltaY * 0.0015);
    const k = Math.max(0.25, Math.min(5, S.k * f));
    S.tx = mx - (mx - S.tx) * (k / S.k); S.ty = my - (my - S.ty) * (k / S.k); S.k = k; S.bouge = true;
    dessine();
  };
  const obs = new ResizeObserver(() => { taille(); dessine(); });
  obs.observe(canvas.parentElement);
  taille();
  const api_ = {
    get cluster() { return S.cluster; }, set cluster(v) { S.cluster = v; },
    dessine, voisins, reprend() { S.alpha = Math.max(S.alpha, 0.6); cadre_fait = S.bouge; dessine(); },
    cadre() { cadre(); S.bouge = false; dessine(); },
  };
  if (Object.keys(pos).length) { S.alpha = 0.3; cadre(); }   // une disposition connue : on la reprend doucement
  boucle();
  return api_;
}

async function pageFiche(slug, section, I) {
  const page = document.getElementById("page");
  let f;
  try { f = await api(`/fiches/${encodeURIComponent(slug)}`); }
  catch { page.replaceChildren(el("p", "mut", `Pas de fiche « ${slug} ».`)); return; }
  const deja = etat.ficheCourante === slug;
  etat.ficheCourante = slug;

  const titres = Object.fromEntries(I.map((x) => [x.slug, x.titre]));
  const fil = el("p", "fil");
  const retour = el("a", null, "Fiches");
  retour.href = "#fiches";
  const gr = el("a", null, "graphe");
  gr.href = "#fiches/graphe";
  fil.append(retour, ` › ${slug}`);
  const corps = el("div", "fiche-corps");
  corps.innerHTML = f.html;
  corps.querySelectorAll("a.wiki").forEach((a) => {
    const cible = a.getAttribute("href").split("/")[1];
    if (titres[cible]) a.title = titres[cible];
  });
  corps.querySelectorAll(".wiki-hors").forEach((s) => {
    const l = f.liens.find((x) => x.cible === s.textContent);
    if (l?.heritage_abs) {
      s.classList.add("ouvrable");
      s.onclick = () => window.open("vscode://file" + l.heritage_abs);
    }
  });
  enrichit(corps);
  marqueConfiance(corps, f.confiance_par);
  corps.querySelectorAll("h2[data-section], h3[data-section], h4[data-section]").forEach((h) =>
    h.append(boutonRef(`@fiche/${f.slug}#${h.dataset.section}`, "pan-lien ref-copie ref-titre")));
  corps.querySelectorAll(".wiki-mort").forEach((s) => {
    s.onclick = () => {
      document.querySelector("#page .form-fiche")?.remove();
      const fm = formFiche({ slug: s.dataset.cible, chapitres: f.chapitres.map((c) => c.slug),
        question: `Fiche « ${s.dataset.cible} », citée par [[${f.slug}]] : ` });
      corps.before(fm);
      fm.scrollIntoView({ block: "center" });
    };
  });
  page.replaceChildren(fil, el("h1", null, f.titre));
  if (f.meta.sujet && f.meta.sujet !== f.titre) page.append(el("p", "mut fiche-sujet-page", f.meta.sujet));
  if (f.meta.origine === "claude") {
    const b = el("div", ["brouillon", "a_confirmer"].includes(f.meta.etat) ? "fiche-alerte petit bandeau-brouillon" : "mut petit bandeau-brouillon");
    b.append(`Écrite par Claude (demande ${f.meta.demande ?? "?"}) · état : ${f.meta.etat ?? "?"}` +
      (f.meta.relue ? ` le ${f.meta.relue}` : "") + (f.meta.etat === "brouillon" ? " — à relire. " : f.meta.etat === "a_confirmer"
        ? " — créée d'office par la file, pas encore confirmée. " : ". "));
    if (f.meta.etat === "a_confirmer" && f.meta.demande) {
      const c = el("button", "bouton", "confirmer, ou non →");
      c.onclick = () => tiroir(f.meta.demande);
      b.append(c);
    }
    if (f.meta.etat === "brouillon") {
      const ok = el("button", "bouton", "✓ marquer comme relue");
      ok.title = "tu l'as relue : elle passe de brouillon à relue, et les renvois vers elle te sont proposés";
      ok.onclick = async () => {
        const r = await fetch(`/api/fiches/${f.slug}/relue`, { method: "POST" });
        if (!r.ok) { alert((await r.json().catch(() => ({}))).detail ?? r.status); return; }
        await indexFiches(true);
        pageFiche(f.slug, null, etat.fichesIndex ?? []);
      };
      b.append(ok);
    }
    page.append(b);
  }
  // les actions sur cette fiche : dans la barre ; leurs formulaires s'ouvrent ici, sous la confiance
  const actions = el("div", "actions-fiche");
  const ouvre = (noeud) => { actions.replaceChildren(noeud); noeud.scrollIntoView({ block: "center" }); };
  const creuser = el("button", "b-versions", "◇ creuser…");
  creuser.title = "Claude lit la fiche et propose des fiches complémentaires, après avoir vérifié qu'elles ne sont pas déjà couvertes";
  creuser.onclick = () => ouvre(formPistes(f.slug));
  const sup = el("button", "b-versions danger", "supprimer…");
  sup.title = "le ménage : la fiche va à la corbeille (récupérable) ; voir d'abord ce qui en dépend";
  sup.onclick = () => formSuppression(f).then(ouvre);
  const aFiche = el("span", "actions-barre");
  aFiche.append(el("span", "etiq", "cette fiche"), boutonRef("@fiche/" + f.slug, "b-versions"), creuser, sup);
  barreFiches(null, aFiche);
  api(`/fiches/${f.slug}/renvois`).then((x) => {
    if (x.voisines?.length) { const b = boutonRenvois(f.slug, x.voisines); b.className = "b-versions"; sup.before(b); }
  }).catch(() => {});
  page.append(pastilles(f.confiance, true), barreConfiance(f, corps), actions, corps);
  planFiche(f);
  liensFiche(f);
  if (section) {
    const h = document.getElementById("fs-" + section);
    if (h) { h.scrollIntoView({ block: "start" }); h.classList.add("eclair"); setTimeout(() => h.classList.remove("eclair"), 1600); }
  } else if (!deja) zone().scrollTo(0, 0);
}

// À gauche : le plan de la fiche ; un clic va à la section (l'adresse suit, sans recharger).
function planFiche(f) {
  const volet = document.getElementById("volet-chapitre");
  volet.hidden = false;
  volet.querySelector(".volet-titre").textContent = `Plan de la fiche · ${f.slug}`;
  const col = document.getElementById("plan-col");
  const racine = el("div", "pl-arbre plan-fiche");
  const min = Math.min(...f.sections.map((s) => s.niveau), 2);
  for (const s of f.sections) {
    const a = el("a", "pf-ligne", s.titre.replace(/\*\*/g, ""));
    a.style.paddingLeft = ((s.niveau - min) * .9 + .6) + "rem";
    a.href = `#fiches/${f.slug}/${s.id}`;
    a.onclick = (e) => {
      e.preventDefault();
      history.replaceState(null, "", `#fiches/${f.slug}/${s.id}`);
      document.getElementById("fs-" + s.id)?.scrollIntoView({ block: "start", behavior: "smooth" });
    };
    racine.append(a);
  }
  if (!f.sections.length) racine.append(el("p", "mut", "Pas d'intertitres."));
  col.replaceChildren(racine);
}

// À droite : ce qui relie la fiche au livre.
function liensFiche(f) {
  const d = document.getElementById("fiche");
  d.replaceChildren();
  const section = (titre, n) => d.append(el("h4", null, n != null ? `${titre} · ${n}` : titre));
  const lienFiche = (s) => {
    const a = el("a", "lien-fiche", (etat.fichesIndex ?? []).find((x) => x.slug === s)?.titre ?? s);
    a.href = `#fiches/${s}`;
    a.title = s;
    return a;
  };

  // les pistes déjà demandées pour cette fiche
  api("/fiches/demandes").then((ds) => {
    const P = ds.filter((x) => x.type === "pistes" && x.fiche === f.slug).sort((a, b) => (a.cree < b.cree ? 1 : -1));
    if (!P.length) return;
    const aDecider = P.filter((x) => x.etat === "prete");
    const h1 = document.querySelector("#page h1");
    if (aDecider.length && h1 && !document.querySelector("#page .banniere-pistes")) {
      const b = el("button", "banniere-pistes", `◇ ${aDecider.length > 1 ? aDecider.length + " lectures « creuser »" : "Des pistes proposées en creusant cette fiche"} ` +
        "attendent ta décision → ouvrir");
      b.onclick = () => tiroir(aDecider[0].id);
      h1.before(b);
    }
    const bloc = el("div");
    bloc.append(el("h4", null, `Creuser · ${P.length}`));
    for (const x of P) {
      const a = el("button", "pan-lien", `${x.cree.slice(0, 10)} · ${etiquetteDemande(x)}`);
      a.onclick = () => tiroir(x.id);
      bloc.append(a, el("br"));
    }
    d.prepend(bloc);
  }).catch(() => {});
  section("Chapitres", f.chapitres.length);
  if (!f.chapitres.length) d.append(el("p", "mut petit", "Aucun chapitre de l'atelier ne la liste dans son brief."));
  for (const c of f.chapitres) {
    const a = el("a", "lien-fiche", `${c.numero ?? ""} · ${c.title}`);
    a.href = `#${c.slug}/essai/texte`;
    d.append(a);
  }

  const sortantes = f.liens.filter((l) => l.fiche);
  section("Cite", sortantes.length);
  for (const l of sortantes) d.append(lienFiche(l.cible));
  const hors = f.liens.filter((l) => !l.fiche);
  if (hors.length) {
    const p = el("p", "mut petit");
    p.append("Hors fiches : ");
    hors.forEach((l, i) => {
      const s = el(l.heritage_abs ? "a" : "span", "wiki-hors", l.cible);
      s.title = l.heritage ? `${l.heritage} — ancien dépôt, lecture seule` : "lien mort";
      if (l.heritage_abs) s.href = "vscode://file" + l.heritage_abs;
      p.append(i ? ", " : "", s);
    });
    d.append(p);
  }

  section("Citée par", f.entrants.length);
  if (!f.entrants.length) d.append(el("p", "mut petit", "Aucune fiche n'y renvoie."));
  for (const s of f.entrants) d.append(lienFiche(s));

  section("Œuvres dans l'essai", f.oeuvres.length);
  for (const o of f.oeuvres) {
    const b = el("div", "oeuvre-fiche");
    const r = el("span", "verif-ref");
    r.innerHTML = mdLigne(o.ref);
    b.append(el("code", "petit", o.cle), " ", r);
    for (const c of o.chapitres) {
      for (const n of c.notes.length ? c.notes : [null]) {
        const a = el("a", "pan-lien", n ? `note ${n.replace(c.slug + "-", "")} · ${c.title}` : c.title);
        a.href = `#${c.slug}/essai/${n ? "notes" : "biblio"}`;
        a.onclick = () => { etat.noteApres = n; };
        b.append(el("br"), a);
      }
    }
    d.append(b);
  }
  const oc = f.oeuvres_centrales;
  if (oc?.total) d.append(el("p", "mut petit",
    `${oc.total} œuvre(s) de la bibliographie centrale y sont exploitées` +
    (oc.hors_chapitres.length ? `, dont ${oc.hors_chapitres.length} pas encore dans un chapitre de l'atelier.` : ".")));

  section("Fichier");
  const fl = el("div", "fichier-ligne");
  fl.append(el("code", null, `kb/fiches/${f.slug}.md`));
  const vs = el("a", "lien-ext", "VS Code ↗");
  vs.href = "vscode://file" + f.fichier;
  fl.append(vs);
  d.append(fl);
}

// « Fiches · n » : les demandes de la base (fiches, pistes) à décider ou en attente.
async function majCompteFiches() {
  const ds = await api("/fiches/demandes").catch(() => null);
  if (!ds) return;
  const decider = ds.filter((x) => x.etat === "prete" || x.etat === "a_confirmer").length, attente = ds.filter((x) => x.etat === "en_attente").length;
  const b = document.getElementById("b-fiches");
  b.textContent = decider + attente ? `Fiches · ${decider + attente}` : "Fiches";
  b.classList.toggle("a-decider", decider > 0);
  b.title = `${decider} à décider · ${attente} en attente — dans Fiches › En création`;
  const cours = ds.filter((x) => x.etat === "en_cours").length, err = ds.filter((x) => x.etat === "erreur").length;
  const o = document.getElementById("onglet-creation");
  if (o) o.textContent = `en création` + (cours + attente + decider + err ? ` · ${cours + attente + decider + err}` : "");
}
setInterval(() => { if (!document.hidden) majCompteFiches(); }, 10000);

window.addEventListener("hashchange", depuisAdresse);

etat.livre = await api("/livre").catch(() => ({ titre: "" }));
afficheTitre();
document.getElementById("titre-livre").onclick = () => { location.hash = "livre"; };
document.getElementById("b-demandes").onclick = () => tiroir(null);
document.getElementById("b-annotations").onclick = () => tiroirAnnotations();
document.getElementById("b-plan").onclick = () => { location.hash = "plan"; };
document.getElementById("b-fiches").onclick = () => { location.hash = etat.ficheCourante ? `fiches/${etat.ficheCourante}` : "fiches"; };
etat.chapitres = await api("/chapitres");
api("/sources").then((s) => { etat.sources = s; }).catch(() => {});
etat.regles = await api("/regles").catch(() => ({}));
indexFiches();
await chargeModeles();
majCompteAnnotations();
sommaire();
fiche();
majCompteFiches();
{
  // un tiroir ouvert avant le rafraîchissement : le rouvrir
  let t = null;
  try { t = JSON.parse(sessionStorage.getItem("atelier-tiroir") ?? "null"); } catch { /* rien */ }
  if (t?.id && t.slug !== "_kb" && location.hash.slice(1).split("/")[0] === t.slug) etat.tiroirApres = t.id;
  depuisAdresse();
  if (t?.id && t.slug === "_kb") setTimeout(() => tiroir(t.id), 300);
}

// ------------------------------------------------------------------ parler avec Claude
//
// Un panneau ouvert depuis l'en-tête, dans toutes les vues. Claude lit le livre et répond ; il ne
// touche à rien. Ses propositions de travail sont des actions que l'auteur lance d'un clic : elles
// deviennent des demandes ordinaires. « ici » : la référence de ce que l'auteur regarde, jointe à la
// question (décochable).

let suiviDialogue = null;

const poste = (chemin, corps, methode = "POST") =>
  fetch("/api" + chemin, { method: methode, headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps ?? {}) })
    .then(async (r) => (r.ok ? r.json() : Promise.reject((await r.json().catch(() => ({}))).detail ?? r.status)));

// Ce que l'auteur regarde, en référence.
function refIci() {
  const [a, b, c] = decodeURIComponent(location.hash.slice(1)).split("/");
  if (a === "fiches" && b) return `@fiche/${b}${c ? "#" + c : ""}`;
  if (a === "biblio" && b) return `@oeuvre/${b}`;
  if (a === "plan" && b === "p" && c) return `@partie/${c}`;
  if (a === "plan" && b === "c" && c) return `@chapitre/${c}`;
  if ((a === "livre" || !a) && b === "regles" && c) return etat.regleCible ? `@regle/${c}/${etat.regleCible}` : null;
  if (etat.accueil || etat.wiki || !etat.slug) return null;
  const v = versionVue();
  const bloc = v === "essai" ? etat.blocEssai : etat.bloc;
  return bloc ? `@chapitre/${etat.slug}/${v}^${bloc}` : `@chapitre/${etat.slug}/${v}`;
}

// Un Markdown sobre : titres, listes, paragraphes, **gras**, *italique*, `code`.
function mdDialogue(texte) {
  const f = document.createDocumentFragment();
  const enLigne = (n, s) => {
    for (const m of s.split(/(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/)) {
      if (!m) continue;
      if (m.startsWith("**")) n.append(el("strong", null, m.slice(2, -2)));
      else if (m.startsWith("`")) n.append(el("code", null, m.slice(1, -1)));
      else if (m.startsWith("*") && m.length > 2) n.append(el("em", null, m.slice(1, -1)));
      else n.append(document.createTextNode(m));
    }
    return n;
  };
  let liste = null;
  for (const bloc of (texte ?? "").split(/\n{2,}/)) {
    const lignes = bloc.split("\n");
    if (lignes.every((l) => /^\s*([-*]|\d+\.)\s/.test(l) || !l.trim())) {
      liste = el(/^\s*\d/.test(lignes[0]) ? "ol" : "ul");
      for (const l of lignes.filter((x) => x.trim())) liste.append(enLigne(el("li"), l.replace(/^\s*([-*]|\d+\.)\s+/, "")));
      f.append(liste);
      continue;
    }
    const h = bloc.match(/^(#{1,4})\s+(.*)$/);
    if (h && lignes.length === 1) { f.append(enLigne(el("h5"), h[2])); continue; }
    const p = el("p");
    lignes.forEach((l, i) => { if (i) p.append(el("br")); enLigne(p, l); });
    f.append(p);
  }
  return f;
}

const LIB_ACTION = { fiche: "✚ fiche", pistes: "⛏ creuser", verification: "🔎 vérification", reecriture: "↻ réécriture",
  naive: "👁 lecture naïve", plan: "✦ plan" };

function cibleAction(a) {
  const x = [];
  if (a.chapitre) x.push("@chapitre/" + a.chapitre);
  if (a.fiche) x.push("@fiche/" + a.fiche);
  if (a.question) x.push("question : " + a.question);
  if (a.slug) x.push("slug : " + a.slug);
  if (a.chapitres?.length) x.push("chapitres : " + a.chapitres.join(", "));
  if (a.assertions?.length) x.push("assertions : " + a.assertions.join(", "));
  if (a.blocs?.length) x.push("paragraphes : " + a.blocs.map((b) => "^" + b).join(" "));
  if (a.plan) x.push("plan " + a.plan);
  if (a.annotation) x.push("annotation " + a.annotation);
  if (a.version) x.push(a.version);
  if (a.niveau) x.push(a.niveau + (a.partie ? " " + a.partie : ""));
  return x.join(" · ");
}

function carteAction(c, n, i, a) {
  const d = el("div", "dia-action" + (a.lancee ? " lancee" : ""));
  const tete = el("div", "dia-action-tete");
  tete.append(el("span", "dia-type", LIB_ACTION[a.type] ?? a.type), el("strong", null, a.titre));
  d.append(tete, el("div", "mut petit", a.pourquoi ?? ""));
  const cible = el("div", "dia-cible", cibleAction(a));
  d.append(cible);
  setTimeout(() => lieRefs(cible), 0);
  if (a.lancee) {
    const o = el("a", "ref-lien", "lancée · " + a.lancee.id + " · ouvrir");
    o.href = "#";
    o.onclick = (e) => { e.preventDefault(); ouvreDemande(a.lancee.slug, a.lancee.id); };
    d.append(o);
    return d;
  }
  const consigne = el("textarea", "dem-motif dia-consigne");
  consigne.rows = 2;
  consigne.placeholder = "consigne (facultative)";
  consigne.value = a.consigne ?? "";
  const b = el("button", "b-versions", "lancer");
  const err = el("span", "err petit");
  b.onclick = async () => {
    b.disabled = true;
    err.textContent = "";
    try {
      const r = await poste(`/conversations/${c.id}/tours/${n}/actions/${i}`, { consigne: consigne.value });
      a.lancee = { id: r.demande.id, slug: r.slug };
      d.replaceWith(carteAction(c, n, i, a));
      marquesDemandes?.();
    } catch (e) { err.textContent = String(e); b.disabled = false; }
  };
  const pied = el("div", "dia-pied");
  pied.append(b, err);
  d.append(consigne, pied);
  return d;
}

function tourDialogue(c, t, n) {
  const d = el("div", "dia-tour");
  const q = el("div", "dia-question");
  q.append(el("div", null, t.question));
  if (t.ici) q.append(el("div", "dia-ici", "ici : " + t.ici));
  d.append(q);
  setTimeout(() => lieRefs(q), 0);
  if (t.etat === "en_cours") {
    const z = el("div", "dia-direct");
    const der = (t.deroule ?? []).filter((e) => e.nom !== "StructuredOutput");
    z.append(el("div", "dem-attente", `Claude lit et réfléchit… (${der.length} étapes)`));
    const ol = el("ol", "deroule");
    ol.append(...der.slice(-6).map(ligneDeroule));
    z.append(ol);
    d.append(z);
    return d;
  }
  if (t.etat === "erreur") d.append(el("div", "err", t.erreur ?? "erreur"));
  if (t.reponse) {
    const r = el("div", "dia-reponse");
    r.append(mdDialogue(t.reponse));
    d.append(r);
    setTimeout(() => lieRefs(r), 0);
  }
  (t.actions ?? []).forEach((a, i) => d.append(carteAction(c, n, i, a)));
  const pied = el("div", "dia-meta");
  const ex = t.execution ?? {};
  pied.append(el("span", "mut petit", [ex.modele, ex.duree_s != null ? ex.duree_s + " s" : null,
    ex.cout_usd != null ? "$" + ex.cout_usd.toFixed(3) : null].filter(Boolean).join(" · ")));
  const j = ligneJetons(ex.jetons);
  if (j) pied.append(j);
  d.append(pied);
  const dc = derouleComplet({ deroule: t.deroule ?? [] });
  if (dc) d.append(dc);
  return d;
}

async function dialogue(ident = etat.conversation) {
  clearTimeout(suiviDialogue);
  const z = document.getElementById("dialogue");
  z.hidden = false;
  document.body.dataset.dialogue = "1";
  document.getElementById("b-claude").classList.add("actif");
  etat.conversation = ident ?? null;
  try { sessionStorage.setItem("atelier-conversation", ident ?? ""); } catch { /* sans stockage */ }
  const tete = el("div", "dia-tete");
  const liste = el("select", "dia-liste");
  const L = await api("/conversations").catch(() => []);
  liste.append(new Option("— nouvelle conversation —", ""));
  for (const x of L) liste.append(new Option(`${(x.titre ?? "sans titre").slice(0, 60)} · ${x.tours} · ${(x.modifie ?? "").slice(0, 10)}`, x.id, false, x.id === ident));
  liste.onchange = () => dialogue(liste.value || null);
  const sup = el("button", "pan-lien", "🗑");
  sup.title = "supprimer cette conversation";
  sup.hidden = !ident;
  sup.onclick = async () => {
    if (!confirm("Supprimer cette conversation ?")) return;
    await poste(`/conversations/${ident}`, null, "DELETE").catch((e) => alert(e));
    dialogue(null);
  };
  const x = el("button", "fermer", "×");
  x.onclick = () => { clearTimeout(suiviDialogue); z.hidden = true; delete document.body.dataset.dialogue; document.getElementById("b-claude").classList.remove("actif"); };
  tete.append(el("h4", null, "✦ Claude"), liste, sup, x);
  const fil = el("div", "dia-fil");
  let c = null;
  if (ident) {
    c = await api(`/conversations/${ident}`).catch(() => null);
    if (!c) return dialogue(null);
    c.tours.forEach((t, n) => fil.append(tourDialogue(c, t, n)));
  } else {
    fil.append(el("p", "mut", "Une question sur le livre : ce qu'il dit, où, sur quelles sources, ce qui manque, ce qui se contredit. " +
      "Claude lit tout (textes, cadres, fiches, bibliographie, garde-fous) et peut proposer du travail — vous le lancez. " +
      "Collez des références (⧉) pour viser un morceau précis."));
  }
  const saisie = el("div", "dia-saisie");
  const q = el("textarea", "dem-motif dia-q");
  q.rows = 3;
  q.placeholder = "votre question… (⌘/Ctrl + Entrée pour envoyer)";
  q.value = etat.brouillonDialogue ?? "";
  q.oninput = () => { etat.brouillonDialogue = q.value; };
  const ref = refIci();
  const lieu = el("label", "dia-ici-choix");
  q.onfocus = () => { const r = refIci(); lieu.hidden = !r; lieu.lastChild.textContent = " joindre ici : " + (r ?? "—"); };
  const coche = el("input");
  coche.type = "checkbox";
  coche.checked = !!ref;
  lieu.append(coche, document.createTextNode(" joindre ici : " + (ref ?? "—")));
  lieu.hidden = !ref;
  const envoi = el("button", "b-versions", "envoyer");
  const err = el("span", "err petit");
  const occupe = c?.etat === "en_cours";
  envoi.disabled = occupe;
  const part = async () => {
    const question = q.value.trim();
    if (!question || envoi.disabled) return;
    envoi.disabled = true;
    const corps = { question, ici: coche.checked ? refIci() : null };
    try {
      const r = ident ? await poste(`/conversations/${ident}`, corps) : await poste("/conversations", corps);
      etat.brouillonDialogue = "";
      dialogue(r.id);
    } catch (e) { err.textContent = String(e); envoi.disabled = false; }
  };
  envoi.onclick = part;
  q.onkeydown = (e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); part(); } };
  const pied = el("div", "dia-pied");
  pied.append(envoi, lieu, err);
  saisie.append(q, pied);
  z.replaceChildren(tete, fil, saisie);
  fil.scrollTop = fil.scrollHeight;
  if (!occupe) q.focus();
  if (occupe) suiviDialogue = setTimeout(() => rafraichitDialogue(ident), 2000);
}

async function rafraichitDialogue(ident) {
  const z = document.getElementById("dialogue");
  if (z.hidden || etat.conversation !== ident) return;
  const c = await api(`/conversations/${ident}`).catch(() => null);
  if (!c) return;
  if (c.etat !== "en_cours") return dialogue(ident);
  const n = c.tours.length - 1;
  const tours = z.querySelectorAll(".dia-tour");
  tours[tours.length - 1]?.replaceWith(tourDialogue(c, c.tours[n], n));
  suiviDialogue = setTimeout(() => rafraichitDialogue(ident), 2000);
}

// La référence de la vue change avec la navigation : la case « ici » suit.
window.addEventListener("hashchange", () => {
  const z = document.getElementById("dialogue");
  if (!z || z.hidden) return;
  setTimeout(() => {
    const l = z.querySelector(".dia-ici-choix");
    if (!l) return;
    const r = refIci();
    l.hidden = !r;
    l.lastChild.textContent = " joindre ici : " + (r ?? "—");
    l.querySelector("input").checked = !!r;
  }, 300);
});

document.getElementById("b-claude").onclick = () => {
  const z = document.getElementById("dialogue");
  if (!z.hidden) return z.querySelector(".fermer").click();
  let id = etat.conversation;
  if (id === undefined) { try { id = sessionStorage.getItem("atelier-conversation") || null; } catch { id = null; } }
  dialogue(id);
};

// ------------------------------------------------------------------ le thème
// auto (celui du système, qui suit ses bascules) → clair → sombre ; retenu dans le navigateur.

const THEMES = { auto: ["◐", "Thème : celui du système"], clair: ["☀", "Thème : clair"], sombre: ["☾", "Thème : sombre"] };

function poseTheme(th) {
  document.documentElement.dataset.theme = th;
  const b = document.getElementById("b-theme");
  b.textContent = THEMES[th][0];
  b.title = THEMES[th][1] + " — clic : " + THEMES[{ auto: "clair", clair: "sombre", sombre: "auto" }[th]][1].toLowerCase();
}

poseTheme(THEMES[document.documentElement.dataset.theme] ? document.documentElement.dataset.theme : "auto");
document.getElementById("b-theme").onclick = () => {
  const th = { auto: "clair", clair: "sombre", sombre: "auto" }[document.documentElement.dataset.theme] ?? "auto";
  try { localStorage.setItem("atelier-theme", th); } catch { /* sans stockage : pour cette page seulement */ }
  poseTheme(th);
  retheme();
};
// le graphe des fiches lit ses couleurs au rendu : il se redessine quand le thème change
function retheme() { if (/graphe/.test(location.hash)) depuisAdresse(); }
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { if (document.documentElement.dataset.theme === "auto") retheme(); });

// ------------------------------------------------------------------ la consommation de Claude
// Le journal consommation.jsonl (une ligne par exécution), résumé sur une période.

const LIB_GENRES = { ...LIB_TYPES, conversation: "✦ conversation", confiance: "◐ confiance" };
const PERIODES_CONSO = [["tout", "tout"], ["7", "7 jours"], ["30", "30 jours"], ["mois", "ce mois"], ["date", "depuis le…"]];

function bornesConso(P) {
  const j = (n) => { const d = new Date(); d.setDate(d.getDate() - n + 1); return d.toLocaleDateString("sv"); };
  if (P.periode === "7" || P.periode === "30") return j(Number(P.periode));
  if (P.periode === "mois") return new Date().toLocaleDateString("sv").slice(0, 8) + "01";
  if (P.periode === "date") return P.depuis || "";
  return "";
}

async function sectionConsommation() {
  const P = etat.periodeConso ??= { periode: "tout", depuis: "" };
  const S = await api("/consommation?depuis=" + bornesConso(P)).catch(() => null);
  const s = el("section", "livre-bloc conso");
  const barre = el("div", "dem-filtres");
  const g = el("span", "groupe filtres");
  for (const [v, lib] of PERIODES_CONSO) {
    const b = el("button", P.periode === v ? "actif" : null, lib);
    b.onclick = () => { P.periode = v; accueil(); };
    g.append(b);
  }
  barre.append(g);
  if (P.periode === "date") {
    const d = el("input", "dem-date");
    d.type = "date";
    d.value = P.depuis;
    d.onchange = () => { P.depuis = d.value; accueil(); };
    barre.append(d);
  }
  const tel = el("a", "lien-ext", "consommation.jsonl ↓");
  tel.href = "/api/consommation/journal";
  tel.title = "le journal brut : une ligne JSON par exécution de Claude";
  barre.append(el("span", "espace"), tel);
  s.append(barre);
  if (!S || !S.lignes) {
    s.append(el("p", "mut", "Rien au journal pour cette période. Chaque demande, tour de conversation ou lecture de confiance y ajoute une ligne en finissant ; " +
      "« migrer/consommation.py » reconstitue le travail d'avant le journal."));
    return s;
  }
  const T = S.total;
  const usd = (x) => (x == null ? "—" : x < 0.1 ? x.toFixed(3) + " $" : x.toFixed(2) + " $");
  const duree = (x) => (x >= 3600 ? (x / 3600).toFixed(1) + " h" : x >= 60 ? Math.round(x / 60) + " min" : Math.round(x) + " s");
  const cartes = el("div", "conso-cartes");
  const carte = (val, lib, titre) => { const c = el("div", "conso-carte"); c.append(el("strong", null, val), el("span", "mut petit", lib)); if (titre) c.title = titre; cartes.append(c); };
  carte(usd(T.cout_usd), "au tarif API", "somme des coûts rapportés par Claude Code");
  carte(String(T.n), `exécutions${T.erreurs ? ` · ${T.erreurs} en erreur` : ""}`);
  carte(k(T.entree + T.cache_cree + T.cache_lu), "jetons en entrée", `neufs ${k(T.entree)} · cache créé ${k(T.cache_cree)} · cache relu ${k(T.cache_lu)}`);
  carte(k(T.sortie), "jetons en sortie");
  carte(T.cache_part == null ? "—" : T.cache_part + " %", "de l'entrée relue du cache", "relu du cache : facturé un dixième");
  carte(duree(T.duree_s), "de travail de Claude");
  carte(`${T.recherches} · ${T.pages}`, "recherches web · pages lues");
  s.append(cartes);
  s.append(el("p", "mut petit", `${S.lignes} lignes du ${(S.premiere ?? "").slice(0, 10)} au ${(S.derniere ?? "").slice(0, 10)}` +
    (S.reconstituees ? ` — dont ${S.reconstituees} reconstituées depuis les demandes (les reprises y sont cumulées)` : "")));
  // par jour : une barre par jour, la hauteur au coût
  if (S.jour.length > 1) {
    const max = Math.max(...S.jour.map((x) => x.cout_usd), 0.0001);
    const h = el("div", "conso-jours");
    for (const x of S.jour) {
      const c = el("div", "conso-jour");
      const b = el("div", "conso-barre");
      b.style.height = Math.max(2, (x.cout_usd / max) * 100) + "%";
      c.title = `${x.cle} : ${usd(x.cout_usd)} · ${x.n} exécution(s) · ↑${k(x.entree + x.cache_cree + x.cache_lu)} ↓${k(x.sortie)}`;
      c.append(b, el("span", "conso-date", x.cle.slice(5)));
      h.append(c);
    }
    s.append(el("h3", null, "Par jour"), h);
  }
  const table = (titre, rangs, lib = (c) => c) => {
    const tb = el("table", "conso-table");
    const th = el("tr");
    for (const x of ["", "n", "coût", "moyen", "entrée", "cache relu", "sortie", "durée", "web"]) th.append(el("th", null, x));
    tb.append(th);
    const max = Math.max(...rangs.map((x) => x.cout_usd), 0.0001);
    for (const x of rangs) {
      const tr = el("tr");
      const nom = el("td", "conso-nom");
      const barre = el("span", "conso-part");
      barre.style.width = (x.cout_usd / max) * 100 + "%";
      nom.append(barre, el("span", null, lib(x.cle)));
      tr.append(nom, el("td", null, x.n + (x.erreurs ? ` (${x.erreurs}✗)` : "")), el("td", null, usd(x.cout_usd)), el("td", "mut", usd(x.cout_moyen)),
        el("td", null, k(x.entree + x.cache_cree + x.cache_lu)), el("td", "mut", x.cache_part == null ? "—" : x.cache_part + " %"),
        el("td", null, k(x.sortie)), el("td", "mut", duree(x.duree_s)), el("td", "mut", x.recherches || x.pages ? `${x.recherches} · ${x.pages}` : ""));
      tb.append(tr);
    }
    s.append(el("h3", null, titre), tb);
  };
  const titreChap = (c) => etat.chapitres.find((x) => x.slug === c)?.title ?? c;
  const MODS = etat.modeles?.modeles ?? {};
  table("Par type de requête", S.genre, (c) => LIB_GENRES[c] ?? c);
  table("Par modèle", S.modele, (c) => MODS[c] ?? c);
  table("Par chapitre", S.chapitre, titreChap);
  table("Par phase", S.phase, (c) => ({ initiale: "première exécution", reprise: "reprise (réponse sans recherche)", encore: "chercher encore",
    tour: "tour de conversation", cumul: "reconstituée, reprises cumulées" }[c] ?? c));
  s.append(el("p", "mut petit", "Le journal se lit aussi hors de l'atelier : duckdb -c \"select genre, sum(cout_usd) from 'consommation.jsonl' group by 1\", " +
    "ou pandas.read_json('consommation.jsonl', lines=True)."));
  return s;
}

// ------------------------------------------------------------------ les exports PDF
// Le serveur imprime avec Chrome sans interface ; faute de Chrome, la version imprimable s'ouvre (⌘P).

function titrePdf(version) {
  return version === "essai"
    ? "tout l'essai en un PDF : page de garde, table des matières (le plan), chaque partie et ses chapitres — " +
      "le texte avec son statut (brouillon, en relecture, validé, harnais), le squelette, ou le synopsis seul ; bibliographie des œuvres citées"
    : "tout le récit en un PDF : page de garde, table des matières (le plan), chaque partie et ses chapitres — " +
      "le texte avec son statut (brouillon, en relecture, validé, harnais), le storyboard (plans et micro-récits), ou le synopsis seul";
}

function boutonsPdf(quoi, lib, nomDefaut, titre) {
  const pdf = el("button", "b-versions", lib);
  pdf.title = titre;
  pdf.onclick = async () => {
    pdf.disabled = true;
    pdf.textContent = "⎙ génération…";
    try {
      const r = await fetch(`/api/${quoi}/pdf`);
      if (!r.ok) {
        alert(((await r.json().catch(() => ({}))).detail ?? r.status) + "\n\nLa version imprimable va s'ouvrir : ⌘P, puis « Enregistrer au format PDF ».");
        window.open(`/api/${quoi}/imprimable`, "_blank");
        return;
      }
      const nom = decodeURIComponent((r.headers.get("Content-Disposition") ?? "").split("UTF-8''")[1] ?? nomDefaut);
      const a = el("a");
      a.href = URL.createObjectURL(await r.blob());
      a.download = nom;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    } finally {
      pdf.disabled = false;
      pdf.textContent = lib;
    }
  };
  const imp = el("a", "lien-ext", "imprimable ↗");
  imp.href = `/api/${quoi}/imprimable`;
  imp.target = "_blank";
  imp.title = "le même document, en HTML, dans un onglet";
  return [pdf, imp];
}


// ------------------------------------------------------------------ écrire l'essai
//
// Claude écrit l'essai d'un chapitre depuis son brief (synopsis, question, fiches ; squelette et verrou
// s'il est amorcé), les fiches et les chapitres déjà écrits — sans web. Ce qui manque, il le dit :
// une fiche à créer, une fiche à creuser. L'auteur pose le texte (ou le fait poser d'office).

function formRedaction(zone, { slug = null, partie = undefined } = {}) {
  const serie = slug == null;
  const f = el("div", "form-demande");
  const cons = el("textarea", "annot-texte petit-texte");
  cons.placeholder = "Précision (facultatif) : l'angle, ce qui compte, le ton, une référence (@fiche/…, @chapitre/…)…";
  const lon = el("select", "livre-select");
  for (const [v, lib] of [["courte", "courte (1 500–2 500 mots)"], ["moyenne", "moyenne (3 000–4 500 mots)"], ["longue", "longue (5 000–7 000 mots)"]]) {
    lon.append(new Option(lib, v, false, v === "moyenne"));
  }
  const mod = choixModele("redaction");
  const pl = el("label", "dem-consulter");
  const poser = el("input");
  poser.type = "checkbox";
  poser.checked = serie;
  pl.append(poser, serie ? " poser chaque chapitre d'office (le suivant lit le précédent ; on relit après)"
    : " poser d'office dans l'essai (sinon : relire, puis poser)");
  let sel = null;
  if (serie && partie === null) {
    sel = el("select", "livre-select");
    sel.append(new Option("tout le livre", ""));
    for (const p of etat.plan?.parties ?? []) sel.append(new Option(p.title, p.id));
  }
  const go = el("button", "bouton", serie ? "✎ écrire la série" : "✎ écrire");
  const err = el("span", "err petit");
  go.onclick = async () => {
    go.disabled = true;
    err.textContent = "";
    const corps = { consigne: cons.value, longueur: lon.value, modele: mod.valeur(), poser: poser.checked };
    try {
      if (serie) {
        const r = await poste("/redaction/serie", { ...corps, partie: partie ?? (sel?.value || null) });
        f.replaceChildren(el("p", "annot-corps", `Série lancée : ${r.chapitres.length} chapitre(s), l'un après l'autre — ${r.chapitres.join(", ")}.`));
        tiroir(r.demandes[0]);
      } else {
        const r = await poste("/redaction", { ...corps, chapitre: slug });
        f.remove();
        tiroir(r.id);
      }
    } catch (e) { err.textContent = String(e); go.disabled = false; }
  };
  const non = el("button", "pan-lien", "annuler");
  non.onclick = () => f.remove();
  const act = el("div", "annot-actions");
  act.append(go, non, err);
  const lieu = serie ? "Écrire l'essai des chapitres qui n'ont qu'un synopsis ou un brief, dans l'ordre du plan, l'un après l'autre"
    : "Écrire l'essai de ce chapitre";
  f.append(el("span", "appui-lieu", lieu + " — depuis les fiches et les chapitres déjà écrits, sans web ; ce qui manque est signalé"),
    ...(sel ? [sel] : []), cons, lon, mod.noeud, pl, act);
  zone.replaceChildren(f);
  f.scrollIntoView({ block: "center" });
}

function boutonEcrire(slug, classe = "b-versions") {
  const b = el("button", classe, "✎ écrire l'essai…");
  b.title = "Claude écrit l'essai de ce chapitre depuis son brief, ses fiches et les chapitres déjà écrits";
  b.onclick = () => formRedaction(document.querySelector("#page .actions-fiche") ?? document.getElementById("page"), { slug });
  return b;
}

function boutonSerie(partie) {
  const b = el("button", "b-versions", partie ? "✎ écrire la partie…" : "✎ écrire l'essai…");
  b.title = "Écrire l'essai de chaque chapitre qui n'a qu'un synopsis ou un brief, l'un après l'autre (une demande par chapitre)";
  b.onclick = () => formRedaction(document.querySelector("#page > .actions-fiche") ?? document.getElementById("page"), { partie });
  return b;
}

function banniereSquelette(slug) {
  const d = el("div", "banniere-squelette");
  const z = el("div", "actions-fiche");
  d.append(el("span", null, "Squelette : les sections prévues, pas encore le texte. "), boutonEcrire(slug, "pan-lien"), z);
  return d;
}

// Un chapitre sans texte dans cette version : ce qu'on sait déjà de lui, et de quoi l'écrire.
async function vueSansTexte(page, slug, vue) {
  const c = etat.chapitres.find((x) => x.slug === slug) ?? {};
  const P = await api("/plan").catch(() => null);
  const pc = P?.parties.flatMap((p) => p.chapitres).find((x) => x.slug === slug) ?? {};
  const niv = c.avancement?.[vue === "essai" ? "essai" : "recit"] ?? "vide";
  const t = el("div", "sans-texte");
  const st = el("span", "st av av-" + niv, LIB_AVANCEMENT[niv] ?? niv);
  st.title = TITRE_AVANCEMENT[niv] ?? "";
  t.append(el("h1", null, c.title ?? slug));
  if (c.periode) t.append(el("p", "periode", c.periode));
  const etatL = el("p", "mut petit");
  etatL.append(`${vue === "essai" ? "L'essai" : "Le récit"} n'est pas encore écrit · `, st);
  t.append(etatL, el("hr"));
  if (pc.synopsis) { t.append(el("h3", "sans-texte-titre", "Synopsis")); t.append(el("p", "sans-texte-synopsis", pc.synopsis)); }
  if (pc.question) { t.append(el("h3", "sans-texte-titre", "Question")); t.append(el("p", "sans-texte-question", pc.question)); }
  if (pc.fiches?.length) {
    t.append(el("h3", "sans-texte-titre", "Fiches"));
    const f = el("div", "pastilles");
    f.append(...pc.fiches.map((x) => puceFiche(x)));
    t.append(f);
  }
  if (!pc.synopsis && !pc.question) t.append(el("p", "mut", "Ni synopsis ni question pour l'instant : le développer d'abord dans le plan."));
  const act = el("div", "annot-actions");
  const z = el("div", "actions-fiche");
  if (vue === "essai" && ["synopsis", "brief"].includes(niv)) act.append(boutonEcrire(slug, "bouton"));
  const plan = el("a", "pan-lien", "✦ le chapitre dans le plan (synopsis, fiches, amorcer)");
  plan.href = `#plan/c/${slug}`;
  act.append(plan);
  t.append(act, z);
  page.replaceChildren(t);
  const ds = (await api("/fiches/demandes").catch(() => [])).filter((x) => x.type === "redaction" && x.chapitre === slug
    && ["en_cours", "en_attente", "prete", "erreur"].includes(x.etat));
  for (const x of ds) {
    const b = el("button", "banniere-pistes", `✎ ${x.titre} — ${etiquetteDemande(x)} → ouvrir`);
    b.onclick = () => tiroir(x.id);
    act.after(b);
  }
}

async function tiroirRedaction(t, d) {
  const slug = d.cible.chapitre;
  t.replaceChildren(teteTiroir(d.titre ?? "Rédaction", () => historique(t, "fiches")));
  const cible = el("div", "dem-cible");
  const a = el("a", null, `@chapitre/${slug}`);
  a.href = `#plan/c/${slug}`;
  const l = el("p", "mut petit");
  l.append(a, ` · depuis : ${LIB_AVANCEMENT[d.cible.niveau] ?? d.cible.niveau} · longueur ${d.longueur}` +
    (d.poser ? " · posé d'office" : "") + (d.serie ? ` · ${d.serie}` : ""));
  cible.append(l);
  if (d.consigne) cible.append(el("p", "annot-corps", "« " + d.consigne + " »"));
  t.append(cible);
  if (d.etat === "en_attente") {
    t.append(el("p", "dem-attente", d.serie ? "En attente : la série la lance quand la précédente a fini." : "En attente."));
    return piedTiroir(t, d);
  }
  if (d.etat === "en_cours") {
    t.append(enDirect(d));
    suivi = setTimeout(() => rafraichitDirect(d.id), 2000);
    return piedTiroir(t, d);
  }
  if (d.etat === "erreur") { t.append(el("p", "annot-orph-titre", "Échec : " + d.erreur)); return piedTiroir(t, d); }
  const R = d.resultat ?? {};
  const bilan = el("p", "mut petit", `${R.mots ?? "?"} mots · ${R.sections?.length ?? 0} sections · ${R.citations?.length ?? 0} source(s) citée(s)` +
    ` · fiches lues : ${(R.fiches_lues ?? []).join(", ") || "—"}`);
  t.append(bilan);
  if (R.citations_inconnues?.length) t.append(el("p", "err petit", "Clés citées absentes de la bibliographie : " + R.citations_inconnues.join(", ")));
  if (R.notes_orphelines?.length) t.append(el("p", "err petit", "Notes appelées sans définition (ou l'inverse) : " + R.notes_orphelines.join(", ")));
  if (d.erreur_pose) t.append(el("p", "err", "Pas posé d'office : " + d.erreur_pose));
  if (R.remarques) t.append(el("p", "annot-corps", R.remarques));
  // ce qui manque : de quoi le chercher
  if (R.manques?.length) {
    t.append(el("h5", null, "Ce qui manque aux fiches"));
    for (const m of R.manques) {
      const b = el("div", "piste piste-nouvelle");
      b.append(el("p", "annot-corps", `${m.type === "creuser" ? "◇ creuser " + (m.fiche ?? "") + " — " : "✚ "}${m.question}`));
      if (m.pourquoi) b.append(el("p", "mut petit", m.pourquoi + (m.section ? ` (section : ${m.section})` : "")));
      const go = el("button", "pan-lien", m.type === "creuser" && m.fiche ? "◇ creuser la fiche" : "✚ créer la fiche");
      go.onclick = async () => {
        go.disabled = true;
        try {
          const r = m.type === "creuser" && m.fiche
            ? await poste(`/fiches/${m.fiche}/pistes`, { consigne: m.question })
            : await poste("/fiches/demandes", { question: m.question, chapitres: [slug], consigne: m.pourquoi ?? "" });
          go.replaceWith(Object.assign(el("a", "pan-lien", "lancée → ouvrir"), { href: "#", onclick: (e) => { e.preventDefault(); tiroir(r.id); } }));
        } catch (e) { go.disabled = false; alert(e); }
      };
      b.append(go);
      t.append(b);
    }
  }
  // décider
  if (d.etat === "prete") {
    const act = el("div", "annot-actions");
    const ok = el("button", "bouton", "✓ poser dans l'essai");
    ok.title = "écrit chapters/" + slug + "/essai.md (le squelette est remplacé) ; le chapitre passe en brouillon";
    const non = el("button", "pan-lien", "✕ rejeter");
    const decide = async (corps, b) => {
      b.disabled = true;
      const r = await fetch(`/api/chapitres/_kb/demandes/${d.id}/decision`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps) });
      if (!r.ok) { b.disabled = false; alert((await r.json().catch(() => ({}))).detail ?? r.status); return; }
      etat.chapitres = await api("/chapitres").catch(() => etat.chapitres);
      sommaire();
      tiroir(d.id);
    };
    ok.onclick = () => decide({ action: "retenir" }, ok);
    non.onclick = () => decide({ action: "rejeter" }, non);
    act.append(ok, non);
    t.append(act);
  } else if (d.decision?.proposition === "posee") {
    const p = el("p", "annot-corps");
    const lire = el("a", null, "lire l'essai →");
    lire.href = `#${slug}/essai/texte`;
    p.append(`Posé dans l'essai${d.decision.d_office ? " (d'office)" : ""} le ${(d.decision.date ?? "").slice(0, 10)}. `, lire);
    t.append(p);
  } else if (d.etat === "decidee") t.append(el("p", "mut", "Rejeté."));
  // le texte proposé
  if (R.html) {
    const det = el("details", "apercu-essai-det");
    det.open = d.etat === "prete";
    det.append(el("summary", null, "le texte proposé"));
    const ap = el("div", "apercu-essai");
    ap.innerHTML = R.html;
    det.append(ap);
    t.append(det);
  }
  return piedTiroir(t, d);
}
