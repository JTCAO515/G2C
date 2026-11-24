"""The app image keeps third-party dependencies in a layer that source changes do not invalidate."""
from pathlib import Path


DOCKERFILE = Path(__file__).resolve().parents[1] / 'Dockerfile'


def instructions():
    lines, current = [], ''
    for raw in DOCKERFILE.read_text().splitlines():
        if not raw.strip() or raw.lstrip().startswith('#'):
            continue
        current += raw.rstrip('\\').strip() + ' '
        if not raw.rstrip().endswith('\\'):
            lines.append(current.strip())
            current = ''
    return lines


def test_dependency_layer_precedes_every_source_copy():
    steps = instructions()
    deps = [i for i, step in enumerate(steps) if step == 'RUN uv sync --locked --no-dev --no-install-project']
    assert len(deps) == 1, 'one dependency-only sync step required'
    before = [step for step in steps[:deps[0]] if step.startswith(('COPY', 'ADD'))]
    assert before == ['COPY pyproject.toml uv.lock ./']
    after = [step for step in steps[deps[0] + 1:] if step.startswith(('COPY', 'ADD'))]
    assert any(step.startswith('COPY backend ') for step in after)


def test_project_is_installed_after_all_sources_with_the_same_lock():
    steps = instructions()
    final = [i for i, step in enumerate(steps) if step == 'RUN uv sync --locked --no-dev']
    assert len(final) == 1
    copies = [i for i, step in enumerate(steps) if step.startswith(('COPY', 'ADD'))]
    assert max(copies) < final[0]
    assert steps[-1] == 'ENTRYPOINT ["python", "-B", "-m", "deploy.entrypoint"]'
