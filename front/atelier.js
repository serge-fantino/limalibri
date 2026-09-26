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
    a.append(el("span", "n", c.numero ?? "—"), el("span", null, c.title),
      el("span", "st", c.atelier ? "atelier" : c.status === "revised" ? "cadre" : ""));
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
    if (c.atelier) a.lastChild.classList.add("migre");
    const dispo = etat.version === "storyboard" ? c.atelier : c.versions.includes(etat.version);
    if (!dispo) a.classList.add("mut");
    if (c.slug === etat.slug) a.classList.add("actif");
    nav.append(a);
  }
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
      page.replaceChildren(el("p", "mut", `Pas de version « ${vue} » pour ce chapitre.`));
    }
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
    li.append(el("span", "note-cle", n.cle + (n.appels.length ? "" : " · non appelée")));
    liste.append(li);
  }
  page.replaceChildren(el("h1", null, c?.title ?? etat.slug),
    el("p", "sous", `Notes de l'essai · ${notes.length}`), liste);
  page._notes = notes;
  document.getElementById("fiche").replaceChildren(
    el("p", "mut", "Choisir une note : le texte qui l'appelle s'affiche en marge."));
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
  } else if (v === "essai") {
    const g = el("span", "groupe");
    for (const [m, lib] of [["texte", "texte"], ["notes", "notes"], ["biblio", "bibliographie"]]) {
      g.append(bouton(lib, etat.essaiMode === m, () => { location.hash = `${etat.slug}/essai/${m}`; }));
    }
    o.append(g);
    o.append(el("span", "espace"));
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
    f.append(el("p", "mut petit",
      `${Object.keys(a.assertions).length} assertions · ${br.beats?.length ?? 0} plans · ` +
      (etat.version === "storyboard" ? "cliquer un micro-récit" : "cliquer un paragraphe") +
      " pour sa fiche."));
    return;
  }
  const version = etat.version === "storyboard" ? "recit" : etat.version;
  const l = a.links?.[version]?.[id];
  f.append(el("h4", null, "Bloc ^" + id));
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
  tete.append(el("span", "appui-lieu", "annotations · ^" + bloc), x);
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
  tete.append(el("span", "annot-date", `${a.auteur ?? ""} · ${(a.modifie ?? a.cree ?? "").slice(0, 10)}`));
  d.append(tete);
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

const ETIQ_DEM = { en_cours: "en cours", prete: "à décider", erreur: "erreur", remplacee: "remplacée" };

function avise(d) {
  const a = el("button", "avis", `${d.type === "verification" ? "🔎 Vérification" : "↻ Réécriture"} ${d.etat === "prete" ? "prête" : d.etat} — ${(d.titre ?? "").slice(0, 60)} · ouvrir`);
  a.onclick = () => { a.remove(); tiroir(d.id); };
  document.body.append(a);
  setTimeout(() => a.remove(), 15000);
}
function etiquetteDemande(d) {
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
async function tiroir(ident) {
  clearTimeout(suivi);
  const t = document.getElementById("tiroir");
  t.hidden = false;
  document.body.dataset.tiroir = "1";
  if (!etat.slug || !etat.atelier) {
    t.replaceChildren(teteTiroir("Réécritures"), el("p", "mut", "Ouvrir un chapitre de l'atelier."));
    return;
  }
  if (!ident) return historique(t);
  const d = await api(`/chapitres/${etat.slug}/demandes/${ident}`);
  if (d.type === "verification") return tiroirVerif(t, d);
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
  const verbe = d.type === "verification" ? "Claude cherche" : "Claude travaille";
  const je = d.jetons_en_cours;
  z.replaceChildren(el("p", "dem-attente", `${verbe}… ${Math.floor(depuis / 60)} min ${String(depuis % 60).padStart(2, "0")} s`
    + ` · ${(d.deroule ?? []).filter((x) => x.type === "outil").length} étapes`
    + ` · ${nomModele(d.modele_en_cours ?? d.modele_choisi ?? etat.modeles?.defaut?.[d.type === "verification" ? "verification" : "reecriture"])}`
    + (je ? ` · ↑ ${k((je.entree ?? 0) + (je.cache_cree ?? 0) + (je.cache_lu ?? 0))} (${partCache(je)} % du cache) ↓ ${k(je.sortie ?? 0)} jetons` : "")
    + (d.budget?.limites?.recherches ? ` · ${d.budget.recherches}/${d.budget.limites.recherches} recherches, ${d.budget.pages}/${d.budget.limites.pages} pages` : "")));
  const ol = el("ol", "deroule");
  for (const e of (d.deroule ?? []).slice(-10)) ol.append(ligneDeroule(e));
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
    li.append(el("span", "der-icone", { echec: "⚠", pensee: "💭", limite: "⛔", reprise: "⏵" }[e.type] ?? "✎"),
      el("span", "der-detail", e.texte));
  }
  return li;
}

