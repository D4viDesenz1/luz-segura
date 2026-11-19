"""Classificação de iluminação a partir de foto noturna e de leitura do LDR.

O classificador de imagem aqui é HEURÍSTICO (luminância média + fração de
pixels claros). Ele existe para o MVP funcionar ponta a ponta. A disciplina de
Visão Computacional substitui `classificar_imagem` pelo modelo treinado,
mantendo a mesma assinatura e o mesmo formato de retorno.

Privacidade (LGPD): a foto é processada só em memória e descartada. Nada da
imagem é gravado, nem os metadados EXIF (GPS do aparelho, modelo do celular).
Guardamos apenas números derivados e um hash perceptual para deduplicar.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageStat, UnidentifiedImageError

# Proteção contra "decompression bomb" (imagem pequena em bytes e gigante em pixels).
Image.MAX_IMAGE_PIXELS = 40_000_000

FORMATOS_ACEITOS = {"JPEG", "PNG", "WEBP"}
CLASSES = ("inexistente", "fraca", "adequada")


class ImagemInvalida(ValueError):
    pass


@dataclass(frozen=True)
class ResultadoImagem:
    classificacao: str
    luminancia_media: float
    fracao_pixels_claros: float
    confianca: float
    ahash: str
    modelo: str = "heuristica-luminancia-v1"


def _average_hash(img_l: Image.Image) -> str:
    """Hash perceptual de 64 bits: fotos iguais ou quase iguais geram o mesmo hash."""
    pequena = img_l.resize((8, 8), Image.Resampling.BILINEAR)
    pixels = list(pequena.tobytes())
    media = sum(pixels) / len(pixels)
    bits = "".join("1" if p >= media else "0" for p in pixels)
    return f"{int(bits, 2):016x}"


def classificar_imagem(conteudo: bytes) -> ResultadoImagem:
    try:
        with Image.open(io.BytesIO(conteudo)) as probe:
            probe.verify()  # valida a estrutura sem decodificar tudo
        img = Image.open(io.BytesIO(conteudo))
        if img.format not in FORMATOS_ACEITOS:
            raise ImagemInvalida(f"Formato não aceito: {img.format}. Use JPEG, PNG ou WEBP.")
        img.load()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise ImagemInvalida("Arquivo enviado não é uma imagem válida.") from exc

    # Reduz para 256 px: barato, e descarta detalhes como rostos e placas.
    img_l = img.convert("L")
    img_l.thumbnail((256, 256))

    stat = ImageStat.Stat(img_l)
    media = float(stat.mean[0])
    hist = img_l.histogram()
    total = sum(hist) or 1
    claros = sum(hist[200:]) / total

    if media < 25 and claros < 0.01:
        classe = "inexistente"
        confianca = min(1.0, 0.6 + (25 - media) / 60)
    elif media < 60:
        classe = "fraca"
        confianca = 0.55 + min(0.3, abs(media - 42) / 100)
    else:
        classe = "adequada"
        confianca = min(1.0, 0.6 + (media - 60) / 200)

    return ResultadoImagem(
        classificacao=classe,
        luminancia_media=round(media, 2),
        fracao_pixels_claros=round(claros, 4),
        confianca=round(confianca, 2),
        ahash=_average_hash(img_l),
    )


def classificar_lux(lux: float) -> str:
    """Classifica a leitura do LDR (já convertida para lux pela estação).

    Referência de ordem de grandeza: vias de pedestres e paradas costumam ter
    iluminância média de alguns lux a ~20 lux (ver ABNT NBR 5101 - confirmar a
    versão vigente). O LDR não é calibrado; os limiares são do MVP e estão
    documentados para serem ajustados com medições reais.
    """
    if lux < 5:
        return "inexistente"
    if lux < 15:
        return "fraca"
    return "adequada"
