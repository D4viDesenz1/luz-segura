#!/usr/bin/env python3
"""Popula o MVP com dados de demonstração e gera tráfego para o Grafana.

Só usa a biblioteca padrão do Python (não precisa instalar nada).

  python3 scripts/popular_demo.py --url https://app-luz-segura-xxxxx.azurewebsites.net \
      --admin-token "$ADMIN_TOKEN" --device-token "$DEVICE_TOKEN" --relatos 14 --trafego 300

Com 14 relatos escuros em pontos diferentes, o alerta LuzSeguraFilaDeManutencaoAlta
(> 10 chamados ativos) dispara em ~1 minuto: é a evidência de "alerta disparado".
Os dados são SIMULADOS e documentados (o briefing permite).
"""

from __future__ import annotations

import argparse
import json
import random
import struct
import time
import urllib.error
import urllib.request
import uuid
import zlib

# Pontos no entorno do centro de Osasco (simulados). Alguns colados em paradas.
PONTOS = [
    (-23.5269, -46.7771), (-23.5286, -46.7779), (-23.5326, -46.7841), (-23.5411, -46.7721),
    (-23.5319, -46.7906), (-23.5241, -46.7931), (-23.5301, -46.7811), (-23.5461, -46.7901),
    (-23.5381, -46.7961), (-23.5201, -46.7851), (-23.5151, -46.7741), (-23.5346, -46.7616),
    (-23.5500, -46.8000), (-23.5100, -46.8100), (-23.5550, -46.7650), (-23.5050, -46.7900),
]


def png_cinza(largura: int, altura: int, brilho: int, semente: int) -> bytes:
    """PNG em tons de cinza com ruído (foto noturna sintética), sem Pillow."""
    rnd = random.Random(semente)
    linhas = bytearray()
    for y in range(altura):
        linhas.append(0)
        for x in range(largura):
            v = brilho + rnd.randint(-4, 4)
            # um "poste" fraco em posição aleatória para variar o hash da imagem
            if abs(x - semente * 13 % largura) < 6 and y < altura // 3:
                v += 25
            linhas.append(max(0, min(255, v)))

    def chunk(tipo: bytes, dados: bytes) -> bytes:
        return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", largura, altura, 8, 0, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(linhas), 9)) + chunk(b"IEND", b"")


def req(metodo: str, url: str, corpo: bytes | None = None, headers: dict | None = None) -> tuple[int, dict | str]:
    r = urllib.request.Request(url, data=corpo, method=metodo, headers=headers or {})
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:  # nosemgrep - URL informada pelo próprio operador do script
            txt = resp.read().decode()
            return resp.status, (json.loads(txt) if "json" in resp.headers.get("content-type", "") else txt)
    except urllib.error.HTTPError as e:
        txt = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(txt)
        except ValueError:
            return e.code, txt
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return 0, str(e)


def enviar_relato(base: str, lat: float, lon: float, imagem: bytes) -> tuple[int, dict | str]:
    fronteira = uuid.uuid4().hex
    partes = []
    for nome, valor in (("lat", str(lat)), ("lon", str(lon))):
        partes.append(f'--{fronteira}\r\nContent-Disposition: form-data; name="{nome}"\r\n\r\n{valor}\r\n'.encode())
    partes.append(
        f'--{fronteira}\r\nContent-Disposition: form-data; name="foto"; filename="noite.png"\r\n'
        f"Content-Type: image/png\r\n\r\n".encode() + imagem + b"\r\n"
    )
    partes.append(f"--{fronteira}--\r\n".encode())
    return req("POST", f"{base}/api/v1/relatos", b"".join(partes),
               {"Content-Type": f"multipart/form-data; boundary={fronteira}"})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True)
    ap.add_argument("--admin-token", default="")
    ap.add_argument("--device-token", default="")
    ap.add_argument("--relatos", type=int, default=14)
    ap.add_argument("--trafego", type=int, default=120, help="segundos de tráfego de leitura após popular")
    ap.add_argument("--intervalo", type=float, default=6.5, help="segundos entre relatos (rate limit: 10/min)")
    a = ap.parse_args()
    base = a.url.rstrip("/")

    print(f"== Enviando {a.relatos} relatos noturnos para {base}")
    ids = []
    for i in range(a.relatos):
        lat, lon = PONTOS[i % len(PONTOS)]
        lat += (i // len(PONTOS)) * 0.0011  # evita cair no mesmo raio quando repetir a lista
        brilho = random.choice([4, 8, 12, 35, 45])  # inexistente ou fraca
        st, body = enviar_relato(base, lat, lon, png_cinza(160, 120, brilho, i + int(time.time())))
        cid = body.get("chamado", {}).get("id") if isinstance(body, dict) else None
        print(f"  relato {i + 1:02d}: HTTP {st} -> chamado {cid} {body.get('analise_ia', {}).get('classificacao', '') if isinstance(body, dict) else ''}")
        if cid:
            ids.append(cid)
        time.sleep(a.intervalo)

    # Relato duplicado (mesma região) para mostrar a deduplicação
    lat, lon = PONTOS[2]
    st, body = enviar_relato(base, lat + 0.0001, lon, png_cinza(160, 120, 6, 999))
    print(f"  relato duplicado no mesmo ponto: HTTP {st} -> {body.get('mensagem') if isinstance(body, dict) else body}")

    if a.device_token:
        print("== Leituras do sensor LDR")
        for (lat, lon), lux in zip(PONTOS[:4], (1.5, 3.2, 40.0, 8.0)):
            st, body = req("POST", f"{base}/api/v1/leituras-ldr",
                           json.dumps({"estacao_id": "estacao-osasco-01", "lat": lat, "lon": lon, "lux": lux}).encode(),
                           {"Content-Type": "application/json", "X-Device-Token": a.device_token})
            print(f"  lux={lux}: HTTP {st} -> {body}")

    if a.admin_token and len(ids) > 3:
        print("== Equipe de manutenção resolve 2 chamados (gera o indicador de tempo médio)")
        for cid in ids[-2:]:
            st, _ = req("PATCH", f"{base}/api/v1/chamados/{cid}", json.dumps({"status": "resolvido"}).encode(),
                        {"Content-Type": "application/json", "Authorization": f"Bearer {a.admin_token}"})
            print(f"  chamado {cid} resolvido: HTTP {st}")

    print(f"== Gerando tráfego de leitura por {a.trafego}s (inclui alguns 4xx de entrada inválida)")
    fim = time.time() + a.trafego
    n = 0
    while time.time() < fim:
        rota = random.choice(["/", "/api/v1/chamados", "/api/v1/estatisticas", "/api/v1/paradas",
                              "/api/v1/chamados?status=aberto", "/health", "/api/v1/chamados/999999"])
        req("GET", base + rota)
        n += 1
        time.sleep(random.uniform(0.2, 0.8))
    print(f"   {n} requisições enviadas.")

    st, body = req("GET", f"{base}/api/v1/estatisticas")
    print("== Estatísticas finais:", json.dumps(body, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
