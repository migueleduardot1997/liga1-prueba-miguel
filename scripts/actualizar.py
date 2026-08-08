#!/usr/bin/env python3
"""Liga 1 Perú 2026. Acumulado = Apertura (final, fijo) + Clausura (en vivo desde ESPN)."""
import json, sys, traceback, unicodedata, urllib.request
from datetime import datetime, timezone, timedelta

URLS = ["https://site.api.espn.com/apis/v2/sports/soccer/per.1/standings?season=2026",
        "https://site.api.espn.com/apis/v2/sports/soccer/per.1/standings"]
URL_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/soccer/per.1/scoreboard"
ARCHIVO = "data.json"
LIMA = timezone(timedelta(hours=-5))
MESES = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]
MESES_L = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto",
           "septiembre","octubre","noviembre","diciembre"]
DIAS = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]

# Torneo Apertura 2026 FINAL (17 fechas), con sanciones de puntos ya aplicadas.
APERTURA = {
    "Alianza Lima":        (40, 22), "Los Chankas":         (34, 4),
    "Universitario":       (29, 9),  "Cienciano":           (33, 12),
    "Melgar":              (28, 9),  "Cusco FC":            (27, -3),
    "Dep. Garcilaso":      (26, 3),  "Alianza Atlético":    (21, 2),
    "Sporting Cristal":    (19, -2), "Comerciantes Unidos": (21, -2),
    "Sport Boys":          (20, -4), "Sport Huancayo":      (16, -10),
    "Dep. Moquegua":       (18, -7), "ADT":                 (20, 1),
    "Juan Pablo II":       (16, -18),"Atlético Grau":       (16, -6),
    "FC Cajamarca":        (17, -5), "UTC":                 (13, -5),
}

# Reglas ordenadas para reconocer los nombres que use ESPN (sin tildes, minúsculas)
ALIAS = [("garcilaso","Dep. Garcilaso"),("grau","Atlético Grau"),("chanka","Los Chankas"),
         ("universitario","Universitario"),("cristal","Sporting Cristal"),("cienciano","Cienciano"),
         ("melgar","Melgar"),("boys","Sport Boys"),("huancayo","Sport Huancayo"),
         ("moquegua","Dep. Moquegua"),("adt","ADT"),("tarma","ADT"),("juan pablo","Juan Pablo II"),
         ("utc","UTC"),("comerciantes","Comerciantes Unidos"),("cusco","Cusco FC"),
         ("alianza atl","Alianza Atlético"),("atletico","Alianza Atlético"),
         ("alianza","Alianza Lima"),("cajamarca","FC Cajamarca")]

