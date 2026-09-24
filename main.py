"""
API de Distância entre CEPs
===========================
Dois endpoints:
  GET  /distancia?cep_origem=01001000&cep_destino=20040020
  POST /distancia  body: {"cep_origem": "01001000", "cep_destino": "20040020"}

Ambos retornam:
  {
    "distancia_km": 450,
    "duracao_horas": 5.25,
    "mapa_url": "https://seu-app.onrender.com/mapa?cep_origem=...&cep_destino=..."
  }

O endpoint /mapa gera a imagem PNG do trajeto no mapa (OpenStreetMap).
"""

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from typing import Tuple, List, Optional
import requests
import math
from urllib.parse import urlencode

# staticmap gera a imagem do mapa com tiles do OSM
from staticmap import StaticMap, Line, CircleMarker

app = FastAPI(
    title="API Distância entre CEPs",
    description="Calcula distância e tempo de viagem entre dois CEPs brasileiros e gera imagem do trajeto no mapa.",
    version="1.0.0",
)


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------

class CepRequest(BaseModel):
    cep_origem: str = Field(..., example="01001000", description="CEP de origem (8 dígitos)")
    cep_destino: str = Field(..., example="20040020", description="CEP de destino (8 dígitos)")


class DistanciaResponse(BaseModel):
    distancia_km: float = Field(..., description="Distância em km (com margem de +1%)")
    duracao_horas: float = Field(..., description="Duração estimada em horas")
    mapa_url: str = Field(..., description="URL da imagem PNG do trajeto no mapa")


# ---------------------------------------------------------------------------
# Lógica de negócio (reaproveitada do app original)
# ---------------------------------------------------------------------------

def limpar_cep(cep: str) -> str:
    return "".join(filter(str.isdigit, cep))


def get_coordinates_from_cep(cep: str) -> Tuple[float, float]:
    cep_limpo = limpar_cep(cep)
    if len(cep_limpo) != 8:
        raise ValueError("CEP deve conter exatamente 8 dígitos.")

    url = f"https://cep.awesomeapi.com.br/json/{cep_limpo}"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    data = response.json()

    if "lat" not in data or "lng" not in data:
        raise ValueError(f"CEP {cep_limpo} não encontrado ou sem coordenadas.")

    return float(data["lat"]), float(data["lng"])


def buscar_rota(lat1: float, lon1: float, lat2: float, lon2: float) -> Tuple[float, float, List[Tuple[float, float]]]:
    """
    Retorna (distancia_km, duracao_segundos, path[(lat, lon), ...])
    """
    url = (
        f"https://router.project-osrm.org/route/v1/driving/"
        f"{lon1},{lat1};{lon2},{lat2}"
        f"?overview=full&geometries=geojson"
    )
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    data = response.json()

    if data.get("code") == "Ok" and data.get("routes"):
        route = data["routes"][0]
        distancia = route["distance"] / 1000.0  # m → km
        duracao = route["duration"]             # segundos
        coords = route["geometry"]["coordinates"]  # [lon, lat]
        path = [(lat, lon) for lon, lat in coords]
        return distancia, duracao, path

    raise ValueError("Não foi possível calcular a rota entre os pontos.")


def calcular_distancia(cep1: str, cep2: str) -> dict:
    coord1 = get_coordinates_from_cep(cep1)
    coord2 = get_coordinates_from_cep(cep2)
    distancia, duracao, path = buscar_rota(coord1[0], coord1[1], coord2[0], coord2[1])

    distancia_ajustada = distancia * 1.01  # margem de +1% (igual ao app original)

    return {
        "distancia_km": round(distancia_ajustada, 1),
        "duracao_horas": round(duracao / 3600, 2),
        "path": path,
        "coord_origem": coord1,
        "coord_destino": coord2,
    }


