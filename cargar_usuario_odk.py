# -*- coding: utf-8 -*-
"""
Carga el usuario de ODK como secreto del repositorio en GitHub, sin que la
contrasena quede escrita en ningun lado.

    python cargar_usuario_odk.py

1. Pide correo y contrasena (la contrasena no se ve al escribir).
2. Prueba que ODK los acepte.
3. Los sube cifrados como ODK_EMAIL y ODK_PASSWORD, usando la sesion de
   GitHub que git ya tiene guardada en esta compu.
4. Lanza la primera actualizacion de la pagina.
"""
import base64
import getpass
import subprocess
import sys

import requests
from nacl import encoding, public

REPO = "DavidIbujes/Seguimiento_planes"
ODK_URL = "https://odk.campiq.space"


def token_github():
    out = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                         capture_output=True, text=True, timeout=60).stdout
    return dict(l.split("=", 1) for l in out.splitlines() if "=" in l).get("password")


def main():
    print("Usuario de ODK para el seguimiento (el de solo lectura)\n")
    email = input("Correo: ").strip()
    clave = getpass.getpass("Contraseña (no se ve al escribir): ")
    if not email or not clave:
        sys.exit("Faltó el correo o la contraseña.")

    print("\nProbando en ODK...", end=" ")
    r = requests.post(ODK_URL + "/v1/sessions", json={"email": email, "password": clave}, timeout=60)
    if r.status_code != 200:
        sys.exit("ODK no lo aceptó (%s). Revisa correo y contraseña." % r.status_code)
    t = r.json()["token"]
    f = requests.get(ODK_URL + "/v1/projects/1/forms/planes_comerciales",
                     headers={"Authorization": "Bearer " + t}, timeout=60)
    if f.status_code != 200:
        sys.exit("El usuario entra, pero no puede ver el formulario Planes Comerciales (%s)."
                 % f.status_code)
    print("ok, ve Planes Comerciales")

    gh = requests.Session()
    gh.headers.update({"Authorization": "Bearer " + token_github(),
                       "Accept": "application/vnd.github+json"})
    k = gh.get("https://api.github.com/repos/%s/actions/secrets/public-key" % REPO, timeout=60).json()
    pk = public.PublicKey(k["key"].encode(), encoding.Base64Encoder())
    for nombre, valor in (("ODK_EMAIL", email), ("ODK_PASSWORD", clave)):
        cifrado = base64.b64encode(public.SealedBox(pk).encrypt(valor.encode())).decode()
        r = gh.put("https://api.github.com/repos/%s/actions/secrets/%s" % (REPO, nombre),
                   json={"encrypted_value": cifrado, "key_id": k["key_id"]}, timeout=60)
        print("GitHub · %s: %s" % (nombre, "guardado" if r.status_code in (201, 204) else r.status_code))

    r = gh.post("https://api.github.com/repos/%s/actions/workflows/actualizar.yml/dispatches" % REPO,
                json={"ref": "main"}, timeout=60)
    print("Primera actualización:", "lanzada" if r.status_code == 204 else r.status_code)
    print("\nEn 2 o 3 minutos: https://davidibujes.github.io/Seguimiento_planes/  (contraseña 123456)")


if __name__ == "__main__":
    main()