def normal(t):
    t = unicodedata.normalize("NFD", str(t).lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")

def canonico(nombre):
    n = normal(nombre)
    for clave, oficial in ALIAS:
        if clave in n:
            return oficial
    return nombre

def get_json(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def stat(e, *ns):
    for s in e.get("stats", []):
        if s.get("name") in ns or s.get("abbreviation") in ns or s.get("type") in ns:
            v = s.get("value", s.get("displayValue"))
            try: return int(float(v))
            except (TypeError, ValueError): pass
    return None

def buscar_grupos(nodo, out):
    if isinstance(nodo, dict):
        st = nodo.get("standings")
        if isinstance(st, dict) and st.get("entries"):
            out.append(((str(nodo.get("name","")) + " " + str(nodo.get("abbreviation",""))).lower(),
                        st["entries"]))
        for v in nodo.values(): buscar_grupos(v, out)
    elif isinstance(nodo, list):
        for v in nodo: buscar_grupos(v, out)

def parsear(entries):
    filas = []
    for e in entries:
        eq = e.get("team", {})
        filas.append({"eq": canonico(eq.get("shortDisplayName") or eq.get("displayName") or "?"),
                      "pj": stat(e,"gamesPlayed","GP") or 0,
                      "dg": stat(e,"pointDifferential","GD","pointsDiff") or 0,
                      "pts": stat(e,"points","P","PTS") or 0})
    return filas

def ordenar(filas):
    filas.sort(key=lambda f: (-(f["pts"] or 0), -(f["dg"] or 0)))
    for i, f in enumerate(filas, 1): f["pos"] = i
    return filas

def extraer_partidos():
    try:
        data = get_json(URL_SCOREBOARD); por_dia = {}
        for ev in data.get("events", []):
            fecha = datetime.fromisoformat(ev["date"].replace("Z","+00:00")).astimezone(LIMA)
            et = f"{DIAS[fecha.weekday()]} {fecha.day} de {MESES_L[fecha.month-1]}"
            comp = ev.get("competitions", [{}])[0]
            lados = {c.get("homeAway"): c for c in comp.get("competitors", [])}
            L, V = lados.get("home", {}), lados.get("away", {})
            j = {"l": canonico((L.get("team") or {}).get("shortDisplayName","?")),
                 "v": canonico((V.get("team") or {}).get("shortDisplayName","?"))}
            est = (ev.get("status") or {}).get("type", {})
            if est.get("completed") or est.get("state") == "in":
                j["m"] = f"{L.get('score','')} - {V.get('score','')}"
            else:
                j["h"] = fecha.strftime("%I:%M %p").lstrip("0").lower().replace("am","a.m.").replace("pm","p.m.")
            por_dia.setdefault((fecha.strftime("%Y-%m-%d"), et), []).append(j)
        return [{"dia": et, "juegos": js} for (_, et), js in sorted(por_dia.items())]
    except Exception as e:
        print(f"Aviso: sin partidos ({e})."); return None

def main():
    data = None
    for url in URLS:
        try:
            print("Probando:", url); data = get_json(url); break
        except Exception: traceback.print_exc()
    if data is None:
        print("ERROR: la fuente no respondió; se conserva data.json."); sys.exit(1)

    grupos = []; buscar_grupos(data, grupos)
    print("Grupos:", [g[0] or "(sin nombre)" for g in grupos])
    if not grupos:
        print("ERROR: sin tablas en la respuesta; se conserva data.json."); sys.exit(1)

    # Preferir un grupo llamado "clausura"; si no, el grupo más grande
    entries = next((e for n, e in grupos if "clausura" in n), max(grupos, key=lambda g: len(g[1]))[1])
    tabla = parsear(entries)
    max_pj = max(f["pj"] for f in tabla)

    if max_pj <= 10:          # ESPN entregó el CLAUSURA → sumar el Apertura fijo
        clausura = ordenar([dict(f) for f in tabla])
        acumulado = ordenar([{"eq": f["eq"], "pj": f["pj"] + 17,
                              "dg": f["dg"] + APERTURA.get(f["eq"], (0,0))[1],
                              "pts": f["pts"] + APERTURA.get(f["eq"], (0,0))[0]} for f in tabla])
    else:                      # ESPN entregó el ACUMULADO → restar el Apertura fijo
        acumulado = ordenar([dict(f) for f in tabla])
        clausura = ordenar([{"eq": f["eq"], "pj": f["pj"] - 17,
                             "dg": f["dg"] - APERTURA.get(f["eq"], (0,0))[1],
                             "pts": f["pts"] - APERTURA.get(f["eq"], (0,0))[0]} for f in tabla])

    sin_base = [f["eq"] for f in tabla if f["eq"] not in APERTURA]
    if sin_base: print("Aviso: equipos sin base del Apertura:", sin_base)
    if len(sin_base) > 3:
        print("ERROR: demasiados nombres sin reconocer; se conserva data.json."); sys.exit(1)

    ahora = datetime.now(LIMA)
    hora = ahora.strftime("%I:%M %p").lstrip("0").lower().replace("am","a.m.").replace("pm","p.m.")
    salida = {"actualizado": f"{ahora.day} {MESES[ahora.month-1]} {ahora.year}, {hora}",
              "acumulado": acumulado, "clausura": clausura, "partidos": extraer_partidos()}
    with open(ARCHIVO, "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=2)
    print(f"OK: {salida['actualizado']} · Clausura max PJ={max_pj}")

if __name__ == "__main__":
    main()