def gerar_imagem_mapa(path: List[Tuple[float, float]],
                      origem: Tuple[float, float],
                      destino: Tuple[float, float],
                      width: int = 800,
                      height: int = 600) -> bytes:
    """
    Gera PNG do trajeto usando tiles do OpenStreetMap via biblioteca staticmap.
    Faz downsample do path para não sobrecarregar (máx ~150 pontos).
    """
    m = StaticMap(width, height, padding_x=40, padding_y=40)

    # Downsample se houver muitos pontos
    if len(path) > 150:
        step = math.ceil(len(path) / 150)
        path_reduzido = path[::step]
        if path_reduzido[-1] != path[-1]:
            path_reduzido.append(path[-1])
    else:
        path_reduzido = path

    # Coordenadas no formato (lon, lat) que o staticmap espera
    coords_line = [(lon, lat) for lat, lon in path_reduzido]

    # Linha do trajeto (roxo)
    m.add_line(Line(coords_line, "#7c3aed", 4))

    # Marcador origem (verde)
    m.add_marker(CircleMarker((origem[1], origem[0]), "#22c55e", 12))
    # Marcador destino (vermelho)
    m.add_marker(CircleMarker((destino[1], destino[0]), "#ef4444", 12))

    image = m.render()
    from io import BytesIO
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/", tags=["Info"])
def root():
    return {
        "mensagem": "API Distância entre CEPs",
        "endpoints": {
            "GET /distancia": "Recebe CEPs via query string",
            "POST /distancia": "Recebe CEPs via body JSON",
            "GET /mapa": "Retorna imagem PNG do trajeto",
            "GET /docs": "Documentação interativa (Swagger)",
        },
        "exemplo_get": "/distancia?cep_origem=01001000&cep_destino=20040020",
        "exemplo_post": {
            "url": "/distancia",
            "body": {"cep_origem": "01001000", "cep_destino": "20040020"},
        },
    }


@app.get("/distancia", response_model=DistanciaResponse, tags=["Distância"])
def distancia_por_url(
    request: Request,
    cep_origem: str = Query(..., example="01001000", description="CEP de origem"),
    cep_destino: str = Query(..., example="20040020", description="CEP de destino"),
):
    """
    Calcula distância e duração entre dois CEPs.
    Os CEPs são passados pela **URL** (query parameters).
    """
    try:
        resultado = calcular_distancia(cep_origem, cep_destino)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Erro ao consultar APIs externas: {str(e)}")

    params = urlencode({
        "cep_origem": limpar_cep(cep_origem),
        "cep_destino": limpar_cep(cep_destino),
    })
    base = str(request.base_url).rstrip("/")
    mapa_url = f"{base}/mapa?{params}"

    return DistanciaResponse(
        distancia_km=resultado["distancia_km"],
        duracao_horas=resultado["duracao_horas"],
        mapa_url=mapa_url,
    )


@app.post("/distancia", response_model=DistanciaResponse, tags=["Distância"])
def distancia_por_body(request: Request, body: CepRequest):
    """
    Calcula distância e duração entre dois CEPs.
    Os CEPs são passados no **body** como JSON.
    """
    try:
        resultado = calcular_distancia(body.cep_origem, body.cep_destino)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Erro ao consultar APIs externas: {str(e)}")

    params = urlencode({
        "cep_origem": limpar_cep(body.cep_origem),
        "cep_destino": limpar_cep(body.cep_destino),
    })
    base = str(request.base_url).rstrip("/")
    mapa_url = f"{base}/mapa?{params}"

    return DistanciaResponse(
        distancia_km=resultado["distancia_km"],
        duracao_horas=resultado["duracao_horas"],
        mapa_url=mapa_url,
    )


@app.get("/mapa", tags=["Mapa"])
def gerar_mapa(
    cep_origem: str = Query(..., example="01001000"),
    cep_destino: str = Query(..., example="20040020"),
    width: int = Query(800, ge=200, le=1200),
    height: int = Query(600, ge=200, le=1000),
):
    """
    Gera e retorna a imagem PNG do trajeto entre os dois CEPs.
    Use a URL retornada em `mapa_url` dos endpoints de distância.
    """
    try:
        resultado = calcular_distancia(cep_origem, cep_destino)
        png_bytes = gerar_imagem_mapa(
            resultado["path"],
            resultado["coord_origem"],
            resultado["coord_destino"],
            width=width,
            height=height,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Erro ao consultar APIs externas: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar imagem: {str(e)}")

    return Response(content=png_bytes, media_type="image/png")