# -*- coding: utf-8 -*-
"""El vocabulario del vigía: qué titular de un organismo se convierte en hecho.

**Esto es el instrumento, no una lista de palabras.** Decide qué se mide, y un
vocabulario mal escrito sesga la medición desde el primer día sin que el sesgo
se vea: se ve como «no pasó nada» o como «pasa todo el tiempo». Por eso la
dirección lo leyó y lo aprobó antes de que corriera, el 7/10/2026
(`revision/vocabulario-del-vigia-2026-10-07.md`).

**La decisión que ordena todo lo demás.** Una policía publica delitos porque ése
es su trabajo. Con «homicidio» adentro, el vigía dispararía todos los días y la
familia nacería siendo ruido.

    De un organismo oficial, la señal no es el hecho:
    es la respuesta institucional EXCEPCIONAL al hecho.

Un asesinato en Nassau es noticia policial. Un toque de queda en Nassau es una
decisión de autoridad, es rara, y cambia lo que se puede decir de ese Estado.

**El costo, declarado:** el vigía no ve la violencia corriente. Para eso están
ACLED y GDELT. El vigía ve cuándo el Estado hace algo al respecto.

**Por qué hay tres idiomas.** Hasta el 7/10/2026 el vocabulario estaba sólo en
español, y Guyana, Belice y Barbados publican en inglés: los tres estaban
vigilados, con línea de base tomada, y **ninguna palabra podía coincidir con lo
que publicaban**. Si Guyana anunciaba su fecha, el vigía la veía moverse y no la
declaraba. Eso explica parte del «cero hechos» de los primeros días.
"""

# Las palabras van sin tildes y en minúsculas: así se las compara. Los
# fragmentos cortados —«renunci», «resign»— son a propósito y cubren las
# variantes (renuncia, renunció, renuncian).

ELECTORAL = {
    "es": ("convocatoria", "convoca", "cronograma", "calendario electoral",
           "fecha de la eleccion", "fecha de las elecciones", "dia de la eleccion",
           "postergacion", "posterga", "aplazamiento", "aplaza", "suspension de",
           "segunda vuelta", "balotaje", "ballotage", "eleccion extraordinaria",
           "elecciones generales", "elecciones nacionales", "comicios",
           "inscripcion de candidat", "cierre de listas", "padron electoral"),
    "en": ("election date", "polling day", "general election", "by-election",
           "nomination day", "voter registration", "postpone", "writ of election",
           "electoral calendar", "runoff", "run-off", "election day"),
    "fr": ("date du scrutin", "jour du scrutin", "elections generales",
           "calendrier electoral", "inscription des electeurs", "second tour",
           "report du scrutin"),
}

# Rupturas de la normalidad institucional.
GOBERNABILIDAD = {
    "es": ("renunci", "dimision", "destitu", "remocion del", "mocion de censura",
           "voto de censura", "disolucion del congreso", "disolucion del parlamento",
           "juicio politico", "estado de sitio", "estado de excepcion",
           "cambio de gabinete", "nuevo gabinete", "huelga general", "paro general",
           "manifestacion", "marcha de", "protesta"),
    "en": ("resign", "step down", "removed from office", "ousted",
           "no-confidence", "no confidence", "dissolve parliament",
           "dissolution of parliament", "prorogation", "impeach",
           "state of emergency", "cabinet reshuffle", "sworn in as minister",
           "general strike", "industrial action", "demonstration",
           "protest march", "rally"),
    "fr": ("demission", "demissionne", "destitu", "revocation",
           "motion de censure", "dissolution du parlement", "etat d'urgence",
           "remaniement", "greve generale", "manifestation"),
}

# Medidas de excepción, no delitos.
SEGURIDAD = {
    "es": ("toque de queda", "estado de emergencia", "despliegue militar",
           "fuerzas armadas en las calles", "operativo de seguridad", "motin",
           "amotinamiento", "fuga masiva", "masacre", "alerta de seguridad",
           "aviso a la poblacion", "cierre de frontera"),
    "en": ("curfew", "state of emergency", "state of public emergency",
           "emergency powers", "defence force deployed", "troops deployed",
           "security operation", "joint operation", "riot", "prison unrest",
           "mass escape", "prison break", "massacre", "mass casualty",
           "security alert", "public safety advisory", "border closure",
           "border closed"),
    "fr": ("couvre-feu", "etat d'urgence", "deploiement militaire",
           "operation de securite", "mutinerie", "emeute", "evasion massive",
           "massacre", "alerte de securite", "fermeture de la frontiere"),
}

# Hoy ningún organismo del padrón es un regulador de telecomunicaciones. Queda
# escrito para el día que entre uno, y no se aplica a nadie mientras tanto.
ENTORNO = {
    "es": ("suspension del servicio", "bloqueo de", "restriccion de acceso",
           "corte de internet"),
    "en": ("service suspension", "service disruption", "blocked", "access restriction",
           "internet shutdown", "internet outage"),
    "fr": ("suspension du service", "blocage", "coupure d'internet"),
}

# Qué vocabulario le toca a cada organismo, según su `materia`, y a qué eje de
# FEMÓNOE va el hecho que produzca.
POR_MATERIA = {
    "electoral":      (ELECTORAL, "gobernabilidad"),
    "gobernabilidad": (GOBERNABILIDAD, "gobernabilidad"),
    "seguridad":      (SEGURIDAD, "seguridad"),
    "entorno":        (ENTORNO, "entorno informativo"),
}


def eje_de(materia):
    """A qué eje de la casa va lo que publique un organismo de esta materia."""
    return POR_MATERIA.get(materia, POR_MATERIA["electoral"])[1]


def menciona(titular, materia="electoral", idioma="es"):
    """La palabra del vocabulario que aparece en el titular, o None.

    Se busca **en el idioma del organismo y además en los otros dos**: un
    gobierno caribeño puede publicar un comunicado en español, y un organismo
    haitiano alterna francés y criollo. Perderse un hecho por el idioma en que
    vino escrito sería repetir el defecto que esto vino a corregir.
    """
    plano = _plano(titular)
    tabla = POR_MATERIA.get(materia, POR_MATERIA["electoral"])[0]
    orden = [idioma] + [k for k in tabla if k != idioma]
    for lengua in orden:
        for palabra in tabla.get(lengua, ()):
            if palabra in plano:
                return palabra
    return None


def _plano(texto):
    import unicodedata
    t = unicodedata.normalize("NFD", str(texto or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")
