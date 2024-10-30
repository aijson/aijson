from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, AsyncIterator

import jinja2

from aijson.models.config.flow import ActionConfig
from aijson.services.action_service import ActionService

from aijson.log_config import get_logger
from aijson.models.config.value_declarations import VarDeclaration
from aijson.repos.blob_repo import InMemoryBlobRepo, BlobRepo
from aijson.repos.cache_repo import ShelveCacheRepo, CacheRepo, asyncio
from aijson.utils.async_utils import merge_iterators
from aijson.utils.loader_utils import load_config_file, load_config_text
from aijson.utils.static_utils import check_config_consistency
from aijson.models.primitives import ExecutableId


class Flow:
    def __init__(
        self,
        config: ActionConfig,
        cache_repo: CacheRepo | type[CacheRepo] = ShelveCacheRepo,
        blob_repo: BlobRepo | type[BlobRepo] = InMemoryBlobRepo,
        temp_dir: None | str | TemporaryDirectory = None,
        _vars: None | dict[str, Any] = None,
    ):
        self.log = get_logger()
        self.variables = _vars or {}
        if isinstance(temp_dir, TemporaryDirectory):
            self.temp_dir = temp_dir
            temp_dir_path = temp_dir.name
        elif isinstance(temp_dir, str):
            self.temp_dir = temp_dir
            temp_dir_path = temp_dir
        else:
            self.temp_dir = TemporaryDirectory()
            temp_dir_path = self.temp_dir.name

        if isinstance(cache_repo, CacheRepo):
            self.cache_repo = cache_repo
        else:
            self.cache_repo = cache_repo(
                temp_dir=temp_dir_path,
            )

        if isinstance(blob_repo, BlobRepo):
            self.blob_repo = blob_repo
        else:
            self.blob_repo = blob_repo(
                temp_dir=temp_dir_path,
            )

        self.action_config = config
        self.action_service = ActionService(
            temp_dir=temp_dir_path,
            use_cache=True,
            cache_repo=self.cache_repo,
            blob_repo=self.blob_repo,
            config=self.action_config,
        )

    async def close(self):
        await self.cache_repo.close()
        await self.blob_repo.close()
        if isinstance(self.temp_dir, TemporaryDirectory):
            self.temp_dir.cleanup()

    @classmethod
    def from_text(
        cls,
        text: str,
        cache_repo: CacheRepo | type[CacheRepo] = ShelveCacheRepo,
        blob_repo: BlobRepo | type[BlobRepo] = InMemoryBlobRepo,
    ):
        config = load_config_text(text)
        return Flow(
            config=config,
            cache_repo=cache_repo,
            blob_repo=blob_repo,
        )

    @classmethod
    def from_file(
        cls,
        file: str | Path,
        cache_repo: CacheRepo | type[CacheRepo] = ShelveCacheRepo,
        blob_repo: BlobRepo | type[BlobRepo] = InMemoryBlobRepo,
    ) -> "Flow":
        if isinstance(file, Path):
            file = file.as_posix()
        config = load_config_file(file)
        return Flow(
            config=config,
            cache_repo=cache_repo,
            blob_repo=blob_repo,
        )

    def set_vars(self, **kwargs) -> "Flow":
        variables = self.variables | kwargs
        return Flow(
            config=self.action_config,
            cache_repo=self.cache_repo,
            blob_repo=self.blob_repo,
            temp_dir=self.temp_dir,
            _vars=variables,
        )

    async def run_all(self) -> list[Any]:
        action_ids = list(self.action_config.flow)
        flows = [self.run(action_id) for action_id in action_ids]
        outputs = await asyncio.gather(*flows)
        return outputs

    async def run(self, target_output: None | str = None) -> Any:
        """
        Run the subset of the flow required to get the target output.
        If the action has already been run, the cached output will be returned.

        Parameters
        ----------
        target_output : None | str
            the output to return (defaults to `default_output` in the config, or the last action's output if not set)
        """

        if target_output is None:
            target_output = self.action_config.get_default_output()

        if not check_config_consistency(
            self.log,
            self.action_config,
            set(self.variables),
            target_output,
        ):
            raise ValueError("Flow references unset variables")

        declaration = VarDeclaration(
            var=target_output,
        )

        dependencies = declaration.get_dependencies()
        if len(dependencies) != 1:
            raise NotImplementedError("Only one dependency is supported for now")
        executable_id = list(dependencies)[0]

        outputs = await self.action_service.run_executable(
            self.log,
            executable_id=executable_id,
            variables=self.variables,
        )
        context = {
            executable_id: outputs,
        }

        result = await declaration.render(context)
        if isinstance(result, jinja2.Undefined):
            raise RuntimeError("Failed to render result")
        return result

    async def stream_all(self) -> AsyncIterator[dict[ExecutableId, Any]]:
        action_ids = list(self.action_config.flow)
        iterators = [self.stream(action_id) for action_id in action_ids]
        outputs = {}
        async for action_id, output in merge_iterators(self.log, action_ids, iterators):
            outputs[action_id] = output
            yield outputs

    async def stream(self, target_output: None | str = None) -> AsyncIterator[Any]:
        """
        Run the subset of the flow required to get the target output, and asynchronously iterate the output.
        If the action has already been run, the cached output will be returned.

        Parameters
        ----------
        target_output : None | str
            the output to return (defaults to `default_output` in the config, or the last action's output if not set)
        """
        if target_output is None:
            target_output = self.action_config.get_default_output()

        if not check_config_consistency(
            self.log,
            self.action_config,
            set(self.variables),
            target_output,
        ):
            raise ValueError("Flow references unset variables")

        declaration = VarDeclaration(
            var=target_output,
        )

        dependencies = declaration.get_dependencies()
        if len(dependencies) != 1:
            raise NotImplementedError("Only one dependency is supported for now")
        executable_id = list(dependencies)[0]

        result = jinja2.Undefined()
        async for outputs in self.action_service.stream_executable(
            self.log,
            executable_id=executable_id,
            variables=self.variables,
        ):
            context = {
                executable_id: outputs,
            }

            result = await declaration.render(context)
            if isinstance(result, jinja2.Undefined):
                continue
            yield result
        if isinstance(result, jinja2.Undefined):
            raise RuntimeError("Failed to render result")
