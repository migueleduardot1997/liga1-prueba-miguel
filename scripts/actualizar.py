#!/usr/bin/env python3
"""
Actualiza data.json con las tablas de la Liga 1 Perú (código ESPN: per.1).
Se ejecuta cada hora vía GitHub Actions. Si algo falla, NO toca el data.json
existente: la página sigue mostrando los últimos datos buenos con su fecha.
"""
import json, sys, urllib.request
from datetime import datetime, timezone, timedelta

BASE_STANDINGS = "https://site.api.espn.com/apis/v2/sports/soccer/per.1/standings?season=2026"
BASE_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/soccer/per.1/scoreboard"
ARCHIVO = "data.json"
LIMA = timezone(timedelta(hours=-5))

MESES = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]
DIAS = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (tabla personal Liga 1)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def stat(entry, *nombres):
    """Busca un stat por nombre/abreviatura dentro de una entrada de ESPN."""
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
                "pg": stat(e, "wins", "W"),
                "pe": stat(e, "ties", "D"),
                "pp": stat(e, "losses", "L"),
                "gf": stat(e, "pointsFor", "F", "GF"),
                "gc": stat(e, "pointsAgainst", "A", "GA"),
            })
        filas.append(fila)
    # Ordenar por puntos y luego diferencia de gol; asignar posición
    filas.sort(key=lambda f: (-(f["pts"] or 0), -(f["dg"] or 0)))
    for i, f in enumerate(filas, 1):
        f["pos"] = i
    return filas


def extraer_tablas(data):
    """Devuelve (acumulado, clausura) buscando por nombre de grupo, con tolerancia."""
    grupos = data.get("children") or []
    acumulado = clausura = None
    for g in grupos:
        nombre = (g.get("name", "") + " " + g.get("abbreviation", "")).lower()
        entries = (g.get("standings") or {}).get("entries") or []
        if not entries:
            continue
        if "clausura" in nombre:
            clausura = parsear_tabla(entries, completa=False)
        elif any(p in nombre for p in ("acumulad", "aggregate", "overall", "total")):
            acumulado = parsear_tabla(entries, completa=True)
    # Algunos años ESPN entrega una sola tabla general en la raíz
    if acumulado is None:
        entries = (data.get("standings") or {}).get("entries") or []
        if entries:
            acumulado = parsear_tabla(entries, completa=True)
    return acumulado, clausura


def extraer_partidos():
    """Últimos resultados y próximos partidos (opcional: si falla, se omite)."""
    try:
        data = get_json(BASE_SCOREBOARD)
        por_dia = {}
        for ev in data.get("events", []):
            fecha = datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(LIMA)
            clave = fecha.strftime("%Y-%m-%d")
            etiqueta = f"{DIAS[fecha.weekday()]} {fecha.day} de {['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'][fecha.month-1]}"
            comp = ev.get("competitions", [{}])[0]
            lados = {c.get("homeAway"): c for c in comp.get("competitors", [])}
            local, visita = lados.get("home", {}), lados.get("away", {})
            juego = {
                "l": (local.get("team") or {}).get("shortDisplayName", "?"),
                "v": (visita.get("team") or {}).get("shortDisplayName", "?"),
            }
            estado = (ev.get("status") or {}).get("type", {})
            if estado.get("completed") or estado.get("state") == "in":
                juego["m"] = f"{local.get('score','')} - {visita.get('score','')}"
            else:
                juego["h"] = fecha.strftime("%I:%M %p").lstrip("0").lower().replace("am", "a.m.").replace("pm", "p.m.")
            por_dia.setdefault((clave, etiqueta), []).append(juego)
        return [{"dia": et, "juegos": js} for (_, et), js in sorted(por_dia.items())]
    except Exception as e:
        print(f"Aviso: no se pudieron leer los partidos ({e}). Se omite la sección.")
        return None


def main():
    data = get_json(BASE_STANDINGS)
    acumulado, clausura = extraer_tablas(data)

    if not acumulado or len(acumulado) < 10:
        print("ERROR: no se obtuvo una tabla acumulada válida. Se conserva data.json anterior.")
        sys.exit(1)

    # Si ESPN no separa el Clausura, conservar el clausura previo antes que borrarlo
    if not clausura:
        try:
            with open(ARCHIVO, encoding="utf-8") as f:
                clausura = json.load(f).get("clausura")
            print("Aviso: ESPN no entregó tabla del Clausura; se conserva la anterior.")
        except Exception:
            clausura = []

    ahora = datetime.now(LIMA)
    hora = ahora.strftime("%I:%M %p").lstrip("0").lower().replace("am", "a.m.").replace("pm", "p.m.")
    salida = {
        "actualizado": f"{ahora.day} {MESES[ahora.month-1]} {ahora.year}, {hora}",
        "acumulado": acumulado,
        "clausura": clausura,
        "partidos": extraer_partidos(),
    }
    with open(ARCHIVO, "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=2)
    print(f"data.json actualizado: {salida['actualizado']} · {len(acumulado)} equipos en el acumulado.")


if __name__ == "__main__":
    main()
