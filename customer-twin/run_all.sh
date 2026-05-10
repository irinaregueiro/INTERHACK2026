#!/bin/bash

# --- Script d'arrencada unificada (Backend + Frontend + ETL) ---

cleanup() {
    echo ""
    echo "Aturant servidors..."
    kill $BACKEND_PID
    kill $FRONTEND_PID
    exit
}

trap cleanup SIGINT

echo "🚀 Iniciant procés automàtic..."

# 1. Comprovar i executar ETL si hi ha dades noves
if [ -f "data/raw/Datasets.xlsx" ]; then
    echo "📊 S'ha detectat Datasets.xlsx. Processant dades (ETL)..."
    source venv/bin/activate
    python -m etl.pipeline
    echo "✅ ETL completat amb èxit."
else
    echo "⚠️  No s'ha trobat data/raw/Datasets.xlsx. S'usaran les dades processades anteriorment o el mode Mock."
fi

echo "---------------------------------------"

# 2. Engegar Backend
echo "📡 Engegant el Backend (FastAPI) al port 8000..."
source venv/bin/activate
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

# 3. Engegar Frontend
echo "💻 Engegant el Frontend (Vite) al port 5173..."
cd frontend
npm run dev &
FRONTEND_PID=$!

echo ""
echo "✅ Tot en marxa!"
echo "🔗 Dashboard: http://127.0.0.1:5173"
echo "⚠️  Prem CTRL+C per aturar-ho tot."
echo ""

wait