async function rafraichitDirect(ident) {
  const t = document.getElementById("tiroir");
  if (t.hidden) return;
  const d = await api(`/chapitres/${etat.slug}/demandes/${ident}`).catch(() => null);
  const z = document.getElementById("dem-direct");
  if (!d || d.etat !== "en_cours" || !z) return tiroir(ident);      // fini (ou autre tiroir) : tout redessiner
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
  det.append(el("summary", null, `le déroulé de Claude (${n} étapes : recherches, lectures, réflexions)`));
  const ol = el("ol", "deroule complet");
  for (const e of d.deroule) ol.append(ligneDeroule(e));
  det.append(ol);
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
  const dc = d.etat !== "en_cours" && derouleComplet(d);
  if (dc) t.append(dc);
  // reprendre : la session est gardée ; Claude y retrouve ce qu'il a lu et rend sa réponse
  const finir = d.etat === "erreur";
  const chercher = d.type === "verification" && (d.etat === "erreur" || d.etat === "prete");
  if (d.session_id && !d.remplacee_par && (finir || chercher)) {
    const bloc = el("div", "relance reprise");
    const act = el("div", "annot-actions");
    const envoie = async (b, quoi, corps) => {
      b.disabled = true;
      const r = await fetch(`/api/chapitres/${etat.slug}/demandes/${d.id}/${quoi}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps ?? {}) });
      if (!r.ok) { b.disabled = false; alert((await r.json().catch(() => ({}))).detail ?? r.status); return; }
      await chargeDemandes();
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
      const mod = choixModele(d.type === "verification" ? "verification" : "reecriture", d.modele_choisi ?? "");
      const go = el("button", "bouton", "↻ relancer");
      go.onclick = async () => {
        go.disabled = true;
        const r = await fetch(`/api/chapitres/${etat.slug}/demandes/${d.id}/relance`, {
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
    r.onclick = retour;
    h.append(r);
  }
  const x = el("button", "fermer", "×");
  x.onclick = () => { clearTimeout(suivi); document.getElementById("tiroir").hidden = true; delete document.body.dataset.tiroir; };
  h.append(el("h4", null, titre), x);
  return h;
}

const OUVERTES = new Set(["en_cours", "prete"]);

async function historique(t) {
  const F = etat.filtresDem ??= { portee: "chapitre", type: "tout", statut: "tout" };
  const ds = F.portee === "livre" ? await api("/demandes").catch(() => [])
    : (await api(`/chapitres/${etat.slug}/demandes`).catch(() => [])).map((d) => ({ ...d, chapitre: etat.slug }));
  t.replaceChildren(teteTiroir(F.portee === "livre" ? "Demandes du livre" : "Demandes du chapitre"));
  const filtre = (cle, options) => {
    const g = el("span", "groupe filtres");
    for (const [v, lib] of options) {
      const b = el("button", F[cle] === v ? "actif" : null, lib);
      b.onclick = () => { F[cle] = v; historique(t); };
      g.append(b);
    }
    return g;
  };
  const barre = el("div", "dem-filtres");
  barre.append(filtre("portee", [["chapitre", "ce chapitre"], ["livre", "tout le livre"]]),
    filtre("type", [["tout", "tout"], ["reecriture", "réécritures"], ["verification", "recherches"]]),
    filtre("statut", [["tout", "tout"], ["ouvertes", "ouvertes"], ["closes", "closes"]]));
  t.append(barre);
  const garde = ds.filter((d) => (F.type === "tout" || (d.type ?? "reecriture") === F.type)
    && (F.statut === "tout" || (F.statut === "ouvertes") === OUVERTES.has(d.etat)));
  if (!garde.length) {
    t.append(el("p", "mut", ds.length ? "Aucune demande pour ces filtres." :
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
  const totaux = [];
  if (tot.n) totaux.push(`jetons (${tot.n} demande${tot.n > 1 ? "s" : ""}) : ↑ ${k(tot.e)} en entrée · ↓ ${k(tot.s)} en sortie`);
  if (tot.nc) totaux.push(`≈ ${tot.c.toFixed(2)} $ au tarif API (${tot.nc} demande${tot.nc > 1 ? "s" : ""})`);
  if (totaux.length) t.append(el("p", "mut petit", "Total — " + totaux.join(" ; ")));
  // classement par chapitre, dans l'ordre du livre ; dans un chapitre, les plus récentes d'abord
  const parChap = new Map();
  for (const d of garde) {
    if (!parChap.has(d.chapitre)) parChap.set(d.chapitre, []);
    parChap.get(d.chapitre).push(d);
  }
  const ordre = etat.chapitres.map((c) => c.slug);
  for (const slug of [...parChap.keys()].sort((a, b) => ordre.indexOf(a) - ordre.indexOf(b))) {
    const c = etat.chapitres.find((x) => x.slug === slug);
    const liste = parChap.get(slug);
    const ouvertes = liste.filter((d) => OUVERTES.has(d.etat)).length;
    t.append(el("h5", "dem-chapitre", `${c?.numero ?? ""} · ${c?.title ?? slug} — ${liste.length} demande(s)${ouvertes ? `, ${ouvertes} ouverte(s)` : ""}`));
    for (const d of liste) {
      const l = el("button", "dem-ligne " + (OUVERTES.has(d.etat) ? "ouverte" : "close"));
      const haut = el("span", "dem-haut");
      haut.append(el("span", "annot-type", d.type === "verification" ? "🔎 recherche" : "↻ réécriture"),
        el("span", "dem-etat " + d.etat, etiquetteDemande(d)), el("span", "annot-date", d.cree.slice(0, 16).replace("T", " ")));
      l.append(haut, el("span", "dem-titre-ligne", d.titre ?? ""));
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
  if (slug === etat.slug) return tiroir(id);
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
function ongletsLivre() {
  const o = el("nav", "livre-onglets");
  const onglet = (texte, actif, hash) => {
    const a = el("a", actif ? "actif" : null, texte);
    a.href = "#" + hash;
    o.append(a);
  };
  onglet("Présentation", etat.ongletLivre !== "regles", "livre");
  for (const v of Object.keys(etat.regles ?? {})) {
    const n = etat.regles[v].elements.filter((e) => e.type === "regle").length;
    onglet(`Garde-fous · ${etat.livre.versions?.[v]?.titre ?? v} (${n})`,
      etat.ongletLivre === "regles" && etat.reglesVue === v, `livre/regles/${v}`);
  }
  return o;
}

async function accueil() {
  document.body.dataset.vue = "livre";
  document.getElementById("outils").hidden = true;
  document.getElementById("volet-chapitre").hidden = true;
  delete document.body.dataset.panneau;
  etat.livre = await api("/livre").catch(() => etat.livre);
  afficheTitre();
  sommaire();
  const L = etat.livre;
  const page = document.getElementById("page");
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
  const cl = sectionClaude(L);

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

  page.replaceChildren(ongletsLivre(), tete, corps, versions, cl, st);
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
  s.append(el("h3", null, "Claude"), el("p", "mut petit",
    "Le modèle et le budget de chaque demande (livre.yaml, section « claude »). Un modèle moins cher convient souvent " +
    "à une retouche ; la vérification demande du jugement sur les sources. Chaque demande peut choisir le sien."));
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
  const LIB = { verification: "Vérification", reecriture: "Réécriture" };
  const CH = { tours: "tours", recherches: "recherches web", pages: "pages lues" };
  for (const g of ["verification", "reecriture"]) {
    const G = C[g] ?? {};
    const lim = etat.modeles?.limites?.[g] ?? {};
    const box = el("div", "claude-genre");
    box.append(el("strong", null, LIB[g]),
      selModele(G.modele, "comme le livre", (v) => apres({ [g]: { modele: v } })));
    for (const cle of g === "verification" ? ["tours", "recherches", "pages"] : ["tours"]) {
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
  h.append(el("span", "regle-id", e.id), el("span", "regle-titre", e.titre));
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
  document.querySelector(".livre-onglets")?.replaceWith(ongletsLivre());
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
}

function depuisAdresse() {
  quitte();
  const [slug, vue, mode] = decodeURIComponent(location.hash.slice(1)).split("/");
  if (slug.startsWith("fn")) return;
  if (!slug || slug === "livre") {
    etat.accueil = true;
    etat.ongletLivre = vue === "regles" ? "regles" : "presentation";
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

window.addEventListener("hashchange", depuisAdresse);

etat.livre = await api("/livre").catch(() => ({ titre: "" }));
afficheTitre();
document.getElementById("titre-livre").onclick = () => { location.hash = "livre"; };
document.getElementById("b-demandes").onclick = () => tiroir(null);
document.getElementById("b-annotations").onclick = () => tiroirAnnotations();
etat.chapitres = await api("/chapitres");
api("/sources").then((s) => { etat.sources = s; }).catch(() => {});
etat.regles = await api("/regles").catch(() => ({}));
await chargeModeles();
majCompteAnnotations();
sommaire();
fiche();
depuisAdresse();
