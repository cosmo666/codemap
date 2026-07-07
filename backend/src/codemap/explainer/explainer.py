import asyncio
from collections.abc import Callable
from typing import Protocol

import structlog

from codemap.analyzer.models import ParsedModule
from codemap.explainer.cache import ExplanationCache, digest_of
from codemap.explainer.skeleton import build_skeleton

log = structlog.get_logger()

MODULE_SYSTEM = (
    "You are a senior engineer explaining code to a newcomer. Given a Python module "
    "skeleton, reply with 2-4 plain-English sentences: what the module does, its role "
    "in the system, and its key classes/functions. No code, no markdown headers."
)
PACKAGE_SYSTEM = (
    "Summarize this Python package in 2-3 plain-English sentences based on its "
    "module explanations. Describe the package's overall responsibility."
)
OVERVIEW_SYSTEM = (
    "Write a 3-5 sentence architectural overview of this repository based on its "
    "package summaries: what the system does and how the pieces fit together."
)


class SupportsComplete(Protocol):
    async def complete(self, system: str, user: str) -> str: ...


class Explainer:
    """Map-reduce: per-module explanations, package rollups, repo overview."""

    def __init__(self, llm: SupportsComplete, cache: ExplanationCache) -> None:
        self._llm = llm
        self._cache = cache

    async def explain_all(
        self,
        parsed: list[ParsedModule],
        on_progress: Callable[[int, int, str], None],
    ) -> dict[str, str]:
        todo = [p for p in parsed if p.info.status == "ok"]
        total = len(todo)
        results: dict[str, str] = {}
        done = 0

        async def explain_one(pm: ParsedModule) -> None:
            nonlocal done
            digest = digest_of(pm.source)
            cached = self._cache.get(pm.info.path, digest)
            if cached is not None:
                results[pm.info.path] = cached
            else:
                try:
                    explanation = await self._llm.complete(
                        MODULE_SYSTEM, build_skeleton(pm)
                    )
                    results[pm.info.path] = explanation
                    self._cache.put(pm.info.path, digest, explanation)
                except Exception as exc:  # noqa: BLE001 - one failure must not kill the run
                    log.warning("explain_failed", path=pm.info.path, error=str(exc))
            done += 1
            on_progress(done, total, pm.info.path)

        await asyncio.gather(*(explain_one(pm) for pm in todo))
        self._cache.save()
        return results

    async def summarize_packages(
        self, explanations: dict[str, str], parsed: list[ParsedModule]
    ) -> dict[str, str]:
        by_package: dict[str, list[str]] = {}
        for pm in parsed:
            text = explanations.get(pm.info.path)
            if text and pm.info.package != "root":
                by_package.setdefault(pm.info.package, []).append(
                    f"{pm.info.path}: {text}"
                )
        summaries: dict[str, str] = {}
        for package, texts in by_package.items():
            try:
                summaries[package] = await self._llm.complete(
                    PACKAGE_SYSTEM, f"Package '{package}':\n" + "\n".join(texts)
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("package_summary_failed", package=package, error=str(exc))
        return summaries

    async def overview(self, package_summaries: dict[str, str]) -> str:
        body = "\n".join(f"{pkg}: {text}" for pkg, text in package_summaries.items())
        try:
            return await self._llm.complete(OVERVIEW_SYSTEM, body)
        except Exception as exc:  # noqa: BLE001
            log.warning("overview_failed", error=str(exc))
            return ""
