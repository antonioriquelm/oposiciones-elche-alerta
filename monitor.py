import os
import json
import re
import urllib.request
import urllib.parse
from html.parser import HTMLParser
from urllib.parse import urljoin


# ============================================================
# CONFIGURACIÓN
# ============================================================

URL = "https://gestion.elche.es/procesos/"
STATE_FILE = "estado_elche.json"

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


# ============================================================
# DESCARGAR PÁGINA
# ============================================================

def descargar(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; OposicionesElcheBot/1.0)"
        }
    )

    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", errors="ignore")


# ============================================================
# LIMPIAR TEXTO
# ============================================================

def limpiar(texto):
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


# ============================================================
# PARSER HTML
# ============================================================

class TablaParser(HTMLParser):

    def __init__(self):
        super().__init__()

        self.en_fila = False
        self.en_celda = False

        self.fila = []
        self.filas = []

        self.texto_actual = ""
        self.enlace_actual = None

    def handle_starttag(self, tag, attrs):

        attrs = dict(attrs)

        if tag == "tr":
            self.en_fila = True
            self.fila = []

        elif tag in ("td", "th") and self.en_fila:
            self.en_celda = True
            self.texto_actual = ""
            self.enlace_actual = None

        elif tag == "a" and self.en_celda:
            self.enlace_actual = attrs.get("href")

    def handle_data(self, data):

        if self.en_celda:
            self.texto_actual += data

    def handle_endtag(self, tag):

        if tag in ("td", "th") and self.en_celda:

            texto = limpiar(self.texto_actual)

            self.fila.append({
                "texto": texto,
                "enlace": self.enlace_actual
            })

            self.en_celda = False
            self.texto_actual = ""
            self.enlace_actual = None

        elif tag == "tr" and self.en_fila:

            if self.fila:
                self.filas.append(self.fila)

            self.en_fila = False
            self.fila = []


# ============================================================
# EXTRAER PROCESOS
# ============================================================

def obtener_procesos(html):

    parser = TablaParser()
    parser.feed(html)

    procesos = {}

    for fila in parser.filas:

        if len(fila) < 3:
            continue

        nombre = fila[0]["texto"]
        tipo = fila[1]["texto"]
        estado = fila[2]["texto"]

        if nombre.lower() in ("nombre", "buscar", "tipo", "estado"):
            continue

        if not nombre or not estado:
            continue

        enlace = None

        for celda in fila:
            if celda["enlace"]:
                enlace = urljoin(URL, celda["enlace"])
                break

        clave = nombre.lower()

        procesos[clave] = {
            "nombre": nombre,
            "tipo": tipo,
            "estado": estado,
            "enlace": enlace
        }

    return procesos


# ============================================================
# TELEGRAM
# ============================================================

def enviar_telegram(mensaje):

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    datos = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensaje,
        "disable_web_page_preview": "false"
    }).encode()

    urllib.request.urlopen(
        url,
        data=datos,
        timeout=30
    )


# ============================================================
# ESTADO ANTERIOR
# ============================================================

def cargar_estado():

    if not os.path.exists(STATE_FILE):
        return {}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception:
        return {}


def guardar_estado(estado):

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            estado,
            f,
            ensure_ascii=False,
            indent=2
        )


# ============================================================
# ANALIZAR CAMBIOS
# ============================================================

def analizar_cambios(anterior, actual):

    cambios = []

    # NUEVOS PROCESOS
    for clave, proceso in actual.items():

        if clave not in anterior:

            cambios.append({
                "tipo": "nuevo",
                "proceso": proceso
            })

    # CAMBIOS DE ESTADO
    for clave, proceso in actual.items():

        if clave not in anterior:
            continue

        viejo = anterior[clave]

        if proceso["estado"] != viejo["estado"]:

            cambios.append({
                "tipo": "estado",
                "proceso": proceso,
                "estado_anterior": viejo["estado"]
            })

    return cambios


# ============================================================
# FORMATEAR ALERTAS
# ============================================================

def mensaje_nuevo(proceso):

    mensaje = (
        "🚨 NUEVO PROCESO SELECTIVO\n\n"
        f"📌 {proceso['nombre']}\n"
        f"🏷️ Grupo: {proceso['tipo']}\n"
        f"📋 Estado: {proceso['estado']}\n"
    )

    if proceso["enlace"]:
        mensaje += f"\n🔗 {proceso['enlace']}"

    return mensaje


def mensaje_estado(proceso, estado_anterior):

    estado_nuevo = proceso["estado"]

    if "abierto" in estado_nuevo.lower():
        titulo = "🔴 ¡PLAZO ABIERTO!"

    elif "pendiente" in estado_nuevo.lower():
        titulo = "🟠 CAMBIO DE ESTADO"

    else:
        titulo = "🔔 CAMBIO EN PROCESO SELECTIVO"

    mensaje = (
        f"{titulo}\n\n"
        f"📌 {proceso['nombre']}\n"
        f"🏷️ Grupo: {proceso['tipo']}\n\n"
        f"Antes:\n"
        f"▫️ {estado_anterior}\n\n"
        f"Ahora:\n"
        f"▫️ {estado_nuevo}\n"
    )

    if proceso["enlace"]:
        mensaje += f"\n🔗 {proceso['enlace']}"

    return mensaje


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    print("Comprobando Ayuntamiento de Elche...")

    html = descargar(URL)

    procesos = obtener_procesos(html)

    print(f"Procesos encontrados: {len(procesos)}")

    anterior = cargar_estado()

    # Primera ejecución:
    # guardamos todo sin mandar decenas de mensajes
    if not anterior:

        guardar_estado(procesos)

        enviar_telegram(
            "✅ Monitor de oposiciones de Elche activado.\n\n"
            f"Se han registrado {len(procesos)} procesos.\n\n"
            "A partir de ahora te avisaré cuando aparezcan "
            "nuevos procesos o cambien de estado."
        )

        print("Primera ejecución completada.")

        return

    cambios = analizar_cambios(anterior, procesos)

    print(f"Cambios detectados: {len(cambios)}")

    for cambio in cambios:

        if cambio["tipo"] == "nuevo":

            enviar_telegram(
                mensaje_nuevo(cambio["proceso"])
            )

        elif cambio["tipo"] == "estado":

            enviar_telegram(
                mensaje_estado(
                    cambio["proceso"],
                    cambio["estado_anterior"]
                )
            )

    guardar_estado(procesos)


if __name__ == "__main__":
    main()
