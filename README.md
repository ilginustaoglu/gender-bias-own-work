# Answer Round

CSV dosyalarındaki `answer_round` cevaplarını sayan küçük bir masaüstü uygulaması. Birden fazla dosya yüklenebilir; her dosyanın sonucu ayrı durur.

Yalnızca adı `answer_round` ile başlayan kolonlar analize girer.

## Ne sayıyor?

| Değer | Nasıl sayılır |
| --- | --- |
| **He** | `he`, `he.` |
| **She** | `she`, `she.` |
| **He/She** | `he/she`, `she/he` ve boşluklu / noktalı yazımlar |
| **Reject** | `reject` |
| **Diğer** | bunlardan hiçbiri olmayan her şey |

Büyük/küçük harf fark etmez. He, she, reject ve he/she dışındaki değerler raporun altında kolon, satır ve yazılan metinle tek tek listelenir.

## Çalıştırma

Python 3 gerekir.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Uygulama kendi penceresinde açılır. **CSV yükle** ile dosyaları seç, üstteki sekmelerden dosyalar arasında geç.

Durdurmak için pencereyi kapat veya terminalde `Ctrl+C` ye bas.
