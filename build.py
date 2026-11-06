# -*- coding: utf-8 -*-
"""
Seguimiento de Planes Comerciales (Plan Ninja y Aliado Diamante).

Lee ODK Central, cuenta cuantos locales de cada plan ya se visitaron en el mes
y arma una pagina con el avance por zona y por cadena. Solo seguimiento: no hay
fotos ni reporte, eso vive en el tablero de Ninja.

    ODK_EMAIL=... ODK_PASSWORD=... SEGUIMIENTO_CLAVE=... python build.py

ENTRA   variables de entorno
          ODK_URL            (por defecto https://odk.campiq.space)
          ODK_EMAIL / ODK_PASSWORD   usuario con permiso de lectura
          SEGUIMIENTO_CLAVE  contrasena de la pagina; sin ella sale SIN cifrar
          MES                AAAA-MM; por defecto el mes en curso (hora Ecuador)
SALE    sitio/index.html y sitio/version.json

EL OBJETIVO
-----------
Es la lista de locales que el formulario trae colgada (locales_planes_*.csv):
plan_n = 1 son los de Ninja, plan_d = 1 los de Diamante. Si se sube una lista
nueva al formulario, el objetivo cambia solo.

QUE CUENTA COMO VISITADO
------------------------
Un envio del mes cuyo local esta en la lista del plan. En una visita se puede
marcar Ninja, Diamante o los dos (plan_modo n / d / a). Se cruza por la llave
(AI.183) y, si no cuadra, por el nombre del local. Lo que no cuadra no cuenta
y se dice cuantos son. En Ninja, "no habia girasol" tambien cuenta como
visitado: el local se fue a ver.

Tambien se lee el formulario viejo de Ninja (sos_visibilidad_plan_ninja) por si
algun telefono sin actualizar sigue mandando ahi.

LOS DATOS VAN CIFRADOS
----------------------
El repositorio es publico. Los datos se cifran con AES-256-GCM y una clave
derivada de la contrasena (PBKDF2-SHA256); la pagina los abre en el navegador.
No se publican nombres de mercaderistas ni cedulas: solo locales y clientes.
"""
import base64
import csv
import io
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone

import requests

ODK_URL = os.environ.get("ODK_URL", "https://odk.campiq.space").rstrip("/")
PROYECTO = 1
FORM = "planes_comerciales"
FORM_VIEJO_NINJA = "sos_visibilidad_plan_ninja"
ITERACIONES = 600000
BASE = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(BASE, "sitio")

ECUADOR = timezone(timedelta(hours=-5))
AHORA = datetime.now(ECUADOR)
MES = os.environ.get("MES") or AHORA.strftime("%Y-%m")
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
MES_NOMBRE = "%s %s" % (MESES[int(MES[5:]) - 1], MES[:4])


