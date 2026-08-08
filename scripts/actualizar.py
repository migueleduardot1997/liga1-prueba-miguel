#!/usr/bin/env python3
"""Actualiza data.json con las tablas de la Liga 1 Perú desde la API pública de ESPN.
Si todo falla, no toca el data.json existente y deja el error completo en el log."""
import json, sys, traceback, urllib.request
from datetime import datetime, timezone, timedelta

URLS_STANDINGS = [
    "https://site.api.espn.com/apis/v2/sports/soccer/per.1/standings?season=2026",
    "https://site.api.espn.com/apis/v2/sports/soccer/per.1/standings",
    "https://cdn.espn.com/core/soccer/table?xhr=1&league=per.1",
]
URL_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/soccer/per.1/scoreboard"
ARCHIVO = "data.json"
LIMA = timezone(timedelta(hours=-5))
MESES = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]
MESES_L = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto",
           "septiembre","octubre","noviembre","diciembre"]
DIAS = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]

def get_json(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def stat(entry, *nombres):
    for s in entry.get("stats", []):
        if s.get("name") in nombres or s.get("abbreviation") in nombres or s.get("type") in nombres:
            v = s.get("value", s.get("displayValue"))
            try:
                return int(float(v))
            except (TypeError, ValueError):
                pass
    return None

def parsear_tabla(entries, completa):
    filas = []
    for e in entries:
        equipo = e.get("team", {})
        fila = {
            "eq": equipo.get("shortDisplayName") or equipo.get("displayName") or "?",
            "pj": stat(e, "gamesPlayed", "GP"),
            "dg": stat(e, "pointDifferential", "GD", "pointsDiff"),
            "pts": stat(e, "points", "P", "PTS"),
        }
        if completa:
            fila.update({
                "pg": stat(e, "wins", "W"), "pe": stat(e, "ties", "D"),
                "pp": stat(e, "losses", "L"), "gf": stat(e, "pointsFor", "F", "GF"),
                "gc": stat(e, "pointsAgainst", "A", "GA"),
            })
        filas.append(fila)
    filas.sort(key=lambda f: (-(f["pts"] or 0), -(f["dg"] or 0)))
    for i, f in enumerate(filas, 1):
        f["pos"] = i
    return filas

def buscar_grupos(nodo, encontrados):
    """Recorre la respuesta buscando grupos con standings.entries, a cualquier profundidad."""
    if isinstance(nodo, dict):
        entries = (nodo.get("standings") or {}).get("entries") if isinstance(nodo.get("standings"), dict) else None
        if entries:
            nombre = (str(nodo.get("name", "")) + " " + str(nodo.get("abbreviation", ""))).lower()
            encontrados.append((nombre, entries))
        for v in nodo.values():
            buscar_grupos(v, encontrados)
    elif isinstance(nodo, list):
        for v in nodo:
            buscar_grupos(v, encontrados)

def extraer_tablas(data):
    grupos = []
    buscar_grupos(data, grupos)
    print("Grupos encontrados:", [g[0] or "(sin nombre)" for g in grupos])
    acumulado = clausura = None
    for nombre, entries in grupos:
        if "clausura" in nombre and clausura is None:
            clausura = parsear_tabla(entries, completa=False)
        elif any(p in nombre for p in ("acumulad", "aggregate", "overall", "total")) and acumulado is None:
            acumulado = parsear_tabla(entries, completa=True)
    if acumulado is None and grupos:
        # Sin nombre reconocible: usar el grupo más grande como acumulado
        nombre, entries = max(grupos, key=lambda g: len(g[1]))
        acumulado = parsear_tabla(entries, completa=True)
    return acumulado, clausura

def extraer_partidos():
    try:
        data = get_json(URL_SCOREBOARD)
        por_dia = {}
        for ev in data.get("events", []):
            fecha = datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(LIMA)
            etiqueta = f"{DIAS[fecha.weekday()]} {fecha.day} de {MESES_L[fecha.month-1]}"
            comp = ev.get("competitions", [{}])[0]
            lados = {c.get("homeAway"): c for c in comp.get("competitors", [])}
            local, visita = lados.get("home", {}), lados.get("away", {})
            juego = {"l": (local.get("team") or {}).get("shortDisplayName", "?"),
                     "v": (visita.get("team") or {}).get("shortDisplayName", "?")}
            estado = (ev.get("status") or {}).get("type", {})
            if estado.get("completed") or estado.get("state") == "in":
                juego["m"] = f"{local.get('score','')} - {visita.get('score','')}"
            else:
                juego["h"] = fecha.strftime("%I:%M %p").lstrip("0").lower().replace("am","a.m.").replace("pm","p.m.")
            por_dia.setdefault((fecha.strftime("%Y-%m-%d"), etiqueta), []).append(juego)
        return [{"dia": et, "juegos": js} for (_, et), js in sorted(por_dia.items())]
    except Exception as e:
        print(f"Aviso: sin partidos ({e}).")
        return None

def main():
    data = None
    for url in URLS_STANDINGS:
        try:
            print("Probando:", url)
            data = get_json(url)
            break
        except Exception:
            traceback.print_exc()
    if data is None:
        print("ERROR: ninguna fuente respondió. Se conserva el data.json anterior.")
        sys.exit(1)

    acumulado, clausura = extraer_tablas(data)
    if not acumulado or len(acumulado) < 10:
        print("ERROR: no se obtuvo una tabla acumulada válida. Se conserva el data.json anterior.")
        sys.exit(1)

    if not clausura:
        try:
            with open(ARCHIVO, encoding="utf-8") as f:
                clausura = json.load(f).get("clausura") or []
            print("Aviso: sin tabla del Clausura en la fuente; se conserva la anterior.")
        except Exception:
            clausura = []

    ahora = datetime.now(LIMA)
    hora = ahora.strftime("%I:%M %p").lstrip("0").lower().replace("am","a.m.").replace("pm","p.m.")
    salida = {"actualizado": f"{ahora.day} {MESES[ahora.month-1]} {ahora.year}, {hora}",
              "acumulado": acumulado, "clausura": clausura, "partidos": extraer_partidos()}
    with open(ARCHIVO, "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=2)
    print(f"data.json actualizado: {salida['actualizado']} · {len(acumulado)} equipos.")

if __name__ == "__main__":
    main()
