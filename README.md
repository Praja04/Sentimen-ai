# XEDY V30 Dashboard Replica

Replica dashboard dari `http://localhost:5000/` dengan data yang sudah diambil ke `xedy_v30_data.json`.

## Jalankan

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Default server berjalan di `http://localhost:5000/`. Kalau port 5000 masih dipakai app lama:

```powershell
$env:PORT = "5001"
python app.py
```

Endpoint utama:

- `/api/xedy_v30`
- `/api/live_ticks`
- `/api/prices`

`MetaTrader5` bersifat opsional. Kalau package dan terminal MT5 tersedia, `/api/live_ticks` memakai harga live. Kalau tidak, endpoint otomatis memakai harga dari data hasil grab.
