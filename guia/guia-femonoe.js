/* Guía FEMÓNOE — asistente de navegación. Copia propia de la guía de SIWA
   (sitio/_comun/guia-siwa.js), recoloreada al violeta de la casa y con el
   catálogo de FEMÓNOE. SIWA no se toca.
   Una burbuja fija abajo a la derecha que abre una ventana de chat: conversa,
   entiende lo que el usuario escribe (tema, país, herramienta o pregunta), lo
   cruza contra el catálogo real y lo lleva a la página que existe. Corre ENTERO
   en el navegador: no gasta un solo token, no consulta ninguna IA paga, no manda
   datos a ningún lado. Nunca inventa: si no encuentra, lo dice.
   Se carga con <script defer src="guia/guia-femonoe.js"></script>. */
(function () {
  if (window.__guiaFemonoe) return;            // una sola vez por página
  window.__guiaFemonoe = true;

  var script = document.currentScript ||
    (function () { var s = document.getElementsByTagName("script"); return s[s.length - 1]; })();
  var base = script.src.replace(/guia\/[^\/]*$/, "");   // carpeta del tablero
  var datosUrl = base + "guia/guia-femonoe.json";

  var norm = function (s) {
    return (s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")
      .replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim();
  };

  /* ---------- estilos (todo con prefijo gf- para no chocar con la página) ---------- */
  var css = "" +
  ".gf-lanzador{position:fixed;right:22px;bottom:22px;z-index:9000;width:60px;height:60px;border-radius:50%;" +
    "border:0;cursor:pointer;background:#8C00E0;color:#fff;box-shadow:0 10px 26px rgba(140,0,224,.38);" +
    "display:flex;align-items:center;justify-content:center;transition:transform .15s,box-shadow .15s;" +
    "font-family:'Inter',system-ui,sans-serif;}" +
  ".gf-lanzador:hover{transform:translateY(-2px);box-shadow:0 14px 30px rgba(140,0,224,.46);}" +
  ".gf-lanzador svg{width:28px;height:28px;}.gf-lanzador .gf-cerrar{display:none;}" +
  ".gf-on .gf-lanzador .gf-abrir{display:none;}.gf-on .gf-lanzador .gf-cerrar{display:block;}" +
  ".gf-globo{position:fixed;right:92px;bottom:34px;z-index:9000;background:#00121E;color:#fff;font-size:12.5px;" +
    "font-family:'Inter',system-ui,sans-serif;padding:8px 12px;border-radius:12px;box-shadow:0 8px 20px rgba(0,18,30,.2);" +
    "max-width:200px;line-height:1.4;cursor:pointer;}" +
  ".gf-globo::after{content:'';position:absolute;right:-6px;bottom:16px;border:6px solid transparent;border-left-color:#00121E;}" +
  ".gf-on .gf-globo{display:none;}" +
  ".gf-pop{position:fixed;right:22px;bottom:94px;z-index:9001;width:376px;max-width:calc(100vw - 32px);" +
    "height:min(560px,calc(100vh - 130px));display:none;flex-direction:column;background:#fff;border:1px solid #DDE2E5;" +
    "border-radius:16px;overflow:hidden;box-shadow:0 20px 50px rgba(0,18,30,.28);" +
    "font-family:'Inter',system-ui,sans-serif;color:#00121E;}" +
  ".gf-on .gf-pop{display:flex;}" +
  ".gf-tope{background:#00121E;color:#fff;padding:13px 15px;display:flex;align-items:center;gap:9px;}" +
  ".gf-tope .gf-p{width:9px;height:9px;border-radius:50%;background:#BA66EC;box-shadow:0 0 0 3px rgba(186,102,236,.3);}" +
  ".gf-tope .gf-t{font-weight:700;font-size:14px;}" +
  ".gf-tope .gf-g{margin-left:auto;font-size:10.5px;color:#9FB0BC;}" +
  ".gf-tope .gf-x{background:transparent;border:0;color:#9FB0BC;font-size:20px;cursor:pointer;line-height:1;margin-left:6px;font-family:inherit;}" +
  ".gf-tope .gf-x:hover{color:#fff;}" +
  ".gf-hilo{flex:1;padding:14px;overflow-y:auto;display:flex;flex-direction:column;gap:11px;}" +
  ".gf-msg{max-width:88%;padding:10px 12px;border-radius:14px;font-size:13.5px;line-height:1.48;white-space:pre-wrap;}" +
  ".gf-msg.gf-bot{align-self:flex-start;background:#F9F9F7;border:1px solid #DDE2E5;border-bottom-left-radius:5px;}" +
  ".gf-msg.gf-yo{align-self:flex-end;background:#00121E;color:#fff;border-bottom-right-radius:5px;}" +
  ".gf-card{display:block;margin-top:8px;text-decoration:none;color:inherit;border:1px solid #DDE2E5;border-radius:10px;" +
    "padding:9px 11px;background:#fff;transition:.15s;}" +
  ".gf-card:hover{border-color:#8C00E0;background:rgba(140,0,224,.06);}" +
  ".gf-card .gf-k{font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:#667B89;}" +
  ".gf-card .gf-v{font-weight:700;color:#00121E;margin-top:2px;font-size:13.5px;}" +
  ".gf-card .gf-ir{color:#8C00E0;}" +
  ".gf-chips{display:flex;flex-wrap:wrap;gap:7px;margin-top:2px;}" +
  ".gf-chip{border:1px solid #DDE2E5;background:#fff;color:#5A6E7B;border-radius:999px;padding:6px 12px;font-size:12.5px;" +
    "cursor:pointer;font-family:inherit;transition:.15s;}" +
  ".gf-chip:hover{border-color:#8C00E0;color:#00121E;background:rgba(140,0,224,.07);}" +
  ".gf-chip.gf-eje{border-color:rgba(140,0,224,.35);}" +
  ".gf-barra{display:flex;gap:7px;border-top:1px solid #DDE2E5;padding:10px;}" +
  ".gf-barra input{flex:1;border:1px solid #DDE2E5;border-radius:999px;padding:10px 14px;font-size:13.5px;" +
    "font-family:inherit;color:#00121E;outline:none;}" +
  ".gf-barra input:focus{border-color:#8C00E0;}" +
  ".gf-barra button{background:#8C00E0;color:#fff;border:0;border-radius:999px;padding:0 16px;font-weight:700;" +
    "font-size:13.5px;cursor:pointer;font-family:inherit;}" +
  "@media(max-width:460px){.gf-pop{right:8px;left:8px;bottom:84px;width:auto;height:min(70vh,520px);}" +
    ".gf-lanzador{right:16px;bottom:16px;}.gf-globo{display:none;}}" +
  "@media print{.gf-lanzador,.gf-globo,.gf-pop{display:none !important;}}";

  var st = document.createElement("style"); st.textContent = css; document.head.appendChild(st);

  /* ---------- DOM ---------- */
  var raiz = document.createElement("div");
  raiz.innerHTML =
    '<div class="gf-globo" id="gf-globo">¿Te ayudo a encontrar algo?</div>' +
    '<button class="gf-lanzador" id="gf-lanzador" aria-label="Abrir la guía de FEMÓNOE">' +
      '<svg class="gf-abrir" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>' +
      '<svg class="gf-cerrar" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>' +
    '</button>' +
    '<div class="gf-pop" id="gf-pop" role="dialog" aria-label="Guía FEMÓNOE">' +
      '<div class="gf-tope"><span class="gf-p"></span><span class="gf-t">Guía FEMÓNOE</span>' +
        '<span class="gf-g">sin costo · sin IA paga</span>' +
        '<button class="gf-x" id="gf-x" aria-label="Cerrar">×</button></div>' +
      '<div class="gf-hilo" id="gf-hilo"></div>' +
      '<div class="gf-barra"><input id="gf-entrada" autocomplete="off" placeholder="Escribí: alertas en Perú">' +
        '<button id="gf-ir">Ir</button></div>' +
    '</div>';
  function montarDom() { while (raiz.firstChild) document.body.appendChild(raiz.firstChild); }

  /* ---------- motor ---------- */
  var DATOS = null, hilo, entrada, ctxPais = null, arrancado = false;

  function puntaje(qt, texto) {
    var t = " " + norm(texto) + " ", p = 0;
    for (var i = 0; i < qt.length; i++) { var w = qt[i];
      if (w.length > 2 && t.indexOf(" " + w) >= 0) p += (t.indexOf(" " + w + " ") >= 0 ? 2 : 1); }
    return p;
  }
  // busca el mejor ítem en una lista [{slug/archivo, rotulo, s?, eje?}]
  function mejor(qt, lista, campoClave) {
    var top = null, mp = 0;
    for (var i = 0; i < lista.length; i++) {
      var it = lista[i];
      var texto = (it.rotulo || "") + " " + (it.s || "") + " " + String(it[campoClave] || "").replace(/[_-]/g, " ");
      var p = puntaje(qt, texto);
      if (p > mp) { mp = p; top = it; }
    }
    return mp > 0 ? { it: top, p: mp } : null;
  }

  function burbuja(clase, html) {
    var d = document.createElement("div"); d.className = "gf-msg " + clase; d.innerHTML = html;
    hilo.appendChild(d); hilo.scrollTop = hilo.scrollHeight; return d;
  }
  function chips(items) {
    var c = document.createElement("div"); c.className = "gf-chips";
    items.forEach(function (it) {
      var b = document.createElement("button"); b.className = "gf-chip" + (it.eje ? " gf-eje" : "");
      b.textContent = it.t; b.onclick = it.fn; c.appendChild(b);
    });
    hilo.appendChild(c); hilo.scrollTop = hilo.scrollHeight;
  }
  function card(k, r, url) {
    return '<a class="gf-card" href="' + url + '"><div class="gf-k">' + k + '</div>' +
      '<div class="gf-v">' + r + ' <span class="gf-ir">↗</span></div></a>';
  }
  // FEMÓNOE es una sola página: se navega con anclas, y el país queda resaltado
  // por :target. Ninguna de estas direcciones sale del tablero.
  var uT = function (s) { return "#" + s; };
  var uP = function (s) { return "#pais-" + s; };
  var uH = function (a) { return "#" + a; };

  function saludar() {
    hilo.innerHTML = ""; ctxPais = null;
    burbuja("gf-bot", "Guía de FEMÓNOE. Orienta por eje, por Estado o sobre el método con que se produce una alerta.\n\n¿Por dónde empezamos?");
    var chipsEje = DATOS.ejes_orden.map(function (e) { return { t: e, eje: 1, fn: function () { abrirEje(e); } }; });
    chipsEje.push({ t: "Un Estado", fn: function () {
      burbuja("gf-yo", "Un Estado");
      burbuja("gf-bot", "Escribí el país abajo —por ejemplo <b>Perú</b>— y te lo marco en el mosaico."); } });
    chipsEje.push({ t: "Qué hay en la página", fn: mostrarHerr });
    chipsEje.push({ t: "¿Qué es FEMÓNOE?", fn: function () { responder("que es femonoe"); } });
    chips(chipsEje);
  }
  function abrirEje(e) {
    burbuja("gf-yo", e);
    burbuja("gf-bot", "Temas de <b>" + e + "</b> —tocá uno:");
    var temas = DATOS.temas.filter(function (t) { return t.eje === e; });
    chips(temas.map(function (t) { return { t: t.rotulo, fn: function () { llevarTema(t); } }; }));
  }
  function mostrarHerr() {
    burbuja("gf-yo", "Herramientas");
    var d = burbuja("gf-bot", "La página tiene estas partes:");
    DATOS.herramientas.forEach(function (h) { d.innerHTML += card("Sección", h.rotulo, uH(h.archivo)); });
    seguir();
  }
  function llevarTema(t, pais) {
    var d = burbuja("gf-bot", pais
      ? "Te dejo <b>" + t.rotulo + "</b> y marco <b>" + pais.rotulo + "</b> en el mosaico:"
      : "Ahí va <b>" + t.rotulo + "</b>:");
    d.innerHTML += card("Sección", t.rotulo, uT(t.slug));
    if (pais) d.innerHTML += card("Estado", pais.rotulo, uP(pais.slug));
    seguir();
  }
  function llevarPais(p) {
    var d = burbuja("gf-bot", "Te marco <b>" + p.rotulo + "</b> en el mosaico. Las tres letras dicen en qué ejes tiene alerta vigente:");
    d.innerHTML += card("Estado", p.rotulo, uP(p.slug));
    ctxPais = p; seguir();
  }
  function seguir() {
    chips([
      { t: "Buscar otra cosa", fn: function () { burbuja("gf-bot", "Dale, escribila abajo."); entrada.focus(); } },
      { t: "¿Cómo nace una alerta?", fn: function () { responder("como nace una alerta"); } },
      { t: "Volver al inicio", fn: saludar }
    ]);
  }
  function responder(texto) {
    var q = norm(texto), qt = q.split(" ");
    burbuja("gf-yo", texto);
    var ft = null, fp = 0;
    DATOS.faq.forEach(function (f) { var p = puntaje(qt, f.q); if (p > fp) { fp = p; ft = f; } });
    var tP = mejor(qt, DATOS.paises, "slug");
    var tT = mejor(qt, DATOS.temas, "slug");
    var tH = mejor(qt, DATOS.herramientas, "archivo");
    var mx = Math.max(tT ? tT.p : 0, tP ? tP.p : 0);
    if (ft && fp >= 2 && fp >= mx) { burbuja("gf-bot", ft.r); seguir(); return; }
    if (tP && tT) { llevarTema(tT.it, tP.it); return; }
    if (tT) { llevarTema(tT.it, ctxPais); return; }
    if (tP) { llevarPais(tP.it); return; }
    if (tH) { var d = burbuja("gf-bot", "Creo que buscás esta herramienta:");
      d.innerHTML += card("Herramienta", tH.it.rotulo, uH(tH.it.archivo)); seguir(); return; }
    burbuja("gf-bot", "No lo tengo con ese nombre —y prefiero no adivinar. Probá con un eje (gobernabilidad, seguridad, entorno informativo), con un Estado, o preguntame cómo nace una alerta.");
    chips([{ t: "Volver al inicio", fn: saludar }, { t: "Qué hay en la página", fn: mostrarHerr }]);
  }

  /* ---------- arranque ---------- */
  function abrir() {
    document.body.classList.add("gf-on");
    if (!arrancado && DATOS) { saludar(); arrancado = true; }
    if (entrada) entrada.focus();
  }
  function cerrar() { document.body.classList.remove("gf-on"); }

  function iniciar() {
    montarDom();
    hilo = document.getElementById("gf-hilo");
    entrada = document.getElementById("gf-entrada");
    document.getElementById("gf-lanzador").onclick = function () {
      document.body.classList.contains("gf-on") ? cerrar() : abrir();
    };
    document.getElementById("gf-x").onclick = cerrar;
    document.getElementById("gf-globo").onclick = abrir;
    document.getElementById("gf-ir").onclick = function () {
      var v = entrada.value.trim(); if (v) { responder(v); entrada.value = ""; }
    };
    entrada.addEventListener("keydown", function (e) { if (e.key === "Enter") document.getElementById("gf-ir").click(); });
    // Traer el catálogo. Si falla, la burbuja no aparece: mejor nada que algo roto.
    fetch(datosUrl, { cache: "no-cache" }).then(function (r) { return r.json(); }).then(function (d) {
      DATOS = d;
    }).catch(function () {
      var l = document.getElementById("gf-lanzador"), g = document.getElementById("gf-globo");
      if (l) l.style.display = "none"; if (g) g.style.display = "none";
    });
  }

  if (document.body) iniciar();
  else document.addEventListener("DOMContentLoaded", iniciar);
})();
