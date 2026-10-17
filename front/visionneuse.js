// La visionneuse des planches : un clic sur une planche l'ouvre par-dessus la page, pour zoomer et la parcourir,
// et passer en plein écran. Un seul fichier, sans dépendance, partagé par LimaLibri (front/index.html) et le site
// public (copié à sa racine) : il s'accroche aux liens « a.planche-lien » des figures (planches.py).
//
//   molette, pincement, + −     zoomer (autour du pointeur)          glisser       déplacer
//   double-clic                  ajuster ⇄ zoom ×2 à cet endroit      0             ajuster
//   f                            plein écran                          Échap         fermer
//
// Le zoom change la taille de l'image, pas une transformation : le SVG est redessiné net à chaque échelle.
(function () {
  "use strict";
  if (window.Visionneuse) return;

  var CSS = [
    ".vis{position:fixed;inset:0;z-index:2147483000;background:rgba(18,16,13,.94);color:#eee8dc;display:flex;flex-direction:column;",
    "font-family:system-ui,-apple-system,'Segoe UI',sans-serif;font-size:14px;touch-action:none;user-select:none;-webkit-user-select:none}",
    ".vis-barre{display:flex;align-items:center;gap:.35rem;padding:.5rem .75rem;flex-wrap:wrap}",
    ".vis-titre{flex:1;min-width:8rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:600}",
    ".vis button,.vis a.vis-b{background:rgba(255,255,255,.08);color:inherit;border:1px solid rgba(255,255,255,.18);border-radius:6px;",
    "padding:.3rem .6rem;font:inherit;cursor:pointer;text-decoration:none;line-height:1.2}",
    ".vis button:hover,.vis a.vis-b:hover{background:rgba(255,255,255,.18)}",
    ".vis-niv{min-width:3.6rem;text-align:center;font-variant-numeric:tabular-nums;opacity:.8}",
    ".vis-scene{position:relative;flex:1;overflow:hidden;cursor:grab}",
    ".vis-scene.tire{cursor:grabbing}",
    ".vis-scene img{position:absolute;left:0;top:0;max-width:none;max-height:none;background:#fffdf8;border-radius:4px;",
    "box-shadow:0 6px 30px rgba(0,0,0,.5);-webkit-user-drag:none;user-select:none}",
    ".vis-legende{padding:.5rem 1rem .8rem;max-height:22vh;overflow:auto;line-height:1.45;opacity:.9;font-size:13px}",
    ".vis-legende:empty{display:none}",
    "@media (max-width:600px){.vis-b-lib{display:none}.vis-legende{font-size:12px}}"
  ].join("");

  var etat = null;                 // la visionneuse ouverte : {racine, scene, img, n, x, y, ajuste, retour}

  function noeud(tag, cls, txt) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (txt != null) e.textContent = txt;
    return e;
  }

  function pleinEcranPossible() {
    var d = document.documentElement;
    return !!(d.requestFullscreen || d.webkitRequestFullscreen);
  }
  function pleinEcran() { return document.fullscreenElement || document.webkitFullscreenElement; }
  function basculePleinEcran() {
    if (!etat) return;
    if (pleinEcran()) (document.exitFullscreen || document.webkitExitFullscreen).call(document);
    else (etat.racine.requestFullscreen || etat.racine.webkitRequestFullscreen).call(etat.racine);
  }

  // la taille naturelle de l'image (un SVG sans dimensions : sa largeur affichée de référence, 800)
  function naturel() {
    var i = etat.img;
    if (i.naturalWidth && i.naturalHeight) return { l: i.naturalWidth, h: i.naturalHeight };
    if (!etat.mesure) {                     // sans dimensions : 800 de large, la hauteur de ses proportions
      i.style.width = "800px"; i.style.height = "auto";
      etat.mesure = { l: 800, h: i.getBoundingClientRect().height || 600 };
    }
    return etat.mesure;
  }

  function pose() {
    var N = naturel(), i = etat.img;
    i.style.width = N.l * etat.n + "px";
    i.style.height = N.h * etat.n + "px";
    i.style.left = etat.x + "px";
    i.style.top = etat.y + "px";
    etat.niv.textContent = Math.round(etat.n * 100) + " %";
  }

  function ajuste() {
    var N = naturel(), S = etat.scene.getBoundingClientRect(), m = 16;
    etat.n = Math.max(0.05, Math.min((S.width - 2 * m) / N.l, (S.height - 2 * m) / N.h));
    etat.x = (S.width - N.l * etat.n) / 2;
    etat.y = (S.height - N.h * etat.n) / 2;
    etat.ajuste = true;
    pose();
  }

  // zoomer d'un facteur f autour du point (px, py) de la scène
  function zoome(f, px, py) {
    var S = etat.scene.getBoundingClientRect();
    if (px == null) { px = S.width / 2; py = S.height / 2; }
    var n = Math.max(0.05, Math.min(12, etat.n * f));
    f = n / etat.n;
    etat.x = px - (px - etat.x) * f;
    etat.y = py - (py - etat.y) * f;
    etat.n = n;
    etat.ajuste = false;
    pose();
  }

  function ferme() {
    if (!etat) return;
    if (pleinEcran()) try { (document.exitFullscreen || document.webkitExitFullscreen).call(document); } catch (e) {}
    etat.racine.remove();
    document.removeEventListener("keydown", clavier, true);
    window.removeEventListener("resize", surRedim);
    document.removeEventListener("fullscreenchange", surRedim);
    document.removeEventListener("webkitfullscreenchange", surRedim);
    document.documentElement.style.overflow = etat.debord;
    var r = etat.retour;
    etat = null;
    if (r && r.focus) try { r.focus({ preventScroll: true }); } catch (e) {}
  }

  function clavier(e) {
    if (!etat) return;
    var k = e.key;
    if (k === "Escape") { if (!pleinEcran()) ferme(); }
    else if (k === "+" || k === "=") zoome(1.25);
    else if (k === "-" || k === "_") zoome(0.8);
    else if (k === "0") ajuste();
    else if (k === "f" || k === "F") basculePleinEcran();
    else return;
    e.preventDefault();
    e.stopPropagation();
  }

  function surRedim() { if (etat && etat.ajuste) ajuste(); }

  // src : l'image ; titre, legende : du texte ; seul : l'adresse pour l'ouvrir seule (par défaut, src)
  function ouvre(src, titre, legende, seul) {
    if (!document.getElementById("vis-css")) {
      var st = noeud("style");
      st.id = "vis-css";
      st.textContent = CSS;
      document.head.appendChild(st);
    }
    ferme();
    var racine = noeud("div", "vis");
    racine.setAttribute("role", "dialog");
    racine.setAttribute("aria-modal", "true");
    racine.setAttribute("aria-label", titre || "planche");
    var barre = noeud("div", "vis-barre");
    var t = noeud("div", "vis-titre", titre || "");
    var moins = noeud("button", null, "−"), niv = noeud("span", "vis-niv", ""), plus = noeud("button", null, "+");
    var aj = noeud("button", null, "ajuster");
    moins.title = "dézoomer (−)"; plus.title = "zoomer (+, molette)"; aj.title = "toute la planche (0)";
    barre.append(t, moins, niv, plus, aj);
    if (pleinEcranPossible()) {
      var pe = noeud("button", null, "⛶");
      pe.title = "plein écran (f)";
      pe.append(noeud("span", "vis-b-lib", " plein écran"));
      pe.onclick = basculePleinEcran;
      barre.append(pe);
    }
    var a = noeud("a", "vis-b", "↗");
    a.href = seul || src; a.target = "_blank"; a.rel = "noopener"; a.title = "ouvrir le dessin seul, dans un onglet";
    var x = noeud("button", null, "✕");
    x.title = "fermer (Échap)";
    barre.append(a, x);
    var scene = noeud("div", "vis-scene");
    var img = noeud("img");
    img.alt = titre || "";
    img.draggable = false;
    scene.append(img);
    racine.append(barre, scene, noeud("div", "vis-legende", legende || ""));
    etat = { racine: racine, scene: scene, img: img, niv: niv, n: 1, x: 0, y: 0, ajuste: true,
             retour: document.activeElement, debord: document.documentElement.style.overflow };
    document.documentElement.style.overflow = "hidden";
    document.body.appendChild(racine);
    moins.onclick = function () { zoome(0.8); };
    plus.onclick = function () { zoome(1.25); };
    aj.onclick = ajuste;
    x.onclick = ferme;
    img.onload = ajuste;
    img.src = src;
    if (img.complete && img.naturalWidth) ajuste();
    document.addEventListener("keydown", clavier, true);
    window.addEventListener("resize", surRedim);
    document.addEventListener("fullscreenchange", surRedim);
    document.addEventListener("webkitfullscreenchange", surRedim);

    // la molette zoome autour du pointeur (un trackpad : de petits pas)
    scene.addEventListener("wheel", function (e) {
      e.preventDefault();
      var r = scene.getBoundingClientRect();
      zoome(Math.exp(-e.deltaY * (e.deltaMode === 1 ? 0.05 : 0.0022)), e.clientX - r.left, e.clientY - r.top);
    }, { passive: false });
    // glisser pour déplacer ; à deux doigts, pincer pour zoomer
    var P = {}, pince = null, tire = null, dernierClic = 0;
    scene.addEventListener("pointerdown", function (e) {
      scene.setPointerCapture(e.pointerId);
      P[e.pointerId] = { x: e.clientX, y: e.clientY };
      var ids = Object.keys(P);
      if (ids.length === 2) {
        var a1 = P[ids[0]], b1 = P[ids[1]];
        pince = { d: Math.hypot(a1.x - b1.x, a1.y - b1.y) };
        tire = null;
      } else if (ids.length === 1) {
        tire = { x: e.clientX, y: e.clientY, ox: etat.x, oy: etat.y };
        etat.bouge = false;
        scene.classList.add("tire");
        // double-tap au doigt : comme un double-clic
        var mtn = Date.now();
        if (e.pointerType !== "mouse" && mtn - dernierClic < 300) basculeZoom(e);
        dernierClic = mtn;
      }
    });
    scene.addEventListener("pointermove", function (e) {
      if (!P[e.pointerId]) return;
      P[e.pointerId] = { x: e.clientX, y: e.clientY };
      var ids = Object.keys(P);
      if (pince && ids.length === 2) {
        var a1 = P[ids[0]], b1 = P[ids[1]], d = Math.hypot(a1.x - b1.x, a1.y - b1.y), r = scene.getBoundingClientRect();
        if (pince.d > 0) zoome(d / pince.d, (a1.x + b1.x) / 2 - r.left, (a1.y + b1.y) / 2 - r.top);
        pince.d = d;
      } else if (tire) {
        if (Math.abs(e.clientX - tire.x) + Math.abs(e.clientY - tire.y) > 4) etat.bouge = true;
        etat.x = tire.ox + e.clientX - tire.x;
        etat.y = tire.oy + e.clientY - tire.y;
        etat.ajuste = false;
        pose();
      }
    });
    function lache(e) {
      delete P[e.pointerId];
      if (Object.keys(P).length < 2) pince = null;
      if (!Object.keys(P).length) { tire = null; scene.classList.remove("tire"); }
    }
    scene.addEventListener("pointerup", lache);
    scene.addEventListener("pointercancel", lache);
    function basculeZoom(e) {
      var r = scene.getBoundingClientRect();
      if (etat.ajuste) zoome(2, e.clientX - r.left, e.clientY - r.top);
      else ajuste();
    }
    scene.addEventListener("dblclick", basculeZoom);
    // un clic sur le fond (hors de l'image, sans avoir glissé) ferme
    scene.addEventListener("click", function (e) {
      if (e.target === scene && !etat.bouge) {
        var r = img.getBoundingClientRect();
        if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) ferme();
      }
    });
    x.focus({ preventScroll: true });
  }

  // une figure de planche : son titre (« Planche 5.1 — … ») et sa légende, depuis la légende de la figure
  function depuisFigure(a) {
    var fig = a.closest("figure"), cap = fig && fig.querySelector("figcaption");
    var titre = "", legende = "";
    if (cap) {
      var b = cap.querySelector("b");
      titre = b ? b.textContent.replace(/\.\s*$/, "") : "";
      legende = cap.textContent.slice(b ? b.textContent.length : 0).trim();
    }
    var img = a.querySelector("img");
    ouvre(a.getAttribute("href") || (img && img.src), titre || (img && img.alt) || "", legende, a.getAttribute("href"));
  }

  document.addEventListener("click", function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey) return;   // ⌘-clic : l'onglet, comme avant
    var a = e.target.closest && e.target.closest("a.planche-lien, [data-visionneuse]");
    if (!a) return;
    e.preventDefault();
    if (a.hasAttribute("data-visionneuse")) {
      ouvre(a.getAttribute("data-visionneuse"), a.getAttribute("data-titre") || "", a.getAttribute("data-legende") || "",
            a.getAttribute("href") || null);
    } else depuisFigure(a);
  });

  window.Visionneuse = { ouvre: ouvre, ferme: ferme };
})();
