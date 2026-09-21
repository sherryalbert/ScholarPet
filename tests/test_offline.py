from pathlib import Path
import pytest


def test_bundled_model_translates_academic_sample():
    from scholarpet.offline import model_path, translate_offline
    try:
        path = model_path({})
    except Exception as exc:
        pytest.skip(str(exc))
    result = translate_offline(["Beamforming improves the signal-to-interference-plus-noise ratio."], {}, None, None)
    assert path.joinpath("model", "model.bin").is_file()
    assert len(result) == 1
    assert any("信" in result[0] or "噪" in result[0] or "干扰" in result[0] for _ in [0])
