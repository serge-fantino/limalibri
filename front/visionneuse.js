// La visionneuse des planches : un clic sur une planche l'ouvre par-dessus la page, pour zoomer et la parcourir,
// et passer en plein écran. Un seul fichier, sans dépendance, partagé par LimaLibri (front/index.html) et le site
// public (copié à sa racine) : il s'accroche aux liens « a.planche-lien » des figures (planches.py).
//
//   molette, pincement, + −     zoomer (autour du pointeur, des doigts)   glisser (souris, un doigt)   déplacer
//   double-clic, double-tap      ajuster ⇄ zoom ×2 à cet endroit           0                            ajuster
//   f                            plein écran                          Échap         fermer
//
// Le zoom change la taille de l'image, pas une transformation : le SVG est redessiné net à chaque échelle.
// Au doigt : les événements tactiles (le zoom natif de la page est bloqué tant qu'elle est ouverte) ; le point de
// la planche pris entre les doigts y reste. La planche ne sort pas de l'écran.
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

  var MAX = 8;                     // zoom maximal (×8 : un texte de 11 lu à 88)
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

  // la planche ne sort pas de la scène : plus petite, elle reste centrée ; plus grande, elle la couvre
  function borne() {
    var N = naturel(), S = etat.scene.getBoundingClientRect(), l = N.l * etat.n, h = N.h * etat.n;
    etat.x = l <= S.width ? (S.width - l) / 2 : Math.min(0, Math.max(S.width - l, etat.x));
    etat.y = h <= S.height ? (S.height - h) / 2 : Math.min(0, Math.max(S.height - h, etat.y));
  }

  function pose() {
    var N = naturel(), i = etat.img;
    if (!etat.ajuste) borne();
    i.style.width = N.l * etat.n + "px";
    i.style.height = N.h * etat.n + "px";
    i.style.left = etat.x + "px";
    i.style.top = etat.y + "px";
    etat.niv.textContent = Math.round(etat.n * 100) + " %";
  }

  function ajuste() {
    var N = naturel(), S = etat.scene.getBoundingClientRect(), m = 16;
    if (S.width < 40 || S.height < 40) return;          // pas encore mise en page : l'observateur reviendra
    etat.n = Math.max(0.05, Math.min((S.width - 2 * m) / N.l, (S.height - 2 * m) / N.h));
    etat.min = etat.n / 2;                              // dézoomer : jusqu'à la moitié de la planche ajustée
    etat.x = (S.width - N.l * etat.n) / 2;
    etat.y = (S.height - N.h * etat.n) / 2;
    etat.ajuste = true;
    pose();
  }

  // zoomer d'un facteur f autour du point (px, py) de la scène
  function zoome(f, px, py) {
    var S = etat.scene.getBoundingClientRect();
    if (px == null) { px = S.width / 2; py = S.height / 2; }
    var n = Math.max(etat.min || 0.05, Math.min(MAX, etat.n * f));
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
    document.removeEventListener("gesturestart", bloque, true);
    document.removeEventListener("gesturechange", bloque, true);
    if (etat.obs) etat.obs.disconnect();
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

  function surRedim() { if (!etat) return; if (etat.ajuste) ajuste(); else pose(); }
  function bloque(e) { e.preventDefault(); }             // Safari : le zoom de la page, pendant la visionneuse

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
    img.onload = function () { etat.mesure = null; ajuste(); };
    img.src = src;
    if (img.complete && img.naturalWidth) ajuste();
    // la scène change de taille (mise en page, rotation, barre d'adresse, plein écran) : on ré-ajuste
    if (window.ResizeObserver) { etat.obs = new ResizeObserver(surRedim); etat.obs.observe(scene); }
    requestAnimationFrame(function () { if (etat && etat.ajuste) ajuste(); });
    document.addEventListener("gesturestart", bloque, true);
    document.addEventListener("gesturechange", bloque, true);
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
    // la souris : glisser pour déplacer
    var tire = null;
    scene.addEventListener("pointerdown", function (e) {
      if (e.pointerType !== "mouse") return;            // le doigt : plus bas
      scene.setPointerCapture(e.pointerId);
      tire = { x: e.clientX, y: e.clientY, ox: etat.x, oy: etat.y };
      etat.bouge = false;
      scene.classList.add("tire");
    });
    scene.addEventListener("pointermove", function (e) {
      if (!tire || e.pointerType !== "mouse") return;
      if (Math.abs(e.clientX - tire.x) + Math.abs(e.clientY - tire.y) > 4) etat.bouge = true;
      etat.x = tire.ox + e.clientX - tire.x;
      etat.y = tire.oy + e.clientY - tire.y;
      etat.ajuste = false;
      pose();
    });
    function lache() { tire = null; scene.classList.remove("tire"); }
    scene.addEventListener("pointerup", lache);
    scene.addEventListener("pointercancel", lache);

    // le doigt : un doigt déplace, deux doigts zooment (et déplacent) ; double-tap : ajuster ⇄ ×2.
    // Le geste part de son état au début (doigts, échelle, point de la planche sous les doigts) : pas de dérive.
    var geste = null, dernierTap = 0;
    function points(e) {
      var r = scene.getBoundingClientRect(), T = e.touches, L = [];
      for (var k = 0; k < T.length && k < 2; k++) L.push({ x: T[k].clientX - r.left, y: T[k].clientY - r.top });
      return L;
    }
    function commence(e) {
      var L = points(e);
      if (L.length === 2) {
        var mx = (L[0].x + L[1].x) / 2, my = (L[0].y + L[1].y) / 2;
        geste = { deux: true, d: Math.hypot(L[0].x - L[1].x, L[0].y - L[1].y) || 1, n: etat.n,
                  ix: (mx - etat.x) / etat.n, iy: (my - etat.y) / etat.n };
      } else if (L.length === 1) {
        geste = { deux: false, x: L[0].x, y: L[0].y, ox: etat.x, oy: etat.y };
      } else geste = null;
    }
    scene.addEventListener("touchstart", function (e) {
      e.preventDefault();
      if (e.touches.length === 1) {
        var mtn = Date.now(), L = points(e);
        if (mtn - dernierTap < 300) {
          var r = scene.getBoundingClientRect();
          basculeZoom({ clientX: L[0].x + r.left, clientY: L[0].y + r.top });
          dernierTap = 0;
          geste = null;
          return;
        }
        dernierTap = mtn;
      }
      commence(e);
    }, { passive: false });
    scene.addEventListener("touchmove", function (e) {
      e.preventDefault();
      if (!geste) return;
      var L = points(e);
      if (geste.deux && L.length === 2) {
        var mx = (L[0].x + L[1].x) / 2, my = (L[0].y + L[1].y) / 2;
        var n = Math.max(etat.min || 0.05, Math.min(MAX, geste.n * Math.hypot(L[0].x - L[1].x, L[0].y - L[1].y) / geste.d));
        etat.n = n;
        etat.x = mx - geste.ix * n;
        etat.y = my - geste.iy * n;
      } else if (!geste.deux && L.length === 1) {
        if (Math.abs(L[0].x - geste.x) + Math.abs(L[0].y - geste.y) > 6) dernierTap = 0;   // un glisser n'est pas un tap
        etat.x = geste.ox + L[0].x - geste.x;
        etat.y = geste.oy + L[0].y - geste.y;
      } else return;
      etat.ajuste = false;
      pose();
    }, { passive: false });
    function finTouche(e) { e.preventDefault(); commence(e); }   // un doigt levé : on repart de ceux qui restent
    scene.addEventListener("touchend", finTouche, { passive: false });
    scene.addEventListener("touchcancel", finTouche, { passive: false });
    // ailleurs dans la visionneuse (la barre, la légende) : pas de zoom de la page
    racine.addEventListener("touchmove", function (e) { if (e.touches.length > 1) e.preventDefault(); }, { passive: false });
    function basculeZoom(e) {
      var r = scene.getBoundingClientRect();
      if (etat.ajuste) zoome(2.5, e.clientX - r.left, e.clientY - r.top);
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
