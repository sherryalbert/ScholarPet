"""Collect installed distribution license texts for the portable build."""
from importlib.metadata import distributions
from pathlib import Path
import shutil

target = Path(__file__).resolve().parents[1] / 'dist' / 'ScholarPet' / '_internal' / 'licenses'
target.mkdir(parents=True, exist_ok=True)
for dist in distributions():
    for file in dist.files or []:
        if any(part.lower().startswith(('license', 'copying', 'notice')) for part in file.parts):
            source = Path(dist.locate_file(file))
            if source.is_file() and source.suffix.lower() not in ['.py', '.pyc', '.dll']:
                destination = target / dist.metadata['Name'] / str(file).replace('../', '')
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
print('Collected dependency licenses into', target)
