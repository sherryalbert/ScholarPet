# Offline model goes here

This directory is intentionally empty in Git. The English → Chinese model is
about 82 MB (a single 82.7 MB `model.bin` dominates it), which would bloat the
repository and slow every clone for everyone, so it is downloaded on demand
instead.

```powershell
python scripts\fetch_model.py          # download and unpack into this folder
python scripts\fetch_model.py --check  # report whether it is already installed
python scripts\fetch_model.py --archive translate-en_zh-1_9.argosmodel
```

After it runs you should have `models/translate-en_zh-1_9/` containing
`model/model.bin`, `model/config.json`, `model/shared_vocabulary.json`,
`sentencepiece.model`, `metadata.json` and `stanza/`.

Everything that needs the model reads it from `models/translate-en_zh-1_9`:

* the offline engine (`scholarpet/offline.py`) — see `offline._candidates()`;
* the test suite, which translates a real academic sample;
* `scripts/build.ps1`, because `ScholarPet.spec` ships this folder into the
  portable build's `_internal/models`.

The model is Argos Translate `translate-en_zh-1_9`, derived from the OPUS-MT
English → Chinese model by Jörg Tiedemann and Santhosh Thottingal
("OPUS-MT — Building open translation services for the World", EAMT 2020), and
is licensed **CC-BY 4.0**. Attribution is kept here and in
`../THIRD_PARTY_NOTICES.md`; the full text that ships inside the model package
is written to this folder's own `README.md` by the fetch script.