def apretado(s):
    t = unicodedata.normalize("NFKD", str(s or ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", t.upper())).strip()


def hondo(d, *ruta):
    for k in ruta:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


# ------------------------------------------------------------------ ODK
class ODK:
    def __init__(self):
        email, clave = os.environ.get("ODK_EMAIL"), os.environ.get("ODK_PASSWORD")
        if not email or not clave:
            sys.exit("Faltan ODK_EMAIL y ODK_PASSWORD")
        r = requests.post(ODK_URL + "/v1/sessions",
                          json={"email": email, "password": clave}, timeout=60)
        if r.status_code != 200:
            sys.exit("ODK no acepto el usuario (%s)" % r.status_code)
        self.s = requests.Session()
        self.s.headers["Authorization"] = "Bearer " + r.json()["token"]

    def get(self, ruta, **kw):
        r = self.s.get("%s/v1/projects/%d%s" % (ODK_URL, PROYECTO, ruta), timeout=300, **kw)
        r.raise_for_status()
        return r

    def envios(self, form):
        """Los del mes. Solo los campos que hacen falta para no bajar todo."""
        campos = "__id,fecha,plan_modo,plan_grp/plan,datos_local/local_id,datos_local/local_nombre"
        try:
            v = self.get("/forms/%s.svc/Submissions" % form,
                         params={"$select": campos}).json().get("value", [])
        except requests.HTTPError:
            # el form viejo de Ninja no tiene plan_*: se pide sin $select
            try:
                v = self.get("/forms/%s.svc/Submissions" % form).json().get("value", [])
            except requests.HTTPError as ex:
                print("   %s no se pudo leer (%s)" % (form, ex.response.status_code))
                return []
        return [x for x in v if str(x.get("fecha") or "")[:7] == MES]


def plan_de(x, form):
    if form == FORM_VIEJO_NINJA:
        return {"ninja"}
    modo = str(x.get("plan_modo") or "")
    if modo:
        return {"n": {"ninja"}, "d": {"diamante"}, "a": {"ninja", "diamante"}}.get(modo, set())
    return set(str(hondo(x, "plan_grp", "plan") or "").split())


# ---------------------------------------------------------------- armar
def armar():
    odk = ODK()
    adj = [a["name"] for a in odk.get("/forms/%s/attachments" % FORM).json()
           if a.get("exists") and re.match(r"locales_planes_.*\.csv$", a["name"])]
    if not adj:
        sys.exit("El formulario no trae la lista de locales")
    texto = odk.get("/forms/%s/attachments/%s" % (FORM, sorted(adj)[-1])).content.decode("utf-8-sig")
    maestro = list(csv.DictReader(io.StringIO(texto)))
    print("lista %s: %d locales" % (sorted(adj)[-1], len(maestro)))

    envios = [(x, FORM) for x in odk.envios(FORM)]
    envios += [(x, FORM_VIEJO_NINJA) for x in odk.envios(FORM_VIEJO_NINJA)]
    print("envíos de %s: %d" % (MES_NOMBRE, len(envios)))

    planes = []
    for clave, nombre, col in (("ninja", "Plan Ninja", "plan_n"),
                               ("diamante", "Aliado Diamante", "plan_d")):
        lista = [r for r in maestro if str(r.get(col, "")).strip() == "1"]
        por_llave = {r["llave"].strip().upper(): r for r in lista}
        por_nombre = {apretado(r["pdv"]): r["llave"].strip().upper() for r in lista}
        visita, sin_cruzar = {}, 0
        for x, form in envios:
            if clave not in plan_de(x, form):
                continue
            cod = str(hondo(x, "datos_local", "local_id") or "").strip().upper()
            llave = cod if cod in por_llave else por_nombre.get(
                apretado(hondo(x, "datos_local", "local_nombre")), "")
            if not llave:
                sin_cruzar += 1
                continue
            f = str(x.get("fecha") or "")[:10]
            visita[llave] = max(visita.get(llave, ""), f)
        locales = [{
            "zona": r.get("zona_nom") or r.get("zona", ""),
            "cadena": r.get("cliente", ""),
            "local": r.get("pdv", ""),
            "ciudad": r.get("ciudad", ""),
            "formato": r.get("formato", ""),
            "codigo": r["llave"].strip().upper(),
            "visita": visita.get(r["llave"].strip().upper(), ""),
        } for r in lista]
        hechos = len([t for t in locales if t["visita"]])
        planes.append({"clave": clave, "nombre": nombre, "objetivo": len(locales),
                       "visitados": hechos, "sin_cruzar": sin_cruzar, "locales": locales})
        print("   %-16s %3d de %3d visitados · %d envíos sin cruzar"
              % (nombre, hechos, len(locales), sin_cruzar))

    return {"generado": AHORA.strftime("%Y-%m-%d %H:%M"), "mes": MES,
            "mes_nombre": MES_NOMBRE, "planes": planes}


# --------------------------------------------------------------- cifrar
def cifrar(datos, clave):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    sal, iv = os.urandom(16), os.urandom(12)
    k = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=sal,
                   iterations=ITERACIONES).derive(clave.encode("utf-8"))
    ct = AESGCM(k).encrypt(iv, json.dumps(datos, ensure_ascii=False).encode("utf-8"), None)
    b = lambda v: base64.b64encode(v).decode()
    return {"sal": b(sal), "iv": b(iv), "iter": ITERACIONES, "datos": b(ct)}


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    datos = armar()
    clave = os.environ.get("SEGUIMIENTO_CLAVE", "")
    carga = {"cifrado": cifrar(datos, clave)} if clave else {"plano": datos}
    if not clave:
        print("AVISO: sin SEGUIMIENTO_CLAVE la página sale sin cifrar")
    html = open(os.path.join(BASE, "plantilla.html"), encoding="utf-8").read()
    html = html.replace("__CARGA__", json.dumps(carga, ensure_ascii=False).replace("</", "<\\/"))
    os.makedirs(SALIDA, exist_ok=True)
    with open(os.path.join(SALIDA, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(html)
    with open(os.path.join(SALIDA, "version.json"), "w", encoding="utf-8") as fh:
        json.dump({"generado": datos["generado"]}, fh)
    print("escrito sitio/index.html (%d KB)" % (len(html.encode()) // 1024))


if __name__ == "__main__":
    main()
