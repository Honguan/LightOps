from pathlib import Path

from lightops.deployments import DeploymentService
from lightops.schemas import ProjectCreate
from lightops.store import Store


def test_static_project_deploys_to_versioned_release(tmp_path: Path) -> None:
    store = Store(f"sqlite:///{tmp_path / 'lightops.db'}")
    deploy_path = tmp_path / "deployed"
    store.create_project(
        ProjectCreate(
            name="Site",
            code="site",
            project_type="static",
            repository="https://example.com/site.git",
            branch="main",
            deploy_path=str(deploy_path),
        )
    )

    def runner(command, _cwd):
        if command[:2] == ["git", "clone"]:
            release = Path(command[-1])
            release.mkdir()
            (release / "index.html").write_text("deployed", encoding="utf-8")
            return 0, "cloned", ""
        return 0, "abc123", ""

    result = DeploymentService(store, runner=runner).deploy("site")

    assert result["result"] == "success"
    assert result["commit_hash"] == "abc123"
    assert (deploy_path / "current" / "index.html").read_text(encoding="utf-8") == "deployed"
    assert len(store.deployments(result["project_id"])) == 1
