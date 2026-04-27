from __future__ import annotations

from pathlib import Path

from src.domain.media_workflow import Recipe, WorkflowJob, default_language_profile
from src.storage.json_store import JsonStore


class WorkflowState:
    def __init__(self, root: Path) -> None:
        state_dir = Path(root) / "workdir" / "state"
        self.jobs = JsonStore(state_dir / "jobs.json", default_data={"items": []}, schema_version=1)
        self.recipes = JsonStore(state_dir / "recipes.json", default_data={"items": []}, schema_version=1)
        self.language_profiles = JsonStore(
            state_dir / "language_profiles.json",
            default_data={"items": [default_language_profile().to_dict()]},
            schema_version=1,
        )

    @staticmethod
    def _upsert(store: JsonStore, item: dict) -> dict:
        payload = store.read()
        items = [row for row in payload.get("items", []) if row.get("id") != item.get("id")]
        items.append(item)
        return store.write({"items": items})

    def list_jobs(self) -> list[dict]:
        return list(self.jobs.read().get("items", []))

    def upsert_job(self, job: WorkflowJob) -> dict:
        return self._upsert(self.jobs, job.to_dict())

    def list_recipes(self) -> list[dict]:
        return list(self.recipes.read().get("items", []))

    def get_recipe(self, recipe_id: str) -> dict | None:
        for recipe in self.list_recipes():
            if recipe.get("id") == recipe_id:
                return recipe
        return None

    def upsert_recipe(self, recipe: Recipe) -> dict:
        return self._upsert(self.recipes, recipe.to_dict())

    def list_language_profiles(self) -> list[dict]:
        profiles = list(self.language_profiles.read().get("items", []))
        if profiles:
            return profiles
        default_profile = default_language_profile().to_dict()
        self.language_profiles.write({"items": [default_profile]})
        return [default_profile]
