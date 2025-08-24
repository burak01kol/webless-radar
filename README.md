# Webless Radar

Google Places API + Streamlit ile **gerçek web sitesi olmayan** işletmeleri bulur.
- Çoklu sektör/ilçe
- Sosyal linkleri site saymaz
- CSV/PDF çıktı

## Çalıştırma
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env  # key'i yaz
python -m streamlit run app.py
