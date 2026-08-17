"""FastAPI エントリポイント.

起動例:
  cd プロジェクトルート
  .venv/bin/uvicorn api.main:app --reload --port 8000

環境変数はプロジェクト直下の `.env` から読み込む（例: OPENAI_API_KEY）。
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
load_dotenv(ROOT / ".env")

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.schemas import (  # noqa: E402
    ChatRequest,
    ChatResponse,
    DataStatusResponse,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    PredictRequest,
    PredictResponse,
    ShopInfo,
)
from api.services.chat import chat as run_chat  # noqa: E402
from api.services.data import data_status, ingest_buying  # noqa: E402
from api.services.forecast import forecast_service  # noqa: E402


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """起動時にパネルを用意してモデルを学習する（データが無ければ取込待ち）。"""
    forecast_service.startup()
    yield


app = FastAPI(
    title="青梅DX 来店・売上予測 API",
    description=(
        "フェーズ6.9: 既存の実データ予測（A系統）と施策提案LLMを HTTP API 化したエンドポイント。"
        "Next.js フロントから `/predict` と `/chat` を呼び出す想定。"
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    if not forecast_service.ready:
        return HealthResponse(status="need_data", model_ready=False)
    b = forecast_service.ensure_ready()
    return HealthResponse(
        status="ok",
        model_ready=True,
        n_shops=len(b.shop_ids),
        data_start=b.data_start.strftime("%Y-%m-%d"),
        data_end=b.data_end.strftime("%Y-%m-%d"),
        train_end=b.train_end.strftime("%Y-%m-%d"),
    )


@app.get("/shops", response_model=list[ShopInfo])
def shops() -> list[ShopInfo]:
    if not forecast_service.ready:
        raise HTTPException(
            status_code=503,
            detail="学習データがまだありません。data/real_store_daily.csv を配置して API を再起動してください。",
        )
    try:
        return [ShopInfo(**row) for row in forecast_service.list_shops()]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/data/status", response_model=DataStatusResponse)
def get_data_status() -> DataStatusResponse:
    row = data_status()
    row["model_ready"] = forecast_service.ready
    return DataStatusResponse(**row)


@app.post("/data/ingest", response_model=IngestResponse)
def ingest_data(req: IngestRequest = IngestRequest()) -> IngestResponse:
    """サーバ上の生購買を店舗×日に集計し、モデルを再学習する（ブラウザアップロードはしない）。"""
    try:
        stats = ingest_buying(req.source_path)
        bundle = forecast_service.load_and_train()
        return IngestResponse(
            **stats,
            model_ready=True,
            n_predict_shops=len(bundle.shop_ids),
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest) -> PredictResponse:
    if not forecast_service.ready:
        raise HTTPException(
            status_code=503,
            detail="学習データがまだありません。data/real_store_daily.csv を配置して API を再起動してください。",
        )
    try:
        return forecast_service.predict(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest) -> ChatResponse:
    try:
        return run_chat(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
