# Phase 1 — Text Detection & OCR MVP

## Objective

Build MVP để kiểm tra và tối ưu bài toán:

* Upload ảnh manga / CG / webtoon
* Detect vùng text
* OCR text
* Hiển thị bbox + text OCR
* Cho phép sửa block thủ công
* Export JSON kết quả

Chưa làm translation trong Phase 1.

---

# Tech Stack

## Frontend

```text
HTML
CSS
JavaScript
Canvas API
```

Lý do:

* đơn giản
* dễ debug
* dễ convert sang browser extension
* không phụ thuộc framework

## Backend

```text
Python 3.11+
FastAPI
PaddleOCR
Pillow
OpenCV
```

---

# Phase 1 Scope

## Must Have

* Upload ảnh
* Preview ảnh trên canvas
* Gửi ảnh lên API
* Detect text regions
* OCR text
* Vẽ bounding boxes
* Hiển thị danh sách text blocks
* Click block để highlight bbox
* Sửa text OCR thủ công
* Export JSON

## Not In Scope

* Translation
* Overlay bubble
* Inpainting
* Browser extension
* Database
* Auth
* Batch processing

---

# Core Flow

```text
Upload image
→ Backend detect + OCR
→ Return text blocks
→ Frontend draw bbox
→ User review/edit
→ Export JSON
```

---

# API Design

## POST /api/ocr

Input:

```text
multipart/form-data
- image
- source_lang: ja / auto
```

Response:

```json
{
  "image": {
    "width": 1200,
    "height": 1800
  },
  "blocks": [
    {
      "id": 1,
      "bbox": [[100,120], [220,120], [220,180], [100,180]],
      "text": "ありがとう",
      "confidence": 0.96,
      "direction": "horizontal"
    }
  ]
}
```

---

# Text Block Schema

```python
class TextBlock:
    id: int
    bbox: list[list[int]]
    text: str
    confidence: float
    direction: str
```

---

# Frontend Layout

```text
+--------------------------------------------------+
| Upload Image                                     |
+--------------------------------------------------+

+-----------------------------+--------------------+
| Canvas Preview              | OCR Blocks          |
| - image                     | - block list        |
| - bbox overlay              | - editable text     |
| - selected block highlight  |                    |
+-----------------------------+--------------------+

[ Detect OCR ] [ Export JSON ]
```

---

# Frontend Features

## Canvas

* render image
* draw bbox
* zoom
* pan
* click bbox to select block
* highlight selected bbox

## Block List

Each block shows:

* id
* confidence
* OCR text
* editable textarea

---

# Backend Modules

```text
backend/
├─ main.py
├─ requirements.txt
├─ api/
│  └─ ocr.py
├─ modules/
│  ├─ detector.py
│  ├─ ocr.py
│  └─ image_utils.py
├─ schemas/
│  └─ block.py
└─ outputs/
```

---

# Project Structure

```text
manga-ocr-detector/

├─ backend/
│  ├─ main.py
│  ├─ requirements.txt
│  ├─ api/
│  │  └─ ocr.py
│  ├─ modules/
│  │  ├─ paddle_ocr.py
│  │  └─ image_utils.py
│  └─ schemas/
│     └─ block.py
│
├─ frontend/
│  ├─ index.html
│  ├─ styles.css
│  └─ app.js
│
└─ README.md
```

---

# PaddleOCR Strategy

Use PaddleOCR for both:

* text detection
* text recognition

Initial config:

```python
PaddleOCR(
    use_angle_cls=True,
    lang="japan"
)
```

Later improvements:

* test vertical Japanese text
* test rotated text
* adjust detection thresholds
* add preprocessing
* add block grouping

---

# Debug Priority

Phase 1 phải tập trung debug:

* bbox có đúng không
* text nhỏ có bị miss không
* text dọc có đọc đúng không
* text trên nền rối có detect không
* confidence thấp nằm ở đâu
* OCR sai kiểu gì

---

# Success Criteria

Phase 1 hoàn thành khi:

* upload 1 ảnh
* detect được phần lớn text
* OCR text đủ dùng để review
* user có thể sửa text sai
* export được JSON chuẩn

---

# Example Export JSON

```json
{
  "source_image": "sample.jpg",
  "blocks": [
    {
      "id": 1,
      "bbox": [[100,120], [220,120], [220,180], [100,180]],
      "text": "ありがとう",
      "confidence": 0.96,
      "direction": "horizontal"
    }
  ]
}
```

---

# Future Phase

## Phase 2

* text grouping
* reading order
* translation
* overlay bubble

## Phase 3

* browser extension
* web reader
* batch chapter processing
