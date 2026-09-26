// Le front de l'atelier : sommaire (structure.yaml), lecture d'un chapitre, et —
// pour un chapitre migré — la fiche de chaque bloc : son plan, son micro-récit,
// les assertions du verrou qu'il porte.
// Pas de build : modules ES servis tels quels par le serveur.

const etat = { version: "recit", slug: null, chapitres: [], atelier: null, bloc: null, blocEssai: null, survol: null, essai: null,
  garde: null, defil: {}, docs: {}, sources: {},
  essaiMode: "texte", noteChoisie: null, noteFocus: null, sourceChoisie: null };

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
  const pres = el("a", "lien-livre" + (etat.accueil ? " actif" : ""), "Le livre");
  pres.href = "#livre";
  nav.append(pres);
  let partie;
  for (const c of etat.chapitres) {
    if (c.partie !== partie) {
      partie = c.partie;
      nav.append(el("h3", null, c.partie_titre ?? "Ouverture"));
    }
    const a = el("a");
    a.href = `#${c.slug}/${etat.version}${etat.version === "essai" ? "/" + etat.essaiMode : ""}`;
    a.dataset.slug = c.slug;
    a.append(el("span", "n", c.numero ?? "—"), el("span", null, c.title),
      el("span", "st", c.atelier ? "atelier" : c.status === "revised" ? "cadre" : ""));
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
    Object.assign(etat, { bloc: null, blocEssai: null, essai: null, garde: null, defil: {}, docs: {},
      noteChoisie: null, noteFocus: null, sourceChoisie: null });
  }
  etat.slug = slug;
  const vue = etat.version;
  const sel = vue === "essai" ? etat.blocEssai : etat.bloc;
  document.body.dataset.vue = vue;
  document.body.dataset.essai = etat.essaiMode;
  delete document.body.dataset.panneau;
  sommaire();
  const page = document.getElementById("page");
  const c = etat.chapitres.find((x) => x.slug === slug);
  etat.atelier = c?.atelier ? await api(`/chapitres/${slug}/atelier`).catch(() => null) : null;
  if (etat.atelier) await chargeDocs(slug);

  if (vue === "storyboard" && etat.garde?.slug === slug) {        // retour : on remet tout
    const g = etat.garde;
    page.replaceChildren(...g.page);
    document.getElementById("fiche").replaceChildren(...g.fiche);
    if (g.panneau) document.body.dataset.panneau = g.panneau;
    if (sel && sel !== g.bloc) choisis(sel, true);                // choisi ailleurs entre-temps
    else window.scrollTo(0, g.scroll);
    return;
  }

  if (vue === "storyboard") {
    await storyboard(page);
  } else {
    try {
      const t = await api(`/chapitres/${slug}/${vue}`);
      page.innerHTML = t.html;
      page.append(el("p", "origine", t.origine));
      enrichit(page);
    } catch {
      page.replaceChildren(el("p", "mut", `Pas de version « ${vue} » pour ce chapitre.`));
    }
    marges();
    if (vue === "essai") {
      page.querySelectorAll("h2").forEach((h) => {             // le titre de la liste de notes
        if (h.textContent.trim() === "Notes") h.classList.add("titre-notes");
      });
      if (etat.essaiMode === "notes") return vueNotes(page);
      if (etat.essaiMode === "biblio") return vueBiblio(page);
    }
  }
  fiche();
  const d = etat.defil[cleVue()];
  if (sel && document.querySelector(`#page [data-block="${sel}"]`)) {
    const memeSel = d && d.bloc === sel;
    const focus = etat.noteFocus;
    etat.noteFocus = null;
    choisis(sel, !memeSel && !focus, focus);
    if (focus) document.querySelector(`#page [data-block="${sel}"]`).scrollIntoView({ block: "center" });
    else if (memeSel) window.scrollTo(0, d.scroll);
    return;
  }
  window.scrollTo(0, d ? d.scroll : 0);
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
  else window.scrollTo(0, etat.defil[cleVue()]?.scroll ?? 0);
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
  else window.scrollTo(0, etat.defil[cleVue()]?.scroll ?? 0);
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
  etat.defil[cleVue()] = { scroll: window.scrollY, bloc: sel };
  if (vue === "storyboard") {
    etat.garde = {
      slug: etat.slug, scroll: window.scrollY, bloc: etat.bloc,
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
  const np = e.target.closest(".note-pleine");
  if (np && !e.target.closest("a")) { choisisNote(np.dataset.note); return; }
  const pl = e.target.closest("[data-plan-titre]");
  if (pl) { panneauPlan(pl.dataset.planTitre); return; }
  const pu = e.target.closest("[data-assertion]");
  if (pu) panneauAssertion(pu.dataset.assertion);
  const b = e.target.closest("[data-block]");
  if (!b || e.target.closest("a, button")) return;
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
      d.append(el("span", "sb-rang", String(i + 1)),
        el("span", "sb-recit", recits[i] ?? "— (pas de micro-récit)"));
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

  f.append(el("h5", null, "Dans le récit"));
  f.append(...appuisRecit(id));
  f.append(el("h5", null, "Dans l'essai"));
  f.append(...appuisEssai(id));
}

async function panneauPlan(pid) {
  const a = etat.atelier;
  const b = (a.brief.beats ?? []).find((x) => x.id === pid);
  if (!b) return;
  marque(`#page [data-plan-titre="${pid}"]`);
  const f = panneau(`Plan ${b.id} — ${b.title}`);
  for (const k of ["lieu", "temps", "ambiance", "attaque", "chute"]) if (b[k]) champ(f, k, b[k]);
  const ids = parPlan()[pid] ?? [];
  const ajouts = ids.filter((i) => a.links.recit[i].ajout).length;
  champ(f, "comptes", `${b.recits?.length ?? 0} micro-récits · ${ids.length} paragraphes · ` +
    `ajouts ${ajouts}/${b.ajouts ?? 0}`);
  if (b.sequence?.length) champ(f, "séquence déclarée", b.sequence.join("  /  "));
  if (b.note) champ(f, "note", b.note);

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
}

document.getElementById("fiche").addEventListener("click", (e) => {
  const d = e.target.closest("[data-assertion]");
  if (d) panneauAssertion(d.dataset.assertion);
});

// ------------------------------------------------------------------ fiche

function fiche(id) {
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

async function accueil() {
  document.body.dataset.vue = "livre";
  delete document.body.dataset.panneau;
  etat.livre = await api("/livre").catch(() => etat.livre);
  afficheTitre();
  sommaire();
  const L = etat.livre;
  const page = document.getElementById("page");
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
      a.href = `#${c.slug}/recit`;
      const li = el("li");
      li.append(a);
      ol.append(li);
    }
    col.append(ol);
    grille.append(col);
  }
  if (!parties.length) grille.append(el("p", "mut", "Aucun chapitre : structure.yaml est vide."));
  st.append(grille);

  page.replaceChildren(tete, corps, versions, st);
  page.querySelectorAll("textarea").forEach(ajuste);
  colonneLivre();
  window.scrollTo(0, 0);
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
  for (const nom of ["livre.yaml", "structure.yaml"]) {
    const d = el("div", "fichier-ligne");
    d.append(el("code", null, nom));
    const ouvrir = el("button", "pan-lien", "ouvrir");
    ouvrir.title = "Ouvrir dans l'application par défaut du poste";
    ouvrir.onclick = () => fetch(`/api/ouvrir?chemin=${encodeURIComponent(nom)}`, { method: "POST" });
    const vs = el("a", "lien-ext", "VS Code ↗");
    vs.href = "vscode://file" + (etat.livre.chemins?.[nom] ?? "");
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

// ------------------------------------------------------------------ bascules

document.getElementById("modes-essai").addEventListener("click", (e) => {
  const m = e.target.dataset.m;
  if (m && etat.slug) location.hash = `${etat.slug}/essai/${m}`;
});

document.getElementById("versions").addEventListener("click", (e) => {
  if (e.target.dataset.v) bascule(e.target.dataset.v);
});

// L'adresse porte le chapitre et la vue : #la-mer/storyboard. Recharger garde la vue.
const VUES = ["recit", "essai", "storyboard"];

const MODES_ESSAI = ["texte", "notes", "biblio"];

function bascule(v) {
  const suite = v === "essai" ? "/" + etat.essaiMode : "";
  if (etat.slug) location.hash = `${etat.slug}/${v}${suite}`;   // -> hashchange -> depuisAdresse
  else { etat.version = v; boutons(); sommaire(); }
}

function boutons() {
  document.querySelectorAll("#versions button[data-v]").forEach((b) =>
    b.classList.toggle("actif", b.dataset.v === etat.version));
  document.querySelectorAll("#modes-essai button").forEach((b) =>
    b.classList.toggle("actif", b.dataset.m === etat.essaiMode));
}

function depuisAdresse() {
  quitte();
  const [slug, vue, mode] = decodeURIComponent(location.hash.slice(1)).split("/");
  if (slug.startsWith("fn")) return;
  if (!slug || slug === "livre") { etat.accueil = true; return accueil(); }
  etat.accueil = false;
  if (VUES.includes(vue)) etat.version = vue;
  if (vue === "essai" && MODES_ESSAI.includes(mode)) etat.essaiMode = mode;
  boutons();
  ouvre(slug);
}

window.addEventListener("hashchange", depuisAdresse);

etat.livre = await api("/livre").catch(() => ({ titre: "" }));
afficheTitre();
document.getElementById("titre-livre").onclick = () => { location.hash = "livre"; };
etat.chapitres = await api("/chapitres");
api("/sources").then((s) => { etat.sources = s; }).catch(() => {});
sommaire();
fiche();
depuisAdresse();
