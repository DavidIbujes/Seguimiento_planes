# Seguimiento Planes Comerciales

Avance del mes de **Plan Ninja** y **Aliado Diamante**: cuántos locales de cada
lista ya se visitaron y cuántos faltan, por zona y por cadena. Solo seguimiento.

- Los datos salen de ODK Central (formulario `planes_comerciales` y su lista de
  locales). Cada 10 minutos, de 06:00 a 22:00 (Ecuador), GitHub Actions corre
  `build.py` y publica la página en GitHub Pages.
- Los datos van cifrados (AES-256-GCM) dentro de la página; se abren con la
  contraseña en el navegador. No se publican nombres de mercaderistas ni cédulas.

## Secretos (Settings → Secrets and variables → Actions)

| Nombre | Qué es |
|---|---|
| `ODK_URL` | `https://odk.campiq.space` |
| `ODK_EMAIL` | usuario de ODK con permiso de lectura |
| `ODK_PASSWORD` | su contraseña |
| `SEGUIMIENTO_CLAVE` | contraseña de la página |

## Probar en la compu

    set ODK_EMAIL=...  &  set ODK_PASSWORD=...  &  set SEGUIMIENTO_CLAVE=...
    python build.py          → sitio/index.html

El mes es el que está en curso; para otro: `set MES=2026-11`.
