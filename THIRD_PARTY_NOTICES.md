# Third-party components

ScholarPet source is MIT licensed. Dependencies and OCR model files retain their own licenses.

| Component | License | Upstream |
| --- | --- | --- |
| Qt for Python / PySide6 / Shiboken | LGPL-3.0 / GPL / commercial, according to module | https://www.qt.io/qt-for-python |
| RapidOCR | Apache-2.0 | https://github.com/RapidAI/RapidOCR |
| PaddleOCR models bundled by RapidOCR | Apache-2.0 | https://github.com/PaddlePaddle/PaddleOCR |
| ONNX Runtime | MIT | https://github.com/microsoft/onnxruntime |
| NumPy | BSD-3-Clause | https://numpy.org/ |
| OpenCV | Apache-2.0 | https://opencv.org/ |
| Requests | Apache-2.0 | https://requests.readthedocs.io/ |
| CTranslate2 | MIT | https://github.com/OpenNMT/CTranslate2 |
| SentencePiece | Apache-2.0 | https://github.com/google/sentencepiece |
| PyInstaller | GPL-2.0 with bootloader distribution exception | https://pyinstaller.org/ |

The English→Chinese model is Argos Translate `translate-en_zh-1_9`
(<https://data.argosopentech.com/argospm/v1/translate-en_zh-1_9.argosmodel>),
derived from the OPUS-MT English→Chinese model by Jörg Tiedemann and Santhosh
Thottingal ("OPUS-MT — Building open translation services for the World",
EAMT 2020). It is licensed **CC-BY 4.0**; that attribution is this notice and
the README shipped inside the model package. The model is **not** part of this
repository — it is ~82 MB and is downloaded on demand by
`scripts/fetch_model.py` — but it *is* redistributed inside the portable build's
`_internal/models` directory, which is why attribution ships with the build too.

## Artwork

`assets/haibara_head.png` is fan artwork depicting a character from *Detective
Conan*. The character design, name and likeness remain the property of their
respective rights holders; no licence to that artwork is granted here. It is
included for personal, non-commercial study, and it is **not** covered by the
MIT licence that applies to this project's source code.

If you fork or redistribute ScholarPet, replace that file with artwork you are
entitled to use and re-run `python scripts/calibrate_face.py` to regenerate
`assets/haibara_head.rig.json`; the blink, gaze and mouth animation adapt to the
new artwork automatically.

The Windows build uses Qt Core/Gui/Widgets as separate dynamically linked libraries. The `_internal` directory is part of the application: keep it alongside the executable. Users may replace compatible Qt libraries. This application does not restrict reverse engineering for debugging modifications to LGPL libraries. Upstream source and license information are available from the links above; bundled distribution metadata and license texts are copied to `_internal/licenses` by the release script.

Network translation services are separate third-party services, not bundled models. Their service terms and usage limits apply. No API credentials are bundled.
