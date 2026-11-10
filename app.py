from flask import Flask, render_template
import sqlite3
import os

app = Flask(__name__)

DB_YOLU = os.path.join(
    os.path.dirname(__file__),
    "utkuerekincikutuphane.db"
)

@app.route("/")
def anasayfa():
    baglanti = sqlite3.connect(DB_YOLU)
    baglanti.row_factory = sqlite3.Row

    tablolar = {}

    for tablo in ["Kitaplar", "Yazarlar", "YayınEvleri"]:
        veriler = baglanti.execute(
            f'SELECT * FROM "{tablo}"'
        ).fetchall()

        sutunlar = baglanti.execute(
            f'PRAGMA table_info("{tablo}")'
        ).fetchall()

        tablolar[tablo] = {
            "sutunlar": [s[1] for s in sutunlar],
            "veriler": [list(v) for v in veriler]
        }

    baglanti.close()

    return render_template("index.html", tablolar=tablolar)

if __name__ == "__main__":
    app.run(debug=True)