# API Distância entre CEPs

API REST que calcula a distância e o tempo de viagem entre dois CEPs brasileiros e gera uma imagem do trajeto no mapa.

## Endpoints

| Método | URL | Descrição |
|--------|-----|-----------|
| `GET`  | `/distancia?cep_origem=01001000&cep_destino=20040020` | CEPs na URL |
| `POST` | `/distancia` | CEPs no body JSON |
| `GET`  | `/mapa?cep_origem=...&cep_destino=...` | Imagem PNG do trajeto |
| `GET`  | `/docs` | Documentação interativa (Swagger) |

### Exemplo de resposta

```json
{
  "distancia_km": 432.5,
  "duracao_horas": 5.12,
  "mapa_url": "/mapa?cep_origem=01001000&cep_destino=20040020"
}